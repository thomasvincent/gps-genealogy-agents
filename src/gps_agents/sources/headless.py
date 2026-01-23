"""Headless browser utilities for automated genealogy searches.

Provides Playwright-based automation for genealogy websites that require
JavaScript rendering or form interaction. Used by source adapters to
fetch and parse search results programmatically.

Usage:
    async with HeadlessBrowser() as browser:
        results = await browser.search_find_a_grave("Durham", "California")
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result from a headless browser search."""
    title: str
    url: str
    snippet: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class HeadlessConfig:
    """Configuration for headless browser sessions."""
    headless: bool = True
    timeout_ms: int = 30000
    slow_mo: int = 0  # Milliseconds to slow down operations (useful for debugging)
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str = "Mozilla/5.0 (compatible; GenealogyResearchBot/1.0)"


class HeadlessBrowser:
    """Headless browser wrapper using Playwright for genealogy searches.

    Example:
        async with HeadlessBrowser() as browser:
            results = await browser.search_chronicling_america("Durham", state="California")
    """

    def __init__(self, config: HeadlessConfig | None = None) -> None:
        self.config = config or HeadlessConfig()
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
            )
            self._context = await self._browser.new_context(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                user_agent=self.config.user_agent,
            )
        except ImportError:
            logger.warning("Playwright not installed. Run: uv add playwright && playwright install")
            raise
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        return False

    async def _new_page(self):
        """Create a new browser page."""
        if not self._context:
            raise RuntimeError("Browser not initialized. Use 'async with HeadlessBrowser()' context.")
        return await self._context.new_page()

    async def search_chronicling_america(
        self,
        query: str,
        state: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search Chronicling America historic newspapers.

        Args:
            query: Search terms (e.g., surname)
            state: State name to filter (e.g., "California")
            date_from: Start date (YYYY or YYYY-MM-DD)
            date_to: End date (YYYY or YYYY-MM-DD)
            limit: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        page = await self._new_page()
        results: list[SearchResult] = []

        try:
            # Build URL with parameters
            params = [f"proxtext={quote_plus(query)}"]
            if state:
                params.append(f"state={quote_plus(state)}")
            if date_from:
                params.append(f"date1={date_from}")
            if date_to:
                params.append(f"date2={date_to}")
            params.append(f"rows={limit}")

            url = f"https://chroniclingamerica.loc.gov/search/pages/results/?{'&'.join(params)}"
            await page.goto(url, timeout=self.config.timeout_ms)

            # Wait for results to load
            await page.wait_for_selector(".result", timeout=10000)

            # Extract results
            result_elements = await page.query_selector_all(".result")

            for elem in result_elements[:limit]:
                try:
                    title_elem = await elem.query_selector("a")
                    title = await title_elem.inner_text() if title_elem else ""
                    link = await title_elem.get_attribute("href") if title_elem else ""

                    snippet_elem = await elem.query_selector(".highlight")
                    snippet = await snippet_elem.inner_text() if snippet_elem else ""

                    # Extract metadata
                    date_elem = await elem.query_selector(".date")
                    pub_date = await date_elem.inner_text() if date_elem else ""

                    results.append(SearchResult(
                        title=title.strip(),
                        url=f"https://chroniclingamerica.loc.gov{link}" if link else "",
                        snippet=snippet.strip(),
                        metadata={"publication_date": pub_date},
                        source="ChroniclingAmerica",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing result: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Chronicling America search failed: {e}")
        finally:
            await page.close()

        return results

    async def search_find_a_grave(
        self,
        surname: str,
        given_name: str | None = None,
        location: str | None = None,
        birth_year: int | None = None,
        death_year: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search Find A Grave for burial records.

        Args:
            surname: Last name to search
            given_name: First name (optional)
            location: City, state, or country (optional)
            birth_year: Approximate birth year (optional)
            death_year: Approximate death year (optional)
            limit: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        page = await self._new_page()
        results: list[SearchResult] = []

        try:
            # Navigate to Find A Grave search
            url = "https://www.findagrave.com/memorial/search"
            await page.goto(url, timeout=self.config.timeout_ms)

            # Fill in search form
            await page.fill("#firstname", given_name or "")
            await page.fill("#lastname", surname)

            if location:
                await page.fill("#location", location)

            if birth_year:
                await page.fill("#birthYear", str(birth_year))

            if death_year:
                await page.fill("#deathYear", str(death_year))

            # Submit search
            await page.click('button[type="submit"]')

            # Wait for results
            await page.wait_for_selector(".memorial-item", timeout=15000)

            # Extract results
            result_elements = await page.query_selector_all(".memorial-item")

            for elem in result_elements[:limit]:
                try:
                    name_elem = await elem.query_selector(".name-grave a")
                    name = await name_elem.inner_text() if name_elem else ""
                    link = await name_elem.get_attribute("href") if name_elem else ""

                    dates_elem = await elem.query_selector(".dates")
                    dates = await dates_elem.inner_text() if dates_elem else ""

                    cemetery_elem = await elem.query_selector(".cemetery")
                    cemetery = await cemetery_elem.inner_text() if cemetery_elem else ""

                    results.append(SearchResult(
                        title=name.strip(),
                        url=f"https://www.findagrave.com{link}" if link and not link.startswith("http") else link or "",
                        snippet=f"{dates} - {cemetery}".strip(" -"),
                        metadata={
                            "dates": dates,
                            "cemetery": cemetery,
                        },
                        source="FindAGrave",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing result: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Find A Grave search failed: {e}")
        finally:
            await page.close()

        return results

    async def search_familysearch(
        self,
        surname: str,
        given_name: str | None = None,
        birth_place: str | None = None,
        birth_year: int | None = None,
        collection_id: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search FamilySearch historical records (no login required).

        Args:
            surname: Last name to search
            given_name: First name (optional)
            birth_place: Birth location (optional)
            birth_year: Approximate birth year (optional)
            collection_id: Specific collection ID (optional)
            limit: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        page = await self._new_page()
        results: list[SearchResult] = []

        try:
            # Build URL with parameters
            params = [f"q.surname={quote_plus(surname)}"]
            if given_name:
                params.append(f"q.givenName={quote_plus(given_name)}")
            if birth_place:
                params.append(f"q.birthLikePlace={quote_plus(birth_place)}")
            if birth_year:
                params.append(f"q.birthLikeDate.from={birth_year - 2}")
                params.append(f"q.birthLikeDate.to={birth_year + 2}")
            if collection_id:
                params.append(f"f.collectionId={collection_id}")
            params.append(f"count={limit}")

            url = f"https://www.familysearch.org/search/record/results?{'&'.join(params)}"
            await page.goto(url, timeout=self.config.timeout_ms)

            # Wait for results (FamilySearch uses React, so we wait for the result container)
            await page.wait_for_selector('[data-testid="searchResults"]', timeout=15000)

            # Extract results
            result_elements = await page.query_selector_all('[data-testid="record-row"]')

            for elem in result_elements[:limit]:
                try:
                    name_elem = await elem.query_selector("a")
                    name = await name_elem.inner_text() if name_elem else ""
                    link = await name_elem.get_attribute("href") if name_elem else ""

                    # Get other details
                    details_elem = await elem.query_selector(".fs-data-labels")
                    details = await details_elem.inner_text() if details_elem else ""

                    results.append(SearchResult(
                        title=name.strip(),
                        url=f"https://www.familysearch.org{link}" if link and link.startswith("/") else link or "",
                        snippet=details.strip(),
                        metadata={},
                        source="FamilySearch",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing result: {e}")
                    continue

        except Exception as e:
            logger.warning(f"FamilySearch search failed: {e}")
        finally:
            await page.close()

        return results

    async def search_calisphere(
        self,
        query: str,
        institution: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search Calisphere for California digital collections.

        Args:
            query: Search terms
            institution: Filter by institution name (optional)
            limit: Maximum results to return

        Returns:
            List of SearchResult objects
        """
        page = await self._new_page()
        results: list[SearchResult] = []

        try:
            # Build URL
            url = f"https://calisphere.org/search/?q={quote_plus(query)}"
            if institution:
                url += f"&repository_name={quote_plus(institution)}"

            await page.goto(url, timeout=self.config.timeout_ms)

            # Wait for results
            await page.wait_for_selector(".thumbnail-container", timeout=15000)

            # Extract results
            result_elements = await page.query_selector_all(".thumbnail-container")

            for elem in result_elements[:limit]:
                try:
                    link_elem = await elem.query_selector("a")
                    link = await link_elem.get_attribute("href") if link_elem else ""

                    title_elem = await elem.query_selector(".item-title")
                    title = await title_elem.inner_text() if title_elem else ""

                    institution_elem = await elem.query_selector(".institution")
                    inst = await institution_elem.inner_text() if institution_elem else ""

                    results.append(SearchResult(
                        title=title.strip(),
                        url=f"https://calisphere.org{link}" if link and link.startswith("/") else link or "",
                        snippet=inst.strip(),
                        metadata={"institution": inst},
                        source="Calisphere",
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing result: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Calisphere search failed: {e}")
        finally:
            await page.close()

        return results

    async def search_pasadena_news_index(
        self,
        surname: str,
        record_type: str = "obituary",
    ) -> list[SearchResult]:
        """Search Pasadena Public Library News Index.

        Args:
            surname: Last name to search
            record_type: Type of record (obituary, birth, marriage, etc.)

        Returns:
            List of SearchResult objects
        """
        page = await self._new_page()
        results: list[SearchResult] = []

        try:
            # Navigate to Pasadena News Index
            url = "https://ww2.cityofpasadena.net/library/newsindex/"
            await page.goto(url, timeout=self.config.timeout_ms)

            # Wait for search form
            await page.wait_for_selector("#surname", timeout=10000)

            # Fill search form
            await page.fill("#surname", surname)

            # Select record type if available
            try:
                await page.select_option("#record_type", record_type)
            except Exception:
                pass  # Record type selector may not exist

            # Submit search
            await page.click('input[type="submit"]')

            # Wait for results
            await page.wait_for_selector("table", timeout=15000)

            # Extract results from table
            rows = await page.query_selector_all("table tr")

            for row in rows[1:]:  # Skip header row
                try:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 4:
                        name = await cells[0].inner_text()
                        date = await cells[1].inner_text()
                        source = await cells[2].inner_text()
                        page_ref = await cells[3].inner_text()

                        results.append(SearchResult(
                            title=name.strip(),
                            url=url,  # No direct links available
                            snippet=f"{date} - {source}, {page_ref}".strip(),
                            metadata={
                                "date": date.strip(),
                                "newspaper": source.strip(),
                                "page_reference": page_ref.strip(),
                                "record_type": record_type,
                            },
                            source="PasadenaNewsIndex",
                        ))
                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Pasadena News Index search failed: {e}")
        finally:
            await page.close()

        return results


async def run_headless_search(
    source_name: str,
    surname: str,
    given_name: str | None = None,
    location: str | None = None,
    **kwargs,
) -> list[SearchResult]:
    """Convenience function to run a headless search.

    Args:
        source_name: Name of source to search (chronicling_america, find_a_grave, etc.)
        surname: Last name to search
        given_name: First name (optional)
        location: Location filter (optional)
        **kwargs: Additional source-specific parameters

    Returns:
        List of SearchResult objects
    """
    async with HeadlessBrowser() as browser:
        source_map = {
            "chronicling_america": lambda: browser.search_chronicling_america(
                f"{given_name or ''} {surname}".strip(),
                state=location,
                **kwargs,
            ),
            "find_a_grave": lambda: browser.search_find_a_grave(
                surname,
                given_name=given_name,
                location=location,
                **kwargs,
            ),
            "familysearch": lambda: browser.search_familysearch(
                surname,
                given_name=given_name,
                birth_place=location,
                **kwargs,
            ),
            "calisphere": lambda: browser.search_calisphere(
                f"{given_name or ''} {surname}".strip(),
                **kwargs,
            ),
            "pasadena_news_index": lambda: browser.search_pasadena_news_index(
                surname,
                **kwargs,
            ),
        }

        if source_name.lower() not in source_map:
            raise ValueError(f"Unknown source: {source_name}. Available: {list(source_map.keys())}")

        return await source_map[source_name.lower()]()


# Synchronous wrapper for convenience
def search_sync(
    source_name: str,
    surname: str,
    given_name: str | None = None,
    location: str | None = None,
    **kwargs,
) -> list[SearchResult]:
    """Synchronous wrapper for headless search.

    Example:
        results = search_sync("find_a_grave", "Durham", given_name="Ruby", location="California")
    """
    return asyncio.run(run_headless_search(source_name, surname, given_name, location, **kwargs))
