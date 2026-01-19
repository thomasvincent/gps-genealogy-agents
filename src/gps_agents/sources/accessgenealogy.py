"""AccessGenealogy web scraper for Native American records."""
from __future__ import annotations

from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class AccessGenealogySource(BaseSource):
    """AccessGenealogy.com data source.

    Free resource focused on Native American genealogy, including
    Dawes Rolls, Cherokee, and other tribal records.
    """

    name = "AccessGenealogy"
    base_url = "https://www.accessgenealogy.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search AccessGenealogy for Native American records.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        import httpx

        records = []

        # Build search URL - AccessGenealogy uses simple search
        search_terms = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        if not search_terms:
            return []

        search_query = "+".join(search_terms)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Search the site
                url = f"{self.base_url}/?s={search_query}"
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                records.extend(self._parse_search_page(soup))

                # Also search specific Native American databases
                native_urls = [
                    f"{self.base_url}/native/dawes-rolls/?s={search_query}",
                    f"{self.base_url}/native/cherokee/?s={search_query}",
                ]

                for native_url in native_urls:
                    try:
                        response = await client.get(native_url)
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, "html.parser")
                            records.extend(self._parse_search_page(soup))
                    except Exception:
                        continue

        except Exception as e:
            print(f"AccessGenealogy search error: {e}")

        return records

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
            print(f"AccessGenealogy get_record error: {e}")
            return None

    def _parse_search_page(self, soup: BeautifulSoup) -> list[RawRecord]:
        """Parse search results page.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            List of records found
        """
        records = []

        # Find article entries (typical WordPress structure)
        articles = soup.find_all("article") or soup.find_all("div", class_="post")

        for article in articles[:20]:  # Limit results
            title_elem = article.find("h2") or article.find("h3")
            link_elem = article.find("a")

            if not title_elem or not link_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = link_elem.get("href", "")

            # Extract snippet/summary
            excerpt = article.find("div", class_="entry-content") or article.find("p")
            summary = excerpt.get_text(strip=True)[:500] if excerpt else ""

            record = RawRecord(
                source=self.name,
                record_id=url,
                record_type="article",
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
        content = content_elem.get_text(strip=True)[:2000] if content_elem else ""

        # Try to extract structured data (names, dates, etc.)
        extracted = {"title": title, "content_preview": content[:500]}

        # Look for table data (common in rolls/census lists)
        tables = soup.find_all("table")
        if tables:
            extracted["has_tabular_data"] = "true"
            extracted["table_count"] = str(len(tables))

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type="article",
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )
