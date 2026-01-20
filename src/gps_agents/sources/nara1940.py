"""NARA 1940 Census connector (Catalog API)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class Nara1940Source(BaseSource):
    name = "NARA1940"
    base_url = "https://catalog.archives.gov/api/v1"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
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

    def _build_q(self, q: SearchQuery) -> str:
        tokens: list[str] = ["\"1940 census\""]
        if q.given_name:
            tokens.append(q.given_name)
        if q.surname:
            tokens.append(q.surname)
        if q.birth_place:
            tokens.append(q.birth_place)
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
            or "1940 Census item"
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
