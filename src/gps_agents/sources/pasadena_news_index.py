"""Pasadena News Index source for newspaper citations.

The Pasadena News Index (PNI) is a FREE searchable database maintained by
the Pasadena Public Library. It indexes local Pasadena newspapers including:
- Pasadena Star-News
- Pasadena Weekly
- Pasadena Journal
- Other historical Pasadena papers

Coverage: 1880s to present (primarily 1996-present, with older indexed material)
Records: Obituaries, news articles, local events, city records
Access: FREE - No login required

URL: https://pni.cityofpasadena.net/
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

# Mapping of article types to search values
ARTICLE_TYPES = {
    "obituary": "Obituary",
    "death": "Obituary",
    "birth": "Birth",
    "marriage": "Marriage",
    "divorce": "Divorce",
    "engagement": "Engagement",
    "anniversary": "Anniversary",
    "all": "",  # Empty = all types
}


class PasadenaNewsIndexSource(BaseSource):
    """Pasadena News Index (PNI) newspaper citation search.

    A FREE searchable index of Pasadena newspaper articles maintained by
    the Pasadena Public Library. Particularly valuable for:
    - Los Angeles County obituaries
    - Pasadena local history
    - African American families in Pasadena (Great Migration)

    Records include:
    - Full name of subject
    - Publication date
    - Newspaper name
    - Page and column location
    - Article type (Obituary, Birth, Marriage, etc.)

    Note: The index provides CITATIONS only - full article text requires
    visiting the library's microfilm collection.
    """

    name = "PasadenaNewsIndex"
    base_url = "https://pni.cityofpasadena.net"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Pasadena News Index for newspaper citations.

        Args:
            query: Search parameters

        Returns:
            List of newspaper citation records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search parameters
        params: dict[str, str] = {}

        # Name search - PNI uses "Name" field
        if query.given_name:
            params["Name"] = f"{query.surname}, {query.given_name}"
        else:
            params["Name"] = query.surname

        # Article type filter
        article_type = ""
        if query.record_types:
            for rt in query.record_types:
                if rt.lower() in ARTICLE_TYPES:
                    article_type = ARTICLE_TYPES[rt.lower()]
                    break

        if article_type:
            params["Article Type"] = article_type

        # Date range (PNI uses date fields)
        if query.death_year:
            year_range = query.get_year_range(query.death_year, query.death_year_range)
            if year_range:
                params["Start Date"] = f"01/01/{year_range[0]}"
                params["End Date"] = f"12/31/{year_range[1]}"

        search_url = f"{self.base_url}/search"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.3.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                # POST search form
                resp = await client.post(search_url, data=params)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_search_results(soup, query)
                else:
                    logger.debug(
                        f"PNI search returned status {resp.status_code}"
                    )

        except httpx.HTTPError as e:
            logger.debug(f"Pasadena News Index search error: {e}")

        # Always add a search URL for manual access
        manual_params = {"Name": params.get("Name", query.surname)}
        if article_type:
            manual_params["Article Type"] = article_type
        manual_url = f"{self.base_url}/search?{urlencode(manual_params)}"

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"pni-search-{query.surname}",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": query.model_dump(), "params": params},
                extracted_fields={
                    "search_type": "Pasadena News Index Search",
                    "search_url": manual_url,
                    "note": (
                        "FREE searchable index of Pasadena newspapers. "
                        "Citations only - full text requires library microfilm access."
                    ),
                    "coverage": "1880s-present (primarily 1996-present)",
                    "newspapers": "Pasadena Star-News, Pasadena Weekly, Pasadena Journal",
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
        """Parse PNI search results page."""
        records: list[RawRecord] = []

        # PNI displays results in a table format
        # Look for result rows
        result_selectors = [
            "table.results tr",
            ".search-results tr",
            "table tr",
            ".result-row",
        ]

        items = []
        for selector in result_selectors:
            items = soup.select(selector)
            if items:
                # Skip header row
                items = [
                    item for item in items if not item.find("th")
                ]
                break

        # Also try looking for result divs
        if not items:
            items = soup.select(".result, .citation")

        for item in items[:50]:  # Limit results
            try:
                record = self._parse_result_row(item, query)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Failed to parse PNI result: {e}")
                continue

        return records

    def _parse_result_row(
        self,
        row: Any,
        query: SearchQuery,  # noqa: ARG002 - reserved for future filtering
    ) -> RawRecord | None:
        """Parse a single result row from PNI."""
        text = row.get_text(" ", strip=True)
        if not text or len(text) < 10:
            return None

        # Extract cells if table row
        cells = row.find_all("td")
        extracted: dict[str, str | None] = {}

        if cells and len(cells) >= 3:
            # Typical PNI table: Name | Date | Page | Article Type
            extracted["full_name"] = cells[0].get_text(strip=True) if len(cells) > 0 else None
            extracted["publication_date"] = cells[1].get_text(strip=True) if len(cells) > 1 else None
            extracted["page_location"] = cells[2].get_text(strip=True) if len(cells) > 2 else None
            extracted["article_type"] = cells[3].get_text(strip=True) if len(cells) > 3 else None
        else:
            # Parse from text
            extracted = self._extract_citation_fields(text)

        # Skip if no useful data
        if not extracted.get("full_name") and not extracted.get("publication_date"):
            return None

        # Build record ID from name and date
        name = extracted.get("full_name", "unknown")
        date = extracted.get("publication_date", "unknown")
        record_id = f"pni-{hash(f'{name}-{date}')}"

        # Determine record type from article type
        article_type = extracted.get("article_type", "").lower()
        if "obituary" in article_type:
            record_type = "obituary"
        elif "birth" in article_type:
            record_type = "birth_notice"
        elif "marriage" in article_type:
            record_type = "marriage_notice"
        else:
            record_type = "newspaper_citation"

        # Add newspaper source
        extracted["newspaper"] = "Pasadena Star-News"  # Most common
        extracted["source_note"] = "Citation from Pasadena News Index - full text requires library microfilm"

        return RawRecord(
            source=self.name,
            record_id=record_id,
            record_type=record_type,
            url=self.base_url,
            raw_data={"text": text[:500]},
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )

    def _extract_citation_fields(self, text: str) -> dict[str, str | None]:
        """Extract citation fields from text."""
        extracted: dict[str, str | None] = {}

        # Name pattern - usually "Lastname, Firstname" or "Firstname Lastname"
        name_match = re.search(
            r"([A-Za-z\-']+,\s+[A-Za-z\s\.\-']+?)(?:\s+\d|$)",
            text,
        )
        if name_match:
            extracted["full_name"] = name_match.group(1).strip()

        # Date patterns
        # MM/DD/YYYY
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
        if date_match:
            extracted["publication_date"] = date_match.group(1)
        else:
            # Month DD, YYYY
            date_match = re.search(
                r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
                text,
            )
            if date_match:
                extracted["publication_date"] = date_match.group(1)

        # Page location - "Page A-10" or "p. A10" or "Page 4, Column 2"
        page_match = re.search(
            r"(?:Page|p\.?)\s*([A-Z]?\-?\d+)(?:,?\s*(?:Column|Col\.?)\s*(\d+))?",
            text,
            re.IGNORECASE,
        )
        if page_match:
            page = page_match.group(1)
            column = page_match.group(2)
            if column:
                extracted["page_location"] = f"Page {page}, Column {column}"
            else:
                extracted["page_location"] = f"Page {page}"

        # Article type
        article_types = ["Obituary", "Birth", "Marriage", "Divorce", "Engagement"]
        for at in article_types:
            if at.lower() in text.lower():
                extracted["article_type"] = at
                break

        return extracted

    async def search_obituaries(
        self,
        surname: str,
        given_name: str | None = None,
        year_start: int | None = None,
        year_end: int | None = None,
    ) -> list[RawRecord]:
        """Convenience method to search specifically for obituaries.

        Args:
            surname: Last name to search
            given_name: Optional first name
            year_start: Optional start year
            year_end: Optional end year

        Returns:
            List of obituary citation records
        """
        query = SearchQuery(
            surname=surname,
            given_name=given_name,
            death_year=year_end,  # Use end year as reference
            death_year_range=((year_end - year_start) // 2) if year_start and year_end else 5,
            record_types=["obituary"],
        )
        return await self.search(query)

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """PNI doesn't have individual record pages - citations only."""
        # PNI provides citations, not full records
        # Return None as there's no direct record URL
        return None


class LosAngelesCountyNewspapersSource(BaseSource):
    """Aggregator for Los Angeles County newspaper sources.

    Combines multiple free newspaper resources for LA County research:
    - Pasadena News Index (free)
    - Chronicling America / LOC (free)
    - California Digital Newspaper Collection (free)
    """

    name = "LACountyNewspapers"

    def __init__(self) -> None:
        super().__init__()
        self.pni = PasadenaNewsIndexSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search multiple LA County newspaper sources."""
        records: list[RawRecord] = []

        # Search Pasadena News Index
        try:
            pni_records = await self.pni.search(query)
            records.extend(pni_records)
        except Exception as e:
            logger.debug(f"PNI search error: {e}")

        # Add links to other LA County newspaper sources
        name_query = query.surname or ""
        if query.given_name:
            name_query = f"{query.given_name} {query.surname}"

        other_sources = [
            {
                "name": "California Digital Newspaper Collection (CDNC)",
                "url": f"https://cdnc.ucr.edu/cgi-bin/cdnc?a=q&hs=1&r=1&results=1&txq={quote_plus(name_query)}&txf=txIN&o=10",
                "description": "Free historical California newspapers (1846-present)",
                "coverage": "LA Times, LA Herald, and 180+ California papers",
            },
            {
                "name": "Chronicling America - Los Angeles",
                "url": f"https://chroniclingamerica.loc.gov/search/pages/results/?state=California&city=Los+Angeles&andtext={quote_plus(name_query)}",
                "description": "Free Library of Congress historic newspapers",
                "coverage": "1777-1963, various LA papers",
            },
            {
                "name": "LA Public Library Photo Collection",
                "url": f"https://tessa.lapl.org/search?q={quote_plus(name_query)}",
                "description": "Historical photos and newspaper clippings",
                "coverage": "Los Angeles area historical materials",
            },
        ]

        for source in other_sources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"la-news-{hash(source['name'])}",
                    record_type="newspaper_source",
                    url=source["url"],
                    raw_data=source,
                    extracted_fields={
                        "resource_title": source["name"],
                        "search_url": source["url"],
                        "description": source["description"],
                        "coverage": source.get("coverage", ""),
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return await self.pni.get_record(record_id)
