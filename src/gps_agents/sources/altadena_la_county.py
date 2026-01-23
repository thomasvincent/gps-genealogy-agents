"""Altadena and Los Angeles County genealogy sources.

Regional archives for LA County with focus on Altadena/Pasadena foothill communities:
- Altadena Historical Society - local history, photographs, oral histories
- LAPL History & Genealogy Department - LA city directories, newspapers, vital records
- Huntington Library - Early California Population Project, manuscript collections
- USC Digital Library - LA Examiner photos, regional newspaper archives
- LA County Registrar-Recorder - vital records access information

Coverage: Los Angeles County, California (1850-present)
Records: Photographs, newspapers, vital records, city directories, manuscripts
Access: Mixed - some free online, others require library card or visit
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote_plus

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# Altadena Historical Society resources
ALTADENA_RESOURCES: dict[str, dict[str, Any]] = {
    "photo_collection": {
        "name": "Altadena Historical Society Photo Archive",
        "description": "Digitized photographs of Altadena families, homes, and events",
        "coverage": "1880s-present",
        "access": "Some on Calisphere, others require visit",
        "url": "https://altadenahistoricalsociety.org/",
    },
    "oral_histories": {
        "name": "Altadena Oral History Project",
        "description": "Recorded interviews with longtime Altadena residents",
        "coverage": "20th century community history",
        "access": "Available at AHS archives",
        "url": "https://altadenahistoricalsociety.org/",
    },
    "newspapers": {
        "name": "Altadena News Collection",
        "description": "Local newspaper clippings and articles",
        "coverage": "Altadena community news",
        "access": "On-site research",
        "url": "https://altadenahistoricalsociety.org/",
    },
    "mount_lowe": {
        "name": "Mount Lowe Railway Digital Collection",
        "description": "Historic railway, Rubio Canyon, hotels, resort ephemera",
        "coverage": "1893-1938 (railway operation era)",
        "access": "Free via AHS digital collections",
        "url": "https://altadenahistoricalsociety.org/collections/mount-lowe/",
    },
    "echo_newsletters": {
        "name": "Echo Newsletters Archive",
        "description": "AHS quarterly newsletters with local history articles",
        "coverage": "2009-present",
        "access": "Free online archive",
        "url": "https://altadenahistoricalsociety.org/the-echo/",
    },
    "crank_collection": {
        "name": "Crank Family Collection",
        "description": "Papers and photographs of the Crank family",
        "coverage": "Early Altadena pioneer family",
        "access": "On-site research at AHS archives",
        "url": "https://altadenahistoricalsociety.org/",
    },
    "brigden_collection": {
        "name": "Brigden Family Collection",
        "description": "Papers and photographs of the Brigden family",
        "coverage": "Early Altadena family",
        "access": "On-site research at AHS archives",
        "url": "https://altadenahistoricalsociety.org/",
    },
    "whitaker_collection": {
        "name": "Whitaker Family Collection",
        "description": "Papers and photographs of the Whitaker family",
        "coverage": "Early Altadena family",
        "access": "On-site research at AHS archives",
        "url": "https://altadenahistoricalsociety.org/",
    },
}


# Altadena Heritage Architectural Database (AHAD)
ALTADENA_AHAD: dict[str, dict[str, Any]] = {
    "ahad_database": {
        "name": "Altadena Heritage Architectural Database (AHAD)",
        "description": "Searchable database of historic Altadena structures by address",
        "coverage": "Altadena historic homes and buildings",
        "access": "Online searchable, searchable by street address",
        "url": "https://altadenaheritage.org/ahad/",
        "search_tip": "Search by street address (e.g., '2600 Lincoln Ave')",
    },
}


# Altadena local newspapers
ALTADENA_NEWSPAPERS: ClassVar[list[dict[str, str]]] = [
    {
        "name": "The Altadenan",
        "dates": "1944-1976",
        "access": "Microfilm at Pasadena Public Library or AHS",
        "notes": "Local community newspaper",
    },
    {
        "name": "The Altadena Press",
        "dates": "1928-1944",
        "access": "Microfilm at Pasadena Public Library",
        "notes": "Predecessor to The Altadenan",
    },
]


# Altadenablog Archive (2007-2015)
ALTADENABLOG: dict[str, dict[str, Any]] = {
    "altadenablog": {
        "name": "Altadenablog Archive",
        "description": "Community blog with extensive local history, obituaries, and events",
        "coverage": "2007-2015",
        "access": "Archived via Wayback Machine",
        "url": "https://web.archive.org/web/*/altadenablog.com/*",
        "search_tip": "Rich source for recent deaths, community events, local personalities",
    },
}


# LAPL (Los Angeles Public Library) genealogy resources
LAPL_RESOURCES: dict[str, dict[str, Any]] = {
    "city_directories": {
        "name": "Los Angeles City Directories",
        "description": "Annual directories 1872-1998 (digital 1872-1990)",
        "coverage": "LA residents, businesses, addresses",
        "access": "Free at LAPL branches or via Ancestry Library Edition",
        "url": "https://www.lapl.org/collections-resources/research-and-homework/city-directories",
    },
    "city_directory_index": {
        "name": "LAPL City Directory Index",
        "description": "Searchable index to historic LA city directories",
        "coverage": "1872-1990 (searchable online)",
        "access": "Free online search at LAPL",
        "url": "https://www.lapl.org/collections-resources/research-and-homework/city-directories",
        "search_tip": "Search by surname to find addresses across decades",
    },
    "obituary_index": {
        "name": "LAPL Obituary Index",
        "description": "Index to LA Times obituaries 1881-1985",
        "coverage": "Death notices and obituaries",
        "access": "Searchable at Central Library History Department",
        "url": "https://www.lapl.org/",
    },
    "photo_collection": {
        "name": "LAPL Photo Collection",
        "description": "2.3 million photographs in digital collections",
        "coverage": "Los Angeles history 1860s-present",
        "access": "Free online via LAPL digital collections",
        "url": "https://tessa.lapl.org/",
    },
    "california_index": {
        "name": "California Index (1900-present)",
        "description": "Newspaper article index for California subjects",
        "coverage": "LA Times, other CA newspapers",
        "access": "Available at LAPL History Department",
        "url": "https://www.lapl.org/",
    },
    "sanborn_maps": {
        "name": "Sanborn Fire Insurance Maps",
        "description": "Detailed property maps of LA County",
        "coverage": "1888-1970",
        "access": "Free via LAPL with library card",
        "url": "https://www.lapl.org/collections-resources/research-and-homework/sanborn-maps",
    },
    "la_times_historical": {
        "name": "LA Times Historical Archives",
        "description": "Full-text searchable Los Angeles Times archives",
        "coverage": "1881-present",
        "access": "Free with LAPL library card via ProQuest",
        "url": "https://www.lapl.org/collections-resources/research-and-homework/newspapers",
        "search_tip": "Extensive obituary and death notice coverage",
    },
}


# LA Area Court Records (early California)
LA_COURT_RECORDS: dict[str, dict[str, Any]] = {
    "early_court_records": {
        "name": "LA Area Court Records (1850s-1910)",
        "description": "Early California court records, civil and criminal cases",
        "coverage": "1850s-1910",
        "access": "Huntington Library special collections",
        "url": "https://www.huntington.org/library",
        "search_tip": "Includes naturalization, probate, civil disputes",
    },
    "superior_court": {
        "name": "LA County Superior Court Archives",
        "description": "Historic court case files",
        "coverage": "1850-present",
        "access": "LA County Archives or Huntington Library (early records)",
        "url": "https://www.lacourt.org/",
    },
}


# CSUN University Library Digital Collections
CSUN_RESOURCES: dict[str, dict[str, Any]] = {
    "urban_archives": {
        "name": "CSUN Urban Archives Center",
        "description": "San Fernando Valley and LA regional history collections",
        "coverage": "San Fernando Valley, LA region",
        "access": "Free online and on-site research",
        "url": "https://library.csun.edu/SCA/collections/urban-archives-center",
    },
    "international_guitar": {
        "name": "International Guitar Research Archives",
        "description": "Guitar history, includes musician biographies",
        "coverage": "Global guitar history",
        "access": "On-site research",
        "url": "https://library.csun.edu/igra",
    },
    "oviatt_special": {
        "name": "CSUN Oviatt Library Special Collections",
        "description": "Regional history manuscripts and photographs",
        "coverage": "LA region, California history",
        "access": "Free online finding aids, on-site research",
        "url": "https://library.csun.edu/SCA",
    },
}


# Huntington Library genealogy resources
HUNTINGTON_RESOURCES: dict[str, dict[str, Any]] = {
    "ecpp": {
        "name": "Early California Population Project (ECPP)",
        "description": "Database of 250,000+ individuals from mission registers 1769-1850",
        "coverage": "Spanish/Mexican California baptisms, marriages, burials",
        "access": "Free searchable database online",
        "url": "https://www.huntington.org/verso/ecpp",
    },
    "manuscripts": {
        "name": "Huntington Manuscript Collections",
        "description": "Family papers, diaries, correspondence from California pioneers",
        "coverage": "Early California and American West",
        "access": "On-site research with reader card",
        "url": "https://www.huntington.org/library",
    },
    "photographs": {
        "name": "Huntington Photo Archives",
        "description": "Historic photographs of Southern California",
        "coverage": "1850s-1960s",
        "access": "Digital images via Huntington Digital Library",
        "url": "https://hdl.huntington.org/",
    },
}


# USC Digital Library resources
USC_RESOURCES: dict[str, dict[str, Any]] = {
    "la_examiner": {
        "name": "Los Angeles Examiner Photographs Collection",
        "description": "1.4 million news photographs 1921-1961",
        "coverage": "LA daily news coverage",
        "access": "Free online via USC Digital Library",
        "url": "https://digitallibrary.usc.edu/cs/los-angeles-examiner-photographs",
    },
    "california_historical": {
        "name": "California Historical Society Collection",
        "description": "150,000+ photographs of California history",
        "coverage": "State history 1860s-1960s",
        "access": "Free online",
        "url": "https://digitallibrary.usc.edu/",
    },
    "korean_american": {
        "name": "Korean American Digital Archive",
        "description": "Korean immigration and community history",
        "coverage": "1903-present",
        "access": "Free online",
        "url": "https://digitallibrary.usc.edu/cs/korean-american-digital-archive",
    },
}


# LA County vital records information
LA_COUNTY_VITAL_RECORDS: dict[str, dict[str, Any]] = {
    "registrar_recorder": {
        "name": "LA County Registrar-Recorder/County Clerk",
        "description": "Official vital records (birth, death, marriage certificates)",
        "coverage": "1866-present",
        "access": "Fee-based certified copies; some indexes free via FamilySearch",
        "url": "https://www.lavote.gov/home/county-clerk/vital-records",
    },
    "familysearch_la": {
        "name": "FamilySearch LA County Collections",
        "description": "Digitized LA County records",
        "coverage": "Various dates, includes some vital records indexes",
        "access": "Free online at FamilySearch.org",
        "url": "https://www.familysearch.org/search/collection/location/1927063",
    },
}


# LA County newspapers on CDNC (California Digital Newspaper Collection)
LA_COUNTY_NEWSPAPERS: ClassVar[list[dict[str, str]]] = [
    {
        "name": "Los Angeles Star",
        "dates": "1851-1879",
        "access": "CDNC",
        "url": "https://cdnc.ucr.edu/",
        "notes": "First LA newspaper, bilingual English/Spanish",
    },
    {
        "name": "Los Angeles Herald",
        "dates": "1873-1931",
        "access": "CDNC / Chronicling America",
        "url": "https://cdnc.ucr.edu/",
        "notes": "Major daily, extensive coverage",
    },
    {
        "name": "California Eagle",
        "dates": "1879-1965",
        "access": "ProQuest / LAPL",
        "url": "https://www.lapl.org/",
        "notes": "African American newspaper, important for Black genealogy",
    },
    {
        "name": "La Opinion",
        "dates": "1926-present",
        "access": "ProQuest",
        "url": "https://www.proquest.com/",
        "notes": "Spanish-language, largest in US",
    },
    {
        "name": "Pasadena Star-News",
        "dates": "1884-present",
        "access": "Newspapers.com / ProQuest",
        "url": "https://www.newspapers.com/",
        "notes": "San Gabriel Valley coverage",
    },
]


class AltadenaHistoricalSocietySource(BaseSource):
    """Altadena Historical Society archives.

    Collections include:
    - Historical photographs of Altadena families and homes
    - Oral history interviews
    - Local newspaper clippings
    - Mount Lowe Railway Digital Collection
    - Echo Newsletters (2009+)
    - Special Collections (Crank, Brigden, Whitaker families)
    """

    name = "AltadenaHistoricalSociety"
    base_url = "https://altadenahistoricalsociety.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search AHS collections."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Search main AHS resources
        for key, resource in ALTADENA_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ahs-{key}",
                    record_type="archive_collection",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "search_tip": resource.get("search_tip", ""),
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Altadena Heritage Architectural Database (AHAD)
        for key, resource in ALTADENA_AHAD.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ahad-{key}",
                    record_type="property_database",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_tip": resource.get("search_tip", ""),
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Altadenablog archive search
        for key, resource in ALTADENABLOG.items():
            wayback_url = f"https://web.archive.org/web/*/altadenablog.com/*{quote_plus(surname)}*"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"altadenablog-{surname}",
                    record_type="blog_archive",
                    url=wayback_url,
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_url": wayback_url,
                        "search_tip": resource.get("search_tip", ""),
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Altadena local newspapers
        for paper in ALTADENA_NEWSPAPERS:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"altadena-paper-{paper['name'].replace(' ', '-').lower()}",
                    record_type="newspaper_microfilm",
                    url=self.base_url,
                    raw_data={"newspaper": paper},
                    extracted_fields={
                        "newspaper": paper["name"],
                        "coverage": paper["dates"],
                        "access": paper["access"],
                        "notes": paper.get("notes", ""),
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Calisphere search for Altadena
        calisphere_url = f"https://calisphere.org/search/?q={quote_plus(f'{surname} Altadena')}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ahs-calisphere-{surname}",
                record_type="photo_search",
                url=calisphere_url,
                raw_data={"type": "Calisphere search"},
                extracted_fields={
                    "search_type": "Altadena on Calisphere",
                    "search_url": calisphere_url,
                    "description": "Search Altadena collections on Calisphere",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None


class LAPLGenealogySource(BaseSource):
    """Los Angeles Public Library History & Genealogy Department.

    Major resources:
    - City directories (1872-1998)
    - Obituary index (1881-1985)
    - 2.3 million digitized photographs
    - California newspaper index
    - Sanborn fire insurance maps
    """

    name = "LAPLGenealogy"
    base_url = "https://www.lapl.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search LAPL genealogy resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in LAPL_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"lapl-{key}",
                    record_type="library_resource",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add LAPL digital collections search (TESSA)
        tessa_url = f"https://tessa.lapl.org/search?q={quote_plus(surname)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"lapl-tessa-{surname}",
                record_type="photo_search",
                url=tessa_url,
                raw_data={"type": "TESSA search"},
                extracted_fields={
                    "search_type": "LAPL Photo Collections",
                    "search_url": tessa_url,
                    "description": "Search 2.3 million LAPL photographs",
                    "access": "Free online",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None


class HuntingtonLibrarySource(BaseSource):
    """Huntington Library genealogy resources.

    Key collections:
    - Early California Population Project (ECPP) - 250,000+ mission records
    - Manuscript collections - pioneer family papers
    - Historic photographs
    """

    name = "HuntingtonLibrary"
    base_url = "https://www.huntington.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Huntington Library resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in HUNTINGTON_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"huntington-{key}",
                    record_type="library_resource",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add ECPP search link (the main searchable database)
        ecpp_url = "https://www.huntington.org/verso/ecpp"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"huntington-ecpp-{surname}",
                record_type="mission_records",
                url=ecpp_url,
                raw_data={"type": "ECPP database"},
                extracted_fields={
                    "resource_name": "Early California Population Project",
                    "record_count": "250,000+",
                    "search_tip": f"Search for '{surname}' in ECPP database",
                    "description": "Mission registers: baptisms, marriages, burials 1769-1850",
                    "access": "Free searchable database",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None


class USCDigitalLibrarySource(BaseSource):
    """USC Digital Library collections.

    Notable collections:
    - Los Angeles Examiner photographs (1.4 million images)
    - California Historical Society collection
    - Ethnic community archives
    """

    name = "USCDigitalLibrary"
    base_url = "https://digitallibrary.usc.edu"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search USC Digital Library."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in USC_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"usc-{key}",
                    record_type="digital_collection",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add general USC Digital Library search
        usc_search_url = f"https://digitallibrary.usc.edu/search?q={quote_plus(surname)}"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"usc-search-{surname}",
                record_type="photo_search",
                url=usc_search_url,
                raw_data={"type": "USC Digital Library search"},
                extracted_fields={
                    "search_type": "USC Digital Library",
                    "search_url": usc_search_url,
                    "description": "Search across USC digital collections",
                    "highlights": "Includes 1.4M LA Examiner photographs",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None


class LosAngelesCountySource(BaseSource):
    """Aggregator for all Los Angeles County genealogy sources.

    Combines:
    - Altadena Historical Society (with AHAD, Altadenablog, Mount Lowe, etc.)
    - LAPL History & Genealogy Department
    - Huntington Library (ECPP and manuscripts)
    - USC Digital Library
    - LA County vital records information
    - LA Area Court Records (1850s-1910)
    - CSUN University Library Digital Collections
    - Regional newspaper portals
    """

    name = "LosAngelesCounty"

    COMPONENT_SOURCES: ClassVar[list[type[BaseSource]]] = [
        AltadenaHistoricalSocietySource,
        LAPLGenealogySource,
        HuntingtonLibrarySource,
        USCDigitalLibrarySource,
    ]

    def __init__(self) -> None:
        super().__init__()
        self.ahs = AltadenaHistoricalSocietySource()
        self.lapl = LAPLGenealogySource()
        self.huntington = HuntingtonLibrarySource()
        self.usc = USCDigitalLibrarySource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Los Angeles County sources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Search component sources
        sources = [
            ("AHS", self.ahs),
            ("LAPL", self.lapl),
            ("Huntington", self.huntington),
            ("USC", self.usc),
        ]

        for source_name, source in sources:
            try:
                source_records = await source.search(query)
                records.extend(source_records)
            except Exception as e:
                logger.debug(f"{source_name} search error: {e}")

        # Add LA Area Court Records
        for key, resource in LA_COURT_RECORDS.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"la-court-{key}",
                    record_type="court_records",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_tip": resource.get("search_tip", ""),
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add CSUN resources
        for key, resource in CSUN_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"csun-{key}",
                    record_type="university_archives",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add vital records information
        for key, resource in LA_COUNTY_VITAL_RECORDS.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"la-vital-{key}",
                    record_type="vital_records",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add newspaper resources with CDNC links
        for paper in LA_COUNTY_NEWSPAPERS:
            if "CDNC" in paper["access"]:
                cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&txq={quote_plus(surname)}"
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"la-paper-{paper['name'].replace(' ', '-').lower()}",
                        record_type="newspaper_search",
                        url=cdnc_url,
                        raw_data={"newspaper": paper},
                        extracted_fields={
                            "newspaper": paper["name"],
                            "coverage": paper["dates"],
                            "search_url": cdnc_url,
                            "access": paper["access"],
                            "notes": paper.get("notes", ""),
                        },
                        accessed_at=datetime.now(UTC),
                    )
                )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None
