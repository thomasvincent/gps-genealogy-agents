"""Find A Grave source connector (best-effort HTML parsing)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class FindAGraveSource(BaseSource):
    name = "FindAGrave"
    base_url = "https://www.findagrave.com/memorial/search"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> List[RawRecord]:
        params: dict[str, Any] = {}
        if query.given_name:
            params["firstname"] = query.given_name
        if query.surname:
            params["lastname"] = query.surname
        if query.birth_year:
            params["birthyear"] = str(query.birth_year)
        # limit to first page
        params["size"] = "20"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                return self._parse_results(soup)
        except Exception:
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        url = record_id if record_id.startswith("http") else f"https://www.findagrave.com/memorial/{record_id}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                title_el = soup.find("title")
                title = title_el.get_text(strip=True) if title_el else "Find A Grave memorial"
                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="burial",
                    url=url,
                    raw_data={"title": title},
                    extracted_fields={"title": title},
                    accessed_at=datetime.now(UTC),
                )
        except Exception:
            return None

    def _parse_results(self, soup: BeautifulSoup) -> List[RawRecord]:
        records: List[RawRecord] = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "/memorial/" in href:
                # Extract id and name snippet
                parts = href.split("/memorial/")[-1]
                mem_id = parts.split("/")[0]
                name = a.get_text(strip=True)
                url = href if href.startswith("http") else f"https://www.findagrave.com{href}"
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=mem_id,
                        record_type="burial",
                        url=url,
                        raw_data={"name": name},
                        extracted_fields={"full_name": name},
                        accessed_at=datetime.now(UTC),
                    )
                )
                if len(records) >= 20:
                    break
        return records
