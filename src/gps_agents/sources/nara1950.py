"""NARA 1950 Census connector (Catalog API).

Best-effort search via Catalog API for 1950 population schedules and related items.
Parses results into RawRecord entries tagged as record_type="census".
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class Nara1950Source(BaseSource):
    """National Archives Catalog connector targeting the 1950 US Census."""

    name = "NARA1950"
    base_url = "https://catalog.archives.gov/api/v1"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search for 1950 census items matching the name/filters.

        Strategy:
        - Build a keyword query including "1950 census" and person name tokens
        - Request JSON results; cap to ~50 items
        - Map each catalog item to RawRecord
        """
        params: dict[str, Any] = {
            "q": self._build_q(query),
            "rows": 50,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.base_url, params=params)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return self._parse_results(data)
        except Exception:
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Fetch a single catalog item by NAID."""
        try:
            na_id = record_id
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.base_url, params={"naIds": na_id})
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                items = self._extract_items(data)
                if not items:
                    return None
                return self._item_to_record(items[0])
        except Exception:
            return None

    # ------------------------- helpers -------------------------
    def _build_q(self, q: SearchQuery) -> str:
        tokens: list[str] = ["\"1950 census\""]
        if q.given_name:
            tokens.append(q.given_name)
        if q.surname:
            tokens.append(q.surname)
        if q.birth_place:
            tokens.append(q.birth_place)
        # Allow callers to bias to "population schedule" by adding words here later
        return " ".join(tokens)

    def _parse_results(self, data: dict[str, Any]) -> list[RawRecord]:
        items = self._extract_items(data)
        out: list[RawRecord] = []
        for it in items[:50]:
            try:
                rec = self._item_to_record(it)
                if rec:
                    out.append(rec)
            except Exception:
                continue
        return out

    def _extract_items(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        # NARA Catalog returns items under various shapes; handle common forms
        # Prefer 'opaResponse' -> 'results' -> 'result'
        try:
            results = data.get("opaResponse", {}).get("results", {})
            items = results.get("result") or []
            if isinstance(items, dict):
                items = [items]
            return items
        except Exception:
            return []

    def _item_to_record(self, item: dict[str, Any]) -> RawRecord:
        naid = str(item.get("naId") or item.get("naid") or item.get("naIds") or "")
        title = (
            item.get("title")
            or item.get("description", {}).get("seriesTitle")
            or item.get("description", {}).get("title")
            or "1950 Census item"
        )
        desc = item.get("description", {})
        scope = desc.get("scopeAndContentNote") if isinstance(desc, dict) else None
        url = f"https://catalog.archives.gov/id/{naid}" if naid else None

        extracted = {
            "title": str(title)[:500],
            "summary": str(scope)[:1000] if scope else "",
            "naid": naid,
        }

        return RawRecord(
            source=self.name,
            record_id=naid or (url or title),
            record_type="census",
            url=url,
            raw_data=item,
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )
