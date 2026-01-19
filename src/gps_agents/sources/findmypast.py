"""FindMyPast API connector."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class FindMyPastSource(BaseSource):
    """FindMyPast.com data source.

    Subscription-based service with strong UK, Ireland, and US records.
    Requires API key for access.
    """

    name = "FindMyPast"
    base_url = "https://api.findmypast.com/v1"

    def requires_auth(self) -> bool:
        return True

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search FindMyPast records.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        if not self.is_configured():
            return []

        params = {"limit": 50}

        if query.given_name:
            params["firstName"] = query.given_name
        if query.surname:
            params["lastName"] = query.surname
        if query.birth_year:
            params["yearOfBirth"] = query.birth_year
            params["yearOfBirthRange"] = query.birth_year_range
        if query.birth_place:
            params["birthPlace"] = query.birth_place
        if query.residence:
            params["residence"] = query.residence

        # Filter by record type if specified
        if query.record_types:
            type_mapping = {
                "birth": "births",
                "death": "deaths",
                "marriage": "marriages",
                "census": "census",
                "military": "military",
                "immigration": "immigration",
            }
            fmp_types = [type_mapping.get(t, t) for t in query.record_types]
            params["collections"] = ",".join(fmp_types)

        try:
            data = await self._make_request(f"{self.base_url}/search", params)
            return self._parse_results(data)
        except Exception as e:
            logger.warning("FindMyPast search error: %s", e)
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record.

        Args:
            record_id: FindMyPast record ID

        Returns:
            The record or None
        """
        if not self.is_configured():
            return None

        try:
            data = await self._make_request(f"{self.base_url}/records/{record_id}")
            return self._parse_single_record(data, record_id)
        except Exception as e:
            logger.warning("FindMyPast get_record error: %s", e)
            return None

    def _parse_results(self, data: dict) -> list[RawRecord]:
        """Parse search results.

        Args:
            data: API response

        Returns:
            List of RawRecord objects
        """
        records = []
        hits = data.get("results", [])

        for hit in hits:
            record = self._hit_to_record(hit)
            if record:
                records.append(record)

        return records

    def _parse_single_record(self, data: dict, record_id: str) -> RawRecord | None:
        """Parse a single record response.

        Args:
            data: Record data
            record_id: Record ID

        Returns:
            RawRecord or None
        """
        return self._hit_to_record(data, record_id)

    def _hit_to_record(self, hit: dict, record_id: str | None = None) -> RawRecord | None:
        """Convert API hit to RawRecord.

        Args:
            hit: Search result hit
            record_id: Optional override

        Returns:
            RawRecord or None
        """
        rid = record_id or hit.get("id")
        if not rid:
            return None

        extracted = {
            "given_name": hit.get("firstName"),
            "surname": hit.get("lastName"),
            "birth_year": str(hit.get("yearOfBirth")) if hit.get("yearOfBirth") else None,
            "birth_place": hit.get("birthPlace"),
            "death_year": str(hit.get("yearOfDeath")) if hit.get("yearOfDeath") else None,
            "residence": hit.get("residence"),
            "occupation": hit.get("occupation"),
        }

        record_type = hit.get("collection", "unknown")

        return RawRecord(
            source=self.name,
            record_id=rid,
            record_type=record_type,
            url=hit.get("url") or f"https://www.findmypast.com/record?id={rid}",
            raw_data=hit,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )
