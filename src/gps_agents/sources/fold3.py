"""Fold3 web scraper for military and historical records.

Fold3 (owned by Ancestry) provides military records, historical documents,
and other primary sources. Supports both free preview and subscription access.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class Fold3Source(BaseSource):
    """Fold3.com data source.

    Military records and historical documents. Works with:
    - Free preview access (limited)
    - Subscription access via credentials or API key

    Environment variables:
    - FOLD3_USERNAME: Account email for full access
    - FOLD3_PASSWORD: Account password
    - FOLD3_API_KEY: Alternative API authentication
    """

    name = "Fold3"
    base_url = "https://www.fold3.com"

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Fold3 source.

        Args:
            api_key: Optional API key (or set FOLD3_API_KEY env var)
        """
        super().__init__(api_key)
        self.username = os.getenv("FOLD3_USERNAME")
        self.password = os.getenv("FOLD3_PASSWORD")
        self._session_cookie: str | None = None
        self._use_playwright = False

    def requires_auth(self) -> bool:
        # Works without auth, but limited
        return False

    def is_configured(self) -> bool:
        """Check if full access is configured."""
        return bool(self.api_key or (self.username and self.password))

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Fold3 for military and historical records.

        Args:
            query: Search parameters. Primarily uses name fields.
                Supported record_types: military, pension, draft, naturalization

        Returns:
            List of matching records
        """
        records: list[RawRecord] = []

        # Build search parameters
        params: dict[str, str] = {}
        if query.surname:
            params["lastName"] = query.surname
        if query.given_name:
            params["firstName"] = query.given_name

        # Add date range if available
        birth_year = getattr(query, "birth_year", None)
        if birth_year:
            params["birthYear"] = str(birth_year)
            params["birthYearRange"] = "5"  # +/- 5 years

        if not params:
            return []

        # Try httpx first
        try:
            records = await self._search_httpx(params)
        except Exception as e:
            logger.debug("Fold3 httpx search failed: %s", e)

        # If no results and JS might be needed, try Playwright
        if not records and self._should_try_playwright():
            try:
                records = await self._search_playwright(params)
            except Exception as e:
                logger.warning("Fold3 Playwright search failed: %s", e)

        return records

    async def _search_httpx(self, params: dict[str, str]) -> list[RawRecord]:
        """Search using httpx (simple HTTP).

        Args:
            params: Search parameters

        Returns:
            List of records found
        """
        import httpx

        records: list[RawRecord] = []

        # Build search URL
        search_params = "&".join(f"{k}={v}" for k, v in params.items())
        search_url = f"{self.base_url}/search?{search_params}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # Add auth if available
        if self._session_cookie:
            headers["Cookie"] = self._session_cookie
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            # Authenticate if credentials available and no session
            if self.username and self.password and not self._session_cookie:
                await self._authenticate(client)

            response = await client.get(search_url, headers=headers)

            if response.status_code != 200:
                logger.debug("Fold3 search returned %d", response.status_code)
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            # Check if we got a JS-heavy page
            if self._is_js_required(soup):
                self._use_playwright = True
                return []

            records = self._parse_search_results(soup)

        return records

    async def _authenticate(self, client) -> bool:
        """Authenticate with Fold3.

        Args:
            client: httpx AsyncClient

        Returns:
            True if successful
        """
        if not self.username or not self.password:
            return False

        try:
            # Get login page for CSRF token
            login_page = await client.get(f"{self.base_url}/login")
            soup = BeautifulSoup(login_page.text, "html.parser")

            # Find CSRF token
            csrf_input = soup.find("input", {"name": "_token"}) or soup.find(
                "input", {"name": "csrf_token"}
            )
            csrf_token = csrf_input.get("value", "") if csrf_input else ""

            # Submit login
            login_data = {
                "email": self.username,
                "password": self.password,
                "_token": csrf_token,
            }

            response = await client.post(
                f"{self.base_url}/login",
                data=login_data,
                follow_redirects=True,
            )

            # Check for session cookie
            if "session" in response.cookies or "fold3_session" in response.cookies:
                self._session_cookie = "; ".join(
                    f"{k}={v}" for k, v in response.cookies.items()
                )
                logger.info("Fold3 authentication successful")
                return True

        except Exception as e:
            logger.warning("Fold3 authentication failed: %s", e)

        return False

    async def _search_playwright(self, params: dict[str, str]) -> list[RawRecord]:
        """Search using Playwright for JS-rendered content.

        Args:
            params: Search parameters

        Returns:
            List of records found
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not available for Fold3 JS fallback")
            return []

        records: list[RawRecord] = []
        search_params = "&".join(f"{k}={v}" for k, v in params.items())
        search_url = f"{self.base_url}/search?{search_params}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(search_url, wait_until="networkidle", timeout=30000)

                # Wait for results to load
                await page.wait_for_selector(".search-result, .record-item, [data-record]", timeout=10000)

                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")
                records = self._parse_search_results(soup)

            except Exception as e:
                logger.debug("Fold3 Playwright error: %s", e)
            finally:
                await browser.close()

        return records

    def _should_try_playwright(self) -> bool:
        """Check if we should try Playwright fallback."""
        return self._use_playwright

    def _is_js_required(self, soup: BeautifulSoup) -> bool:
        """Check if page requires JavaScript to render.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            True if JS is required
        """
        # Look for signs of JS-required content
        body = soup.find("body")
        if not body:
            return True

        body_text = body.get_text(strip=True)

        # Very little content suggests JS rendering
        if len(body_text) < 500:
            return True

        # Check for common JS app indicators
        if soup.find("div", {"id": "app"}) or soup.find("div", {"id": "root"}):
            # If there's no actual content in these divs, JS is needed
            app_div = soup.find("div", {"id": "app"}) or soup.find("div", {"id": "root"})
            if app_div and len(app_div.get_text(strip=True)) < 100:
                return True

        return False

    def _parse_search_results(self, soup: BeautifulSoup) -> list[RawRecord]:
        """Parse Fold3 search results page.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            List of records found
        """
        records: list[RawRecord] = []

        # Try multiple selectors for results (site structure varies)
        result_selectors = [
            "div.search-result",
            "div.record-item",
            "article.result",
            "[data-record-id]",
            "li.result-item",
            "div.hit",
        ]

        results = []
        for selector in result_selectors:
            results = soup.select(selector)
            if results:
                break

        # Fallback: look for links with record-like URLs
        if not results:
            results = soup.find_all("a", href=lambda h: h and "/record/" in h)

        for result in results[:50]:
            record = self._parse_result_item(result)
            if record:
                records.append(record)

        return records

    def _parse_result_item(self, item) -> RawRecord | None:
        """Parse a single search result item.

        Args:
            item: BeautifulSoup element

        Returns:
            RawRecord or None
        """
        # Get title/name
        title_elem = item.find(["h2", "h3", "h4", "a", "span"], class_=lambda c: c and "title" in c.lower() if c else False)
        if not title_elem:
            title_elem = item.find(["h2", "h3", "h4"]) or item.find("a")

        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        # Get URL
        link = item.find("a", href=True)
        url = ""
        if link:
            href = link.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Get record ID from URL or data attribute
        record_id = item.get("data-record-id", "") or url

        # Extract metadata
        metadata: dict[str, str] = {}

        # Look for date
        date_elem = item.find(class_=lambda c: c and "date" in c.lower() if c else False)
        if date_elem:
            metadata["date"] = date_elem.get_text(strip=True)

        # Look for collection/category
        collection_elem = item.find(class_=lambda c: c and ("collection" in c.lower() or "category" in c.lower()) if c else False)
        if collection_elem:
            metadata["collection"] = collection_elem.get_text(strip=True)

        # Look for location
        location_elem = item.find(class_=lambda c: c and "location" in c.lower() if c else False)
        if location_elem:
            metadata["location"] = location_elem.get_text(strip=True)

        # Classify record type
        record_type = self._classify_record_type(title, url)

        return RawRecord(
            source=self.name,
            record_id=record_id,
            record_type=record_type,
            url=url,
            raw_data={"title": title, **metadata},
            extracted_fields={
                "title": title,
                "name": self._extract_name(title),
                **metadata,
            },
            accessed_at=datetime.now(UTC),
        )

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by ID or URL.

        Args:
            record_id: Record ID or URL

        Returns:
            The record or None
        """
        import httpx

        url = record_id if record_id.startswith("http") else f"{self.base_url}/record/{record_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        if self._session_cookie:
            headers["Cookie"] = self._session_cookie

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_record_page(soup, url)

        except Exception as e:
            logger.warning("Fold3 get_record error: %s", e)
            return None

    def _parse_record_page(self, soup: BeautifulSoup, url: str) -> RawRecord | None:
        """Parse a full record page.

        Args:
            soup: BeautifulSoup parsed page
            url: Record URL

        Returns:
            RawRecord or None
        """
        # Get title
        title_elem = soup.find("h1") or soup.find("title")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Record"

        # Get record content
        content_elem = soup.find("div", class_=lambda c: c and "record" in c.lower() if c else False)
        if not content_elem:
            content_elem = soup.find("main") or soup.find("article")

        content = content_elem.get_text(strip=True)[:4000] if content_elem else ""

        # Extract fields from structured data or tables
        extracted: dict[str, str] = {"title": title}

        # Look for field/value pairs
        for row in soup.find_all(["tr", "div"], class_=lambda c: c and "field" in c.lower() if c else False):
            label = row.find(class_=lambda c: c and "label" in c.lower() if c else False)
            value = row.find(class_=lambda c: c and "value" in c.lower() if c else False)
            if label and value:
                extracted[label.get_text(strip=True).lower()] = value.get_text(strip=True)

        record_type = self._classify_record_type(title.lower(), url.lower())

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=record_type,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )

    def _classify_record_type(self, text: str, url: str) -> str:
        """Classify record type based on text/URL.

        Args:
            text: Text content (lowercase)
            url: URL (lowercase)

        Returns:
            Record type
        """
        combined = f"{text} {url}".lower()

        if any(kw in combined for kw in ["draft", "selective service", "registration"]):
            return "draft"
        if any(kw in combined for kw in ["pension", "widow", "bounty"]):
            return "pension"
        if any(kw in combined for kw in ["naturaliz", "citizenship", "declaration"]):
            return "naturalization"
        if any(kw in combined for kw in [
            "military", "soldier", "veteran", "army", "navy", "marine",
            "war", "enlist", "muster", "service record", "discharge"
        ]):
            return "military"
        if any(kw in combined for kw in ["census"]):
            return "census"
        if any(kw in combined for kw in ["city director", "directory"]):
            return "directory"

        return "military"  # Default for Fold3

    def _extract_name(self, title: str) -> str:
        """Extract person name from title.

        Args:
            title: Record title

        Returns:
            Extracted name
        """
        # Common patterns: "John Smith - Draft Registration"
        if " - " in title:
            return title.split(" - ")[0].strip()
        if " | " in title:
            return title.split(" | ")[0].strip()

        # If title looks like a name (2-4 words, starts with capital)
        words = title.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
            return title

        return title
