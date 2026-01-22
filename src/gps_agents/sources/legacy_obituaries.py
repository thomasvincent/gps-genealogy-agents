"""Legacy.com source for obituaries.

Legacy.com is the largest obituary website, aggregating obituaries from
thousands of newspapers. Basic search is free.

Coverage: US, Canada, UK, Australia, primarily 1990s-present
Records: Obituaries, death notices, guest books
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


class LegacyObituariesSource(BaseSource):
    """Legacy.com obituary search.

    Legacy.com aggregates obituaries from thousands of US newspapers.
    Basic search and viewing is free.

    Records typically include:
    - Full name
    - Birth and death dates
    - City/state
    - Surviving family members
    - Funeral information
    - Guest book messages
    """

    name = "LegacyObituaries"
    base_url = "https://www.legacy.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Legacy.com for obituaries.

        Args:
            query: Search parameters

        Returns:
            List of obituary records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search URL
        name_query = query.surname
        if query.given_name:
            name_query = f"{query.given_name} {query.surname}"

        params: dict[str, str] = {
            "fullName": name_query,
        }

        # Location filter
        if query.state:
            params["state"] = query.state
        elif query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                state = parts[-1].strip()
                if len(state) == 2:
                    params["state"] = state

        # Year range
        if query.death_year:
            params["dateRange"] = f"{query.death_year},{query.death_year}"

        search_url = f"{self.base_url}/us/obituaries/name"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                # Legacy.com uses path-based search
                search_path = f"/us/obituaries/name/{quote_plus(name_query)}"
                resp = await client.get(f"{self.base_url}{search_path}")

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_search_results(soup, query)

        except httpx.HTTPError as e:
            logger.debug(f"Legacy.com search error: {e}")

        # Add search URL for manual access
        manual_url = f"{self.base_url}/us/obituaries/name/{quote_plus(name_query)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"legacy-search-{query.surname}",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "Legacy.com Obituary Search",
                    "search_url": manual_url,
                    "note": "Search Legacy.com for newspaper obituaries (US/Canada)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _parse_search_results(
        self,
        soup: BeautifulSoup,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Parse Legacy.com search results."""
        records: list[RawRecord] = []

        # Legacy.com result selectors
        result_selectors = [
            "article.PersonCard",
            ".obit-result",
            "[data-obit-id]",
            ".search-result",
        ]

        items = []
        for selector in result_selectors:
            items = soup.select(selector)
            if items:
                break

        # Also try links to obituaries
        if not items:
            items = soup.find_all("a", href=re.compile(r"/obituaries/"))

        for item in items[:20]:
            try:
                # Handle different element types
                if item.name == "a":
                    link = item
                    text = item.get_text(" ", strip=True)
                else:
                    link = item.select_one("a[href*='/obituaries/']") or item.select_one("a")
                    text = item.get_text(" ", strip=True)

                if not link:
                    continue

                href = link.get("href", "")
                if not href or "search" in href.lower():
                    continue

                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Extract record ID from URL
                record_id = ""
                id_match = re.search(r"/obituaries/[^/]+/(\d+)", href)
                if id_match:
                    record_id = id_match.group(1)

                # Parse obituary info
                extracted = self._extract_obituary_fields(text)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=record_id or f"legacy-{hash(url)}",
                        record_type="obituary",
                        url=url,
                        raw_data={"text": text[:500]},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse Legacy.com result: {e}")
                continue

        return records

    def _extract_obituary_fields(self, text: str) -> dict[str, str]:
        """Extract obituary fields from text."""
        extracted: dict[str, str] = {}

        # Name pattern (usually first part)
        name_match = re.match(r"([A-Za-z\s\.\-'\"]+?)(?:\d|Born|Died|Age|–|-)", text)
        if name_match:
            extracted["full_name"] = name_match.group(1).strip()

        # Date patterns
        # "1932 - 1996" or "Nov 24, 1932 - May 4, 1996"
        date_range = re.search(r"(\d{4})\s*[–\-]\s*(\d{4})", text)
        if date_range:
            extracted["birth_year"] = date_range.group(1)
            extracted["death_year"] = date_range.group(2)

        # Full dates
        full_date = r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})"
        dates = re.findall(full_date, text)
        if len(dates) >= 2:
            extracted["birth_date"] = dates[0]
            extracted["death_date"] = dates[1]
        elif len(dates) == 1:
            extracted["death_date"] = dates[0]

        # Age at death
        age_match = re.search(r"(?:age|aged)\s*(\d+)", text, re.I)
        if age_match:
            extracted["age"] = age_match.group(1)

        # Location
        loc_match = re.search(r"(?:of|from|in)\s+([A-Za-z\s]+,\s*[A-Z]{2})", text, re.I)
        if loc_match:
            extracted["location"] = loc_match.group(1).strip()

        # Newspaper source
        paper_match = re.search(r"(?:Published in|from)\s+([^\.]+)", text, re.I)
        if paper_match:
            extracted["newspaper"] = paper_match.group(1).strip()

        return extracted

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific obituary."""
        if record_id.startswith("http"):
            url = record_id
        else:
            # Need full URL for Legacy.com
            return None

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # Get name
                name_el = soup.select_one("h1, .obit-name, .person-name")
                name = name_el.get_text(strip=True) if name_el else "Unknown"

                # Get full text
                obit_content = soup.select_one(".obit-content, article, .obituary-text")
                full_text = obit_content.get_text(" ", strip=True) if obit_content else soup.get_text(" ", strip=True)

                extracted = self._extract_obituary_fields(full_text)
                extracted["full_name"] = name

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="obituary",
                    url=url,
                    raw_data={"name": name, "text": full_text[:1000]},
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except Exception as e:
            logger.warning(f"Failed to fetch Legacy.com obituary: {e}")
            return None


class NewspaperObituariesSource(BaseSource):
    """Aggregator for free newspaper obituary sources.

    Combines multiple obituary search sources:
    - Legacy.com
    - Newspapers.com (limited free)
    - GenealogyBank (limited free)
    - Local newspaper archives
    """

    name = "NewspaperObituaries"

    def __init__(self) -> None:
        super().__init__()
        self.legacy = LegacyObituariesSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search multiple obituary sources."""
        records: list[RawRecord] = []

        # Search Legacy.com
        try:
            legacy_records = await self.legacy.search(query)
            records.extend(legacy_records)
        except Exception as e:
            logger.debug(f"Legacy.com search error: {e}")

        # Add links to other obituary sources
        other_sources = [
            {
                "name": "Newspapers.com Obituaries",
                "url": f"https://www.newspapers.com/search/?query={quote_plus(query.surname)}&t=17",
                "description": "Historical newspaper obituaries (subscription, some free)",
            },
            {
                "name": "GenealogyBank Obituaries",
                "url": f"https://www.genealogybank.com/explore/obituaries/all/usa?fname={quote_plus(query.given_name or '')}&lname={quote_plus(query.surname)}",
                "description": "Historical obituaries 1690-present (subscription, some free)",
            },
            {
                "name": "Chronicling America (LOC)",
                "url": f"https://chroniclingamerica.loc.gov/search/pages/results/?andtext={quote_plus(query.surname)}&dateFilterType=yearRange",
                "description": "Free historic American newspapers (1777-1963)",
            },
        ]

        for source in other_sources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"obits-{hash(source['name'])}",
                    record_type="obituary_source",
                    url=source["url"],
                    raw_data=source,
                    extracted_fields={
                        "resource_title": source["name"],
                        "search_url": source["url"],
                        "description": source["description"],
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return await self.legacy.get_record(record_id)
