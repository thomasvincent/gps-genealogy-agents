"""Base class for HTML-based genealogy sources."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord
from .base import BaseSource

logger = logging.getLogger(__name__)


class BaseHTMLSourceAdapter(BaseSource):
    """Base adapter for sources requiring HTML parsing.

    Provides common functionality for HTML-based genealogy sources including:
    - Text extraction with CSS selectors
    - Date parsing and normalization
    - HTTP request handling with retry logic
    - Error handling patterns
    """

    def extract_text(self, soup: BeautifulSoup, selector: str, default: str = "") -> str:
        """Extract text from CSS selector with error handling.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string
            default: Default value if extraction fails

        Returns:
            Extracted text or default value
        """
        try:
            element = soup.select_one(selector)
            return element.get_text(strip=True) if element else default
        except Exception as e:
            logger.debug(f"Failed to extract {selector}: {e}")
            return default

    def extract_date(self, soup: BeautifulSoup, selector: str) -> str | None:
        """Extract and normalize date from selector.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string

        Returns:
            Normalized date string or None if not found
        """
        date_text = self.extract_text(soup, selector)
        if not date_text:
            return None

        # Common date patterns
        patterns = [
            r"\d{4}-\d{2}-\d{2}",  # ISO format
            r"\d{1,2}/\d{1,2}/\d{4}",  # US format
            r"\w+ \d{1,2}, \d{4}",  # Month DD, YYYY
        ]

        for pattern in patterns:
            match = re.search(pattern, date_text)
            if match:
                return match.group(0)

        return date_text

    async def fetch_with_retry(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> httpx.Response | None:
        """Fetch URL with automatic retry on transient errors.

        Args:
            url: URL to fetch
            params: Optional query parameters
            max_retries: Maximum number of retry attempts

        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=30.0,
                    follow_redirects=True,
                    headers={"User-Agent": f"{self.name}/1.0 (Genealogy Research)"},
                ) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    return resp

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_retries} after server error")
                    await asyncio.sleep(2**attempt)  # Exponential backoff
                    continue
                raise

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_retries} after timeout")
                    await asyncio.sleep(2**attempt)
                    continue
                raise

        return None

    async def search_with_error_handling(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        parse_func: callable | None = None,
    ) -> list[RawRecord]:
        """Search with comprehensive error handling.

        Args:
            url: Search URL
            params: Query parameters
            parse_func: Function to parse HTML results (soup, query) -> list[RawRecord]

        Returns:
            List of raw records (empty list on error)
        """
        records: list[RawRecord] = []

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": f"{self.name}/1.0 (Genealogy Research)"},
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")

                if parse_func:
                    records = parse_func(soup)

        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                logger.error(f"{self.name} server error {e.response.status_code}: {e}")
                # Re-raise for retry logic
                raise
            if e.response.status_code == 429:
                logger.warning(f"{self.name} rate limit exceeded")
                # Could implement exponential backoff here
            else:
                logger.error(f"{self.name} HTTP error {e.response.status_code}: {e}")

        except httpx.TimeoutException:
            logger.warning(f"{self.name} request timeout after 30s")

        except httpx.RequestError as e:
            logger.error(f"{self.name} request failed: {e}")

        except Exception as e:
            logger.exception(f"{self.name} unexpected error: {e}")

        return records
