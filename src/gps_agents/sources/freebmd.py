"""FreeBMD (England & Wales BMD Index) connector (HTML parsing)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class FreeBMDSource(BaseSource):
    name = "FreeBMD"
    base_url = "https://www.freebmd.org.uk/cgi/search.pl"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> List[RawRecord]:
        # Build simple search for surname/forename and date range
        params: dict[str, Any] = {
            "surname": query.surname or "",
            "firstname": query.given_name or "",
            "type": "BMD",
            "start": str((query.birth_year or 0) - query.birth_year_range) if query.birth_year else "",
            "end": str((query.birth_year or 0) + query.birth_year_range) if query.birth_year else "",
        }
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                return self._parse_results(soup)
        except Exception:
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        # For FreeBMD, record_id may be a link back to the search result row anchor
        url = record_id if record_id.startswith("http") else record_id
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                title = soup.find("title").get_text(strip=True) if soup.find("title") else "FreeBMD"
                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="index",
                    url=url,
                    raw_data={"title": title},
                    extracted_fields={"title": title},
                    accessed_at=datetime.now(UTC),
                )
        except Exception:
            return None

    def _parse_results(self, soup: BeautifulSoup) -> List[RawRecord]:
        records: List[RawRecord] = []
        # FreeBMD often renders results in tables with class="results"
        tables = soup.find_all("table")
        for table in tables:
            # Look for header row with District/Volume/Page
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not headers:
                continue
            if not any(h in headers for h in ["district", "volume", "page", "event", "year"]):
                continue
            for tr in table.find_all("tr")[1:]:
                tds = [td.get_text(strip=True) for td in tr.find_all("td")]
                if len(tds) < 3:
                    continue
                row_text = " | ".join(tds)
                # Try to infer event type
                event = "index"
                ev_candidates = [t for t in tds if t.lower() in {"births", "deaths", "marriages"}]
                if ev_candidates:
                    ev = ev_candidates[0].lower()
                    if "birth" in ev:
                        event = "birth"
                    elif "death" in ev:
                        event = "death"
                    elif "marriage" in ev:
                        event = "marriage"
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=soup.base.get("href") if soup.base else "",
                        record_type=event,
                        url="",
                        raw_data={"row": row_text},
                        extracted_fields={"index_row": row_text},
                        accessed_at=datetime.now(UTC),
                    )
                )
                if len(records) >= 50:
                    break
            if records:
                break
        return records
