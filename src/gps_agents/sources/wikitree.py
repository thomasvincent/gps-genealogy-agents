"""WikiTree API and scraping connector."""
from __future__ import annotations

from datetime import UTC, datetime

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class WikiTreeSource(BaseSource):
    """WikiTree.com data source.

    Free, community-driven genealogy wiki. Has both API and web access.
    Focus on connecting family trees worldwide.
    """

    name = "WikiTree"
    base_url = "https://api.wikitree.com/api.php"

    def requires_auth(self) -> bool:
        # WikiTree API is free but rate-limited
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search WikiTree profiles.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        # WikiTree uses a specific search format
        params = {
            "action": "searchPerson",
            "format": "json",
        }

        if query.surname:
            params["LastName"] = query.surname
        if query.given_name:
            params["FirstName"] = query.given_name
        if query.birth_year:
            params["BirthDate"] = str(query.birth_year)
        if query.death_year:
            params["DeathDate"] = str(query.death_year)
        if query.birth_place:
            params["BirthLocation"] = query.birth_place

        try:
            data = await self._make_request(self.base_url, params)
            return self._parse_search_results(data)
        except Exception as e:
            print(f"WikiTree search error: {e}")
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a WikiTree profile by ID (WikiTree ID format: Surname-####).

        Args:
            record_id: WikiTree profile ID

        Returns:
            The profile or None
        """
        params = {
            "action": "getPerson",
            "key": record_id,
            "fields": "Id,Name,FirstName,LastNameAtBirth,LastNameCurrent,BirthDate,DeathDate,"
            "BirthLocation,DeathLocation,Gender,Father,Mother",
            "format": "json",
        }

        try:
            data = await self._make_request(self.base_url, params)
            return self._parse_person(data, record_id)
        except Exception as e:
            print(f"WikiTree get_record error: {e}")
            return None

    def _parse_search_results(self, data: dict) -> list[RawRecord]:
        """Parse WikiTree search results.

        Args:
            data: API response

        Returns:
            List of RawRecord objects
        """
        records = []
        results = data.get("searchPerson", [])

        if isinstance(results, list):
            for person in results:
                record = self._person_to_record(person)
                if record:
                    records.append(record)

        return records

    def _parse_person(self, data: dict, record_id: str) -> RawRecord | None:
        """Parse a single person response.

        Args:
            data: Person data
            record_id: WikiTree ID

        Returns:
            RawRecord or None
        """
        person_data = data.get("getPerson", {}).get("person", {})
        if not person_data:
            return None

        return self._person_to_record(person_data, record_id)

    def _person_to_record(self, person: dict, record_id: str | None = None) -> RawRecord | None:
        """Convert WikiTree person to RawRecord.

        Args:
            person: Person data dict
            record_id: Optional record ID override

        Returns:
            RawRecord or None
        """
        wiki_id = record_id or person.get("Name") or person.get("Id")
        if not wiki_id:
            return None

        extracted = {
            "wikitree_id": str(wiki_id),
            "given_name": person.get("FirstName"),
            "surname": person.get("LastNameAtBirth") or person.get("LastNameCurrent"),
            "birth_date": person.get("BirthDate"),
            "death_date": person.get("DeathDate"),
            "birth_place": person.get("BirthLocation"),
            "death_place": person.get("DeathLocation"),
            "gender": person.get("Gender"),
        }

        # Add parent info if available
        if person.get("Father"):
            extracted["father_id"] = str(person.get("Father"))
        if person.get("Mother"):
            extracted["mother_id"] = str(person.get("Mother"))

        return RawRecord(
            source=self.name,
            record_id=str(wiki_id),
            record_type="profile",
            url=f"https://www.wikitree.com/wiki/{wiki_id}",
            raw_data=person,
            extracted_fields={k: v for k, v in extracted.items() if v},
            accessed_at=datetime.now(UTC),
        )
