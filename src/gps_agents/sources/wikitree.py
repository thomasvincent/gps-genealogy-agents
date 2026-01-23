"""WikiTree API and scraping connector with US Census search capabilities."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import cached_property
from typing import Any, TypedDict

import httpx

from ..models.search import RawRecord, SearchQuery
from ..net import GUARDS, RateLimitConfig
from .base import BaseSource

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# WikiTree API response status strings
WIKITREE_STATUS_LIMIT_EXCEEDED = "Limit exceeded."

# US Federal Census years (frozenset for O(1) lookups)
US_CENSUS_YEARS: frozenset[int] = frozenset([
    1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860, 1870,
    1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950
])


class WikiTreeAction(str, Enum):
    """WikiTree API action types."""
    SEARCH_PERSON = "searchPerson"
    GET_PERSON = "getPerson"
    GET_BIO = "getBio"
    GET_ANCESTORS = "getAncestors"
    GET_RELATIVES = "getRelatives"


# =============================================================================
# Exceptions
# =============================================================================

class WikiTreeError(Exception):
    """Base exception for WikiTree API errors."""


class RateLimitError(WikiTreeError):
    """Raised when WikiTree API rate limit is exceeded."""


class WikiTreeAPIError(WikiTreeError):
    """Raised when WikiTree API returns an error response."""


# =============================================================================
# Type Definitions
# =============================================================================

class CensusRecordDict(TypedDict, total=False):
    """Dictionary representation of a census record."""
    year: int
    location: str
    state: str
    county: str
    age: int | None
    occupation: str
    birthplace: str
    relationship: str
    household_head: str
    raw_text: str


@dataclass
class CensusRecord:
    """Extracted census record from WikiTree biography."""

    year: int
    location: str = ""
    state: str = ""
    county: str = ""
    household_head: str = ""
    relationship: str = ""
    age: int | None = None
    occupation: str = ""
    birthplace: str = ""
    source_citation: str = ""
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> CensusRecordDict:
        """Convert to dictionary representation."""
        return CensusRecordDict(
            year=self.year,
            location=self.location,
            state=self.state,
            county=self.county,
            age=self.age,
            occupation=self.occupation,
            birthplace=self.birthplace,
            relationship=self.relationship,
            household_head=self.household_head,
            raw_text=self.raw_text,
        )


# =============================================================================
# Regex Patterns (precompiled at module load)
# =============================================================================

class CensusPatterns:
    """Precompiled regex patterns for extracting census data."""

    # Census year patterns
    YEAR_PATTERN = re.compile(
        r"(?:United\s+States|U\.?S\.?|Federal)\s+Census[,\s]+(\d{4})",
        re.IGNORECASE,
    )
    YEAR_SIMPLE = re.compile(
        r"(\d{4})\s+(?:United\s+States|U\.?S\.?|Federal)?\s*Census",
        re.IGNORECASE,
    )
    CENSUS_TEMPLATE = re.compile(
        r"\{\{[Cc]ensus\s*\|\s*year\s*=\s*(\d{4})[^\}]*\}\}",
        re.IGNORECASE,
    )

    # Field extraction patterns
    LOCATION = re.compile(
        r"Census[,\s:]+(\d{4})[,\s:]+([^,\n]+(?:,\s*[^,\n]+)*)",
        re.IGNORECASE,
    )
    STATE = re.compile(
        r"Census[,\s]+\d{4}[,\s]+(?:[^,]+,\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:,|$|\n)",
        re.IGNORECASE,
    )
    AGE = re.compile(
        r"(?:age[d]?|aged?)\s*:?\s*(\d{1,3})",
        re.IGNORECASE,
    )
    OCCUPATION = re.compile(
        r"(?:occupation|occ\.?)\s*:?\s*([^,\n;]+)",
        re.IGNORECASE,
    )
    HEAD_OF_HOUSEHOLD = re.compile(
        r"(?:head\s+of\s+household|household\s+head|HoH)\s*:?\s*([^,\n;]+)",
        re.IGNORECASE,
    )
    RELATIONSHIP = re.compile(
        r"(?:relationship|rel\.?)\s*:?\s*([^,\n;]+)",
        re.IGNORECASE,
    )
    BIRTHPLACE = re.compile(
        r"(?:birthplace|born\s+in|birth\s+place|b\.?p\.?)\s*:?\s*([^,\n;]+)",
        re.IGNORECASE,
    )

    # Context extraction pattern (with placeholder for year)
    # We cache compiled patterns per year to avoid recompilation
    _context_cache: dict[int, re.Pattern] = {}

    @classmethod
    def get_context_pattern(cls, year: int) -> re.Pattern:
        """Get or create a compiled context pattern for a specific year."""
        if year not in cls._context_cache:
            cls._context_cache[year] = re.compile(
                rf"(.{{0,200}}{year}\s*(?:United\s+States|U\.?S\.?|Federal)?\s*Census.{{0,300}})",
                re.IGNORECASE | re.DOTALL,
            )
        return cls._context_cache[year]


# Legacy alias for backwards compatibility
CENSUS_PATTERNS = {
    "year_pattern": CensusPatterns.YEAR_PATTERN,
    "year_simple": CensusPatterns.YEAR_SIMPLE,
    "location": CensusPatterns.LOCATION,
    "state": CensusPatterns.STATE,
    "age": CensusPatterns.AGE,
    "occupation": CensusPatterns.OCCUPATION,
    "head_of_household": CensusPatterns.HEAD_OF_HOUSEHOLD,
    "relationship": CensusPatterns.RELATIONSHIP,
    "birthplace": CensusPatterns.BIRTHPLACE,
    "census_template": CensusPatterns.CENSUS_TEMPLATE,
}


# =============================================================================
# Rate Limit Configuration
# =============================================================================

def _get_wikitree_rate_config() -> RateLimitConfig:
    """Get WikiTree rate limit configuration from environment.

    Called lazily to allow environment variable changes after import.
    """
    return RateLimitConfig(
        max_calls=int(os.getenv("RATE_WIKITREE_MAX", "1")),
        window_seconds=float(os.getenv("RATE_WIKITREE_WINDOW", "10")),
        min_interval=float(os.getenv("RATE_WIKITREE_MIN_INTERVAL", "3")),
    )


# =============================================================================
# WikiTree Source Implementation
# =============================================================================

class WikiTreeSource(BaseSource):
    """WikiTree.com data source.

    Free, community-driven genealogy wiki. Has both API and web access.
    Focus on connecting family trees worldwide.

    Rate Limiting:
        WikiTree API has strict rate limits. This adapter uses conservative
        defaults: 1 request per 10 seconds with 3 second minimum interval.
        Configure via environment variables:
        - RATE_WIKITREE_MAX: Max requests per window (default: 1)
        - RATE_WIKITREE_WINDOW: Window in seconds (default: 10)
        - RATE_WIKITREE_MIN_INTERVAL: Min seconds between requests (default: 3)

    Args:
        api_key: Optional API key (WikiTree doesn't require one)
        strict: If True, raise exceptions on errors instead of returning empty results
        max_concurrent_requests: Maximum concurrent API requests (default: 3)
    """

    name = "WikiTree"
    base_url = "https://api.wikitree.com/api.php"

    # Retry configuration
    MAX_RATE_LIMIT_RETRIES = 3
    RATE_LIMIT_BACKOFF_BASE = 5.0  # Base backoff in seconds

    def __init__(
        self,
        api_key: str | None = None,
        strict: bool = False,
        max_concurrent_requests: int = 3,
    ) -> None:
        """Initialize WikiTree source.

        Args:
            api_key: Optional API key (not required for WikiTree)
            strict: If True, raise exceptions instead of returning empty results
            max_concurrent_requests: Max concurrent requests for batch operations
        """
        super().__init__(api_key)
        self.strict = strict
        self._max_concurrent = max_concurrent_requests
        self._semaphore: asyncio.Semaphore | None = None

    @cached_property
    def rate_limit_config(self) -> RateLimitConfig:
        """Get rate limit configuration (lazy evaluation)."""
        return _get_wikitree_rate_config()

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Get or create semaphore for concurrent request limiting."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    def requires_auth(self) -> bool:
        """WikiTree API is free but rate-limited."""
        return False

    # =========================================================================
    # HTTP Request Methods
    # =========================================================================

    async def _make_wikitree_request(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any] | list[Any]:
        """Make a rate-limited request to WikiTree API with retry on rate limit.

        This method bypasses BaseSource._make_request to avoid double rate limiting.
        It handles WikiTree's "Limit exceeded" status with exponential backoff.

        Args:
            params: Query parameters including 'action'

        Returns:
            Parsed JSON response

        Raises:
            RateLimitError: On rate limit errors after max retries
            WikiTreeAPIError: On other API errors (only if strict mode)
            httpx.HTTPError: On network errors
        """
        # Get WikiTree-specific rate limiter (only one acquire per request)
        limiter = GUARDS.get_limiter("wikitree", self.rate_limit_config)

        # Ensure client exists
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        for attempt in range(self.MAX_RATE_LIMIT_RETRIES):
            # Acquire rate limit token
            await limiter.acquire()

            try:
                # Make HTTP request directly (bypassing BaseSource._make_request)
                resp = await self._client.get(self.base_url, params=params)
                resp.raise_for_status()
                data = resp.json()

                # Check for WikiTree's rate limit response
                if self._is_rate_limited(data):
                    raise RateLimitError("WikiTree API rate limit exceeded")

                return data

            except RateLimitError:
                if attempt < self.MAX_RATE_LIMIT_RETRIES - 1:
                    backoff = self.RATE_LIMIT_BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "WikiTree rate limit hit, backing off %.1fs (attempt %d/%d)",
                        backoff, attempt + 1, self.MAX_RATE_LIMIT_RETRIES
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        "WikiTree rate limit exceeded after %d retries",
                        self.MAX_RATE_LIMIT_RETRIES
                    )
                    raise

            except httpx.HTTPStatusError as e:
                logger.warning("WikiTree HTTP error: %s", e)
                raise

        # Should not reach here
        raise RateLimitError("WikiTree request failed after retries")

    @staticmethod
    def _is_rate_limited(data: dict | list) -> bool:
        """Check if response indicates rate limiting."""
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and first.get("status") == WIKITREE_STATUS_LIMIT_EXCEEDED:
                return True
        elif isinstance(data, dict) and data.get("status") == WIKITREE_STATUS_LIMIT_EXCEEDED:
            return True
        return False

    def _handle_error(self, error: Exception, context: str) -> None:
        """Handle errors based on strict mode setting.

        Args:
            error: The exception that occurred
            context: Description of what operation failed

        Raises:
            WikiTreeAPIError: If strict mode is enabled
        """
        logger.warning("WikiTree %s error: %s", context, error)
        if self.strict:
            raise WikiTreeAPIError(f"{context} failed: {error}") from error

    # =========================================================================
    # Core API Methods
    # =========================================================================

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search WikiTree profiles.

        Args:
            query: Search parameters

        Returns:
            List of matching records (empty on error unless strict mode)

        Raises:
            WikiTreeAPIError: On API errors (only if strict mode)
        """
        params: dict[str, Any] = {
            "action": WikiTreeAction.SEARCH_PERSON.value,
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
            data = await self._make_wikitree_request(params)
            return self._parse_search_results(data)
        except RateLimitError:
            self._handle_error(RateLimitError("Rate limited"), "search")
            return []
        except Exception as e:
            self._handle_error(e, "search")
            return []

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a WikiTree profile by ID (WikiTree ID format: Surname-####).

        Args:
            record_id: WikiTree profile ID

        Returns:
            The profile or None (raises on error if strict mode)

        Raises:
            WikiTreeAPIError: On API errors (only if strict mode)
        """
        params = {
            "action": WikiTreeAction.GET_PERSON.value,
            "key": record_id,
            "fields": "Id,Name,FirstName,LastNameAtBirth,LastNameCurrent,BirthDate,DeathDate,"
                      "BirthLocation,DeathLocation,Gender,Father,Mother",
            "format": "json",
        }

        try:
            data = await self._make_wikitree_request(params)
            return self._parse_person(data, record_id)
        except RateLimitError:
            self._handle_error(RateLimitError("Rate limited"), f"get_record({record_id})")
            return None
        except Exception as e:
            self._handle_error(e, f"get_record({record_id})")
            return None

    # =========================================================================
    # Response Parsing
    # =========================================================================

    def _parse_search_results(self, data: dict | list) -> list[RawRecord]:
        """Parse WikiTree search results.

        Args:
            data: API response - can be:
                - list with [{'status': 0, 'matches': [...]}]
                - dict with {'searchPerson': [...]}
                - list of person dicts directly

        Returns:
            List of RawRecord objects
        """
        records = []
        results: list = []

        # Handle WikiTree's actual response format: [{'status': 0, 'matches': [...]}]
        if isinstance(data, list) and data:
            first_item = data[0]
            if isinstance(first_item, dict):
                if "matches" in first_item:
                    results = first_item.get("matches", [])
                elif "searchPerson" in first_item:
                    results = first_item.get("searchPerson", [])
                else:
                    results = data
            else:
                results = data
        elif isinstance(data, dict):
            if "matches" in data:
                results = data.get("matches", [])
            else:
                results = data.get("searchPerson", [])

        if isinstance(results, list):
            for person in results:
                record = self._person_to_record(person)
                if record:
                    records.append(record)

        return records

    def _parse_person(self, data: dict, record_id: str) -> RawRecord | None:
        """Parse a single person response."""
        person_data = data.get("getPerson", {}).get("person", {})
        if not person_data:
            return None
        return self._person_to_record(person_data, record_id)

    def _person_to_record(self, person: dict, record_id: str | None = None) -> RawRecord | None:
        """Convert WikiTree person to RawRecord."""
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

    # =========================================================================
    # Census Search Methods
    # =========================================================================

    async def get_biography(self, wikitree_id: str) -> str | None:
        """Fetch biography text for a WikiTree profile.

        Args:
            wikitree_id: WikiTree ID (e.g., "Durham-1234")

        Returns:
            Biography text or None if not found
        """
        params = {
            "action": WikiTreeAction.GET_BIO.value,
            "key": wikitree_id,
            "format": "json",
        }

        try:
            data = await self._make_wikitree_request(params)
            return self._extract_bio_from_response(data)
        except RateLimitError:
            self._handle_error(RateLimitError("Rate limited"), f"getBio({wikitree_id})")
            return None
        except Exception as e:
            self._handle_error(e, f"getBio({wikitree_id})")
            return None

    @staticmethod
    def _extract_bio_from_response(data: dict | list) -> str | None:
        """Extract biography text from API response."""
        # getBio returns [{wikitree_id: {..., bio: "..."}}]
        if isinstance(data, list) and data:
            person_data = data[0]
            if isinstance(person_data, dict):
                for value in person_data.values():
                    if isinstance(value, dict) and "bio" in value:
                        return value.get("bio", "")
        elif isinstance(data, dict):
            bio_data = data.get("getBio", {})
            if isinstance(bio_data, dict):
                return bio_data.get("bio", "")
        return None

    def extract_census_years(self, bio_text: str) -> list[int]:
        """Extract census years mentioned in biography text.

        Args:
            bio_text: WikiTree biography text

        Returns:
            List of census years found (sorted, deduplicated)
        """
        years: set[int] = set()

        for pattern in [CensusPatterns.YEAR_PATTERN, CensusPatterns.YEAR_SIMPLE, CensusPatterns.CENSUS_TEMPLATE]:
            for match in pattern.finditer(bio_text):
                year = int(match.group(1))
                if year in US_CENSUS_YEARS:
                    years.add(year)

        return sorted(years)

    def _extract_census_field(
        self,
        context: str,
        pattern: re.Pattern,
        group: int = 1,
    ) -> str:
        """Extract a single field from census context using a pattern."""
        match = pattern.search(context)
        if match:
            return match.group(group).strip()
        return ""

    def _extract_census_age(self, context: str) -> int | None:
        """Extract age from census context."""
        match = CensusPatterns.AGE.search(context)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_census_location(self, context: str, year: int) -> str:
        """Extract location from census context for a specific year."""
        match = CensusPatterns.LOCATION.search(context)
        if match:
            try:
                if int(match.group(1)) == year:
                    return match.group(2).strip()
            except (ValueError, IndexError):
                pass
        return ""

    def _build_census_record(self, year: int, bio_text: str) -> CensusRecord:
        """Build a CensusRecord for a specific year from biography text.

        This is a focused method extracted from the original 'god method'.
        """
        record = CensusRecord(year=year)

        # Find context around census mention
        context_pattern = CensusPatterns.get_context_pattern(year)
        context_match = context_pattern.search(bio_text)

        if not context_match:
            return record

        context = context_match.group(1)
        record.raw_text = context.strip()

        # Extract fields using dedicated methods
        record.location = self._extract_census_location(context, year)
        record.age = self._extract_census_age(context)
        record.occupation = self._extract_census_field(context, CensusPatterns.OCCUPATION)
        record.birthplace = self._extract_census_field(context, CensusPatterns.BIRTHPLACE)
        record.relationship = self._extract_census_field(context, CensusPatterns.RELATIONSHIP)
        record.household_head = self._extract_census_field(context, CensusPatterns.HEAD_OF_HOUSEHOLD)

        return record

    def extract_census_records(self, bio_text: str) -> list[CensusRecord]:
        """Extract structured census records from biography text.

        Args:
            bio_text: WikiTree biography text

        Returns:
            List of CensusRecord objects
        """
        years = self.extract_census_years(bio_text)
        return [self._build_census_record(year, bio_text) for year in years]

    async def get_person_census_history(self, wikitree_id: str) -> list[CensusRecord]:
        """Get all census appearances for a WikiTree profile.

        Args:
            wikitree_id: WikiTree ID

        Returns:
            List of CensusRecord objects for all censuses found
        """
        bio_text = await self.get_biography(wikitree_id)
        if not bio_text:
            return []
        return self.extract_census_records(bio_text)

    async def _fetch_biography_with_semaphore(self, wikitree_id: str) -> tuple[str, str | None]:
        """Fetch biography with semaphore for concurrent limiting.

        Returns:
            Tuple of (wikitree_id, bio_text or None)
        """
        async with self._get_semaphore():
            bio = await self.get_biography(wikitree_id)
            return (wikitree_id, bio)

    async def search_census(
        self,
        query: SearchQuery,
        census_year: int | None = None,
        state: str | None = None,
    ) -> list[RawRecord]:
        """Search WikiTree profiles that have census records.

        This method first searches for profiles matching the query,
        then fetches biographies concurrently and filters based on census data.

        Args:
            query: Search parameters (name, dates, etc.)
            census_year: Specific census year to filter for
            state: State to filter census results

        Returns:
            List of RawRecord objects with census data in extracted_fields
        """
        # First do a standard search
        base_results = await self.search(query)
        if not base_results:
            return []

        # Get wikitree IDs
        id_to_record = {
            r.extracted_fields.get("wikitree_id"): r
            for r in base_results
            if r.extracted_fields.get("wikitree_id")
        }

        # Fetch biographies concurrently with semaphore limiting
        tasks = [
            self._fetch_biography_with_semaphore(wt_id)
            for wt_id in id_to_record.keys()
        ]
        bio_results = await asyncio.gather(*tasks, return_exceptions=True)

        census_results: list[RawRecord] = []

        for result in bio_results:
            if isinstance(result, Exception):
                logger.debug("Biography fetch failed: %s", result)
                continue

            wikitree_id, bio_text = result
            if not bio_text:
                continue

            record = id_to_record.get(wikitree_id)
            if not record:
                continue

            census_records = self.extract_census_records(bio_text)
            if not census_records:
                continue

            # Filter by census year if specified
            if census_year:
                census_records = [c for c in census_records if c.year == census_year]

            # Filter by state if specified
            if state:
                state_lower = state.lower()
                census_records = [
                    c for c in census_records
                    if state_lower in c.location.lower() or state_lower in c.state.lower()
                ]

            if census_records:
                # Enrich the record with census data (using consistent dict format)
                record.extracted_fields["census_years"] = [c.year for c in census_records]
                record.extracted_fields["census_records"] = [c.to_dict() for c in census_records]
                record.record_type = "profile_with_census"
                census_results.append(record)

        return census_results

    async def search_by_census_location(
        self,
        census_year: int,
        state: str,
        county: str | None = None,
        surname: str | None = None,
    ) -> list[RawRecord]:
        """Search for profiles with census records in a specific location.

        Args:
            census_year: Census year (e.g., 1900)
            state: US state name
            county: Optional county name
            surname: Optional surname to filter

        Returns:
            List of matching profiles with census data
        """
        if census_year not in US_CENSUS_YEARS:
            logger.warning(
                "Invalid census year: %d. Valid years: %s",
                census_year, sorted(US_CENSUS_YEARS)
            )
            return []

        query = SearchQuery(birth_place=state, surname=surname)
        results = await self.search_census(query, census_year=census_year, state=state)

        # Further filter by county if specified
        if county:
            county_lower = county.lower()
            results = [
                r for r in results
                if any(
                    county_lower in str(c.get("location", "")).lower()
                    for c in r.extracted_fields.get("census_records", [])
                )
            ]

        return results

    async def _fetch_ancestor_census(
        self,
        ancestor: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Fetch census history for a single ancestor with semaphore limiting."""
        ancestor_id = ancestor.get("Name")
        if not ancestor_id:
            return None

        async with self._get_semaphore():
            census_records = await self.get_person_census_history(ancestor_id)

        return {
            "wikitree_id": ancestor_id,
            "name": f"{ancestor.get('FirstName', '')} {ancestor.get('LastNameAtBirth', '')}".strip(),
            "birth_date": ancestor.get("BirthDate"),
            "death_date": ancestor.get("DeathDate"),
            "birth_location": ancestor.get("BirthLocation"),
            "census_years": [c.year for c in census_records],
            "census_records": [c.to_dict() for c in census_records],
        }

    async def get_ancestors_with_census(
        self,
        wikitree_id: str,
        generations: int = 3,
    ) -> list[dict[str, Any]]:
        """Get ancestors with their census records.

        Fetches ancestor data and then concurrently fetches census records
        for each ancestor using semaphore-limited parallel requests.

        Args:
            wikitree_id: Starting WikiTree ID
            generations: Number of generations to fetch (max 10)

        Returns:
            List of dicts with person info and census records
        """
        generations = min(generations, 10)

        params = {
            "action": WikiTreeAction.GET_ANCESTORS.value,
            "key": wikitree_id,
            "depth": str(generations),
            "fields": "Id,Name,FirstName,LastNameAtBirth,BirthDate,DeathDate,BirthLocation",
            "format": "json",
        }

        try:
            data = await self._make_wikitree_request(params)
            ancestors_data = data.get("ancestors", []) if isinstance(data, dict) else []

            if not ancestors_data:
                return []

            # Fetch census data concurrently for all ancestors
            tasks = [
                self._fetch_ancestor_census(ancestor)
                for ancestor in ancestors_data
                if isinstance(ancestor, dict)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out failures and None results
            return [
                r for r in results
                if r is not None and not isinstance(r, Exception)
            ]

        except RateLimitError:
            self._handle_error(RateLimitError("Rate limited"), f"getAncestors({wikitree_id})")
            return []
        except Exception as e:
            self._handle_error(e, f"getAncestors({wikitree_id})")
            return []
