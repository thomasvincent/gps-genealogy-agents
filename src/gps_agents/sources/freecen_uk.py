"""FreeCEN UK source for British census transcriptions.

FreeCEN is a volunteer project transcribing UK censuses from 1841-1911.
All data is free to access without login.

Coverage: England, Wales, Scotland (partial)
Years: 1841, 1851, 1861, 1871, 1881, 1891, 1901, 1911
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urlencode

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)

# UK Census years available on FreeCEN
UK_CENSUS_YEARS = [1841, 1851, 1861, 1871, 1881, 1891, 1901, 1911]


class FreeCENSource(BaseSource):
    """FreeCEN UK census transcriptions source.

    FreeCEN provides free access to transcribed UK census records:
    - 1841-1911 censuses (coverage varies by county)
    - Name, age, occupation, birthplace
    - Household members
    - Civil parish and registration district

    No authentication required.
    """

    name = "FreeCEN"
    base_url = "https://www.freecen.org.uk"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search FreeCEN for UK census records.

        Args:
            query: Search parameters

        Returns:
            List of census records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search parameters
        params: dict[str, str] = {
            "locale": "en",
            "search_query[last_name]": query.surname,
        }

        if query.given_name:
            params["search_query[first_name]"] = query.given_name

        # Year filter - FreeCEN uses specific census years
        if query.birth_year:
            # Find census years where person would appear (age 0-80)
            for year in UK_CENSUS_YEARS:
                if query.birth_year <= year <= query.birth_year + 80:
                    params["search_query[census_year]"] = str(year)
                    break

        # Birth place might indicate UK county
        if query.birth_place:
            place_lower = query.birth_place.lower()
            # Map common UK locations to counties
            county = self._map_place_to_county(place_lower)
            if county:
                params["search_query[county]"] = county

        search_url = f"{self.base_url}/search_queries/new"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                # FreeCEN uses form POST for search
                resp = await client.post(
                    f"{self.base_url}/search_queries",
                    data=params,
                )

                if resp.status_code in (200, 302):
                    # Follow redirect to results
                    if resp.status_code == 302:
                        redirect_url = resp.headers.get("Location", "")
                        if redirect_url:
                            resp = await client.get(redirect_url if redirect_url.startswith("http") else f"{self.base_url}{redirect_url}")

                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        records = self._parse_search_results(soup, query)

        except httpx.HTTPError as e:
            logger.debug(f"FreeCEN search error: {e}")

        # Always provide search URL for manual access
        manual_params = {
            "locale": "en",
            "search_query[last_name]": query.surname,
        }
        if query.given_name:
            manual_params["search_query[first_name]"] = query.given_name

        manual_url = f"{search_url}?{urlencode(manual_params)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"freecen-search-{query.surname}",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "FreeCEN UK Census Search",
                    "search_url": manual_url,
                    "note": "Search FreeCEN for free UK census transcriptions (1841-1911)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _map_place_to_county(self, place: str) -> str | None:
        """Map UK place names to FreeCEN county codes."""
        # Major UK cities to counties
        place_to_county = {
            "london": "LND",
            "manchester": "LAN",
            "birmingham": "WAR",
            "liverpool": "LAN",
            "leeds": "YKS",
            "sheffield": "YKS",
            "bristol": "GLS",
            "newcastle": "NBL",
            "edinburgh": "MLN",
            "glasgow": "LKS",
            "cardiff": "GLA",
            "dublin": "DUB",
            "belfast": "ANT",
            # English counties
            "devon": "DEV",
            "cornwall": "CON",
            "kent": "KEN",
            "sussex": "SSX",
            "surrey": "SRY",
            "essex": "ESS",
            "norfolk": "NFK",
            "suffolk": "SFK",
            "yorkshire": "YKS",
            "lancashire": "LAN",
            "cheshire": "CHS",
            "derbyshire": "DBY",
            "nottinghamshire": "NTT",
            "lincolnshire": "LIN",
            "warwickshire": "WAR",
            "worcestershire": "WOR",
            "gloucestershire": "GLS",
            "somerset": "SOM",
            "dorset": "DOR",
            "hampshire": "HAM",
            "wiltshire": "WIL",
            "berkshire": "BRK",
            "oxfordshire": "OXF",
            "buckinghamshire": "BKM",
            "hertfordshire": "HRT",
            "middlesex": "MDX",
            # Scottish counties
            "midlothian": "MLN",
            "lanarkshire": "LKS",
            "ayrshire": "AYR",
            "fife": "FIF",
            "aberdeenshire": "ABD",
            # Welsh counties
            "glamorgan": "GLA",
            "carmarthenshire": "CMN",
            "pembrokeshire": "PEM",
        }

        for key, code in place_to_county.items():
            if key in place:
                return code

        return None

    def _parse_search_results(
        self,
        soup: BeautifulSoup,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Parse FreeCEN search results."""
        records: list[RawRecord] = []

        # FreeCEN result table
        result_table = soup.select_one("table.search-results, table#results, .results-table")
        if not result_table:
            # Try finding result rows directly
            rows = soup.select("tr.result, tr[data-record]")
        else:
            rows = result_table.select("tr")[1:]  # Skip header

        for row in rows[:30]:
            try:
                cells = row.select("td")
                if len(cells) < 3:
                    continue

                # FreeCEN typically shows: Name, Age, Relation, Occupation, Birthplace, etc.
                link = row.select_one("a[href*='search_record']") or row.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Extract record ID
                record_id = ""
                id_match = re.search(r"search_records/(\d+)", href)
                if id_match:
                    record_id = id_match.group(1)

                # Parse cell contents
                cell_texts = [c.get_text(strip=True) for c in cells]
                extracted = self._extract_census_fields(cell_texts, row.get_text(" ", strip=True))

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=record_id or f"freecen-{hash(url)}",
                        record_type="census",
                        url=url,
                        raw_data={"cells": cell_texts},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse FreeCEN result row: {e}")
                continue

        return records

    def _extract_census_fields(
        self,
        cells: list[str],
        full_text: str,
    ) -> dict[str, str]:
        """Extract census fields from result data."""
        extracted: dict[str, str] = {}

        # First cell is usually name
        if cells:
            extracted["full_name"] = cells[0]

        # Look for patterns in text
        # Age
        age_match = re.search(r"(?:Age|Aged?)\s*:?\s*(\d+)", full_text, re.I)
        if age_match:
            extracted["age"] = age_match.group(1)

        # Census year
        year_match = re.search(r"\b(1841|1851|1861|1871|1881|1891|1901|1911)\b", full_text)
        if year_match:
            extracted["census_year"] = year_match.group(1)

        # Birthplace
        bp_match = re.search(r"(?:Born|Birth(?:place)?)\s*:?\s*([A-Za-z\s,]+?)(?:\d|$)", full_text, re.I)
        if bp_match:
            extracted["birthplace"] = bp_match.group(1).strip()

        # Occupation
        occ_match = re.search(r"(?:Occupation|Occ\.?)\s*:?\s*([A-Za-z\s]+?)(?:,|\d|$)", full_text, re.I)
        if occ_match:
            extracted["occupation"] = occ_match.group(1).strip()

        # Relation to head
        rel_match = re.search(r"(?:Relation|Rel\.?)\s*:?\s*(Head|Wife|Son|Daughter|Servant|Lodger|Boarder|Visitor)", full_text, re.I)
        if rel_match:
            extracted["relationship"] = rel_match.group(1)

        # Parish/district
        parish_match = re.search(r"(?:Parish|Place|District)\s*:?\s*([A-Za-z\s]+?)(?:,|\d|$)", full_text, re.I)
        if parish_match:
            extracted["parish"] = parish_match.group(1).strip()

        return extracted

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific FreeCEN record."""
        if record_id.startswith("http"):
            url = record_id
        else:
            url = f"{self.base_url}/search_records/{record_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract all text for parsing
                page_text = soup.get_text(" ", strip=True)

                # Try to find name in heading or title
                name_el = soup.select_one("h1, h2, .record-name, .person-name")
                name = name_el.get_text(strip=True) if name_el else "Unknown"

                extracted = self._extract_census_fields([], page_text)
                extracted["full_name"] = name

                # Try to extract household members
                household_table = soup.select_one("table.household, .household-members")
                if household_table:
                    members = []
                    for row in household_table.select("tr")[1:]:  # Skip header
                        cells = row.select("td")
                        if cells:
                            member_name = cells[0].get_text(strip=True)
                            if member_name and member_name != name:
                                members.append(member_name)
                    if members:
                        extracted["household_members"] = ", ".join(members)

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="census",
                    url=url,
                    raw_data={"name": name},
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except Exception as e:
            logger.warning(f"Failed to fetch FreeCEN record: {e}")
            return None


def get_freecen_coverage() -> dict[str, list[int]]:
    """Return FreeCEN coverage by country.

    Returns:
        Dict mapping country to list of census years with good coverage.
    """
    return {
        "England": [1841, 1851, 1861, 1871, 1881, 1891, 1901, 1911],
        "Wales": [1841, 1851, 1861, 1871, 1881, 1891, 1901, 1911],
        "Scotland": [1841, 1851, 1861, 1871, 1881, 1891, 1901],  # 1911 less complete
    }
