"""Tri-Valley (Livermore, Pleasanton, Dublin) genealogy sources.

Specialized local repositories for Alameda County's Tri-Valley region:
- Livermore-Amador Genealogical Society (L-AGS) - Master Index with 132,619+ entries
- Bunshah Index (Livermore Heritage Guild) - Newspaper index 1899-2002
- Pleasanton Weekly Lasting Memories - Recent obituaries
- Calisphere - UC digital collections

Coverage: Eastern Alameda County (Livermore, Pleasanton, Dublin, Murray Township)
Records: Cemetery, church, census, mortuary, obituaries, newspapers, local history
Access: FREE - Most resources don't require login
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote_plus, urlencode

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# L-AGS Database categories with record counts
LAGS_DATABASES = {
    "master_index": {
        "name": "Master Index of Eastern Alameda County History",
        "count": 132619,
        "description": "Comprehensive index of names from 98+ local history books and records",
    },
    "cemetery_livermore": {
        "name": "Livermore Cemeteries Tombstone Transcriptions",
        "count": 5800,
        "description": "Tombstone inscriptions from Livermore area cemeteries",
    },
    "cemetery_pleasanton_dublin": {
        "name": "Cemeteries of Pleasanton and Dublin",
        "count": 4668,
        "description": "Tombstone inscriptions from Pleasanton and Dublin cemeteries",
    },
    "roselawn_burials": {
        "name": "Roselawn Cemetery Burial Records",
        "count": 2252,
        "description": "Burial records from Roselawn Cemetery, Livermore",
    },
    "memory_gardens_burials": {
        "name": "Memory Gardens Burial Records",
        "count": 1183,
        "description": "Burial records from Memory Gardens Cemetery",
    },
    "st_michael_burials": {
        "name": "St. Michael Cemetery Burial Records",
        "count": 2560,
        "description": "Burial records from St. Michael Catholic Cemetery",
    },
    "graham_mortuary": {
        "name": "Robert Graham Mortuary Records",
        "count": 358,
        "description": "Mortuary records from Robert Graham Mortuary, Livermore",
    },
    "callaghan_mortuary": {
        "name": "Callaghan Mortuary Records",
        "count": 1477,
        "description": "Mortuary records from Callaghan Mortuary, Livermore",
    },
    "early_obituaries": {
        "name": "Early Livermore Obituary Information",
        "count": 1712,
        "description": "Pre-1905 obituaries from Livermore newspapers",
    },
    "pleasanton_times_obits": {
        "name": "Pleasanton Times Obituaries Index",
        "count": 146,
        "date_range": "1928-1934",
        "description": "Death notices and obituaries from Pleasanton Times",
    },
    "first_presbyterian": {
        "name": "First Presbyterian Church, Livermore",
        "count": 1119,
        "description": "Church records including baptisms, marriages, deaths",
    },
    "asbury_methodist": {
        "name": "Asbury United Methodist Church, Livermore",
        "count": 621,
        "description": "Church records from Asbury Methodist",
    },
    "presbyterian_pleasanton": {
        "name": "Presbyterian Church of Pleasanton",
        "count": 1135,
        "description": "Church records from Pleasanton Presbyterian",
    },
    "census_1870": {
        "name": "1870 Murray Township Federal Census",
        "count": 2400,
        "description": "Transcribed 1870 census for Murray Township",
    },
    "census_1880": {
        "name": "1880 Murray Township Federal Census",
        "count": 4370,
        "description": "Transcribed 1880 census for Murray Township",
    },
    "luhs_alumni": {
        "name": "Livermore Union High School Alumni",
        "count": 5748,
        "date_range": "1893-1969",
        "description": "Alumni roster from LUHS",
    },
    "alameda_deaths_c": {
        "name": "Alameda County Deaths, Book C",
        "count": 5217,
        "date_range": "1889-1894",
        "description": "County death records",
    },
    "alameda_deaths_d": {
        "name": "Alameda County Deaths, Book D",
        "count": 6655,
        "date_range": "1895-1901",
        "description": "County death records",
    },
    "schellens_papers": {
        "name": "Schellens Papers Index",
        "count": 17219,
        "description": "Index to the Schellens family papers collection",
    },
    "freitas_collection": {
        "name": "Mildred E. Freitas Collection",
        "count": 11000,
        "date_range": "1899-1913",
        "description": "Index to Livermore Herald articles",
    },
}


class LAGSSource(BaseSource):
    """Livermore-Amador Genealogical Society database search.

    L-AGS maintains extensive genealogical databases for Eastern Alameda County,
    including the Master Index with 132,619+ entries from 98 local history sources.

    Databases include:
    - Cemetery records (Roselawn, Memory Gardens, St. Michael)
    - Mortuary records (Graham, Callaghan)
    - Church records (Presbyterian, Methodist, Episcopal)
    - Census transcriptions (1870, 1880 Murray Township)
    - School alumni records (LUHS 1893-1969)
    - County death records (1889-1901)

    Note: L-AGS databases are web-based but may require manual navigation.
    This adapter provides search URLs and database information.
    """

    name = "LAGS"
    base_url = "http://www.l-ags.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search L-AGS databases.

        Note: L-AGS databases use various interfaces. This returns
        database information and search URLs for manual access.
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        # Determine which databases are most relevant
        relevant_dbs = self._get_relevant_databases(query)

        for db_key, db_info in relevant_dbs.items():
            record = RawRecord(
                source=self.name,
                record_id=f"lags-{db_key}",
                record_type="database_reference",
                url=f"{self.base_url}/databases.html",
                raw_data={
                    "database": db_key,
                    "info": db_info,
                    "search_surname": surname,
                    "search_given": given_name,
                },
                extracted_fields={
                    "database_name": db_info["name"],
                    "record_count": str(db_info["count"]),
                    "description": db_info["description"],
                    "date_range": db_info.get("date_range", "Various"),
                    "search_tip": f"Search for '{surname}' in the {db_info['name']}",
                    "access_note": "FREE online database - visit L-AGS website",
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        # Add Master Index as primary recommendation
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id="lags-master-index-search",
                record_type="search_recommendation",
                url=f"{self.base_url}/databases.html",
                raw_data={
                    "query": query.model_dump(),
                    "recommended_database": "master_index",
                },
                extracted_fields={
                    "recommendation": "Start with L-AGS Master Index",
                    "database_name": "Master Index of Eastern Alameda County History",
                    "record_count": "132,619+",
                    "description": (
                        "Comprehensive index covering 98+ local history books and records. "
                        "Best starting point for Tri-Valley genealogy research."
                    ),
                    "coverage": "Livermore, Pleasanton, Dublin, Murray Township",
                    "search_surname": surname,
                },
                accessed_at=datetime.now(UTC),
            ),
        )

        return records

    def _get_relevant_databases(
        self,
        query: SearchQuery,
    ) -> dict[str, dict[str, Any]]:
        """Determine which L-AGS databases are most relevant for a query."""
        relevant: dict[str, dict[str, Any]] = {}

        # Always include Master Index
        relevant["master_index"] = LAGS_DATABASES["master_index"]

        # Check record types
        record_types = [rt.lower() for rt in query.record_types] if query.record_types else []

        if not record_types or "death" in record_types or "obituary" in record_types:
            relevant["early_obituaries"] = LAGS_DATABASES["early_obituaries"]
            relevant["pleasanton_times_obits"] = LAGS_DATABASES["pleasanton_times_obits"]
            relevant["alameda_deaths_c"] = LAGS_DATABASES["alameda_deaths_c"]
            relevant["alameda_deaths_d"] = LAGS_DATABASES["alameda_deaths_d"]

        if not record_types or "burial" in record_types or "cemetery" in record_types:
            relevant["cemetery_livermore"] = LAGS_DATABASES["cemetery_livermore"]
            relevant["cemetery_pleasanton_dublin"] = LAGS_DATABASES["cemetery_pleasanton_dublin"]
            relevant["roselawn_burials"] = LAGS_DATABASES["roselawn_burials"]
            relevant["st_michael_burials"] = LAGS_DATABASES["st_michael_burials"]

        if not record_types or "census" in record_types:
            relevant["census_1870"] = LAGS_DATABASES["census_1870"]
            relevant["census_1880"] = LAGS_DATABASES["census_1880"]

        if not record_types or "church" in record_types:
            relevant["first_presbyterian"] = LAGS_DATABASES["first_presbyterian"]
            relevant["asbury_methodist"] = LAGS_DATABASES["asbury_methodist"]
            relevant["presbyterian_pleasanton"] = LAGS_DATABASES["presbyterian_pleasanton"]

        return relevant

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """L-AGS requires manual database navigation."""
        return None


class BunshahIndexSource(BaseSource):
    """Barbara Bunshah Selective Subject Index to Tri-Valley Newspapers.

    The Bunshah Index is the "gold standard" for searching Livermore-area
    newspapers. It provides a subject-based index for:
    - The Enterprise
    - The Independent
    - Livermore Herald
    - Herald and News
    - Tri-Valley Herald

    Coverage: 1899-2002 (in multiple PDF volumes)
    Format: Searchable PDF files (large - requires download)
    Access: FREE via Livermore Heritage Guild or Livermore Public Library

    Note: Index provides citations (date, page) - full text requires
    microfilm access at the library.
    """

    name = "BunshahIndex"
    base_url = "https://www.lhg.org"

    # Known index volumes
    INDEX_VOLUMES: ClassVar[list[dict[str, Any]]] = [
        {
            "name": "Bunshah Index 1899-1929",
            "url": "https://www.lhg.org/Documents/General/Bunshah_Index_1899-1929.pdf",
            "pages": 2616,
            "years": (1899, 1929),
        },
        {
            "name": "Bunshah Index 1930-1965",
            "url": "https://www.lhg.org/Documents/General/Bunshah_Index_1930-1965.pdf",
            "pages": 8906,
            "years": (1930, 1965),
        },
    ]

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Provide Bunshah Index access information.

        The Bunshah Index is PDF-based and requires manual search.
        This adapter provides download links and usage guidance.
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Determine which volumes are relevant based on date range
        relevant_volumes = self._get_relevant_volumes(query)

        for vol in relevant_volumes:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"bunshah-{vol['years'][0]}-{vol['years'][1]}",
                    record_type="index_reference",
                    url=vol["url"],
                    raw_data=vol,
                    extracted_fields={
                        "index_name": vol["name"],
                        "coverage": f"{vol['years'][0]}-{vol['years'][1]}",
                        "pages": str(vol["pages"]),
                        "format": "Searchable PDF (large file)",
                        "newspapers": "Enterprise, Independent, Livermore Herald, Tri-Valley Herald",
                        "search_tip": f"Download PDF and search (Ctrl+F) for '{surname}'",
                        "note": "Index only - full articles require library microfilm",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add library microfilm information
        records.append(
            RawRecord(
                source=self.name,
                record_id="bunshah-microfilm-info",
                record_type="access_info",
                url="https://library.livermoreca.gov/digital-library/digital-library/local-links/history-and-genealogy",
                raw_data={"type": "microfilm_access"},
                extracted_fields={
                    "resource": "Livermore Public Library - Newspaper Microfilm",
                    "description": (
                        "Once you find a citation in the Bunshah Index, "
                        "visit the Livermore Civic Center Library to view the "
                        "full article on microfilm."
                    ),
                    "location": "Livermore Civic Center Library",
                    "alternative": "Livermore Heritage Guild History Center (Carnegie Building)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _get_relevant_volumes(self, query: SearchQuery) -> list[dict[str, Any]]:
        """Determine which index volumes are relevant for the query."""
        # If death year specified, filter to relevant volumes
        if query.death_year:
            year = query.death_year
            return [
                vol
                for vol in self.INDEX_VOLUMES
                if vol["years"][0] <= year <= vol["years"][1]
            ]

        # Default to all volumes
        return self.INDEX_VOLUMES

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """Bunshah Index is PDF-based - no individual record retrieval."""
        return None


class PleasantonWeeklySource(BaseSource):
    """Pleasanton Weekly Lasting Memories obituary search.

    The Pleasanton Weekly maintains "Lasting Memories", a searchable
    online obituary directory for the Tri-Valley area.

    Coverage: Early 2000s to present
    Content: Full obituaries with photos, life stories, memorials
    Access: FREE - No login required
    """

    name = "PleasantonWeekly"
    base_url = "https://obituaries.pleasantonweekly.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Pleasanton Weekly Lasting Memories.

        Args:
            query: Search parameters

        Returns:
            List of obituary records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        # Build search URL
        search_params = {
            "process": "2",
            "past_options": "all",  # Search all time
            "ob": "sub",  # Sort by submission date
        }

        if given_name:
            search_params["keyword"] = f"{given_name} {surname}"
        else:
            search_params["keyword"] = surname

        search_url = f"{self.base_url}/obituaries/search.php?{urlencode(search_params)}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.3.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_search_results(soup)

        except httpx.HTTPError as e:
            logger.debug(f"Pleasanton Weekly search error: {e}")

        # Add manual search URL
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"pw-search-{surname}",
                record_type="search_url",
                url=search_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "Pleasanton Weekly Lasting Memories",
                    "search_url": search_url,
                    "coverage": "Tri-Valley area (Pleasanton, Livermore, Dublin)",
                    "date_range": "Early 2000s to present",
                    "content_type": "Full obituaries with photos and memorials",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _parse_search_results(self, soup: BeautifulSoup) -> list[RawRecord]:
        """Parse Lasting Memories search results."""
        records: list[RawRecord] = []

        # Look for obituary links
        obit_links = soup.select("a[href*='/obituaries/']")

        for link in obit_links[:20]:
            try:
                href = link.get("href", "")
                if not href or "search" in href.lower():
                    continue

                url = href if href.startswith("http") else f"{self.base_url}{href}"
                text = link.get_text(" ", strip=True)

                if not text or len(text) < 5:
                    continue

                # Extract name and dates
                extracted = self._extract_obituary_info(text)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"pw-{hash(url)}",
                        record_type="obituary",
                        url=url,
                        raw_data={"text": text[:500]},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse PW result: {e}")
                continue

        return records

    def _extract_obituary_info(self, text: str) -> dict[str, str | None]:
        """Extract obituary information from text."""
        extracted: dict[str, str | None] = {}

        # Name is usually first
        name_match = re.match(r"([A-Za-z\s\.\-']+?)(?:\d|,|\()", text)
        if name_match:
            extracted["full_name"] = name_match.group(1).strip()

        # Year range pattern
        year_range = re.search(r"(\d{4})\s*[-–]\s*(\d{4})", text)
        if year_range:
            extracted["birth_year"] = year_range.group(1)
            extracted["death_year"] = year_range.group(2)

        return extracted

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """Retrieve a specific obituary - requires URL."""
        return None


class CalisphereSource(BaseSource):
    """Calisphere - UC digital collections search.

    Calisphere provides access to 2,175,000+ digitized items from
    California's libraries, archives, and museums.

    For Tri-Valley research, useful for:
    - Land grants (Diseños)
    - Early maps
    - Historical photographs
    - Lawrence Livermore National Laboratory archives
    - UC Berkeley and other campus archives

    API: Solr-based search API available
    Access: FREE - No login required
    """

    name = "Calisphere"
    base_url = "https://calisphere.org"
    api_url = "https://solr.calisphere.org/solr/query/"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Calisphere collections.

        Args:
            query: Search parameters

        Returns:
            List of records from California digital collections
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        # Build search query
        search_term = f"{given_name} {surname}".strip() if given_name else surname

        # Try API search first
        try:
            api_records = await self._search_api(search_term, query)
            records.extend(api_records)
        except Exception as e:
            logger.debug(f"Calisphere API error: {e}")

        # Add web search URL
        web_search_url = f"{self.base_url}/?q={quote_plus(search_term)}"

        records.append(
            RawRecord(
                source=self.name,
                record_id=f"calisphere-search-{surname}",
                record_type="search_url",
                url=web_search_url,
                raw_data={"query": query.model_dump()},
                extracted_fields={
                    "search_type": "Calisphere Digital Collections",
                    "search_url": web_search_url,
                    "description": (
                        "UC digital collections with 2.1M+ items from California "
                        "libraries, archives, and museums"
                    ),
                    "useful_for": "Photos, maps, land grants, LLNL archives, newspapers",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add Tri-Valley specific search
        tri_valley_terms = ["Livermore", "Pleasanton", "Dublin", "Murray Township"]
        for location in tri_valley_terms:
            location_search = f"{search_term} {location}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"calisphere-{location.lower()}-{surname}",
                    record_type="search_url",
                    url=f"{self.base_url}/?q={quote_plus(location_search)}",
                    raw_data={"location_filter": location},
                    extracted_fields={
                        "search_type": f"Calisphere - {location} focused",
                        "search_url": f"{self.base_url}/?q={quote_plus(location_search)}",
                        "search_term": location_search,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def _search_api(
        self,
        search_term: str,
        query: SearchQuery,  # noqa: ARG002 - reserved for future filtering
    ) -> list[RawRecord]:
        """Search Calisphere via Solr API."""
        records: list[RawRecord] = []

        params = {
            "q": search_term,
            "rows": 20,
            "wt": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.api_url, params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    docs = data.get("response", {}).get("docs", [])

                    for doc in docs:
                        record_id = doc.get("id", f"cs-{hash(str(doc))}")
                        title = doc.get("title", ["Unknown"])[0] if isinstance(doc.get("title"), list) else doc.get("title", "Unknown")

                        records.append(
                            RawRecord(
                                source=self.name,
                                record_id=record_id,
                                record_type=doc.get("type_ss", ["document"])[0] if isinstance(doc.get("type_ss"), list) else "document",
                                url=f"{self.base_url}/item/{record_id}/",
                                raw_data=doc,
                                extracted_fields={
                                    "title": title,
                                    "collection": doc.get("collection_name", [""])[0] if isinstance(doc.get("collection_name"), list) else "",
                                    "institution": doc.get("repository_name", [""])[0] if isinstance(doc.get("repository_name"), list) else "",
                                    "date": doc.get("date", [""])[0] if isinstance(doc.get("date"), list) else "",
                                },
                                accessed_at=datetime.now(UTC),
                            )
                        )

        except Exception as e:
            logger.debug(f"Calisphere API search failed: {e}")

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """Retrieve a specific Calisphere item."""
        return None


class TriValleyGenealogySource(BaseSource):
    """Aggregator for Tri-Valley genealogy sources.

    Combines multiple specialized local repositories:
    - L-AGS databases (132,619+ indexed names)
    - Bunshah Index (newspapers 1899-2002)
    - Pleasanton Weekly obituaries
    - Calisphere UC collections

    Coverage: Livermore, Pleasanton, Dublin, Murray Township
    (Eastern Alameda County, California)
    """

    name = "TriValleyGenealogy"

    def __init__(self) -> None:
        super().__init__()
        self.lags = LAGSSource()
        self.bunshah = BunshahIndexSource()
        self.pleasanton_weekly = PleasantonWeeklySource()
        self.calisphere = CalisphereSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Tri-Valley sources."""
        records: list[RawRecord] = []

        # Search all component sources
        sources = [
            ("L-AGS", self.lags),
            ("Bunshah", self.bunshah),
            ("PleasantonWeekly", self.pleasanton_weekly),
            ("Calisphere", self.calisphere),
        ]

        for source_name, source in sources:
            try:
                source_records = await source.search(query)
                records.extend(source_records)
            except Exception as e:
                logger.debug(f"{source_name} search error: {e}")

        # Add additional Tri-Valley resources
        surname = query.surname or ""
        additional_resources = [
            {
                "name": "Livermore Heritage Guild Photo Archive",
                "url": "https://www.lhg.org/Documents/index.html",
                "description": "5,000+ historic photos documenting Livermore 1869-mid 20th century",
            },
            {
                "name": "Museum on Main (California Revealed)",
                "url": f"https://archive.org/search?query={quote_plus(f'Pleasanton {surname}')}",
                "description": "Pleasanton Times archives and oral histories on Internet Archive",
            },
            {
                "name": "Livermore Public Library - History & Genealogy",
                "url": "https://library.livermoreca.gov/digital-library/digital-library/local-links/history-and-genealogy",
                "description": "Local history resources and newspaper microfilm access",
            },
        ]

        for resource in additional_resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"tv-{hash(resource['name'])}",
                    record_type="resource_link",
                    url=resource["url"],
                    raw_data=resource,
                    extracted_fields={
                        "resource_name": resource["name"],
                        "search_url": resource["url"],
                        "description": resource["description"],
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """Aggregator doesn't retrieve individual records."""
        return None
