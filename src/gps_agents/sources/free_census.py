"""Free US Census sources that don't require login.

Provides access to publicly available census records and transcriptions
without authentication requirements.

Sources included:
- Census.gov historical records (1790-1950 digitized images)
- Census Finder (directory of free transcriptions)
- Free volunteer transcription sites
- State archives with free online census access
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# US Census years with federal census
CENSUS_YEARS = [1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950]

# Key fields to compare when verifying census matches
# Race is critical for distinguishing between individuals with same name/age
CENSUS_VERIFICATION_FIELDS = [
    "name",
    "race",  # Critical: W=White, B/N/C=Black/Negro/Colored, M=Mulatto, etc.
    "age",
    "birth_place",
    "relationship_to_head",
    "occupation",
    "address",
]

# Race codes used in US Census records (varies by year)
CENSUS_RACE_CODES = {
    # 1850-1870
    "W": "White",
    "B": "Black",
    "M": "Mulatto",
    # 1880-1930
    "N": "Negro",
    "C": "Colored",
    "In": "Indian",
    "Ch": "Chinese",
    "Jp": "Japanese",
    # 1940-1950
    "Negro": "African American",
    "White": "White",
}


class CensusFinderSource(BaseSource):
    """Census Finder - directory of free census transcriptions.

    Census Finder (censusfinder.com) maintains links to free census
    transcriptions organized by state and county. This source searches
    the directory and extracts relevant links.

    No authentication required.
    """

    name = "CensusFinder"
    base_url = "https://www.censusfinder.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Census Finder for census transcription links.

        Args:
            query: Search parameters (state, county, surname)

        Returns:
            List of census resource links
        """
        records: list[RawRecord] = []

        # Determine state from query
        state = self._extract_state(query)
        if not state:
            return []

        # Get state-specific census links page
        state_url = f"{self.base_url}/{state.lower().replace(' ', '-')}.htm"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(state_url)
                if resp.status_code != 200:
                    # Try alternate URL patterns
                    alt_url = f"{self.base_url}/census-{state.lower().replace(' ', '-')}.htm"
                    resp = await client.get(alt_url)
                    if resp.status_code != 200:
                        return []

                soup = BeautifulSoup(resp.text, "html.parser")
                records = self._parse_state_page(soup, state, query)

        except Exception as e:
            logger.debug(f"Census Finder search error: {e}")

        return records

    def _extract_state(self, query: SearchQuery) -> str | None:
        """Extract state from query parameters."""
        if query.state:
            return query.state

        if query.birth_place:
            # Try to extract state from place
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                return parts[-1].strip()
            return query.birth_place.strip()

        return None

    def _parse_state_page(
        self,
        soup: BeautifulSoup,
        state: str,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Parse Census Finder state page for census links."""
        records: list[RawRecord] = []
        surname_lower = (query.surname or "").lower()

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            text_lower = text.lower()

            # Skip navigation and non-census links
            if not href or len(text) < 5:
                continue
            if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#"]):
                continue

            # Check if it's a census-related link
            is_census = any(kw in text_lower or kw in href.lower() for kw in [
                "census", "1790", "1800", "1810", "1820", "1830", "1840",
                "1850", "1860", "1870", "1880", "1900", "1910", "1920",
                "1930", "1940", "1950", "population", "enumerat"
            ])

            if not is_census:
                continue

            # Build full URL
            full_url = href if href.startswith("http") else urljoin(self.base_url, href)

            # Check for surname match if searching for specific surname
            matches_surname = not surname_lower or surname_lower[0] in text_lower

            # Extract census year from text/href
            census_year = None
            for year in CENSUS_YEARS:
                if str(year) in text or str(year) in href:
                    census_year = year
                    break

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"censusfinder-{hash(full_url)}",
                    record_type="census_link",
                    url=full_url,
                    raw_data={"link_text": text, "state": state},
                    extracted_fields={
                        "resource_title": text,
                        "state": state,
                        "census_year": str(census_year) if census_year else "",
                        "note": "Free census transcription - no login required",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records[:50]  # Limit results

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - Census Finder is a directory."""
        return None


class CensusGovSource(BaseSource):
    """Census.gov historical records access.

    The US Census Bureau provides free access to historical census
    images and some transcriptions through their website.

    1950 Census: Fully indexed and searchable (free)
    Earlier censuses: Images available, some transcriptions

    No authentication required for basic access.
    """

    name = "CensusGov"
    base_url = "https://www.census.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Census.gov for historical census records.

        Primary focus is on 1950 census which is fully indexed.
        """
        records: list[RawRecord] = []

        # 1950 Census is the most accessible (fully indexed in 2022)
        if not query.birth_year or query.birth_year <= 1950:
            records_1950 = await self._search_1950_census(query)
            records.extend(records_1950)

        # Add links to older census images
        records.extend(self._get_historical_census_links(query))

        return records

    async def _search_1950_census(self, query: SearchQuery) -> list[RawRecord]:
        """Search the 1950 Census via Census.gov."""
        records: list[RawRecord] = []

        # Build search URL for 1950 census
        # Note: The actual search is handled by NARA, but Census.gov has landing pages
        search_params = []
        if query.given_name:
            search_params.append(f"first_name={quote_plus(query.given_name)}")
        if query.surname:
            search_params.append(f"last_name={quote_plus(query.surname)}")

        state = self._get_state_code(query)
        if state:
            search_params.append(f"state={state}")

        # Census.gov 1950 census landing
        landing_url = "https://www.census.gov/programs-surveys/decennial-census/decade/2020/2020-census-results/1950-census.html"

        # NARA 1950 census search (free, no login)
        nara_url = "https://1950census.archives.gov/search/"
        if search_params:
            nara_url += "?" + "&".join(search_params)

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"1950-census-search-{query.surname or 'unknown'}",
                record_type="census",
                url=nara_url,
                raw_data={"census_year": 1950, "query": query.model_dump()},
                extracted_fields={
                    "census_year": "1950",
                    "search_url": nara_url,
                    "note": "Free 1950 Census search - fully indexed, no login required",
                    "verification_fields": CENSUS_VERIFICATION_FIELDS,
                    "race_comparison_note": "Compare 'Color or Race' column (Negro/White/etc.) when verifying matches",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _get_historical_census_links(self, query: SearchQuery) -> list[RawRecord]:
        """Get links to historical census resources."""
        records: list[RawRecord] = []

        state = self._get_state_code(query)

        # Determine relevant census years based on birth year
        relevant_years = []
        if query.birth_year:
            for year in CENSUS_YEARS:
                if year >= query.birth_year - 5:  # Could appear in census after birth
                    relevant_years.append(year)
        else:
            relevant_years = [1940, 1930, 1920, 1910, 1900]  # Default common years

        for year in relevant_years[:5]:
            if year == 1950:
                continue  # Already handled

            # NARA has free access to 1940 census
            if year == 1940:
                url = "https://1940census.archives.gov/"
                if query.surname:
                    url += f"?ln={quote_plus(query.surname)}"
                if query.given_name:
                    url += f"&fn={quote_plus(query.given_name)}"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"1940-census-{query.surname or 'unknown'}",
                        record_type="census",
                        url=url,
                        raw_data={"census_year": 1940},
                        extracted_fields={
                            "census_year": "1940",
                            "search_url": url,
                            "note": "Free 1940 Census search via NARA - no login required",
                            "verification_fields": CENSUS_VERIFICATION_FIELDS,
                            "race_comparison_note": "Compare 'Color or Race' column (Negro/White/etc.) when verifying matches",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

            # Add FamilySearch collection URLs (browsable without login)
            fs_url = self._get_familysearch_browse_url(year, state)
            if fs_url:
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"{year}-census-browse-{state or 'us'}",
                        record_type="census_browse",
                        url=fs_url,
                        raw_data={"census_year": year, "state": state},
                        extracted_fields={
                            "census_year": str(year),
                            "browse_url": fs_url,
                            "note": f"Browse {year} Census images - free (searching requires FamilySearch account)",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

        return records

    def _get_state_code(self, query: SearchQuery) -> str | None:
        """Extract state code from query."""
        state_codes = {
            "california": "CA", "ca": "CA",
            "texas": "TX", "tx": "TX",
            "new york": "NY", "ny": "NY",
            "florida": "FL", "fl": "FL",
            "illinois": "IL", "il": "IL",
            "pennsylvania": "PA", "pa": "PA",
            "ohio": "OH", "oh": "OH",
            "georgia": "GA", "ga": "GA",
            "north carolina": "NC", "nc": "NC",
            "michigan": "MI", "mi": "MI",
        }

        state = None
        if query.state:
            state = query.state
        elif query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                state = parts[-1].strip()

        if state:
            return state_codes.get(state.lower(), state.upper()[:2])
        return None

    def _get_familysearch_browse_url(self, year: int, state: str | None) -> str | None:
        """Get FamilySearch browse URL for census images."""
        # FamilySearch collection IDs for census
        collections = {
            1790: "1803959",
            1800: "1804228",
            1810: "1803765",
            1820: "1803955",
            1830: "1803958",
            1840: "1786457",
            1850: "1401638",
            1860: "1473181",
            1870: "1438024",
            1880: "1417683",
            1900: "1325221",
            1910: "1727033",
            1920: "1488411",
            1930: "1810731",
            1940: "2000219",
        }

        collection_id = collections.get(year)
        if not collection_id:
            return None

        url = f"https://www.familysearch.org/search/collection/{collection_id}/browse"
        return url

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - Census.gov is primarily a search portal."""
        return None


class FreeCensusSource(BaseSource):
    """Aggregator for free census sources without login requirements.

    Combines multiple free census search tools and directories:
    - Census.gov / NARA (1940, 1950 fully indexed)
    - Census Finder (transcription directory)
    - US GenWeb census projects
    - State archives with free census access

    No authentication required for any source.
    """

    name = "FreeCensus"

    def __init__(self) -> None:
        super().__init__()
        self.census_finder = CensusFinderSource()
        self.census_gov = CensusGovSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all free census sources.

        Args:
            query: Search parameters

        Returns:
            Combined list of census records from all free sources
        """
        records: list[RawRecord] = []

        # Search Census.gov / NARA
        try:
            gov_records = await self.census_gov.search(query)
            records.extend(gov_records)
        except Exception as e:
            logger.debug(f"Census.gov search error: {e}")

        # Search Census Finder directory
        try:
            finder_records = await self.census_finder.search(query)
            records.extend(finder_records)
        except Exception as e:
            logger.debug(f"Census Finder search error: {e}")

        # Add state-specific free census resources
        state_records = await self._search_state_archives(query)
        records.extend(state_records)

        return records

    async def _search_state_archives(self, query: SearchQuery) -> list[RawRecord]:
        """Search state archives with free census access."""
        records: list[RawRecord] = []

        state = None
        if query.state:
            state = query.state.lower()
        elif query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                state = parts[-1].strip().lower()

        if not state:
            return []

        # State archives with free census access (no login)
        state_archives = {
            "california": {
                "url": "https://www.californiagenealogy.org/census/",
                "name": "California Genealogy Census",
            },
            "texas": {
                "url": "https://www.tsl.texas.gov/arc/genfirst.html",
                "name": "Texas State Library Genealogy",
            },
            "ohio": {
                "url": "https://www.ohiohistory.org/collections/genealogy/",
                "name": "Ohio History Genealogy",
            },
            "virginia": {
                "url": "https://www.lva.virginia.gov/public/guides/Genealogy.htm",
                "name": "Library of Virginia Genealogy",
            },
            "north carolina": {
                "url": "https://www.ncpedia.org/genealogy",
                "name": "NC Archives Genealogy",
            },
        }

        if state in state_archives:
            archive = state_archives[state]
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"state-archive-{state}",
                    record_type="census_resource",
                    url=archive["url"],
                    raw_data={"state": state, "archive_name": archive["name"]},
                    extracted_fields={
                        "resource_name": archive["name"],
                        "state": state.title(),
                        "note": "Free state archive - may include census records",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - this is an aggregator."""
        return None


# Convenience function to get all free census years
def get_free_census_years() -> list[int]:
    """Return census years with free online access (no login required).

    Returns:
        List of census years:
        - 1940: Fully indexed via NARA
        - 1950: Fully indexed via NARA (released 2022)
        - Earlier years: Images available, transcriptions via volunteers
    """
    return [1940, 1950]  # Fully indexed without login


def get_census_transcription_urls(state: str, year: int) -> list[str]:
    """Get URLs for free census transcriptions.

    Args:
        state: State name
        year: Census year

    Returns:
        List of URLs to check for transcriptions
    """
    state_lower = state.lower().replace(" ", "-")

    urls = [
        f"https://www.censusfinder.com/{state_lower}.htm",
        f"https://{state_lower}.usgenweb.org/census/",
        f"https://www.usgenweb.org/{state_lower}/census.html",
    ]

    if year == 1940:
        urls.insert(0, "https://1940census.archives.gov/")
    elif year == 1950:
        urls.insert(0, "https://1950census.archives.gov/search/")

    return urls


def normalize_census_race(race_value: str) -> str:
    """Normalize census race values for comparison.

    US Census race designations varied by year:
    - 1850-1870: W (White), B (Black), M (Mulatto)
    - 1880-1930: N or Negro, C or Colored, In (Indian), Ch (Chinese), Jp (Japanese)
    - 1940-1950: Full words (White, Negro, etc.)

    Args:
        race_value: Raw race value from census record

    Returns:
        Normalized race string for comparison
    """
    if not race_value:
        return "Unknown"

    race_upper = race_value.strip().upper()

    # Map to normalized values
    if race_upper in ("W", "WHITE"):
        return "White"
    elif race_upper in ("B", "BLACK", "N", "NEGRO", "C", "COLORED", "BL"):
        return "African American"
    elif race_upper in ("M", "MU", "MULATTO"):
        return "African American (Mulatto)"
    elif race_upper in ("IN", "INDIAN", "I"):
        return "Native American"
    elif race_upper in ("CH", "CHINESE"):
        return "Chinese"
    elif race_upper in ("JP", "JAPANESE"):
        return "Japanese"
    elif race_upper in ("MEX", "MEXICAN"):
        return "Mexican"
    elif race_upper in ("FIL", "FILIPINO"):
        return "Filipino"
    elif race_upper in ("HI", "HINDU"):
        return "Asian Indian"
    elif race_upper in ("KOR", "KOREAN"):
        return "Korean"
    else:
        return race_value.strip().title()


def compare_census_race(race1: str, race2: str) -> bool:
    """Compare two census race values for match.

    Args:
        race1: First race value
        race2: Second race value

    Returns:
        True if races match (after normalization)
    """
    norm1 = normalize_census_race(race1)
    norm2 = normalize_census_race(race2)

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # Handle Mulatto as subset of African American
    african_american_values = {"African American", "African American (Mulatto)"}
    if norm1 in african_american_values and norm2 in african_american_values:
        return True

    return False
