"""JewishGen source for Jewish genealogy records.

JewishGen is the premier site for Jewish genealogy, providing:
- Holocaust records
- Vital records from Eastern Europe
- Cemetery records
- Immigration records
- Family finder database

Most searches are free; some databases require membership.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class JewishGenSource(BaseSource):
    """JewishGen Jewish genealogy database.

    JewishGen provides access to:
    - Family Tree of the Jewish People (FTJP)
    - Holocaust databases (Yizkor books, deportation lists)
    - Vital records indices (Lithuania, Belarus, Ukraine, Poland)
    - Cemetery records
    - KehilaLinks community pages

    Free basic search; membership provides full access.
    """

    name = "JewishGen"
    base_url = "https://www.jewishgen.org"

    def requires_auth(self) -> bool:
        return False  # Basic search is free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search JewishGen databases.

        Args:
            query: Search parameters

        Returns:
            List of matching records and search links
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # JewishGen main search URL
        params: dict[str, str] = {
            "lastName": query.surname,
        }

        if query.given_name:
            params["firstName"] = query.given_name

        # Build search URLs for different databases
        search_urls = [
            {
                "name": "JewishGen Main Search",
                "url": f"{self.base_url}/databases/JGFF/jgffform.asp",
                "params": {"surname": query.surname},
                "description": "Search Family Finder and community databases",
            },
            {
                "name": "Family Tree of the Jewish People",
                "url": f"{self.base_url}/databases/FTJP/",
                "params": {"surname": query.surname},
                "description": "Submitted family trees (free search)",
            },
            {
                "name": "Yizkor Book Names",
                "url": f"{self.base_url}/databases/yizkor/",
                "params": {},
                "description": "Holocaust memorial books - search by town",
            },
            {
                "name": "All Jewish Records",
                "url": f"{self.base_url}/databases/",
                "params": {},
                "description": "Directory of all JewishGen databases",
            },
        ]

        for db in search_urls:
            url = db["url"]
            if db["params"]:
                url += "?" + "&".join(f"{k}={quote_plus(v)}" for k, v in db["params"].items())

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"jewishgen-{hash(db['name'])}",
                    record_type="search_url",
                    url=url,
                    raw_data=db,
                    extracted_fields={
                        "search_type": db["name"],
                        "search_url": url,
                        "description": db["description"],
                        "note": "Free basic search; membership for full access",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Try to fetch actual results from Family Finder
        try:
            ff_records = await self._search_family_finder(query)
            records.extend(ff_records)
        except Exception as e:
            logger.debug(f"JewishGen Family Finder search error: {e}")

        # Add Holocaust database links if death dates are in WWII era
        if query.death_year and 1933 <= query.death_year <= 1950:
            records.extend(self._get_holocaust_resources(query))

        return records

    async def _search_family_finder(self, query: SearchQuery) -> list[RawRecord]:
        """Search JewishGen Family Finder database."""
        records: list[RawRecord] = []

        url = f"{self.base_url}/databases/JGFF/jgff-search.asp"
        params = {
            "surname": query.surname,
        }
        if query.given_name:
            params["given"] = query.given_name

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, params=params)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # Parse results table
                    tables = soup.find_all("table")
                    for table in tables:
                        rows = table.find_all("tr")
                        for row in rows[1:20]:  # Skip header, limit results
                            cells = row.find_all("td")
                            if len(cells) >= 3:
                                surname = cells[0].get_text(strip=True)
                                given = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                                town = cells[2].get_text(strip=True) if len(cells) > 2 else ""

                                if surname.lower() == query.surname.lower():
                                    records.append(
                                        RawRecord(
                                            source=self.name,
                                            record_id=f"jgff-{surname}-{hash(town)}",
                                            record_type="family_finder",
                                            url=url,
                                            raw_data={
                                                "surname": surname,
                                                "given": given,
                                                "town": town,
                                            },
                                            extracted_fields={
                                                "surname": surname,
                                                "given_name": given,
                                                "town": town,
                                                "note": "Contact submitter through JewishGen for more info",
                                            },
                                            accessed_at=datetime.now(UTC),
                                        )
                                    )

        except httpx.HTTPError as e:
            logger.debug(f"JewishGen Family Finder error: {e}")

        return records

    def _get_holocaust_resources(self, query: SearchQuery) -> list[RawRecord]:
        """Get Holocaust-related database links."""
        resources = [
            {
                "name": "Yad Vashem Central Database",
                "url": f"https://yvng.yadvashem.org/nameSearch.html?language=en&s_lastName={quote_plus(query.surname)}",
                "description": "Shoah victims names database",
            },
            {
                "name": "Holocaust Survivors and Victims Database",
                "url": f"https://www.ushmm.org/online/hsv/person_advance_search.php?SourceId=&MaxPageItems=25&Sort=name_primary_sort&lname={quote_plus(query.surname)}",
                "description": "US Holocaust Memorial Museum database",
            },
            {
                "name": "JewishGen Holocaust Database",
                "url": f"{self.base_url}/databases/Holocaust/",
                "description": "Deportation lists, ghetto records, camp records",
            },
        ]

        records: list[RawRecord] = []
        for r in resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"holocaust-{hash(r['name'])}",
                    record_type="holocaust_resource",
                    url=r["url"],
                    raw_data=r,
                    extracted_fields={
                        "resource_title": r["name"],
                        "search_url": r["url"],
                        "description": r["description"],
                        "note": "Holocaust records database",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - JewishGen requires membership for detailed records."""
        return None


class YadVashemSource(BaseSource):
    """Yad Vashem Holocaust victims database.

    Free searchable database of Shoah victims.
    """

    name = "YadVashem"
    base_url = "https://yvng.yadvashem.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Yad Vashem victims database."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        params: dict[str, str] = {
            "language": "en",
            "s_lastName": query.surname,
        }

        if query.given_name:
            params["s_firstName"] = query.given_name

        url = f"{self.base_url}/nameSearch.html"
        search_url = url + "?" + "&".join(f"{k}={quote_plus(v)}" for k, v in params.items())

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"yadvashem-search-{query.surname}",
                record_type="search_url",
                url=search_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "Yad Vashem Names Database",
                    "search_url": search_url,
                    "description": "Central Database of Shoah Victims' Names",
                    "note": "Free search of Holocaust victims memorial database",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
