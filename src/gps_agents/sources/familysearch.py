"""FamilySearch API connector and no-login search.

FamilySearch is the largest free genealogical database with billions of records.
This module provides:
1. FamilySearchSource - Full API access (requires OAuth2 authentication)
2. FamilySearchNoLoginSource - Limited access without authentication:
   - Search URL generation
   - Collection browsing URLs
   - Wiki access
   - Basic search result scraping (publicly visible data)

The new FamilySearchClient in familysearch_client.py provides a modern,
type-safe alternative with Pydantic models and async support.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote_plus, urlencode

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource
from .familysearch_client import (
    ClientConfig as FSClientConfig,
    Environment as FSEnvironment,
    FamilySearchClient,
    Person as FSPerson,
    RecordCollection,
    SearchParams as FSSearchParams,
    SearchResponse as FSSearchResponse,
)

logger = logging.getLogger(__name__)


# FamilySearch collection IDs for common record types (free browsing)
FAMILYSEARCH_COLLECTIONS = {
    # US Census (chronological)
    "us_census_1790": "1803959",
    "us_census_1800": "1804228",
    "us_census_1810": "1803765",
    "us_census_1820": "1803955",
    "us_census_1830": "1803958",
    "us_census_1840": "1786457",
    "us_census_1850": "1401638",
    "us_census_1860": "1473181",
    "us_census_1870": "1438024",
    "us_census_1880": "1417683",
    "us_census_1900": "1325221",
    "us_census_1910": "1727033",
    "us_census_1920": "1488411",
    "us_census_1930": "1810731",
    "us_census_1940": "2000219",
    "us_census_1950": "4179881",  # Released April 2022
    # Vital Records
    "california_death_index": "1932433",
    "california_birth_index": "1932380",
    "ssdi": "1202535",
    # African American
    "freedmens_bureau": "1989155",
    "freedmens_bureau_labor": "2426245",
    "freedmens_bureau_marriages": "1803968",
    "freedmens_bureau_hospital": "2140102",
    "slave_schedules_1850": "1420440",
    "slave_schedules_1860": "1473181",
    "usct_civil_war": "1932402",
    # Immigration
    "ellis_island": "1368704",
    "castle_garden": "1849782",
    "ny_passenger_lists": "1849782",
    # Military
    "wwi_draft_cards": "1968530",
    "wwii_draft_cards": "2513478",
    "civil_war_soldiers": "1910717",
    # Native American - Five Civilized Tribes (Oklahoma)
    "five_civilized_tribes": "1852353",  # Dawes enrollment applications including rejected
    "indian_census_rolls": "1914530",  # Indian Census Rolls 1885-1940
    "dawes_packets": "1913517",  # Dawes enrollment packets (detailed applications)
    "cherokee_freedmen": "1916102",  # Cherokee Freedmen applications
    "choctaw_freedmen": "1916090",  # Choctaw Freedmen applications
    "chickasaw_freedmen": "1916089",  # Chickasaw Freedmen applications
    "creek_freedmen": "1916103",  # Creek Freedmen applications
    "seminole_freedmen": "1916110",  # Seminole Freedmen applications
    # Oklahoma Vital Records
    "oklahoma_death_index": "1320895",  # Oklahoma Death Index 1908-1969
    "oklahoma_marriages": "1674643",  # Oklahoma County Marriages
}


class FamilySearchNoLoginSource(BaseSource):
    """FamilySearch access without authentication.

    Provides:
    - Search URL generation for manual use
    - Collection browsing URLs
    - FamilySearch Wiki links
    - Basic search result scraping (publicly visible before login wall)

    No authentication required, but full record details need FamilySearch account.
    """

    name = "FamilySearchNoLogin"
    base_url = "https://www.familysearch.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search FamilySearch without login.

        Generates search URLs and attempts to scrape publicly visible results.

        Args:
            query: Search parameters

        Returns:
            List of search URLs and any scraped basic data
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search URL with parameters
        search_params = self._build_search_params(query)
        search_url = f"{self.base_url}/search/record/results?{urlencode(search_params)}"

        # Add main search URL
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"fs-search-{query.surname}",
                record_type="search_url",
                url=search_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "FamilySearch Historical Records",
                    "search_url": search_url,
                    "note": "Free account required for full record details",
                    "tip": "Create free FamilySearch account for full access",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Try to scrape basic results from search page
        try:
            scraped_records = await self._scrape_search_results(search_url, query)
            records.extend(scraped_records)
        except Exception as e:
            logger.debug(f"FamilySearch scrape error: {e}")

        # Add relevant collection URLs based on query
        collection_records = self._get_collection_urls(query)
        records.extend(collection_records)

        # Add FamilySearch Wiki link for research guidance
        wiki_records = self._get_wiki_links(query)
        records.extend(wiki_records)

        # Add NARA workaround tip
        records.append(
            RawRecord(
                source=self.name,
                record_id="fs-nara-workaround",
                record_type="tip",
                url="https://www.archives.gov/research/census",
                raw_data={
                    "steps": [
                        "1. Find person in FamilySearch index (visible without login)",
                        "2. Note: Enumeration District (ED), Sheet/Page Number, Line Number",
                        "3. Go to archives.gov/research/census",
                        "4. Browse to that census year > state > county > ED > page",
                    ],
                },
                extracted_fields={
                    "tip_title": "NARA Image Workaround",
                    "description": (
                        "If FamilySearch requires login to view census images, "
                        "note the Enumeration District (ED) and Page Number from the index, "
                        "then look it up on NARA (archives.gov) which is free without login."
                    ),
                    "how_to": (
                        "1) Find person in FamilySearch index; "
                        "2) Note ED/Page/Line; "
                        "3) Go to archives.gov/research/census; "
                        "4) Browse census year > state > county > ED > page"
                    ),
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _build_search_params(
        self,
        query: SearchQuery,
        exact_surname: bool = False,
        exact_given: bool = False,
    ) -> dict[str, str]:
        """Build FamilySearch search URL parameters.

        Args:
            query: Search parameters
            exact_surname: If True, use exact surname matching (q.surname.exact=on)
            exact_given: If True, use exact given name matching

        Note on wildcards:
            Use * for multiple characters (encode as %2A in URL)
            Use ? for single character (encode as %3F in URL)
            Example: q.surname=Durh* matches Durham, Durhan, etc.
        """
        params: dict[str, str] = {}

        if query.given_name:
            params["q.givenName"] = query.given_name
            if exact_given:
                params["q.givenName.exact"] = "on"
        if query.surname:
            params["q.surname"] = query.surname
            if exact_surname:
                params["q.surname.exact"] = "on"

        if query.birth_year:
            params["q.birthLikeDate.from"] = str(query.birth_year - query.birth_year_range)
            params["q.birthLikeDate.to"] = str(query.birth_year + query.birth_year_range)

        if query.birth_place:
            params["q.birthLikePlace"] = query.birth_place

        if query.state:
            params["q.anyPlace"] = query.state

        if query.death_year:
            params["q.deathLikeDate.from"] = str(query.death_year - query.death_year_range)
            params["q.deathLikeDate.to"] = str(query.death_year + query.death_year_range)

        if query.father_name:
            params["q.fatherGivenName"] = query.father_name
        if query.mother_name:
            params["q.motherGivenName"] = query.mother_name
        if query.spouse_name:
            params["q.spouseGivenName"] = query.spouse_name

        # Add race filter if specified (for African American research)
        if hasattr(query, "race") and query.race:
            params["q.race"] = query.race

        return params

    async def _scrape_search_results(
        self,
        search_url: str,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Scrape publicly visible search results.

        FamilySearch shows basic info (name, dates, places) on search results
        before requiring login for full details.
        """
        records: list[RawRecord] = []

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url)

                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for result count
                count_el = soup.select_one(".results-count, [data-testid='results-count']")
                if count_el:
                    count_text = count_el.get_text(strip=True)
                    count_match = re.search(r"([\d,]+)", count_text)
                    if count_match:
                        records.append(
                            RawRecord(
                                source=self.name,
                                record_id=f"fs-count-{query.surname}",
                                record_type="metadata",
                                url=search_url,
                                raw_data={"count": count_match.group(1)},
                                extracted_fields={
                                    "result_count": count_match.group(1),
                                    "note": f"Found {count_match.group(1)} records for {query.surname}",
                                },
                                accessed_at=datetime.now(UTC),
                            )
                        )

                # Parse individual result cards (publicly visible portion)
                result_cards = soup.select(".result-item, [data-testid='search-result']")

                for i, card in enumerate(result_cards[:20]):  # Limit to first 20
                    try:
                        record = self._parse_result_card(card, query, i)
                        if record:
                            records.append(record)
                    except Exception as e:
                        logger.debug(f"Failed to parse result card: {e}")
                        continue

        except httpx.HTTPError as e:
            logger.debug(f"FamilySearch HTTP error: {e}")

        return records

    def _parse_result_card(
        self,
        card: BeautifulSoup,
        query: SearchQuery,
        index: int,
    ) -> RawRecord | None:
        """Parse a single search result card."""
        # Extract name
        name_el = card.select_one(".result-name, [data-testid='result-name'], h3, h4")
        if not name_el:
            return None

        name = name_el.get_text(strip=True)

        # Extract dates
        dates_el = card.select_one(".result-dates, [data-testid='result-dates']")
        dates = dates_el.get_text(strip=True) if dates_el else ""

        # Extract places
        places_el = card.select_one(".result-places, [data-testid='result-places']")
        places = places_el.get_text(strip=True) if places_el else ""

        # Extract record type
        type_el = card.select_one(".result-type, [data-testid='result-type'], .collection-name")
        record_type = type_el.get_text(strip=True) if type_el else "Historical Record"

        # Extract link to full record
        link = card.select_one("a[href*='/ark:/']")
        url = ""
        if link:
            href = link.get("href", "")
            url = href if href.startswith("http") else f"{self.base_url}{href}"

        # Parse birth/death years from dates string
        birth_year = None
        death_year = None
        year_match = re.findall(r"\b(1[789]\d{2}|20[012]\d)\b", dates)
        if year_match:
            birth_year = year_match[0]
            if len(year_match) > 1:
                death_year = year_match[1]

        return RawRecord(
            source=self.name,
            record_id=f"fs-result-{query.surname}-{index}",
            record_type="search_result",
            url=url or f"{self.base_url}/search",
            raw_data={
                "name": name,
                "dates": dates,
                "places": places,
                "record_type": record_type,
            },
            extracted_fields={
                "full_name": name,
                "birth_year": birth_year,
                "death_year": death_year,
                "places": places,
                "record_type": record_type,
                "note": "Basic info - login required for full details",
            },
            accessed_at=datetime.now(UTC),
        )

    def _get_collection_urls(self, query: SearchQuery) -> list[RawRecord]:
        """Get relevant FamilySearch collection URLs based on query."""
        records: list[RawRecord] = []

        # Determine relevant collections based on location and time period
        relevant_collections = []

        # US Census collections based on birth year
        if query.birth_year:
            for year in [1950, 1940, 1930, 1920, 1910, 1900, 1880, 1870, 1860, 1850]:
                if query.birth_year - 5 <= year <= query.birth_year + 80:
                    key = f"us_census_{year}"
                    if key in FAMILYSEARCH_COLLECTIONS:
                        relevant_collections.append((key, f"US Census {year}", FAMILYSEARCH_COLLECTIONS[key]))

        # California vitals if CA location
        location = (query.birth_place or "").lower() + " " + (query.state or "").lower()
        if "california" in location or "ca" in location:
            relevant_collections.append(("california_death_index", "California Death Index", FAMILYSEARCH_COLLECTIONS["california_death_index"]))
            relevant_collections.append(("california_birth_index", "California Birth Index", FAMILYSEARCH_COLLECTIONS["california_birth_index"]))

        # African American collections (check if researching AA genealogy)
        # These are valuable for all researchers with Southern US roots
        if any(state in location for state in ["north carolina", "south carolina", "georgia", "virginia", "alabama", "mississippi", "louisiana", "arkansas", "tennessee"]):
            relevant_collections.append(("freedmens_bureau", "Freedmen's Bureau Records", FAMILYSEARCH_COLLECTIONS["freedmens_bureau"]))
            relevant_collections.append(("slave_schedules_1860", "1860 Slave Schedules", FAMILYSEARCH_COLLECTIONS["slave_schedules_1860"]))

        # Oklahoma and Native American collections
        # Critical for Five Civilized Tribes research (Cherokee, Chickasaw, Choctaw, Creek, Seminole)
        if "oklahoma" in location or "indian territory" in location or "cherokee" in location:
            # Five Civilized Tribes enrollment applications (includes rejected)
            relevant_collections.append(("five_civilized_tribes", "Five Civilized Tribes Enrollment", FAMILYSEARCH_COLLECTIONS["five_civilized_tribes"]))
            # Indian Census Rolls
            relevant_collections.append(("indian_census_rolls", "Indian Census Rolls 1885-1940", FAMILYSEARCH_COLLECTIONS["indian_census_rolls"]))
            # Dawes enrollment packets (detailed applications)
            relevant_collections.append(("dawes_packets", "Dawes Enrollment Packets", FAMILYSEARCH_COLLECTIONS["dawes_packets"]))
            # Cherokee Freedmen (African Americans who were Cherokee citizens)
            relevant_collections.append(("cherokee_freedmen", "Cherokee Freedmen Applications", FAMILYSEARCH_COLLECTIONS["cherokee_freedmen"]))
            # Oklahoma vital records
            relevant_collections.append(("oklahoma_death_index", "Oklahoma Death Index 1908-1969", FAMILYSEARCH_COLLECTIONS["oklahoma_death_index"]))
            relevant_collections.append(("oklahoma_marriages", "Oklahoma County Marriages", FAMILYSEARCH_COLLECTIONS["oklahoma_marriages"]))

        # Build URLs for each collection
        for key, name, collection_id in relevant_collections[:10]:  # Limit
            # Build collection search URL with query params
            params = self._build_search_params(query)
            collection_url = f"{self.base_url}/search/collection/{collection_id}/results?{urlencode(params)}"

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"fs-collection-{key}",
                    record_type="collection_search",
                    url=collection_url,
                    raw_data={"collection_id": collection_id, "collection_name": name},
                    extracted_fields={
                        "collection_name": name,
                        "collection_id": collection_id,
                        "search_url": collection_url,
                        "note": "Browse collection - free account for full details",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _get_wiki_links(self, query: SearchQuery) -> list[RawRecord]:
        """Get relevant FamilySearch Wiki links."""
        records: list[RawRecord] = []

        # Base wiki URL
        wiki_base = "https://www.familysearch.org/en/wiki"

        # State-specific wiki if location known
        location = (query.birth_place or "").lower() + " " + (query.state or "").lower()

        state_wikis = {
            "california": "California_Genealogy",
            "texas": "Texas_Genealogy",
            "new york": "New_York_Genealogy",
            "north carolina": "North_Carolina_Genealogy",
            "georgia": "Georgia_Genealogy",
            "virginia": "Virginia_Genealogy",
            "ohio": "Ohio_Genealogy",
            "pennsylvania": "Pennsylvania_Genealogy",
            "arkansas": "Arkansas_Genealogy",
            "alabama": "Alabama_Genealogy",
        }

        for state, wiki_page in state_wikis.items():
            if state in location:
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"fs-wiki-{state.replace(' ', '-')}",
                        record_type="wiki",
                        url=f"{wiki_base}/{wiki_page}",
                        raw_data={"state": state},
                        extracted_fields={
                            "wiki_title": f"{state.title()} Genealogy Guide",
                            "note": "Free research guide - no login required",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )
                break

        # African American genealogy wiki
        if any(state in location for state in ["north carolina", "south carolina", "georgia", "virginia", "alabama", "mississippi"]):
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="fs-wiki-african-american",
                    record_type="wiki",
                    url=f"{wiki_base}/African_American_Genealogy",
                    raw_data={},
                    extracted_fields={
                        "wiki_title": "African American Genealogy Guide",
                        "note": "Free research guide for African American genealogy",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not available without login."""
        return None


class FamilySearchSource(BaseSource):
    """FamilySearch.org data source.

    Requires OAuth2 authentication. This is the largest free genealogical
    database with billions of records.
    """

    name = "FamilySearch"
    base_url = "https://api.familysearch.org"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, token_file: str | None = None) -> None:
        """Initialize FamilySearch source.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
        """
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._token_file = token_file or "data/fs_token.json"

    def requires_auth(self) -> bool:
        return True

    def is_configured(self) -> bool:
        """Check if FamilySearch source is properly configured.

        Returns True if:
        - OAuth credentials (client_id + client_secret) are provided, OR
        - Access token is available via env var or token file
        """
        import os
        from pathlib import Path

        # OAuth flow credentials
        if self.client_id is not None and self.client_secret is not None:
            return True

        # Check for access token in env var
        if os.getenv("FAMILYSEARCH_ACCESS_TOKEN"):
            return True

        # Check for access token in token file
        try:
            p = Path(self._token_file)
            if p.exists():
                import json
                data = json.loads(p.read_text())
                if data.get("access_token"):
                    return True
        except Exception:
            pass

        return False

    async def _ensure_token(self) -> None:
        """Ensure we have a valid access token.

        Strategy hierarchy:
        1) Use env FAMILYSEARCH_ACCESS_TOKEN if set.
        2) Load from token file (JSON with {"access_token": "..."}).
        3) If neither available, raise and instruct user to set a token.
        """
        import os
        import json as _json
        if self._access_token:
            return
        env_token = os.getenv("FAMILYSEARCH_ACCESS_TOKEN")
        if env_token:
            self._access_token = env_token.strip()
            return
        try:
            from pathlib import Path as _Path
            p = _Path(self._token_file)
            if p.exists():
                data = _json.loads(p.read_text())
                tok = data.get("access_token")
                if tok:
                    self._access_token = tok
                    return
        except Exception:
            pass
        # Could implement OAuth flows here; for now, require a token
        raise RuntimeError("FamilySearch access token not configured. Set FAMILYSEARCH_ACCESS_TOKEN or place {\"access_token\":\"...\"} in data/fs_token.json.")
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
            # Add variants - collect all then join (API expects comma-separated)
            variants = [v for v in self._build_name_variants(query.surname) if v != query.surname]
            if variants:
                params["surname.variants"] = ",".join(variants)

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
            # Use BaseSource client to add token header
            if self._client is None:
                import httpx
                self._client = httpx.AsyncClient(timeout=30.0)
            headers = {"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"}
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            return self._parse_results(data)
        except Exception as e:
            # Log error and return empty results
            logger.warning("FamilySearch search error: %s", e)
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
            logger.warning("FamilySearch get_record error: %s", e)
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
            accessed_at=datetime.now(UTC),
        )

    def _build_name_variants(self, surname: str) -> list[str]:
        """Build surname variants for broader matching.

        Args:
            surname: Original surname

        Returns:
            List of variant spellings
        """
        variants = [surname]

        # Common phonetic substitutions
        substitutions = [
            ("ie", "y"),
            ("y", "ie"),
            ("ck", "k"),
            ("k", "ck"),
            ("ph", "f"),
            ("f", "ph"),
            ("gh", "g"),
            ("ough", "o"),
            ("son", "sen"),
            ("sen", "son"),
            ("man", "mann"),
            ("mann", "man"),
        ]

        lower = surname.lower()
        for old, new in substitutions:
            if old in lower:
                variant = lower.replace(old, new)
                variants.append(variant.title())

        return list(set(variants))

    async def search_with_client(
        self,
        query: SearchQuery,
        client: FamilySearchClient | None = None,
    ) -> list[RawRecord]:
        """Search using the new FamilySearchClient.

        This method provides integration between the legacy BaseSource
        interface and the modern FamilySearchClient.

        Args:
            query: Search parameters
            client: Optional pre-configured client

        Returns:
            List of RawRecords
        """
        if client is None:
            # Create client from environment
            config = FSClientConfig(
                client_id=self.client_id or "default",
                client_secret=self.client_secret,
            )
            async with FamilySearchClient(config) as client:
                return await self._search_with_client_impl(query, client)
        else:
            return await self._search_with_client_impl(query, client)

    async def _search_with_client_impl(
        self,
        query: SearchQuery,
        client: FamilySearchClient,
    ) -> list[RawRecord]:
        """Implementation of client-based search."""
        if not client.is_authenticated:
            if self._access_token:
                await client.login(self._access_token)
            else:
                return []

        params = FSSearchParams(
            given_name=query.given_name,
            surname=query.surname,
            birth_year=query.birth_year,
            birth_year_range=query.birth_year_range,
            death_year=query.death_year,
            death_year_range=query.death_year_range,
            birth_place=query.birth_place,
            father_given_name=query.father_name,
            mother_given_name=query.mother_name,
            spouse_given_name=query.spouse_name,
            count=50,
        )

        response = await client.search_persons(params)
        return self._convert_response_to_records(response)

    def _convert_response_to_records(self, response: FSSearchResponse) -> list[RawRecord]:
        """Convert FSSearchResponse to list of RawRecords."""
        records = []
        for person in response.all_persons:
            extracted = {
                "full_name": person.display_name,
                "given_name": person.given_name,
                "surname": person.surname,
            }

            if person.birth_date:
                extracted["birth_date"] = person.birth_date.original
                if person.birth_date.year:
                    extracted["birth_year"] = person.birth_date.year

            if person.birth_place:
                extracted["birth_place"] = person.birth_place.original

            if person.death_date:
                extracted["death_date"] = person.death_date.original
                if person.death_date.year:
                    extracted["death_year"] = person.death_date.year

            if person.death_place:
                extracted["death_place"] = person.death_place.original

            if person.gender:
                extracted["gender"] = person.gender.value

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=person.id,
                    record_type="person",
                    url=f"https://www.familysearch.org/tree/person/details/{person.id}",
                    raw_data=person.model_dump(),
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )
            )

        return records
