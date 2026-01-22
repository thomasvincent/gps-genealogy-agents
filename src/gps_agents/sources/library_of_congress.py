"""Library of Congress genealogy sources.

The Library of Congress provides free access to:
- Chronicling America (historic newspapers)
- Maps and photographs
- Manuscript collections
- Immigration records
- Census finding aids
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


class ChroniclingAmericaSource(BaseSource):
    """Chronicling America - Historic American Newspapers (LOC).

    Free digitized newspapers from 1777-1963.
    Over 20 million pages from 3,000+ newspapers.
    """

    name = "ChroniclingAmerica"
    base_url = "https://chroniclingamerica.loc.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search historic newspapers for surname mentions.

        Args:
            query: Search parameters

        Returns:
            List of newspaper search results
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search query
        search_terms = query.surname
        if query.given_name:
            search_terms = f'"{query.given_name} {query.surname}"'

        params: dict[str, str] = {
            "andtext": search_terms,
            "format": "html",
        }

        # Date range
        if query.birth_year:
            params["dateFilterType"] = "yearRange"
            params["date1"] = str(query.birth_year - 5)
            params["date2"] = str(min(query.birth_year + 80, 1963))

        # State filter
        if query.state:
            state_codes = self._get_state_code(query.state)
            if state_codes:
                params["state"] = state_codes

        search_url = f"{self.base_url}/search/pages/results/"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url, params=params)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_search_results(soup, query)

        except httpx.HTTPError as e:
            logger.debug(f"Chronicling America search error: {e}")

        # Add search URL for manual access
        manual_url = f"{search_url}?{'&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items())}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ca-search-{query.surname}",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "Chronicling America Newspaper Search",
                    "search_url": manual_url,
                    "note": "Free historic US newspapers (1777-1963)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _get_state_code(self, state: str) -> str | None:
        """Convert state name to LOC state code."""
        states = {
            "california": "California",
            "new york": "New+York",
            "texas": "Texas",
            "pennsylvania": "Pennsylvania",
            "ohio": "Ohio",
            "illinois": "Illinois",
            "georgia": "Georgia",
            "virginia": "Virginia",
            "north carolina": "North+Carolina",
            "michigan": "Michigan",
            # Add more as needed
        }
        return states.get(state.lower())

    def _parse_search_results(
        self,
        soup: BeautifulSoup,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Parse Chronicling America search results."""
        records: list[RawRecord] = []

        # Result items
        items = soup.select(".result, .search-result, [data-page-url]")

        for item in items[:15]:
            try:
                link = item.select_one("a[href*='/lccn/']") or item.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Get newspaper name and date
                title_el = item.select_one(".title, h4, strong")
                title = title_el.get_text(strip=True) if title_el else "Newspaper page"

                date_el = item.select_one(".date, .pub-date")
                date = date_el.get_text(strip=True) if date_el else ""

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"ca-{hash(url)}",
                        record_type="newspaper",
                        url=url,
                        raw_data={"title": title, "date": date},
                        extracted_fields={
                            "newspaper_title": title,
                            "publication_date": date,
                            "note": "Historic newspaper mention",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse Chronicling America result: {e}")
                continue

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class LibraryOfCongressSource(BaseSource):
    """Library of Congress genealogy resources aggregator.

    Combines:
    - Chronicling America newspapers
    - Map collections
    - Manuscript finding aids
    - Immigration resources
    """

    name = "LibraryOfCongress"
    base_url = "https://www.loc.gov"

    def __init__(self) -> None:
        super().__init__()
        self.chronicling_america = ChroniclingAmericaSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search LOC genealogy resources."""
        records: list[RawRecord] = []

        # Search newspapers
        try:
            ca_records = await self.chronicling_america.search(query)
            records.extend(ca_records)
        except Exception as e:
            logger.debug(f"Chronicling America error: {e}")

        # Add LOC genealogy guide
        records.append(
            RawRecord(
                source=self.name,
                record_id="loc-genealogy-guide",
                record_type="resource_link",
                url="https://www.loc.gov/rr/genealogy/",
                raw_data={},
                extracted_fields={
                    "resource_title": "Library of Congress Genealogy Resources",
                    "description": "Guide to genealogy collections at LOC",
                    "note": "Free research guides and finding aids",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add digital collections search
        if query.surname:
            digital_url = f"https://www.loc.gov/search/?q={quote_plus(query.surname)}&fa=original-format%3Amanuscript%2Fmixed+material"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"loc-digital-{query.surname}",
                    record_type="search_url",
                    url=digital_url,
                    raw_data={},
                    extracted_fields={
                        "search_type": "LOC Digital Collections",
                        "search_url": digital_url,
                        "description": "Search manuscripts and mixed materials",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add immigration arrival records
        records.append(
            RawRecord(
                source=self.name,
                record_id="loc-immigration",
                record_type="resource_link",
                url="https://www.loc.gov/rr/genealogy/bib_guid/immigrant/",
                raw_data={},
                extracted_fields={
                    "resource_title": "LOC Immigration Resources",
                    "description": "Research guide for immigrant ancestors",
                    "note": "Free research guide",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class NYPLSource(BaseSource):
    """New York Public Library genealogy resources.

    NYPL Milstein Division provides:
    - New York vital records
    - City directories
    - Census finding aids
    - Immigration records
    """

    name = "NYPL"
    base_url = "https://www.nypl.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search NYPL genealogy resources."""
        records: list[RawRecord] = []

        # NYPL Milstein Division resources
        resources = [
            {
                "name": "NYPL Genealogy Guide",
                "url": "https://www.nypl.org/about/locations/schwarzman/milstein",
                "description": "Milstein Division genealogy resources",
            },
            {
                "name": "NYPL Digital Collections",
                "url": f"https://digitalcollections.nypl.org/search/index?utf8=%E2%9C%93&keywords={quote_plus(query.surname or '')}",
                "description": "Search NYPL digitized materials",
            },
            {
                "name": "NYC Municipal Archives Guide",
                "url": "https://www.nypl.org/blog/2019/01/15/guide-nyc-municipal-archives",
                "description": "Guide to NYC vital records at Municipal Archives",
            },
        ]

        for resource in resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"nypl-{hash(resource['name'])}",
                    record_type="resource_link",
                    url=resource["url"],
                    raw_data=resource,
                    extracted_fields={
                        "resource_title": resource["name"],
                        "description": resource["description"],
                        "note": "NYPL genealogy resource",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class ImmigrationRecordsSource(BaseSource):
    """Immigration and passenger list sources.

    Free sources for immigration records:
    - Ellis Island (free with registration)
    - Castle Garden (free)
    - NARA immigration records
    - Steve Morse tools
    """

    name = "ImmigrationRecords"
    base_url = "https://www.libertyellisfoundation.org"

    def requires_auth(self) -> bool:
        return False  # Ellis Island registration is free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search immigration and passenger list sources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Ellis Island (free registration required)
        ellis_url = f"https://www.libertyellisfoundation.org/passenger-result?search=passengerSearch&searchType=simple&lastName={quote_plus(query.surname)}"
        if query.given_name:
            ellis_url += f"&firstName={quote_plus(query.given_name)}"

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ellis-{query.surname}",
                record_type="search_url",
                url=ellis_url,
                raw_data={},
                extracted_fields={
                    "search_type": "Ellis Island Passenger Search",
                    "search_url": ellis_url,
                    "description": "1892-1957 Ellis Island arrivals (free registration)",
                    "note": "Free with registration",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Castle Garden (pre-Ellis Island)
        castle_url = f"https://www.castlegarden.org/searcher.php?lnm={quote_plus(query.surname)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"castle-{query.surname}",
                record_type="search_url",
                url=castle_url,
                raw_data={},
                extracted_fields={
                    "search_type": "Castle Garden Passenger Search",
                    "search_url": castle_url,
                    "description": "1820-1892 NYC arrivals (free)",
                    "note": "Completely free, no registration",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Steve Morse one-step tools
        morse_url = f"https://stevemorse.org/ellis/ellisisland.html"
        records.append(
            RawRecord(
                source=self.name,
                record_id="morse-tools",
                record_type="resource_link",
                url=morse_url,
                raw_data={},
                extracted_fields={
                    "resource_title": "Steve Morse One-Step Search Tools",
                    "description": "Advanced search tools for Ellis Island and other records",
                    "note": "Free search tools, widely used by genealogists",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # NARA immigration resources
        nara_url = "https://www.archives.gov/research/immigration"
        records.append(
            RawRecord(
                source=self.name,
                record_id="nara-immigration",
                record_type="resource_link",
                url=nara_url,
                raw_data={},
                extracted_fields={
                    "resource_title": "NARA Immigration Records",
                    "description": "National Archives guide to immigration records",
                    "note": "Research guide for passenger lists",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # FamilySearch immigration collections
        fs_immigration_url = f"https://www.familysearch.org/search/collection/list?page=1&recordType=Immigration"
        records.append(
            RawRecord(
                source=self.name,
                record_id="fs-immigration",
                record_type="search_url",
                url=fs_immigration_url,
                raw_data={},
                extracted_fields={
                    "search_type": "FamilySearch Immigration Collections",
                    "search_url": fs_immigration_url,
                    "description": "Free immigration records on FamilySearch",
                    "note": "Free with FamilySearch account",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
