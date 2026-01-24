"""Irish genealogy sources.

Ireland has unique records due to:
- The 1922 Four Courts fire destroying many 19th century records
- Church of Ireland/Catholic/Presbyterian parish registers
- Griffith's Valuation (1847-1864) as census substitute
- Civil registration beginning 1864

Free sources:
- IrishGenealogy.ie (government portal - civil registration)
- RootsIreland.ie (aggregate parish records, some free indexes)
- GRONI (Northern Ireland)
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# Irish Civil Registration began 1864 (all) / 1845 (Protestant marriages)
IRISH_CIVIL_REG_START = 1864
GRIFFITH_YEARS = range(1847, 1865)


class IrishGenealogySource(BaseSource):
    """IrishGenealogy.ie - Irish government civil registration portal.

    Provides free access to:
    - Birth indexes 1864-1921 (Republic) / 1864-present (indexes)
    - Marriage indexes 1845-1946 (Protestant) / 1864-1946 (all)
    - Death indexes 1864-1971

    No authentication required for index searches.
    """

    name = "IrishGenealogy"
    base_url = "https://civilrecords.irishgenealogy.ie"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Irish civil registration indexes."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Search all event types
        event_types = ["births", "marriages", "deaths"]

        for event_type in event_types:
            params: dict[str, str] = {
                "surname": query.surname,
            }

            if query.given_name:
                params["firstname"] = query.given_name

            # Year range
            if query.birth_year:
                if event_type == "births":
                    params["yearfrom"] = str(max(1864, query.birth_year - 2))
                    params["yearto"] = str(query.birth_year + 2)
                elif event_type == "deaths":
                    # Assume death 20-90 years after birth
                    params["yearfrom"] = str(query.birth_year + 20)
                    params["yearto"] = str(min(1971, query.birth_year + 90))
                elif event_type == "marriages":
                    # Assume marriage 18-50 years after birth
                    params["yearfrom"] = str(max(1864, query.birth_year + 18))
                    params["yearto"] = str(query.birth_year + 50)

            search_url = f"{self.base_url}/{event_type}/search"

            try:
                async with httpx.AsyncClient(
                    timeout=30.0,
                    headers={
                        "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                        "Accept": "text/html",
                    },
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(search_url, params=params)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        parsed = self._parse_results(soup, event_type, query)
                        records.extend(parsed)

            except httpx.HTTPError as e:
                logger.debug(f"IrishGenealogy {event_type} search error: {e}")

        # Always add manual search URLs
        for event_type in event_types:
            manual_url = f"{self.base_url}/{event_type}/search?surname={query.surname}"
            if query.given_name:
                manual_url += f"&firstname={query.given_name}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"irish-{event_type}-search",
                    record_type="search_url",
                    url=manual_url,
                    raw_data={"event_type": event_type},
                    extracted_fields={
                        "search_type": f"Irish {event_type.title()} Index",
                        "search_url": manual_url,
                        "coverage": "1864-1971 (varies by record type)",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _parse_results(
        self, soup: BeautifulSoup, event_type: str, query: SearchQuery
    ) -> list[RawRecord]:
        """Parse Irish civil registration results."""
        records: list[RawRecord] = []

        result_table = soup.select_one("table.results, #results, .searchResults")
        if not result_table:
            return []

        rows = result_table.select("tr")[1:]  # Skip header

        for row in rows[:25]:
            try:
                cells = row.select("td")
                if len(cells) < 3:
                    continue

                cell_texts = [c.get_text(strip=True) for c in cells]
                link = row.select_one("a")
                href = link.get("href", "") if link else ""
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                extracted = self._extract_fields(cell_texts, event_type)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"irish-{event_type}-{hash(url)}",
                        record_type=event_type.rstrip("s"),  # births -> birth
                        url=url,
                        raw_data={"cells": cell_texts},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse Irish result: {e}")

        return records

    def _extract_fields(self, cells: list[str], event_type: str) -> dict[str, str]:
        """Extract fields from Irish civil registration record."""
        extracted: dict[str, str] = {}

        # Typical format: Name, Date, District, Volume, Page
        if cells:
            extracted["full_name"] = cells[0]
        if len(cells) > 1:
            # Parse date (often just year or quarter)
            date_str = cells[1]
            year_match = re.search(r"(\d{4})", date_str)
            if year_match:
                extracted[f"{event_type.rstrip('s')}_year"] = year_match.group(1)
        if len(cells) > 2:
            extracted["registration_district"] = cells[2]
        if len(cells) > 3:
            extracted["volume"] = cells[3]
        if len(cells) > 4:
            extracted["page"] = cells[4]

        return extracted

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific Irish civil registration record."""
        if record_id.startswith("http"):
            url = record_id
        else:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")
                title = soup.find("title")
                name = title.get_text(strip=True) if title else "Irish Record"

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="civil_registration",
                    url=url,
                    raw_data={"title": name},
                    extracted_fields={"title": name},
                    accessed_at=datetime.now(UTC),
                )
        except Exception:
            return None


class RootsIrelandSource(BaseSource):
    """RootsIreland.ie - Irish parish and civil records aggregator.

    Provides access to millions of Irish records:
    - Church parish registers (baptisms, marriages, burials)
    - Civil registration indexes
    - Census substitutes (Griffith's, Tithe Applotment)

    Index searches are free; images require subscription.
    """

    name = "RootsIreland"
    base_url = "https://www.rootsireland.ie"

    def requires_auth(self) -> bool:
        return False  # Index searches are free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search RootsIreland free indexes."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        params: dict[str, str] = {"surname": query.surname}
        if query.given_name:
            params["forename"] = query.given_name
        if query.birth_year:
            params["yearfrom"] = str(query.birth_year - 5)
            params["yearto"] = str(query.birth_year + 5)

        search_url = f"{self.base_url}/search"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0",
                    "Accept": "text/html",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url, params=params)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_results(soup, query)

        except httpx.HTTPError as e:
            logger.debug(f"RootsIreland search error: {e}")

        # Manual search link
        manual_url = f"{search_url}?{urlencode(params)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id="rootsireland-search",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": params},
                extracted_fields={
                    "search_type": "RootsIreland Search",
                    "search_url": manual_url,
                    "note": "Irish parish records and census substitutes",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _parse_results(self, soup: BeautifulSoup, query: SearchQuery) -> list[RawRecord]:
        """Parse RootsIreland results."""
        records: list[RawRecord] = []

        results = soup.select(".search-result, .result-row, tr.result")
        for result in results[:20]:
            try:
                link = result.select_one("a")
                if not link:
                    continue

                text = result.get_text(" ", strip=True)
                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                extracted: dict[str, str] = {"summary": text[:200]}

                # Try to extract record type
                if "baptism" in text.lower():
                    record_type = "baptism"
                elif "marriage" in text.lower():
                    record_type = "marriage"
                elif "burial" in text.lower():
                    record_type = "burial"
                elif "griffith" in text.lower():
                    record_type = "griffith_valuation"
                else:
                    record_type = "parish_record"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"rootsireland-{hash(url)}",
                        record_type=record_type,
                        url=url,
                        raw_data={"text": text},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )
            except Exception:
                continue

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get specific RootsIreland record."""
        return None  # Most records require subscription


class GRONISource(BaseSource):
    """General Register Office Northern Ireland.

    Civil registration in Northern Ireland from 1864:
    - Births
    - Marriages
    - Deaths
    - Adoptions (from 1931)

    Free index searching available.
    """

    name = "GRONI"
    base_url = "https://geni.nidirect.gov.uk"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search GRONI indexes."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # GRONI has separate search for each event type
        event_types = ["births", "marriages", "deaths"]

        for event_type in event_types:
            search_url = f"{self.base_url}/{event_type}"
            params = {
                "surname": query.surname,
            }
            if query.given_name:
                params["forenames"] = query.given_name

            manual_url = f"{search_url}?{urlencode(params)}"

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"groni-{event_type}-search",
                    record_type="search_url",
                    url=manual_url,
                    raw_data={"event_type": event_type},
                    extracted_fields={
                        "search_type": f"GRONI {event_type.title()} Index",
                        "search_url": manual_url,
                        "coverage": "Northern Ireland from 1864",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class IrishGenealogyAggregateSource(BaseSource):
    """Aggregate source for all Irish genealogy searches.

    Combines:
    - IrishGenealogy.ie (civil registration)
    - GRONI (Northern Ireland)
    - RootsIreland (parish records)
    """

    name = "IrishGenealogy"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key)
        self._irish_gov = IrishGenealogySource()
        self._roots = RootsIrelandSource()
        self._groni = GRONISource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Irish sources."""
        records: list[RawRecord] = []

        # Run all sub-source searches
        for source in [self._irish_gov, self._roots, self._groni]:
            try:
                results = await source.search(query)
                records.extend(results)
            except Exception as e:
                logger.debug(f"Irish sub-source {source.name} error: {e}")

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        # Delegate based on record ID prefix
        if "groni" in record_id:
            return await self._groni.get_record(record_id)
        elif "rootsireland" in record_id:
            return await self._roots.get_record(record_id)
        return await self._irish_gov.get_record(record_id)


# County mapping for Irish searches
IRISH_COUNTIES = {
    # Republic of Ireland
    "antrim": "Northern Ireland",
    "armagh": "Northern Ireland",
    "carlow": "Leinster",
    "cavan": "Ulster",
    "clare": "Munster",
    "cork": "Munster",
    "derry": "Northern Ireland",
    "donegal": "Ulster",
    "down": "Northern Ireland",
    "dublin": "Leinster",
    "fermanagh": "Northern Ireland",
    "galway": "Connacht",
    "kerry": "Munster",
    "kildare": "Leinster",
    "kilkenny": "Leinster",
    "laois": "Leinster",
    "leitrim": "Connacht",
    "limerick": "Munster",
    "longford": "Leinster",
    "louth": "Leinster",
    "mayo": "Connacht",
    "meath": "Leinster",
    "monaghan": "Ulster",
    "offaly": "Leinster",
    "roscommon": "Connacht",
    "sligo": "Connacht",
    "tipperary": "Munster",
    "tyrone": "Northern Ireland",
    "waterford": "Munster",
    "westmeath": "Leinster",
    "wexford": "Leinster",
    "wicklow": "Leinster",
}
