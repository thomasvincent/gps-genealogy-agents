"""Config-driven connectors for US State Vital Records (indexes/APIs).

This module provides a generic StateVitalsSource that can be configured via
environment variables to point at state-level public search endpoints.

For each supported state we create an instance keyed by its postal code.
If an endpoint is not configured, the source reports is_configured=False and returns no results.

Environment variables (per state):
- <STATE>_VITALS_URL (e.g., CA_VITALS_URL)
- <STATE>_VITALS_API_KEY (optional)

The connector is intentionally conservative: it only issues a simple GET with query parameters
when an endpoint is configured; otherwise, it no-ops. Parsing is a best-effort JSON mapper.
Integrators can supply a small adapter proxy that normalizes state-specific responses to JSON.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Dict, Optional

import httpx

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class StateVitalsSource(BaseSource):
    """Configurable state vital records connector."""

    def __init__(self, state_code: str, display_name: str) -> None:
        super().__init__(api_key=os.getenv(f"{state_code}_VITALS_API_KEY"))
        self.state_code = state_code.upper()
        self.display_name = display_name
        self.endpoint_url = os.getenv(f"{state_code}_VITALS_URL")
        self.name = f"vitals_{state_code.lower()}"

    def requires_auth(self) -> bool:
        # Most endpoints we expect are public; auth optional
        return False

    def is_configured(self) -> bool:
        return bool(self.endpoint_url)

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        if not self.is_configured():
            return []

        params: Dict[str, Any] = {}
        if query.given_name:
            params["given_name"] = query.given_name
        if query.surname:
            params["surname"] = query.surname
        if query.birth_year:
            y0 = query.birth_year - query.birth_year_range
            y1 = query.birth_year + query.birth_year_range
            params["year_from"] = y0
            params["year_to"] = y1
        if query.record_types:
            params["types"] = ",".join(query.record_types)

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(self.endpoint_url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        # Expect a list of records with keys like type, id, url, name, date, place
        out: list[RawRecord] = []
        if isinstance(data, dict) and "results" in data:
            items = data.get("results", [])
        elif isinstance(data, list):
            items = data
        else:
            items = []

        for item in items[:100]:
            try:
                rec_type = str(item.get("type") or item.get("record_type") or "index").lower()
                rec_id = str(item.get("id") or item.get("record_id") or "")
                url = item.get("url") or None
                name = item.get("name") or item.get("full_name")
                date = item.get("date") or item.get("event_date")
                place = item.get("place") or item.get("event_place")
                extracted = {}
                if name:
                    extracted["full_name"] = str(name)
                if date:
                    extracted["event_date"] = str(date)
                if place:
                    extracted["event_place"] = str(place)
                extracted["state"] = self.display_name

                out.append(
                    RawRecord(
                        source=self.name,
                        record_id=rec_id or (url or ""),
                        record_type=rec_type,
                        url=url,
                        raw_data=item if isinstance(item, dict) else {"raw": str(item)},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                        confidence_hint=0.6,  # index-level by default
                    )
                )
            except Exception:
                continue

        return out


# Factory helpers for supported states (CA, OK, UT, OR, TX, GA)

def create_state_vitals_sources() -> dict[str, StateVitalsSource]:
    states = {
        "CA": "California",
        "OK": "Oklahoma",
        "UT": "Utah",
        "OR": "Oregon",
        "TX": "Texas",
        "GA": "Georgia",
    }
    return {code.lower(): StateVitalsSource(code, name) for code, name in states.items()}
