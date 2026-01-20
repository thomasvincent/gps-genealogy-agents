"""Chronicling America source connector (Library of Congress newspapers).

Searches digitized American newspapers from 1777-1963 for:
- Obituaries
- Birth announcements
- Marriage announcements
- News mentions
- Legal notices

No login required - completely free public access.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class ChroniclingAmericaSource(BaseSource):
    """Library of Congress Chronicling America newspaper search.

    API documentation: https://chroniclingamerica.loc.gov/about/api/

    Searches millions of pages of digitized newspapers from 1777-1963.
    Excellent for finding obituaries, local news, and historical context.
    """

    name = "ChroniclingAmerica"
    base_url = "https://chroniclingamerica.loc.gov"
    api_url = f"{base_url}/search/pages/results"

    def requires_auth(self) -> bool:
        """Chronicling America is completely free, no login required."""
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search newspapers for mentions of the subject.

        Args:
            query: Search parameters

        Returns:
            List of newspaper page results
        """
        # Build search terms
        search_terms = []
        if query.given_name:
            search_terms.append(query.given_name)
        if query.surname:
            search_terms.append(query.surname)

        if not search_terms:
            return []

        # API parameters
        params: dict[str, Any] = {
            "andtext": " ".join(search_terms),
            "format": "json",
            "rows": 20,
        }

        # Add date range based on birth/death years
        # Newspapers covered: 1777-1963
        if query.birth_year:
            # Search from a few years before birth to find birth announcements
            # and family context
            params["dateFilterType"] = "range"
            start_year = max(1777, query.birth_year - 5)
            end_year = min(1963, (query.death_year or query.birth_year) + 50)
            params["date1"] = f"{start_year}"
            params["date2"] = f"{end_year}"

        # Add state filter if provided
        if query.state:
            state_codes = self._get_state_code(query.state)
            if state_codes:
                params["state"] = state_codes

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "application/json",
                },
            ) as client:
                resp = await client.get(self.api_url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_results(data)

        except httpx.HTTPError as e:
            logger.warning(f"Chronicling America search failed: {e}")
            return []

    def _parse_results(self, data: dict[str, Any]) -> list[RawRecord]:
        """Parse API JSON response into RawRecords."""
        records: list[RawRecord] = []

        items = data.get("items", [])
        for item in items[:20]:
            try:
                record = self._item_to_record(item)
                if record:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Failed to parse Chronicling America item: {e}")
                continue

        return records

    def _item_to_record(self, item: dict[str, Any]) -> RawRecord:
        """Convert a Chronicling America result to RawRecord."""
        # Extract key fields
        record_id = item.get("id", "")
        url = item.get("url", "") or f"{self.base_url}{record_id}"

        # Newspaper info
        title = item.get("title", "Unknown Newspaper")
        date = item.get("date", "")  # YYYYMMDD format
        place = item.get("city", [])
        state = item.get("state", [])

        # Format date nicely
        date_formatted = ""
        if date and len(date) == 8:
            try:
                date_formatted = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            except (IndexError, ValueError):
                date_formatted = date

        # OCR text snippet
        ocr_text = item.get("ocr_eng", "")[:500] if item.get("ocr_eng") else ""

        # Location
        location_parts = []
        if place:
            location_parts.extend(place if isinstance(place, list) else [place])
        if state:
            location_parts.extend(state if isinstance(state, list) else [state])
        location = ", ".join(location_parts)

        extracted = {
            "newspaper_title": title,
            "publication_date": date_formatted,
            "location": location,
            "text_snippet": ocr_text[:300],
            "page": item.get("page", ""),
            "edition": item.get("edition", ""),
        }

        return RawRecord(
            source=self.name,
            record_id=record_id or url,
            record_type="newspaper",
            url=url,
            raw_data=item,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Fetch a specific newspaper page by ID or URL.

        Args:
            record_id: Chronicling America page URL or ID

        Returns:
            RawRecord with page details or None
        """
        # Build URL
        if record_id.startswith("http"):
            url = record_id
            # Append .json for API access
            if not url.endswith(".json"):
                url = url.rstrip("/") + ".json"
        else:
            url = f"{self.base_url}{record_id}.json"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                },
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                # Extract fields from page JSON
                title = data.get("title", {}).get("name", "Unknown")
                date = data.get("date_issued", "")
                ocr = data.get("ocr_eng", "")

                extracted = {
                    "newspaper_title": title,
                    "publication_date": date,
                    "text_snippet": ocr[:500] if ocr else "",
                    "page_number": data.get("sequence", ""),
                }

                # Page view URL (human readable)
                page_url = url.replace(".json", "")

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type="newspaper",
                    url=page_url,
                    raw_data=data,
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch Chronicling America record: {e}")
            return None

    def _get_state_code(self, state: str) -> str | None:
        """Convert state name to Chronicling America state code."""
        # Chronicling America uses state names
        state_map = {
            "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
            "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
            "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
            "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
            "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
            "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
            "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
            "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
            "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
            "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
            "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
            "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
            "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
        }

        # If already a state name, return as-is
        if state in state_map.values():
            return state

        # Convert abbreviation to name
        state_upper = state.upper()
        if state_upper in state_map:
            return state_map[state_upper]

        # Try to match partial name
        state_lower = state.lower()
        for name in state_map.values():
            if state_lower in name.lower():
                return name

        return None

    def search_obituaries(
        self,
        surname: str,
        given_name: str | None = None,
        death_year: int | None = None,
        state: str | None = None,
    ) -> str:
        """Generate a URL for searching obituaries.

        Useful for directing users to manual search when automated
        search doesn't find specific results.
        """
        terms = [surname]
        if given_name:
            terms.append(given_name)
        terms.append("obituary OR died OR funeral OR burial")

        params = f"andtext={'+'.join(terms)}"
        if death_year:
            params += f"&date1={death_year}&date2={death_year + 1}&dateFilterType=range"
        if state:
            state_name = self._get_state_code(state)
            if state_name:
                params += f"&state={state_name}"

        return f"{self.base_url}/search/pages/results/?{params}"
