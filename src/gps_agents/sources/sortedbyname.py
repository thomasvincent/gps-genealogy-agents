"""SortedByName.com genealogy source.

SortedByName.com is a free genealogy database containing 424+ million entries
compiled from GEDCOM files submitted by genealogists. The site indexes names
alphabetically and provides links to source GEDCOM data.

Features:
- Free access, no login required
- 424+ million genealogy entries
- Organized by surname with paginated indexes
- Links to source GEDCOM files
- Social Security NUMIDENT index
- Related site: SortedByDate.com (organized by birth/death dates)
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class SortedByNameSource(BaseSource):
    """SortedByName.com - Free genealogy database from GEDCOM files.

    Contains 424+ million genealogy entries organized by surname.
    No authentication required.

    Related sites:
    - SortedByDate.com - Same data organized by birth/death dates
    - GEDCOMIndex.com - Reference library
    """

    name = "SortedByName"
    base_url = "https://sortedbyname.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search SortedByName for surname entries.

        Args:
            query: Search parameters (surname required)

        Returns:
            List of search URLs and any extracted records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname.lower()
        first_letter = surname[0] if surname else "a"

        # Build surname index URL
        surname_url = f"{self.base_url}/letter_{first_letter}/{surname}.html"

        # Add main surname index page
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"sbn-{surname}-index",
                record_type="surname_index",
                url=surname_url,
                raw_data={"surname": query.surname},
                extracted_fields={
                    "surname": query.surname,
                    "search_type": "Surname Index",
                    "note": "Free genealogy database with 424M+ entries from GEDCOM files",
                    "tip": "Browse paginated index to find specific individuals",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Try to fetch the surname page to get entry count and page links
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(surname_url)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    page_records = self._parse_surname_page(soup, query)
                    records.extend(page_records)

        except httpx.HTTPError as e:
            logger.debug(f"SortedByName fetch error: {e}")

        # Add SortedByDate search URL for date-based lookup
        if query.birth_year:
            sorted_by_date_url = f"https://sortedbydate.com/year_{query.birth_year}.html"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"sbd-{query.birth_year}",
                    record_type="search_url",
                    url=sorted_by_date_url,
                    raw_data={"birth_year": query.birth_year},
                    extracted_fields={
                        "search_type": "SortedByDate Birth Year Index",
                        "birth_year": str(query.birth_year),
                        "note": "Browse people born in this year",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Social Security NUMIDENT search if US-based
        if self._is_us_location(query):
            numident_url = f"{self.base_url}/numident.html"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="sbn-numident",
                    record_type="resource_link",
                    url=numident_url,
                    raw_data={},
                    extracted_fields={
                        "resource_title": "Social Security NUMIDENT Index",
                        "description": "Index of Social Security death records by birth date",
                        "note": "Useful for finding death dates of US citizens",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _is_us_location(self, query: SearchQuery) -> bool:
        """Check if query location is in the US."""
        us_indicators = [
            "usa", "united states", "america",
            "california", "texas", "new york", "florida", "illinois",
            "pennsylvania", "ohio", "georgia", "north carolina", "michigan",
            "arkansas", "alabama", "mississippi", "louisiana", "tennessee",
        ]

        location = ""
        if query.birth_place:
            location = query.birth_place.lower()
        if query.state:
            location += " " + query.state.lower()

        return any(indicator in location for indicator in us_indicators)

    def _parse_surname_page(
        self,
        soup: BeautifulSoup,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Parse surname index page for entry count and relevant links."""
        records: list[RawRecord] = []

        # Look for entry count in page text
        page_text = soup.get_text()
        count_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s+(?:entries?|records?)\s+for\s+" + re.escape(query.surname or ""), page_text, re.IGNORECASE)

        if count_match:
            entry_count = count_match.group(1)
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"sbn-{query.surname}-count",
                    record_type="metadata",
                    url=f"{self.base_url}/letter_{(query.surname or 'a')[0].lower()}/{(query.surname or '').lower()}.html",
                    raw_data={"entry_count": entry_count},
                    extracted_fields={
                        "surname": query.surname,
                        "entry_count": entry_count,
                        "note": f"Found {entry_count} entries for {query.surname} surname",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Find paginated index links
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Look for index page links (index_1.html, index_2.html, etc.)
            if "index_" in href and query.surname and query.surname.lower() in href.lower():
                full_url = href if href.startswith("http") else urljoin(self.base_url, href)

                # Extract page number
                page_match = re.search(r"index_(\d+)", href)
                page_num = page_match.group(1) if page_match else "1"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"sbn-{query.surname}-page-{page_num}",
                        record_type="index_page",
                        url=full_url,
                        raw_data={"page": page_num},
                        extracted_fields={
                            "surname": query.surname,
                            "page_number": page_num,
                            "note": f"Index page {page_num} for {query.surname}",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

        # Look for individual person entries with dates
        # Pattern: "FirstName Surname (YYYY-YYYY)" or similar
        person_pattern = re.compile(
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+' + re.escape(query.surname or "") + r'\s*\((\d{4})\s*[-–]\s*(\d{4})?\)',
            re.IGNORECASE
        )

        for match in person_pattern.finditer(page_text):
            given_name = match.group(1)
            birth_year = match.group(2)
            death_year = match.group(3) or "?"

            # Filter by query parameters if specified
            if query.given_name and query.given_name.lower() not in given_name.lower():
                continue
            if query.birth_year and str(query.birth_year) != birth_year:
                continue

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"sbn-{given_name}-{query.surname}-{birth_year}",
                    record_type="person",
                    url=f"{self.base_url}/letter_{(query.surname or 'a')[0].lower()}/{(query.surname or '').lower()}.html",
                    raw_data={
                        "given_name": given_name,
                        "surname": query.surname,
                        "birth_year": birth_year,
                        "death_year": death_year,
                    },
                    extracted_fields={
                        "full_name": f"{given_name} {query.surname}",
                        "birth_year": birth_year,
                        "death_year": death_year if death_year != "?" else None,
                        "note": "Entry from GEDCOM-submitted genealogy data",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records[:50]  # Limit results

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - records are found via search."""
        return None


class SortedByDateSource(BaseSource):
    """SortedByDate.com - Genealogy data organized by birth/death dates.

    Sister site to SortedByName.com with the same 424+ million entries
    but organized by year of birth or death for date-based research.
    """

    name = "SortedByDate"
    base_url = "https://sortedbydate.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search SortedByDate for entries by year.

        Args:
            query: Search parameters (birth_year recommended)

        Returns:
            List of date-indexed search URLs
        """
        records: list[RawRecord] = []

        # Birth year search
        if query.birth_year:
            birth_url = f"{self.base_url}/year_{query.birth_year}.html"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"sbd-birth-{query.birth_year}",
                    record_type="search_url",
                    url=birth_url,
                    raw_data={"year": query.birth_year, "type": "birth"},
                    extracted_fields={
                        "search_type": "Birth Year Index",
                        "year": str(query.birth_year),
                        "note": f"Browse people born in {query.birth_year}",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

            # Also add nearby years for potential matches
            for offset in [-1, 1, -2, 2]:
                nearby_year = query.birth_year + offset
                if 1700 <= nearby_year <= 2020:
                    records.append(
                        RawRecord(
                            source=self.name,
                            record_id=f"sbd-birth-{nearby_year}",
                            record_type="search_url",
                            url=f"{self.base_url}/year_{nearby_year}.html",
                            raw_data={"year": nearby_year, "type": "birth"},
                            extracted_fields={
                                "search_type": "Birth Year Index (nearby)",
                                "year": str(nearby_year),
                                "note": f"Check nearby year {nearby_year} for potential matches",
                            },
                            accessed_at=datetime.now(UTC),
                        )
                    )

        # Death year search (estimate from birth + lifespan)
        if query.birth_year:
            # Estimate death years (assuming 60-90 year lifespan)
            for death_offset in [70, 80, 85]:
                est_death_year = query.birth_year + death_offset
                if est_death_year <= 2025:
                    death_url = f"{self.base_url}/death_{est_death_year}.html"
                    records.append(
                        RawRecord(
                            source=self.name,
                            record_id=f"sbd-death-{est_death_year}",
                            record_type="search_url",
                            url=death_url,
                            raw_data={"year": est_death_year, "type": "death"},
                            extracted_fields={
                                "search_type": "Death Year Index (estimated)",
                                "year": str(est_death_year),
                                "note": f"Estimated death year based on {death_offset}-year lifespan",
                            },
                            accessed_at=datetime.now(UTC),
                        )
                    )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
