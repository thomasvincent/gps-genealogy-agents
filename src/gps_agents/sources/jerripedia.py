"""Jerripedia web scraper for Channel Islands records."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class JerripediaSource(BaseSource):
    """Jerripedia.org data source.

    Community wiki for Jersey (Channel Islands) genealogy and history.
    Contains parish records, census data, and local history.
    """

    name = "Jerripedia"
    base_url = "https://www.jerripedia.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Jerripedia wiki.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        import httpx

        records = []

        # Build search query
        search_terms = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        if not search_terms:
            return []

        search_query = " ".join(search_terms)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # MediaWiki search API
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": search_query,
                    "format": "json",
                    "srlimit": 50,
                }

                url = f"{self.base_url}/w/api.php"
                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                records = self._parse_search_results(data)

        except Exception as e:
            logger.warning("Jerripedia search error: %s", e)

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific wiki article.

        Args:
            record_id: Wiki page title or URL

        Returns:
            The record or None
        """
        import httpx

        # Handle both titles and full URLs
        page_title = record_id.split("/wiki/")[-1] if record_id.startswith("http") else record_id

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get page content via API
                params = {
                    "action": "query",
                    "titles": page_title,
                    "prop": "extracts|revisions",
                    "explaintext": "1",
                    "format": "json",
                }

                url = f"{self.base_url}/w/api.php"
                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                return self._parse_page(data, page_title)

        except Exception as e:
            logger.warning("Jerripedia get_record error: %s", e)
            return None

    def _parse_search_results(self, data: dict) -> list[RawRecord]:
        """Parse MediaWiki search results.

        Args:
            data: API response

        Returns:
            List of RawRecord objects
        """
        records = []
        results = data.get("query", {}).get("search", [])

        for result in results:
            title = result.get("title", "")
            snippet = result.get("snippet", "")

            # Clean HTML from snippet
            soup = BeautifulSoup(snippet, "html.parser")
            clean_snippet = soup.get_text()

            record = RawRecord(
                source=self.name,
                record_id=title,
                record_type="wiki_article",
                url=f"{self.base_url}/wiki/{title.replace(' ', '_')}",
                raw_data=result,
                extracted_fields={
                    "title": title,
                    "snippet": clean_snippet,
                    "word_count": str(result.get("wordcount", 0)),
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_page(self, data: dict, page_title: str) -> RawRecord | None:
        """Parse wiki page content.

        Args:
            data: API response
            page_title: Page title

        Returns:
            RawRecord or None
        """
        pages = data.get("query", {}).get("pages", {})

        for page_id, page_data in pages.items():
            if page_id == "-1":  # Page doesn't exist
                return None

            title = page_data.get("title", page_title)
            extract = page_data.get("extract", "")

            # Try to extract biographical info
            extracted = {
                "title": title,
                "content_preview": extract[:1000] if extract else "",
            }

            # Look for date patterns
            import re

            date_patterns = re.findall(r"\b\d{4}\b", extract[:2000])
            if date_patterns:
                extracted["years_mentioned"] = ",".join(date_patterns[:5])

            return RawRecord(
                source=self.name,
                record_id=title,
                record_type="wiki_article",
                url=f"{self.base_url}/wiki/{title.replace(' ', '_')}",
                raw_data=page_data,
                extracted_fields=extracted,
                accessed_at=datetime.now(UTC),
            )

        return None
