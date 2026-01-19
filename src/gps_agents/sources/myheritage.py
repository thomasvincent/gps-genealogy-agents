"""MyHeritage API connector."""

from datetime import UTC, datetime

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class MyHeritageSource(BaseSource):
    """MyHeritage.com data source.

    Subscription-based service with global records and DNA matching.
    Strong European coverage.
    """

    name = "MyHeritage"
    base_url = "https://api.myheritage.com/v1"

    def requires_auth(self) -> bool:
        return True

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search MyHeritage records.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        if not self.is_configured():
            return []

        params = {"maxResults": 50}

        if query.given_name:
            params["givenName"] = query.given_name
        if query.surname:
            params["surname"] = query.surname
        if query.birth_year:
            params["birthYear"] = query.birth_year
        if query.birth_place:
            params["birthPlace"] = query.birth_place
        if query.death_year:
            params["deathYear"] = query.death_year

        try:
            data = await self._make_request(f"{self.base_url}/records/search", params)
            return self._parse_results(data)
        except Exception as e:
            print(f"MyHeritage search error: {e}")
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record.

        Args:
            record_id: MyHeritage record ID

        Returns:
            The record or None
        """
        if not self.is_configured():
            return None

        try:
            data = await self._make_request(f"{self.base_url}/records/{record_id}")
            return self._parse_single_record(data, record_id)
        except Exception as e:
            print(f"MyHeritage get_record error: {e}")
            return None

    def _parse_results(self, data: dict) -> list[RawRecord]:
        """Parse search results."""
        records = []
        items = data.get("records", [])

        for item in items:
            record = self._item_to_record(item)
            if record:
                records.append(record)

        return records

    def _parse_single_record(self, data: dict, record_id: str) -> RawRecord | None:
        """Parse a single record."""
        return self._item_to_record(data, record_id)

    def _item_to_record(self, item: dict, record_id: str | None = None) -> RawRecord | None:
        """Convert API item to RawRecord."""
        rid = record_id or item.get("id")
        if not rid:
            return None

        extracted = {
            "given_name": item.get("givenName"),
            "surname": item.get("surname"),
            "birth_date": item.get("birthDate"),
            "birth_place": item.get("birthPlace"),
            "death_date": item.get("deathDate"),
            "death_place": item.get("deathPlace"),
        }

        return RawRecord(
            source=self.name,
            record_id=rid,
            record_type=item.get("recordType", "unknown"),
            url=item.get("url") or f"https://www.myheritage.com/record/{rid}",
            raw_data=item,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )
