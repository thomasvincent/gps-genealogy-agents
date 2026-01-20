"""Social Security Death Index (SSDI) source connector.

Provides access to SSDI data through publicly available search interfaces.
No login required. Uses multiple fallback sources:
1. FamilySearch SSDI (free, comprehensive)
2. Steve Morse one-step tools (redirects to various sources)
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class SSDISource(BaseSource):
    """Social Security Death Index source (no login required).

    Searches public SSDI data for death records including:
    - Death date
    - Last residence (state/ZIP)
    - SSN (partial, last 4 digits visible in some sources)
    - Birth date (month/year)

    Uses FamilySearch's free SSDI collection as primary source.
    """

    name = "SSDI"
    # FamilySearch search URL (public search interface)
    base_url = "https://www.familysearch.org/search/collection/1202535/results"

    def requires_auth(self) -> bool:
        """SSDI search does not require authentication."""
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search SSDI for death records matching the query.

        Args:
            query: Search parameters (given_name, surname, birth_year, death_year)

        Returns:
            List of SSDI death records found
        """
        records: list[RawRecord] = []

        # Try FamilySearch SSDI first
        fs_records = await self._search_familysearch(query)
        records.extend(fs_records)

        return records

    async def _search_familysearch(self, query: SearchQuery) -> list[RawRecord]:
        """Search FamilySearch's free SSDI collection.

        Collection: United States Social Security Death Index
        """
        # Build FamilySearch search URL
        # Collection ID for SSDI on FamilySearch
        params: dict[str, str] = {
            "count": "20",
            "offset": "0",
            "collection_id": "1202535",  # US Social Security Death Index
        }

        if query.given_name:
            params["q.givenName"] = query.given_name
        if query.surname:
            params["q.surname"] = query.surname

        # Birth year range
        if query.birth_year:
            birth_range = query.get_year_range(query.birth_year, query.birth_year_range)
            if birth_range:
                params["q.birthLikeDate.from"] = str(birth_range[0])
                params["q.birthLikeDate.to"] = str(birth_range[1])

        # Death year range
        if query.death_year:
            death_range = query.get_year_range(query.death_year, query.death_year_range)
            if death_range:
                params["q.deathLikeDate.from"] = str(death_range[0])
                params["q.deathLikeDate.to"] = str(death_range[1])

        if query.state:
            params["q.residencePlace"] = query.state

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "application/json, text/html",
                },
            ) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()

                # FamilySearch may return JSON or HTML depending on headers
                content_type = resp.headers.get("content-type", "")

                if "json" in content_type:
                    return self._parse_familysearch_json(resp.json())
                else:
                    return self._parse_familysearch_html(resp.text)

        except httpx.HTTPError as e:
            logger.warning(f"FamilySearch SSDI search failed: {e}")
            return []

    def _parse_familysearch_json(self, data: dict[str, Any]) -> list[RawRecord]:
        """Parse FamilySearch JSON API response."""
        records: list[RawRecord] = []

        # FamilySearch API returns results in searchResults
        results = data.get("searchResults", [])
        if not results:
            results = data.get("results", [])

        for item in results[:20]:
            try:
                record = self._familysearch_item_to_record(item)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Failed to parse FamilySearch item: {e}")
                continue

        return records

    def _familysearch_item_to_record(self, item: dict[str, Any]) -> RawRecord | None:
        """Convert a FamilySearch search result to RawRecord."""
        # Extract person info from the nested structure
        person = item.get("person", {}) or item
        record_id = item.get("id") or person.get("id") or ""

        # Build URL
        url = f"https://www.familysearch.org/ark:/61903/1:1:{record_id}" if record_id else None

        # Extract fields
        display = person.get("display", {})
        name = display.get("name") or person.get("name") or "Unknown"

        # Birth info
        birth_date = display.get("birthDate") or person.get("birthDate")
        birth_place = display.get("birthPlace") or person.get("birthPlace")

        # Death info
        death_date = display.get("deathDate") or person.get("deathDate")
        death_place = display.get("deathPlace") or person.get("deathPlace")

        extracted = {
            "full_name": name,
            "birth_date": birth_date,
            "birth_place": birth_place,
            "death_date": death_date,
            "death_place": death_place,
            "ssn_last_4": None,  # May not be available in all results
        }

        # Try to extract residence/SSN from raw data
        facts = person.get("facts", [])
        for fact in facts:
            fact_type = fact.get("type", "").lower()
            value = fact.get("value") or fact.get("place", {}).get("original")
            if "residence" in fact_type and value:
                extracted["last_residence"] = value
            elif "ssn" in fact_type and value:
                extracted["ssn_partial"] = value

        return RawRecord(
            source=self.name,
            record_id=record_id,
            record_type="death",
            url=url,
            raw_data=item,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )

    def _parse_familysearch_html(self, html: str) -> list[RawRecord]:
        """Parse FamilySearch HTML search results page."""
        records: list[RawRecord] = []
        soup = BeautifulSoup(html, "html.parser")

        # Find result items - FamilySearch uses various selectors
        result_selectors = [
            ".result-item",
            "[data-testid='searchResult']",
            ".search-result",
            "tr.result",
        ]

        items = []
        for selector in result_selectors:
            items = soup.select(selector)
            if items:
                break

        for item in items[:20]:
            try:
                record = self._parse_html_result_item(item)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Failed to parse HTML result: {e}")
                continue

        return records

    def _parse_html_result_item(self, item: BeautifulSoup) -> RawRecord | None:
        """Parse a single HTML search result item."""
        # Find the link and name
        link = item.select_one("a[href*='/ark:/']") or item.select_one("a")
        if not link:
            return None

        href = link.get("href", "")
        name = link.get_text(strip=True)

        # Extract record ID from URL
        record_id = ""
        ark_match = re.search(r"/ark:/61903/1:1:([A-Z0-9-]+)", href)
        if ark_match:
            record_id = ark_match.group(1)

        url = href if href.startswith("http") else f"https://www.familysearch.org{href}"

        # Try to extract dates and places from surrounding text
        item_text = item.get_text(" ", strip=True)

        extracted = {"full_name": name}

        # Look for date patterns
        date_patterns = [
            (r"(?:born|b\.?)\s*(\d{1,2}?\s*[A-Za-z]+\s*\d{4}|\d{4})", "birth_date"),
            (r"(?:died|d\.?)\s*(\d{1,2}?\s*[A-Za-z]+\s*\d{4}|\d{4})", "death_date"),
        ]

        for pattern, field in date_patterns:
            match = re.search(pattern, item_text, re.IGNORECASE)
            if match:
                extracted[field] = match.group(1)

        return RawRecord(
            source=self.name,
            record_id=record_id or name,
            record_type="death",
            url=url,
            raw_data={"html_text": item_text[:500]},
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific SSDI record by ID.

        Args:
            record_id: FamilySearch ARK ID or full URL

        Returns:
            RawRecord with death information or None
        """
        # Build URL from record_id
        if record_id.startswith("http"):
            url = record_id
        else:
            url = f"https://www.familysearch.org/ark:/61903/1:1:{record_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                },
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract name from title or heading
                title_el = soup.select_one("h1, .person-name, title")
                name = title_el.get_text(strip=True) if title_el else "Unknown"

                # Extract facts from the page
                extracted = {"full_name": name}

                # Look for labeled data fields
                for label_el in soup.select("dt, .label, th"):
                    label = label_el.get_text(strip=True).lower()
                    value_el = label_el.find_next("dd") or label_el.find_next("td")
                    if not value_el:
                        continue
                    value = value_el.get_text(strip=True)

                    if "birth" in label:
                        if "date" in label or "when" in label:
                            extracted["birth_date"] = value
                        elif "place" in label or "where" in label:
                            extracted["birth_place"] = value
                    elif "death" in label:
                        if "date" in label or "when" in label:
                            extracted["death_date"] = value
                        elif "place" in label or "where" in label:
                            extracted["death_place"] = value
                    elif "residence" in label or "last" in label:
                        extracted["last_residence"] = value
                    elif "ssn" in label or "social" in label:
                        extracted["ssn_partial"] = value

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="death",
                    url=url,
                    raw_data={"name": name},
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch SSDI record {record_id}: {e}")
            return None


class SteveMorseOneStepSource(BaseSource):
    """Steve Morse One-Step search tool interface.

    Provides URL generation for various genealogy databases via
    stevemorse.org one-step tools. These tools simplify searching
    by constructing proper query URLs for:
    - SSDI
    - Ellis Island
    - Census records
    - Naturalization records

    Note: This source generates search URLs rather than scraping,
    as the one-step tools redirect to external databases.
    """

    name = "SteveMorse"
    base_url = "https://stevemorse.org"

    def requires_auth(self) -> bool:
        return False

    def get_ssdi_search_url(
        self,
        surname: str | None = None,
        given_name: str | None = None,
        birth_year: int | None = None,
        death_year: int | None = None,
    ) -> str:
        """Generate SSDI search URL via Steve Morse one-step.

        The one-step tool redirects to the appropriate database
        (typically Ancestry or FamilySearch).
        """
        base = f"{self.base_url}/ssdi/ssdi.html"
        params = []

        if surname:
            params.append(f"surname={quote_plus(surname)}")
        if given_name:
            params.append(f"givenname={quote_plus(given_name)}")
        if birth_year:
            params.append(f"birthyear={birth_year}")
        if death_year:
            params.append(f"deathyear={death_year}")

        if params:
            return f"{base}?{'&'.join(params)}"
        return base

    def get_ellis_island_url(
        self,
        surname: str | None = None,
        given_name: str | None = None,
        year: int | None = None,
    ) -> str:
        """Generate Ellis Island passenger search URL."""
        base = f"{self.base_url}/ellis/boat.html"
        params = []

        if surname:
            params.append(f"surname={quote_plus(surname)}")
        if given_name:
            params.append(f"givenname={quote_plus(given_name)}")
        if year:
            params.append(f"year={year}")

        if params:
            return f"{base}?{'&'.join(params)}"
        return base

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Return search URLs as records for manual follow-up.

        Since Steve Morse tools redirect to external sites,
        this returns the generated URLs rather than actual results.
        """
        records: list[RawRecord] = []

        # Generate SSDI search URL
        ssdi_url = self.get_ssdi_search_url(
            surname=query.surname,
            given_name=query.given_name,
            birth_year=query.birth_year,
            death_year=query.death_year,
        )

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ssdi-search-{query.surname or 'unknown'}",
                record_type="search_url",
                url=ssdi_url,
                raw_data={"tool": "ssdi", "query": query.model_dump()},
                extracted_fields={
                    "search_type": "SSDI",
                    "search_url": ssdi_url,
                    "note": "Open this URL to search SSDI via one-step tool",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Generate Ellis Island search URL if immigration is relevant
        if query.birth_year and query.birth_year < 1920:
            ellis_url = self.get_ellis_island_url(
                surname=query.surname,
                given_name=query.given_name,
            )
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ellis-search-{query.surname or 'unknown'}",
                    record_type="search_url",
                    url=ellis_url,
                    raw_data={"tool": "ellis_island", "query": query.model_dump()},
                    extracted_fields={
                        "search_type": "Ellis Island",
                        "search_url": ellis_url,
                        "note": "Open this URL to search Ellis Island passenger records",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - Steve Morse is a search tool generator."""
        return None
