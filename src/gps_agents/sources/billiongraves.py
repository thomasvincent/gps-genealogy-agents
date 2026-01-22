"""BillionGraves source for cemetery/burial records.

BillionGraves is a free cemetery database with GPS-located headstones.
Search is free; some features require account.

Coverage: Worldwide, strongest in US
Records: Headstone photos, burial information, GPS coordinates
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


class BillionGravesSource(BaseSource):
    """BillionGraves cemetery records source.

    BillionGraves provides free access to cemetery records with:
    - Headstone photographs
    - GPS coordinates for grave locations
    - Birth/death dates
    - Family links (when visible on stones)

    Search is free without login. Some detailed views require account.
    """

    name = "BillionGraves"
    base_url = "https://billiongraves.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search BillionGraves for burial records.

        Args:
            query: Search parameters

        Returns:
            List of burial records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search URL
        params: dict[str, str] = {
            "family_name": query.surname,
        }

        if query.given_name:
            params["given_name"] = query.given_name

        # Location filters
        if query.state:
            params["state"] = query.state
        elif query.birth_place:
            # Try to extract state from birth place
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                params["state"] = parts[-1].strip()

        # Year filters
        if query.birth_year:
            params["birth_year"] = str(query.birth_year)
        if query.death_year:
            params["death_year"] = str(query.death_year)

        search_url = f"{self.base_url}/search"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url, params=params)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_search_results(soup, query)

        except httpx.HTTPError as e:
            logger.debug(f"BillionGraves search error: {e}")

        # Always add a search URL record for manual follow-up
        manual_url = f"{search_url}?{'&'.join(f'{k}={quote_plus(v)}' for k, v in params.items())}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"bg-search-{query.surname}",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "BillionGraves Cemetery Search",
                    "search_url": manual_url,
                    "note": "Search BillionGraves for headstone photos and burial records",
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
        """Parse BillionGraves search results."""
        records: list[RawRecord] = []

        # BillionGraves result selectors
        result_selectors = [
            ".search-result",
            ".result-item",
            "[data-record-id]",
            ".person-result",
            "tr.result",
        ]

        items = []
        for selector in result_selectors:
            items = soup.select(selector)
            if items:
                break

        # Also try generic link patterns
        if not items:
            items = soup.find_all("a", href=re.compile(r"/grave/"))

        for item in items[:20]:
            try:
                # Handle both element types
                if item.name == "a":
                    link = item
                    name_text = item.get_text(strip=True)
                else:
                    link = item.select_one("a[href*='/grave/']") or item.select_one("a")
                    name_text = item.get_text(" ", strip=True)

                if not link:
                    continue

                href = link.get("href", "")
                if not href:
                    continue

                url = href if href.startswith("http") else urljoin(self.base_url, href)

                # Extract record ID from URL
                record_id = ""
                id_match = re.search(r"/grave/(\d+)", href)
                if id_match:
                    record_id = id_match.group(1)

                # Parse dates and name from text
                extracted = self._extract_burial_fields(name_text)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=record_id or f"bg-{hash(url)}",
                        record_type="burial",
                        url=url,
                        raw_data={"text": name_text[:500]},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse BillionGraves result: {e}")
                continue

        return records

    def _extract_burial_fields(self, text: str) -> dict[str, str]:
        """Extract burial record fields from text."""
        extracted: dict[str, str] = {}

        # Try to extract name (typically first part)
        # Clean up common prefixes
        clean_text = re.sub(r"^(Honoring|Memorial for|In Memory of)\s*", "", text, flags=re.I)

        # Name is usually before dates
        name_match = re.match(r"([A-Za-z\s\.\-']+?)(?:\d|Birth|Death|–|-)", clean_text)
        if name_match:
            extracted["full_name"] = name_match.group(1).strip()

        # Date patterns
        # Full dates: "24 Nov 1932" or "Nov 24, 1932" or "1932-11-24"
        date_pattern = r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{4})"

        # Look for birth date
        birth_match = re.search(rf"(?:Birth|Born|b\.?)\s*:?\s*{date_pattern}", text, re.I)
        if birth_match:
            extracted["birth_date"] = birth_match.group(1)
        else:
            # Try date range pattern "1932 – 1996"
            range_match = re.search(r"(\d{4})\s*[–\-]\s*(\d{4})", text)
            if range_match:
                extracted["birth_date"] = range_match.group(1)
                extracted["death_date"] = range_match.group(2)

        # Look for death date if not already found
        if "death_date" not in extracted:
            death_match = re.search(rf"(?:Death|Died|d\.?)\s*:?\s*{date_pattern}", text, re.I)
            if death_match:
                extracted["death_date"] = death_match.group(1)

        # Cemetery name
        cemetery_match = re.search(r"(?:Cemetery|Cem\.?|Memorial Park|Mausoleum)\s*[:\-]?\s*([^,\n]+)", text, re.I)
        if cemetery_match:
            extracted["cemetery"] = cemetery_match.group(1).strip()

        # Location
        location_match = re.search(r"(?:Location|Place|City)\s*[:\-]?\s*([^,\n]+,\s*[A-Z]{2})", text, re.I)
        if location_match:
            extracted["location"] = location_match.group(1).strip()

        return extracted

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific BillionGraves record."""
        if record_id.startswith("http"):
            url = record_id
        else:
            url = f"{self.base_url}/grave/{record_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract person name
                name_el = soup.select_one("h1, .person-name, .grave-name")
                name = name_el.get_text(strip=True) if name_el else "Unknown"

                # Extract full page text for field extraction
                page_text = soup.get_text(" ", strip=True)
                extracted = self._extract_burial_fields(page_text)
                extracted["full_name"] = name

                # Try to get GPS coordinates
                gps_match = re.search(r"(-?\d+\.\d+),\s*(-?\d+\.\d+)", page_text)
                if gps_match:
                    extracted["latitude"] = gps_match.group(1)
                    extracted["longitude"] = gps_match.group(2)

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="burial",
                    url=url,
                    raw_data={"name": name},
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except Exception as e:
            logger.warning(f"Failed to fetch BillionGraves record: {e}")
            return None
