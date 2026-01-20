"""Wikimedia Commons duplicate checker and search."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CommonsFile:
    """A file found on Wikimedia Commons."""

    title: str  # File:Example.jpg
    url: str  # Commons page URL
    image_url: str | None  # Direct image URL
    description: str | None  # File description


class CommonsDuplicateChecker:
    """Check Wikimedia Commons for existing files to avoid re-uploading."""

    API_URL = "https://commons.wikimedia.org/w/api.php"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    # Wikimedia requires proper User-Agent with contact info
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (https://github.com/thomasvincent/gps-genealogy-agents; genealogy research)",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_by_name(
        self, subject_name: str, limit: int = 20
    ) -> list[CommonsFile]:
        """Search Commons for files related to a subject.

        Args:
            subject_name: Name of the person to search for
            limit: Maximum results to return

        Returns:
            List of existing Commons files
        """
        client = await self._get_client()
        results: list[CommonsFile] = []

        # Search in File namespace (ns=6)
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": subject_name,
            "srnamespace": "6",  # File namespace
            "srlimit": str(limit),
            "srprop": "snippet|titlesnippet",
        }

        try:
            resp = await client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                snippet = item.get("snippet", "")

                results.append(
                    CommonsFile(
                        title=title,
                        url=f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                        image_url=None,  # Would need another API call
                        description=snippet,
                    )
                )

        except httpx.HTTPError as e:
            logger.warning(f"Commons search failed: {e}")
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse Commons response: {e}")

        return results

    async def search_by_source_url(self, source_url: str) -> list[CommonsFile]:
        """Search Commons for files that cite a specific source URL.

        This helps find if the same photo was already uploaded from
        the same source.

        Args:
            source_url: Original source URL to search for

        Returns:
            List of Commons files citing this source
        """
        client = await self._get_client()
        results: list[CommonsFile] = []

        # Search file descriptions for the URL
        # Use insource: to search within file page content
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f'insource:"{source_url}"',
            "srnamespace": "6",
            "srlimit": "10",
        }

        try:
            resp = await client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                results.append(
                    CommonsFile(
                        title=title,
                        url=f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                        image_url=None,
                        description=None,
                    )
                )

        except httpx.HTTPError as e:
            logger.warning(f"Commons source URL search failed: {e}")

        return results

    async def check_duplicates(
        self,
        subject_name: str,
        source_urls: list[str] | None = None,
    ) -> tuple[list[CommonsFile], list[str]]:
        """Check for existing Commons files to avoid duplicates.

        Args:
            subject_name: Name of the subject
            source_urls: Optional list of source URLs to check

        Returns:
            Tuple of (existing_files, source_urls_already_on_commons)
        """
        existing_files: list[CommonsFile] = []
        urls_on_commons: list[str] = []

        # Search by name
        name_results = await self.search_by_name(subject_name)
        existing_files.extend(name_results)

        # Search by source URLs
        if source_urls:
            for url in source_urls:
                url_results = await self.search_by_source_url(url)
                if url_results:
                    urls_on_commons.append(url)
                    existing_files.extend(url_results)

        # Deduplicate by title
        seen_titles = set()
        unique_files = []
        for f in existing_files:
            if f.title not in seen_titles:
                seen_titles.add(f.title)
                unique_files.append(f)

        return unique_files, urls_on_commons

    async def get_categories_for_subject(
        self, subject_name: str
    ) -> list[str]:
        """Get suggested categories based on existing Commons files.

        Looks at what categories similar files use.

        Args:
            subject_name: Name of the subject

        Returns:
            List of suggested category names
        """
        client = await self._get_client()
        categories: list[str] = []

        # Get existing files
        existing = await self.search_by_name(subject_name, limit=5)
        if not existing:
            return []

        # Get categories from first few files
        for file in existing[:3]:
            params = {
                "action": "query",
                "format": "json",
                "titles": file.title,
                "prop": "categories",
                "cllimit": "20",
            }

            try:
                resp = await client.get(self.API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    for cat in page.get("categories", []):
                        cat_title = cat.get("title", "")
                        # Remove "Category:" prefix
                        if cat_title.startswith("Category:"):
                            cat_title = cat_title[9:]
                        if cat_title and cat_title not in categories:
                            categories.append(cat_title)

            except (httpx.HTTPError, KeyError, ValueError):
                continue

        return categories

    async def __aenter__(self) -> "CommonsDuplicateChecker":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
