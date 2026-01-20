"""AccessGenealogy web scraper for genealogy records.

Supports:
- Native American records (Dawes Rolls, Cherokee, tribal)
- Cemetery records by state
- Census records
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)

# US states for cemetery record URLs
US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming",
]


class AccessGenealogySource(BaseSource):
    """AccessGenealogy.com data source.

    Free resource with:
    - Native American genealogy (Dawes Rolls, Cherokee, tribal records)
    - Cemetery records by state
    - Census transcriptions
    """

    name = "AccessGenealogy"
    base_url = "https://www.accessgenealogy.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search AccessGenealogy for genealogy records.

        Args:
            query: Search parameters. Supported record_types:
                - "census" - Census transcriptions
                - "roll", "tribal", "native", "dawes" - Native American rolls
                - "cemetery", "burial", "grave" - Cemetery records

        Returns:
            List of matching records
        """
        import httpx

        records: list[RawRecord] = []

        # Build base search terms
        search_terms: list[str] = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        # Heuristics: if user asked for specific record types, bias keywords
        rt = {t.lower() for t in (query.record_types or [])}
        if "census" in rt:
            search_terms.append("census")
        # Rolls keywords capture Dawes/tribal enrollments
        if any(k in rt for k in {"roll", "rolls", "tribal", "native", "dawes"}):
            search_terms.extend(["roll", "enrollment", "dawes"])
        # Cemetery keywords
        if any(k in rt for k in {"cemetery", "burial", "grave", "death"}):
            search_terms.append("cemetery")

        if not search_terms:
            return []

        search_query = "+".join(search_terms)

        # Determine state for targeted searches
        query_state = getattr(query, "state", None)
        state_slug = self._normalize_state(query_state) if query_state else None

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                # 1) Site-wide search
                urls: list[str] = [f"{self.base_url}/?s={search_query}"]

                # 2) Targeted sections for Native American rolls
                targeted = [
                    f"{self.base_url}/native/dawes-rolls/?s={search_query}",
                    f"{self.base_url}/native/cherokee/?s={search_query}",
                    f"{self.base_url}/native/?s={search_query}",
                ]
                urls.extend(targeted)

                # 3) If census requested, hit census category pages
                if "census" in rt:
                    urls.append(f"{self.base_url}/census-records/?s={search_query}")

                # 4) Cemetery records - by state if specified, otherwise general
                if any(k in rt for k in {"cemetery", "burial", "grave", "death"}) or not rt:
                    if state_slug and state_slug in US_STATES:
                        urls.append(
                            f"{self.base_url}/{state_slug}/{state_slug}-cemetery-records.htm"
                        )
                        urls.append(f"{self.base_url}/{state_slug}/?s={search_query}")
                    else:
                        # Search general cemetery section
                        urls.append(f"{self.base_url}/cemetery/?s={search_query}")

                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")
                        # Use different parser for index pages vs search results
                        if "cemetery-records.htm" in url:
                            records.extend(self._parse_cemetery_index(soup, url))
                        else:
                            records.extend(self._parse_search_page(soup))
                    except Exception:
                        continue

        except Exception as e:
            logger.warning("AccessGenealogy search error: %s", e)

        # Post-process: classify record types by URL/title hints
        for r in records:
            lower_url = (r.url or "").lower()
            title = (r.raw_data.get("title") or "").lower()
            if any(k in lower_url for k in ["cemetery", "burial", "grave"]) or any(
                k in title for k in ["cemetery", "burial", "grave"]
            ):
                r.record_type = "cemetery"
            elif any(k in lower_url for k in ["dawes", "roll"]) or any(
                k in title for k in ["roll", "enrollment"]
            ):
                r.record_type = "roll"
            elif "census" in lower_url or "census" in title:
                r.record_type = "census"
        return records

    def _normalize_state(self, state: str) -> str | None:
        """Normalize state name to URL slug format.

        Args:
            state: State name (e.g., "California", "New York", "CA")

        Returns:
            URL slug (e.g., "california", "new-york") or None
        """
        if not state:
            return None

        # Handle abbreviations
        state_abbrevs = {
            "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
            "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
            "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
            "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
            "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
            "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
            "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
            "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
            "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
            "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
            "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
            "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia",
            "WI": "wisconsin", "WY": "wyoming",
        }

        upper = state.upper().strip()
        if upper in state_abbrevs:
            return state_abbrevs[upper]

        # Convert full name to slug
        slug = state.lower().strip().replace(" ", "-")
        return slug if slug in US_STATES else None

    def _parse_cemetery_index(self, soup: BeautifulSoup, base_url: str) -> list[RawRecord]:
        """Parse a state cemetery index page.

        Args:
            soup: BeautifulSoup parsed page
            base_url: The URL of the index page

        Returns:
            List of cemetery records
        """
        records: list[RawRecord] = []

        # Cemetery index pages typically have lists of links to county/cemetery pages
        # Look for links in content area
        content = soup.find("div", class_="entry-content") or soup.find("article") or soup

        # Find all links that look like cemetery records
        for link in content.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Skip navigation, external, and non-cemetery links
            if not href or not text:
                continue
            if href.startswith("#") or "accessgenealogy.com" not in href.lower() and not href.startswith("/"):
                continue
            if any(skip in href.lower() for skip in ["facebook", "twitter", "pinterest", "email"]):
                continue

            # Look for cemetery-related content
            text_lower = text.lower()
            if any(k in text_lower for k in ["cemetery", "burial", "grave", "county"]) or any(
                k in href.lower() for k in ["cemetery", "burial"]
            ):
                record = RawRecord(
                    source=self.name,
                    record_id=href,
                    record_type="cemetery",
                    url=href if href.startswith("http") else f"{self.base_url}{href}",
                    raw_data={"title": text, "index_url": base_url},
                    extracted_fields={"title": text, "location": self._extract_location(text)},
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        return records[:50]  # Cap results

    def _extract_location(self, text: str) -> str:
        """Extract location (county) from cemetery title.

        Args:
            text: Cemetery title text

        Returns:
            Extracted location or empty string
        """
        # Common pattern: "County Name County Cemetery Records"
        text_lower = text.lower()
        if "county" in text_lower:
            parts = text.split()
            for i, part in enumerate(parts):
                if part.lower() == "county" and i > 0:
                    return " ".join(parts[:i + 1])
        return ""

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by URL path.

        Args:
            record_id: URL path or article identifier

        Returns:
            The record or None
        """
        import httpx

        url = record_id if record_id.startswith("http") else f"{self.base_url}/{record_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_article(soup, url)

        except Exception as e:
            logger.warning("AccessGenealogy get_record error: %s", e)
            return None

    def _parse_search_page(self, soup: BeautifulSoup) -> list[RawRecord]:
        """Parse search results page.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            List of records found
        """
        records: list[RawRecord] = []

        # Find article entries (typical WordPress structure)
        articles = soup.find_all("article") or soup.find_all("div", class_="post")

        for article in articles[:30]:  # Slightly higher cap
            title_elem = article.find("h2") or article.find("h3")
            link_elem = article.find("a")

            if not title_elem or not link_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = link_elem.get("href", "")

            # Extract snippet/summary
            excerpt = article.find("div", class_="entry-content") or article.find("p")
            summary = excerpt.get_text(strip=True)[:500] if excerpt else ""

            rtype = "article"
            tl = title.lower()
            if "census" in tl:
                rtype = "census"
            if "roll" in tl or "dawes" in tl or "enrollment" in tl:
                rtype = "roll"

            record = RawRecord(
                source=self.name,
                record_id=url,
                record_type=rtype,
                url=url,
                raw_data={"title": title, "summary": summary},
                extracted_fields={"title": title, "summary": summary},
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_article(self, soup: BeautifulSoup, url: str) -> RawRecord | None:
        """Parse a full article page.

        Args:
            soup: BeautifulSoup parsed page
            url: Article URL

        Returns:
            RawRecord or None
        """
        title_elem = soup.find("h1", class_="entry-title") or soup.find("h1")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)

        # Get content
        content_elem = soup.find("div", class_="entry-content") or soup.find("article")
        content = content_elem.get_text(strip=True)[:4000] if content_elem else ""

        # Try to extract structured data (names, dates, etc.)
        extracted: dict[str, str] = {"title": title, "content_preview": content[:800]}

        # Look for table data (common in rolls/census lists)
        tables = soup.find_all("table")
        if tables:
            extracted["has_tabular_data"] = "true"
            extracted["table_count"] = str(len(tables))
            # Pull a small preview of the first table
            first = tables[0]
            headers = [th.get_text(strip=True) for th in first.find_all("th")]
            rows = []
            for tr in first.find_all("tr")[1:6]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if headers:
                extracted["table_headers"] = ", ".join(headers[:10])
            if rows:
                extracted["table_rows_preview"] = "; ".join([" | ".join(r[:10]) for r in rows])

        # Guess record type
        rtype = "article"
        lower_url = url.lower()
        tl = title.lower()
        if any(k in lower_url for k in ["cemetery", "burial", "grave"]) or any(
            k in tl for k in ["cemetery", "burial", "grave"]
        ):
            rtype = "cemetery"
        elif "census" in lower_url or "census" in tl:
            rtype = "census"
        elif any(k in lower_url for k in ["dawes", "roll"]) or any(
            k in tl for k in ["roll", "enrollment"]
        ):
            rtype = "roll"

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=rtype,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )
