"""USGenWeb web scraper for free genealogy records.

USGenWeb is a volunteer-run project organizing genealogy records by state and county.
Records include census transcriptions, cemetery records, vital records, and more.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)

# State abbreviation to full name mapping for URL construction
STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "newhampshire", "NJ": "newjersey", "NM": "newmexico", "NY": "newyork",
    "NC": "northcarolina", "ND": "northdakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhodeisland", "SC": "southcarolina",
    "SD": "southdakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "westvirginia",
    "WI": "wisconsin", "WY": "wyoming",
}

# Reverse mapping
STATE_ABBREVS = {v: k for k, v in STATE_NAMES.items()}


class USGenWebSource(BaseSource):
    """USGenWeb.org data source.

    Free volunteer-run genealogy resource organized by state and county.
    Includes census transcriptions, cemetery records, vital records, and more.
    """

    name = "USGenWeb"
    base_url = "https://usgenweb.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search USGenWeb for genealogy records.

        Args:
            query: Search parameters. Uses state/county if available.
                Supported record_types: census, cemetery, vital, military, land, court

        Returns:
            List of matching records
        """
        import httpx

        records: list[RawRecord] = []

        # Build search terms
        search_terms: list[str] = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        if not search_terms:
            return []

        search_query = " ".join(search_terms)

        # Get state/county from query
        query_state = getattr(query, "state", None)
        query_county = getattr(query, "county", None)
        state_slug = self._normalize_state(query_state) if query_state else None

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                urls: list[str] = []

                # State-specific search if state provided
                if state_slug:
                    # USGenWeb state sites are typically at {state}.usgenweb.org
                    state_base = f"https://{state_slug}.usgenweb.org"
                    urls.append(state_base)

                    # Also try usgenweb.org/{state} pattern
                    urls.append(f"{self.base_url}/{state_slug}/")

                    # County-specific if provided
                    if query_county:
                        county_slug = query_county.lower().replace(" ", "").replace("county", "")
                        urls.append(f"{state_base}/{county_slug}/")

                # Main site search
                urls.append(self.base_url)

                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")
                        page_records = self._parse_page(soup, url, search_query)
                        records.extend(page_records)
                    except Exception as e:
                        logger.debug("USGenWeb fetch error for %s: %s", url, e)
                        continue

        except Exception as e:
            logger.warning("USGenWeb search error: %s", e)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_records: list[RawRecord] = []
        for r in records:
            if r.url and r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_records.append(r)

        return unique_records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by URL.

        Args:
            record_id: URL or path identifier

        Returns:
            The record or None
        """
        import httpx

        url = record_id if record_id.startswith("http") else f"{self.base_url}/{record_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_record_page(soup, url)

        except Exception as e:
            logger.warning("USGenWeb get_record error: %s", e)
            return None

    def _normalize_state(self, state: str) -> str | None:
        """Normalize state input to USGenWeb URL format.

        Args:
            state: State name or abbreviation

        Returns:
            State slug or None
        """
        if not state:
            return None

        state = state.strip()

        # Check if it's an abbreviation
        upper = state.upper()
        if upper in STATE_NAMES:
            return STATE_NAMES[upper]

        # Check if it's already a full name
        lower = state.lower().replace(" ", "").replace("-", "")
        if lower in STATE_ABBREVS:
            return lower

        return None

    def _parse_page(
        self, soup: BeautifulSoup, base_url: str, search_query: str
    ) -> list[RawRecord]:
        """Parse a USGenWeb page for records and links.

        Args:
            soup: BeautifulSoup parsed page
            base_url: The page URL
            search_query: Search terms to match

        Returns:
            List of records found
        """
        records: list[RawRecord] = []
        search_terms = search_query.lower().split()

        # USGenWeb pages are highly variable - look for common patterns
        # 1. Look for links in the page content
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not href or not text or len(text) < 3:
                continue

            # Skip navigation and external links
            if any(skip in href.lower() for skip in [
                "mailto:", "javascript:", "facebook", "twitter",
                "#", "?", "google", "bing"
            ]):
                continue

            # Check if this link matches our search terms
            text_lower = text.lower()
            url_lower = href.lower()

            # Look for surname matches
            matches_search = any(term in text_lower for term in search_terms)

            # Look for genealogy-related content
            is_genealogy = any(kw in text_lower or kw in url_lower for kw in [
                "cemetery", "burial", "grave", "census", "birth", "death",
                "marriage", "vital", "military", "pension", "land", "deed",
                "probate", "court", "church", "obituar"
            ])

            if matches_search or is_genealogy:
                # Determine record type
                record_type = self._classify_record_type(text_lower, url_lower)

                # Build full URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    # Extract domain from base_url
                    from urllib.parse import urlparse
                    parsed = urlparse(base_url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    full_url = f"{base_url.rstrip('/')}/{href}"

                record = RawRecord(
                    source=self.name,
                    record_id=full_url,
                    record_type=record_type,
                    url=full_url,
                    raw_data={"title": text, "found_on": base_url},
                    extracted_fields={
                        "title": text,
                        "state": self._extract_state(base_url),
                    },
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        # 2. Look for tables with data
        for table in soup.find_all("table"):
            table_records = self._parse_table(table, base_url, search_terms)
            records.extend(table_records)

        return records[:100]  # Cap results

    def _parse_table(
        self, table: BeautifulSoup, base_url: str, search_terms: list[str]
    ) -> list[RawRecord]:
        """Parse a table for genealogy records.

        Args:
            table: BeautifulSoup table element
            base_url: Page URL
            search_terms: Search terms to match

        Returns:
            List of records from the table
        """
        records: list[RawRecord] = []

        # Get headers
        headers: list[str] = []
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

        # Look for name-like columns
        name_cols = [i for i, h in enumerate(headers) if any(
            kw in h for kw in ["name", "surname", "given", "person"]
        )]

        # Parse rows
        for row in table.find_all("tr")[1:20]:  # Skip header, limit rows
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            # Check if any cell matches search terms
            row_text = " ".join(cells).lower()
            if not any(term in row_text for term in search_terms):
                continue

            # Extract name
            name = ""
            if name_cols and name_cols[0] < len(cells):
                name = cells[name_cols[0]]
            elif cells:
                name = cells[0]

            record = RawRecord(
                source=self.name,
                record_id=f"{base_url}#row-{hash(row_text)}",
                record_type=self._classify_record_type(row_text, base_url.lower()),
                url=base_url,
                raw_data={"row_data": dict(zip(headers, cells)) if headers else cells},
                extracted_fields={
                    "name": name,
                    "raw_text": " | ".join(cells[:5]),
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_record_page(self, soup: BeautifulSoup, url: str) -> RawRecord | None:
        """Parse a full record page.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL

        Returns:
            RawRecord or None
        """
        # Get title
        title_elem = soup.find("title") or soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        # Get body content
        body = soup.find("body")
        content = body.get_text(strip=True)[:4000] if body else ""

        # Classify
        record_type = self._classify_record_type(title.lower(), url.lower())

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=record_type,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields={
                "title": title,
                "state": self._extract_state(url),
                "content_preview": content[:500],
            },
            accessed_at=datetime.now(UTC),
        )

    def _classify_record_type(self, text: str, url: str) -> str:
        """Classify the record type based on text and URL.

        Args:
            text: Text content (lowercase)
            url: URL (lowercase)

        Returns:
            Record type string
        """
        combined = f"{text} {url}"

        if any(kw in combined for kw in ["cemetery", "burial", "grave", "interment"]):
            return "cemetery"
        if any(kw in combined for kw in ["census", "enumerat"]):
            return "census"
        if any(kw in combined for kw in ["birth", "death", "marriage", "vital", "divorce"]):
            return "vital"
        if any(kw in combined for kw in ["military", "soldier", "veteran", "pension", "war", "draft"]):
            return "military"
        if any(kw in combined for kw in ["land", "deed", "property"]):
            return "land"
        if any(kw in combined for kw in ["probate", "will", "estate", "court"]):
            return "court"
        if any(kw in combined for kw in ["church", "baptism", "christening"]):
            return "church"
        if "obituar" in combined:
            return "obituary"

        return "record"

    def _extract_state(self, url: str) -> str:
        """Extract state from URL.

        Args:
            url: URL to parse

        Returns:
            State abbreviation or empty string
        """
        url_lower = url.lower()

        # Check for state subdomain pattern: {state}.usgenweb.org
        match = re.search(r"(\w+)\.usgenweb\.org", url_lower)
        if match:
            state_slug = match.group(1)
            if state_slug in STATE_ABBREVS:
                return STATE_ABBREVS[state_slug]

        # Check for path pattern: usgenweb.org/{state}/
        match = re.search(r"usgenweb\.org/(\w+)", url_lower)
        if match:
            state_slug = match.group(1)
            if state_slug in STATE_ABBREVS:
                return STATE_ABBREVS[state_slug]

        return ""
