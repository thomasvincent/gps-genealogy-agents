"""National Archives (NARA) census browsing source.

The National Archives provides free access to digitized census images
without login. Better for browsing known locations than searching by name.

Features:
- Free access, no login required
- Full images for 1790-1950 censuses
- Browse by state, county, and enumeration district
- Less indexed than FamilySearch but fully free

Note: US census data from 1960+ isn't public (72-year privacy rule).
- 1950 Census: Released April 2022
- 1960 Census: Releases April 2032
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote_plus

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# NARA catalog IDs for census records
NARA_CENSUS_CATALOG = {
    1790: "566718",
    1800: "566718",
    1810: "566718",
    1820: "566718",
    1830: "566718",
    1840: "566718",
    1850: "653179",
    1860: "653187",
    1870: "653188",
    1880: "653189",
    1890: "653190",  # Most destroyed by fire
    1900: "653191",
    1910: "653199",
    1920: "653209",
    1930: "653210",
    1940: "653211",
    1950: "653212",
}


class NARACensusSource(BaseSource):
    """National Archives Census browsing source.

    Provides direct links to digitized census images at archives.gov.
    No login required. Better for browsing known locations.

    For name-indexed searching, use FamilySearchNoLoginSource instead.
    """

    name = "NARACensus"
    base_url = "https://www.archives.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Generate NARA census browsing URLs.

        Args:
            query: Search parameters

        Returns:
            List of browsing URLs and research guides
        """
        records: list[RawRecord] = []

        # Main census research page
        records.append(
            RawRecord(
                source=self.name,
                record_id="nara-census-main",
                record_type="resource_link",
                url=f"{self.base_url}/research/census",
                raw_data={},
                extracted_fields={
                    "resource_title": "NARA Census Research Guide",
                    "description": "National Archives census research starting point",
                    "note": "Free browsing of census images - no login required",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Determine relevant census years
        relevant_years = self._get_relevant_years(query)

        for year in relevant_years:
            if year not in NARA_CENSUS_CATALOG:
                continue

            # 1940 Census has dedicated search portal
            if year == 1940:
                search_url = "https://1940census.archives.gov/"
                if query.surname:
                    search_url += f"?ln={quote_plus(query.surname)}"
                    if query.given_name:
                        search_url += f"&fn={quote_plus(query.given_name)}"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id="nara-1940-search",
                        record_type="census",
                        url=search_url,
                        raw_data={"year": 1940},
                        extracted_fields={
                            "census_year": "1940",
                            "search_url": search_url,
                            "note": "Fully indexed 1940 Census - free search",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

            # 1950 Census has dedicated search portal
            elif year == 1950:
                search_url = "https://1950census.archives.gov/search/"
                if query.surname:
                    params = [f"ln={quote_plus(query.surname)}"]
                    if query.given_name:
                        params.append(f"fn={quote_plus(query.given_name)}")
                    if query.state:
                        params.append(f"state={self._get_state_code(query.state)}")
                    search_url += "?" + "&".join(params)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id="nara-1950-search",
                        record_type="census",
                        url=search_url,
                        raw_data={"year": 1950},
                        extracted_fields={
                            "census_year": "1950",
                            "search_url": search_url,
                            "note": "Fully indexed 1950 Census - free search (released April 2022)",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

            # Older censuses - catalog browsing
            else:
                catalog_id = NARA_CENSUS_CATALOG[year]
                catalog_url = f"https://catalog.archives.gov/id/{catalog_id}"

                # Add state browsing URL if state is known
                state = self._extract_state(query)
                browse_note = f"Browse {year} Census images by state/county"
                if state:
                    browse_note = f"Browse {year} Census for {state}"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"nara-{year}-catalog",
                        record_type="census_browse",
                        url=catalog_url,
                        raw_data={"year": year, "catalog_id": catalog_id},
                        extracted_fields={
                            "census_year": str(year),
                            "browse_url": catalog_url,
                            "note": browse_note,
                            "tip": "Navigate by state, county, then enumeration district",
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

        # Add 72-year rule note for context
        records.append(
            RawRecord(
                source=self.name,
                record_id="nara-72-year-rule",
                record_type="metadata",
                url="https://www.archives.gov/research/census/when-records-released",
                raw_data={},
                extracted_fields={
                    "info": "Census 72-Year Privacy Rule",
                    "note": "US Census records sealed for 72 years. 1960 Census releases April 2032.",
                    "available_censuses": "1790-1950",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _get_relevant_years(self, query: SearchQuery) -> list[int]:
        """Get census years relevant to the query."""
        if not query.birth_year:
            return [1940, 1930, 1920, 1910, 1900, 1950]

        years = []
        for year in [1950, 1940, 1930, 1920, 1910, 1900, 1880, 1870, 1860, 1850]:
            # Person could appear in census if alive during that year
            if query.birth_year - 5 <= year <= query.birth_year + 80:
                years.append(year)

        return years[:6]  # Limit to 6 most relevant

    def _extract_state(self, query: SearchQuery) -> str | None:
        """Extract state from query."""
        if query.state:
            return query.state
        if query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                return parts[-1].strip()
        return None

    def _get_state_code(self, state: str) -> str:
        """Convert state name to code."""
        codes = {
            "california": "CA", "texas": "TX", "new york": "NY",
            "florida": "FL", "illinois": "IL", "pennsylvania": "PA",
            "ohio": "OH", "georgia": "GA", "north carolina": "NC",
            "michigan": "MI", "arkansas": "AR", "alabama": "AL",
        }
        return codes.get(state.lower(), state.upper()[:2])

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class InternetArchiveCensusSource(BaseSource):
    """Internet Archive census volumes source.

    Search archive.org for digitized census volumes.
    Full PDFs available without login, but limited indexing.

    Best for: Browsing known locations when other sources fail.
    """

    name = "InternetArchiveCensus"
    base_url = "https://archive.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Internet Archive for census volumes.

        Args:
            query: Search parameters

        Returns:
            List of search URLs for census volumes
        """
        records: list[RawRecord] = []

        # Determine relevant census years
        if query.birth_year:
            years = [y for y in [1940, 1930, 1920, 1910, 1900, 1880, 1870]
                     if query.birth_year - 5 <= y <= query.birth_year + 80]
        else:
            years = [1940, 1930, 1920]

        for year in years[:4]:
            # Build search query
            search_terms = [f'"US Census {year}"']

            state = self._extract_state(query)
            if state:
                search_terms.append(f'"{state}"')

            search_query = " ".join(search_terms)
            search_url = f"{self.base_url}/search?query={quote_plus(search_query)}"

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ia-census-{year}",
                    record_type="search_url",
                    url=search_url,
                    raw_data={"year": year, "query": search_query},
                    extracted_fields={
                        "census_year": str(year),
                        "search_url": search_url,
                        "note": "Digitized census volumes - viewable/downloadable PDFs",
                        "tip": "Limited indexing - best for browsing known locations",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add general genealogy search
        if query.surname:
            genealogy_search = f'"{query.surname}" genealogy'
            if query.given_name:
                genealogy_search = f'"{query.given_name} {query.surname}" genealogy'

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ia-genealogy-{query.surname}",
                    record_type="search_url",
                    url=f"{self.base_url}/search?query={quote_plus(genealogy_search)}",
                    raw_data={"surname": query.surname},
                    extracted_fields={
                        "search_type": "Genealogy Books/Documents",
                        "note": "Search digitized genealogy books and documents",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _extract_state(self, query: SearchQuery) -> str | None:
        """Extract state from query."""
        if query.state:
            return query.state
        if query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                return parts[-1].strip()
        return None

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class LibraryAccessSource(BaseSource):
    """Library-based genealogy database access source.

    Many public libraries offer free access to:
    - Ancestry Library Edition (in-library use)
    - HeritageQuest (remote access with library card)
    - ProQuest Historical Newspapers
    - Fold3 (some libraries)

    This source provides information about library access options.
    """

    name = "LibraryAccess"
    base_url = "https://www.worldcat.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Generate library access information.

        Args:
            query: Search parameters

        Returns:
            List of library resource links
        """
        records: list[RawRecord] = []

        # HeritageQuest info (most common remote access)
        records.append(
            RawRecord(
                source=self.name,
                record_id="library-heritagequest",
                record_type="resource_info",
                url="https://www.proquest.com/products-services/heritagequest.html",
                raw_data={},
                extracted_fields={
                    "resource_title": "HeritageQuest Online",
                    "access_method": "Free with library card (remote access)",
                    "content": "US Census 1790-1940, genealogy books, PERSI, Freedman's Bank",
                    "tip": "Check your local library website for 'genealogy databases'",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Ancestry Library Edition info
        records.append(
            RawRecord(
                source=self.name,
                record_id="library-ancestry",
                record_type="resource_info",
                url="https://www.ancestrylibrary.com/",
                raw_data={},
                extracted_fields={
                    "resource_title": "Ancestry Library Edition",
                    "access_method": "In-library use only (no remote access)",
                    "content": "Full Ancestry.com database access",
                    "tip": "Visit your local library to use - most large libraries have it",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # WorldCat library finder
        location = query.birth_place or query.state or ""
        if location:
            library_search = f"https://www.worldcat.org/libraries?q={quote_plus(location)}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="library-finder",
                    record_type="resource_link",
                    url=library_search,
                    raw_data={"location": location},
                    extracted_fields={
                        "resource_title": "Find Libraries Near You",
                        "search_url": library_search,
                        "note": "Find libraries with genealogy resources",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # FamilySearch Centers (free access to premium resources)
        records.append(
            RawRecord(
                source=self.name,
                record_id="familysearch-centers",
                record_type="resource_info",
                url="https://www.familysearch.org/en/centers",
                raw_data={},
                extracted_fields={
                    "resource_title": "FamilySearch Centers",
                    "access_method": "Free in-person access",
                    "content": "Access to Ancestry, Findmypast, MyHeritage, Fold3, and more",
                    "tip": "Free access to premium genealogy sites at FamilySearch Centers (many LDS churches)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Allen County Public Library (premier genealogy collection)
        records.append(
            RawRecord(
                source=self.name,
                record_id="allen-county-library",
                record_type="resource_link",
                url="https://acpl.lib.in.us/genealogy",
                raw_data={},
                extracted_fields={
                    "resource_title": "Allen County Public Library Genealogy Center",
                    "description": "Second largest genealogy collection in North America",
                    "note": "Many free online resources and research assistance",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
