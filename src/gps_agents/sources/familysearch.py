"""FamilySearch API connector."""

from datetime import datetime

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource


class FamilySearchSource(BaseSource):
    """FamilySearch.org data source.

    Requires OAuth2 authentication. This is the largest free genealogical
    database with billions of records.
    """

    name = "FamilySearch"
    base_url = "https://api.familysearch.org"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        """Initialize FamilySearch source.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
        """
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None

    def requires_auth(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return self.client_id is not None and self.client_secret is not None

    async def _ensure_token(self) -> None:
        """Ensure we have a valid access token."""
        if self._access_token is None:
            # In production, implement OAuth2 flow
            # For now, assume token is provided
            pass

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search FamilySearch records.

        Args:
            query: Search parameters

        Returns:
            List of matching records
        """
        if not self.is_configured():
            return []

        await self._ensure_token()

        # Build search URL
        params = {"count": 50}

        if query.given_name:
            params["givenName"] = query.given_name
        if query.surname:
            params["surname"] = query.surname
            # Add variants
            for variant in self._build_name_variants(query.surname):
                if variant != query.surname:
                    params["surname.variants"] = variant

        if query.birth_year:
            params["birthLikeDate.from"] = str(query.birth_year - query.birth_year_range)
            params["birthLikeDate.to"] = str(query.birth_year + query.birth_year_range)

        if query.birth_place:
            params["birthLikePlace"] = query.birth_place

        if query.death_year:
            params["deathLikeDate.from"] = str(query.death_year - query.death_year_range)
            params["deathLikeDate.to"] = str(query.death_year + query.death_year_range)

        if query.father_name:
            params["fatherGivenName"] = query.father_name
        if query.mother_name:
            params["motherGivenName"] = query.mother_name
        if query.spouse_name:
            params["spouseGivenName"] = query.spouse_name

        try:
            url = f"{self.base_url}/platform/tree/search"
            data = await self._make_request(url, params)
            return self._parse_results(data)
        except Exception as e:
            # Log error and return empty results
            print(f"FamilySearch search error: {e}")
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by ID.

        Args:
            record_id: FamilySearch record ID

        Returns:
            The record or None
        """
        if not self.is_configured():
            return None

        await self._ensure_token()

        try:
            url = f"{self.base_url}/platform/tree/persons/{record_id}"
            data = await self._make_request(url)
            return self._parse_person(data, record_id)
        except Exception as e:
            print(f"FamilySearch get_record error: {e}")
            return None

    def _parse_results(self, data: dict) -> list[RawRecord]:
        """Parse FamilySearch search results.

        Args:
            data: API response data

        Returns:
            List of RawRecord objects
        """
        records = []
        entries = data.get("entries", [])

        for entry in entries:
            content = entry.get("content", {})
            gedcomx = content.get("gedcomx", {})
            persons = gedcomx.get("persons", [])

            for person in persons:
                record = self._parse_person_data(person)
                if record:
                    records.append(record)

        return records

    def _parse_person(self, data: dict, record_id: str) -> RawRecord | None:
        """Parse a single person response.

        Args:
            data: Person data from API
            record_id: The record ID

        Returns:
            RawRecord or None
        """
        persons = data.get("persons", [])
        if not persons:
            return None

        return self._parse_person_data(persons[0], record_id)

    def _parse_person_data(self, person: dict, record_id: str | None = None) -> RawRecord | None:
        """Parse person data into RawRecord.

        Args:
            person: Person object from GEDCOM-X
            record_id: Optional override for record ID

        Returns:
            RawRecord or None
        """
        pid = record_id or person.get("id")
        if not pid:
            return None

        # Extract fields
        extracted = {}

        # Name
        names = person.get("names", [])
        if names:
            name_forms = names[0].get("nameForms", [])
            if name_forms:
                extracted["full_name"] = name_forms[0].get("fullText")
                for part in name_forms[0].get("parts", []):
                    if part.get("type") == "http://gedcomx.org/Given":
                        extracted["given_name"] = part.get("value")
                    elif part.get("type") == "http://gedcomx.org/Surname":
                        extracted["surname"] = part.get("value")

        # Facts (birth, death, etc.)
        facts = person.get("facts", [])
        for fact in facts:
            fact_type = fact.get("type", "").split("/")[-1].lower()
            date_info = fact.get("date", {})
            place_info = fact.get("place", {})

            if date_info:
                extracted[f"{fact_type}_date"] = date_info.get("original")
            if place_info:
                extracted[f"{fact_type}_place"] = place_info.get("original")

        # Gender
        gender = person.get("gender", {})
        if gender:
            extracted["gender"] = gender.get("type", "").split("/")[-1]

        return RawRecord(
            source=self.name,
            record_id=pid,
            record_type="person",
            url=f"https://www.familysearch.org/tree/person/details/{pid}",
            raw_data=person,
            extracted_fields=extracted,
            accessed_at=datetime.utcnow(),
        )
