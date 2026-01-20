"""RootsWeb web scraper for community genealogy resources.

RootsWeb (funded by Ancestry) provides free genealogy resources including:
- Message boards with surname/location discussions
- Mailing list archives
- Obituary Daily Times database
- User-contributed websites
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class RootsWebSource(BaseSource):
    """RootsWeb.com data source.

    Free community genealogy resource with:
    - Message boards (surname and location-based discussions)
    - Mailing list archives
    - Obituary Daily Times
    - WorldConnect family trees
    """

    name = "RootsWeb"
    base_url = "https://www.rootsweb.com"
    boards_url = "https://boards.rootsweb.com"
    lists_url = "https://lists.rootsweb.com"
    obituary_url = "https://sites.rootsweb.com/~obituary"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search RootsWeb for genealogy discussions and obituaries.

        Args:
            query: Search parameters. Uses surname primarily.
                Record types: message, obituary, mailing_list

        Returns:
            List of matching records
        """
        import httpx

        records: list[RawRecord] = []

        # Need at least a surname for meaningful search
        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                # 1. Search message boards
                board_records = await self._search_boards(client, surname, given_name)
                records.extend(board_records)

                # 2. Search mailing list archives
                list_records = await self._search_mailing_lists(client, surname)
                records.extend(list_records)

                # 3. Search Obituary Daily Times
                obit_records = await self._search_obituaries(client, surname, given_name)
                records.extend(obit_records)

        except Exception as e:
            logger.warning("RootsWeb search error: %s", e)

        return records

    async def _search_boards(
        self, client, surname: str, given_name: str
    ) -> list[RawRecord]:
        """Search RootsWeb message boards.

        Args:
            client: httpx AsyncClient
            surname: Surname to search
            given_name: Optional given name

        Returns:
            List of message records
        """
        records: list[RawRecord] = []

        # Search by surname board
        surname_lower = surname.lower()
        surname_first = surname_lower[0] if surname_lower else "a"

        urls = [
            # Surname-specific board
            f"{self.boards_url}/surnames.{surname_first}/{surname_lower}/mb.ashx",
            # General search
            f"{self.boards_url}/search?q={quote_plus(surname)}",
        ]

        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                page_records = self._parse_board_page(soup, url, surname, given_name)
                records.extend(page_records)

            except Exception as e:
                logger.debug("RootsWeb boards error for %s: %s", url, e)
                continue

        return records

    async def _search_mailing_lists(self, client, surname: str) -> list[RawRecord]:
        """Search RootsWeb mailing list archives.

        Args:
            client: httpx AsyncClient
            surname: Surname to search

        Returns:
            List of mailing list records
        """
        records: list[RawRecord] = []

        # Mailing lists are organized by surname
        surname_upper = surname.upper()
        surname_first = surname_upper[0] if surname_upper else "A"

        urls = [
            # Surname mailing list archives
            f"{self.lists_url}/surnames/{surname_first}/{surname_upper}/",
            # Search archives
            f"{self.lists_url}/search?list={surname_upper}&q={quote_plus(surname)}",
        ]

        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                page_records = self._parse_mailing_list_page(soup, url, surname)
                records.extend(page_records)

            except Exception as e:
                logger.debug("RootsWeb mailing list error for %s: %s", url, e)
                continue

        return records

    async def _search_obituaries(
        self, client, surname: str, given_name: str
    ) -> list[RawRecord]:
        """Search Obituary Daily Times.

        Args:
            client: httpx AsyncClient
            surname: Surname to search
            given_name: Optional given name

        Returns:
            List of obituary records
        """
        records: list[RawRecord] = []

        # Build search query
        search_term = f"{given_name} {surname}".strip() if given_name else surname

        # Obituary Daily Times search
        url = f"{self.obituary_url}/search.html?q={quote_plus(search_term)}"

        try:
            response = await client.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                page_records = self._parse_obituary_page(soup, url, surname, given_name)
                records.extend(page_records)

        except Exception as e:
            logger.debug("RootsWeb obituary error: %s", e)

        return records

    def _parse_board_page(
        self, soup: BeautifulSoup, base_url: str, surname: str, given_name: str
    ) -> list[RawRecord]:
        """Parse message board page.

        Args:
            soup: BeautifulSoup parsed page
            base_url: Page URL
            surname: Search surname
            given_name: Search given name

        Returns:
            List of message records
        """
        records: list[RawRecord] = []
        search_terms = [surname.lower()]
        if given_name:
            search_terms.append(given_name.lower())

        # Look for message/thread elements
        message_selectors = [
            "div.message",
            "tr.thread",
            "li.post",
            "div.post",
            "article",
        ]

        messages = []
        for selector in message_selectors:
            messages = soup.select(selector)
            if messages:
                break

        # Fallback: look for links with message-like content
        if not messages:
            messages = soup.find_all("a", href=lambda h: h and ("thread" in h or "message" in h or "mb.ashx" in h))

        for msg in messages[:30]:
            # Get title/subject
            title_elem = msg.find(["h2", "h3", "a", "span"], class_=lambda c: c and ("subject" in c.lower() or "title" in c.lower()) if c else False)
            if not title_elem:
                title_elem = msg.find(["h2", "h3"]) or msg.find("a")

            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Check if matches search
            title_lower = title.lower()
            if not any(term in title_lower for term in search_terms):
                continue

            # Get URL
            link = msg.find("a", href=True) if msg.name != "a" else msg
            url = ""
            if link:
                href = link.get("href", "")
                url = href if href.startswith("http") else urljoin(base_url, href)

            # Get date
            date_elem = msg.find(class_=lambda c: c and "date" in c.lower() if c else False)
            date_str = date_elem.get_text(strip=True) if date_elem else ""

            # Get author
            author_elem = msg.find(class_=lambda c: c and ("author" in c.lower() or "poster" in c.lower()) if c else False)
            author = author_elem.get_text(strip=True) if author_elem else ""

            # Get snippet
            content_elem = msg.find(class_=lambda c: c and ("content" in c.lower() or "body" in c.lower() or "snippet" in c.lower()) if c else False)
            snippet = content_elem.get_text(strip=True)[:300] if content_elem else ""

            record = RawRecord(
                source=self.name,
                record_id=url or f"{base_url}#msg-{hash(title)}",
                record_type="message",
                url=url,
                raw_data={
                    "title": title,
                    "date": date_str,
                    "author": author,
                    "snippet": snippet,
                },
                extracted_fields={
                    "subject": title,
                    "surname": surname,
                    "date": date_str,
                    "author": author,
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_mailing_list_page(
        self, soup: BeautifulSoup, base_url: str, surname: str
    ) -> list[RawRecord]:
        """Parse mailing list archive page.

        Args:
            soup: BeautifulSoup parsed page
            base_url: Page URL
            surname: Search surname

        Returns:
            List of mailing list records
        """
        records: list[RawRecord] = []
        surname_lower = surname.lower()

        # Look for archived messages
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not text or len(text) < 5:
                continue

            # Check if this looks like a message
            text_lower = text.lower()
            if surname_lower not in text_lower:
                continue

            # Build URL
            url = href if href.startswith("http") else urljoin(base_url, href)

            # Extract date from text or URL
            date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}|\w+ \d{1,2}, \d{4})", text)
            date_str = date_match.group(1) if date_match else ""

            record = RawRecord(
                source=self.name,
                record_id=url,
                record_type="mailing_list",
                url=url,
                raw_data={"title": text, "list_name": surname.upper()},
                extracted_fields={
                    "subject": text,
                    "surname": surname,
                    "date": date_str,
                    "list": surname.upper(),
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records[:20]

    def _parse_obituary_page(
        self, soup: BeautifulSoup, base_url: str, surname: str, given_name: str
    ) -> list[RawRecord]:
        """Parse Obituary Daily Times results.

        Args:
            soup: BeautifulSoup parsed page
            base_url: Page URL
            surname: Search surname
            given_name: Search given name

        Returns:
            List of obituary records
        """
        records: list[RawRecord] = []
        search_terms = [surname.lower()]
        if given_name:
            search_terms.append(given_name.lower())

        # Look for obituary entries
        # ODT typically uses tables or lists
        for row in soup.find_all(["tr", "li", "div"], class_=lambda c: c and ("result" in c.lower() or "entry" in c.lower() or "obit" in c.lower()) if c else False):
            text = row.get_text(strip=True)
            if not text or not any(term in text.lower() for term in search_terms):
                continue

            # Try to extract structured data
            # Common format: "SURNAME, Given Name - Date - Location - Newspaper"
            parts = re.split(r"\s*[-–|]\s*", text)

            name = parts[0] if parts else text[:50]
            date_str = ""
            location = ""
            newspaper = ""

            for part in parts[1:]:
                # Check if it's a date
                if re.search(r"\d{4}|\d{1,2}/\d{1,2}", part):
                    date_str = part
                # Check if it's a location (often has state abbrev)
                elif re.search(r"\b[A-Z]{2}\b", part) or any(loc in part.lower() for loc in ["county", "city"]):
                    location = part
                else:
                    newspaper = part

            # Get link if available
            link = row.find("a", href=True)
            url = ""
            if link:
                href = link.get("href", "")
                url = href if href.startswith("http") else urljoin(base_url, href)

            record = RawRecord(
                source=self.name,
                record_id=url or f"{base_url}#obit-{hash(text)}",
                record_type="obituary",
                url=url or base_url,
                raw_data={
                    "raw_text": text,
                    "name": name,
                    "date": date_str,
                    "location": location,
                    "newspaper": newspaper,
                },
                extracted_fields={
                    "name": name,
                    "surname": surname,
                    "death_date": date_str,
                    "location": location,
                    "source_newspaper": newspaper,
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        # Fallback: parse any tables
        if not records:
            for table in soup.find_all("table"):
                for row in table.find_all("tr")[1:20]:  # Skip header
                    cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    if not cells:
                        continue

                    row_text = " ".join(cells).lower()
                    if not any(term in row_text for term in search_terms):
                        continue

                    record = RawRecord(
                        source=self.name,
                        record_id=f"{base_url}#obit-{hash(row_text)}",
                        record_type="obituary",
                        url=base_url,
                        raw_data={"cells": cells},
                        extracted_fields={
                            "name": cells[0] if cells else "",
                            "surname": surname,
                            "raw_data": " | ".join(cells[:4]),
                        },
                        accessed_at=datetime.now(UTC),
                    )
                    records.append(record)

        return records[:30]

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by URL.

        Args:
            record_id: Record URL

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
            logger.warning("RootsWeb get_record error: %s", e)
            return None

    def _parse_record_page(self, soup: BeautifulSoup, url: str) -> RawRecord:
        """Parse a full record page.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL

        Returns:
            RawRecord
        """
        # Get title
        title_elem = soup.find("h1") or soup.find("title")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        # Get content
        content_elem = soup.find("div", class_=lambda c: c and ("content" in c.lower() or "message" in c.lower() or "body" in c.lower()) if c else False)
        if not content_elem:
            content_elem = soup.find("article") or soup.find("main")

        content = content_elem.get_text(strip=True)[:4000] if content_elem else ""

        # Determine record type from URL
        record_type = "message"
        if "obituary" in url.lower() or "obit" in url.lower():
            record_type = "obituary"
        elif "lists" in url.lower():
            record_type = "mailing_list"

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=record_type,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields={
                "title": title,
                "content_preview": content[:500],
            },
            accessed_at=datetime.now(UTC),
        )
