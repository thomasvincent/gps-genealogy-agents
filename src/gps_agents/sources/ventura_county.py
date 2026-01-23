"""Ventura County (Ventura, Oxnard, Camarillo) genealogy sources.

Specialized archives for coastal agriculture and oil boom history:
- Museum of Ventura County - Journal of VC History, oral histories, Press-Courier morgue
- Ventura County Genealogical Society - 80,000+ death records, land indices
- Oxnard Public Library - 1,600+ photographs, sugar beet industry history
- San Buenaventura Mission Archives - pre-1850 baptismal/marriage/burial records

Coverage: Ventura County, California (1782-present)
Records: Death indices, photographs, newspapers, land records, mission records
Access: Mixed - VCGS databases free, some require library visit
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# Ventura County resource database
VENTURA_RESOURCES: dict[str, dict[str, Any]] = {
    "museum_of_ventura_county": {
        "name": "Museum of Ventura County Research Library",
        "url": "https://venturamuseum.org/research-library/",
        "resources": {
            "journal": {
                "name": "Journal of Ventura County History",
                "description": "40+ volumes digitized via California Revealed",
                "coverage": "Pioneer family biographies, local history",
                "access": "Free online via California Revealed",
            },
            "oral_histories": {
                "name": "Oral History Collection",
                "description": "425+ recorded interviews with longtime residents",
                "coverage": "20th century community history",
                "access": "PDF index online, audio by request",
            },
            "press_courier_morgue": {
                "name": "Oxnard Press-Courier Morgue",
                "description": "Clippings, photographs, portraits (1890s-1994)",
                "coverage": "Oxnard daily newspaper reference files",
                "access": "On-site research",
            },
        },
    },
    "vcgs": {
        "name": "Ventura County Genealogical Society",
        "url": "https://www.venturacountygenealogy.org/",
        "resources": {
            "death_records": {
                "name": "Death Record Database",
                "description": "80,000+ local death records indexed",
                "coverage": "Ventura County deaths",
                "access": "Searchable online",
            },
            "land_indices": {
                "name": "Grantor/Grantee Land Index",
                "description": "Property transfer records 1873-1917",
                "coverage": "Land purchases and sales",
                "access": "Digital index online",
            },
            "library_collection": {
                "name": "VCGS Library (Camarillo)",
                "description": "Ancestry/FamilySearch affiliate access",
                "coverage": "Full genealogy database access",
                "access": "Free at Camarillo Public Library",
            },
        },
    },
    "oxnard_library": {
        "name": "Oxnard Public Library Digital Collections",
        "url": "https://www.oxnardlibrary.org/",
        "resources": {
            "photo_collection": {
                "name": "Oxnard Photograph Collection",
                "description": "1,600+ digitized images (late 1800s-2001)",
                "coverage": "American Beet Sugar Company, local families",
                "access": "Free via Calisphere",
                "calisphere_url": "https://calisphere.org/institution/oxnard-public-library/",
            },
            "local_history_room": {
                "name": "Local History Room",
                "description": "Big Four families, Channel Islands Harbor development",
                "coverage": "Oxnard agricultural and civic history",
                "access": "On-site research",
            },
        },
    },
    "mission_archives": {
        "name": "San Buenaventura Mission Archives",
        "url": "https://www.sanbuenaventuramission.org/",
        "resources": {
            "sacramental_records": {
                "name": "Mission Sacramental Records",
                "description": "Baptisms, marriages, burials (pre-1850)",
                "coverage": "Californio and Native American families",
                "access": "Indexed in Huntington Library ECPP",
                "huntington_url": "https://www.huntington.org/verso/ecpp",
            },
        },
    },
    "csuci": {
        "name": "CSU Channel Islands Digital Archives",
        "url": "https://library.csuci.edu/digital-archives",
        "resources": {
            "ventura_history": {
                "name": "Ventura County History Collection",
                "description": "Postcards, agricultural maps, local records",
                "coverage": "Regional development history",
                "access": "Free online",
            },
            "camarillo_hospital": {
                "name": "Camarillo State Hospital Records",
                "description": "Historical documentation of the institution",
                "coverage": "1936-1997 institutional history",
                "access": "Digital archives",
            },
        },
    },
}

# Ventura County newspapers
VENTURA_NEWSPAPERS: list[dict[str, str]] = [
    {
        "name": "Ventura Signal",
        "dates": "1871-1884",
        "access": "CDNC",
        "url": "https://cdnc.ucr.edu/",
    },
    {
        "name": "Oxnard Courier",
        "dates": "1899-1922",
        "access": "CDNC / Chronicling America",
        "url": "https://cdnc.ucr.edu/",
    },
    {
        "name": "Ventura County Star",
        "dates": "1925-present",
        "access": "ProQuest (free via CA library cards)",
        "url": "https://www.proquest.com/",
    },
    {
        "name": "The Press-Courier",
        "dates": "1959-1993",
        "access": "Museum of Ventura County (index)",
        "url": "https://venturamuseum.org/",
    },
]


class VenturaCountyGenealogySource(BaseSource):
    """Ventura County Genealogical Society database search.

    VCGS maintains extensive databases including:
    - 80,000+ death records
    - Grantor/Grantee land indices (1873-1917)
    - Access to Ancestry/FamilySearch at Camarillo Library
    """

    name = "VenturaCountyGenealogy"
    base_url = "https://www.venturacountygenealogy.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search VCGS databases."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        vcgs = VENTURA_RESOURCES["vcgs"]

        for key, resource in vcgs["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"vcgs-{key}",
                    record_type="database_reference",
                    url=self.base_url,
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

        # Death records are the primary searchable resource
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"vcgs-death-search-{surname}",
                record_type="death_index",
                url=self.base_url,
                raw_data={"type": "death_records", "surname": surname},
                extracted_fields={
                    "resource_name": "VCGS Death Record Database",
                    "record_count": "80,000+",
                    "search_tip": f"Search for '{surname}' in the death index",
                    "description": "Comprehensive index of Ventura County deaths",
                    "access": "Free searchable online database",
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


class OxnardLibrarySource(BaseSource):
    """Oxnard Public Library digital collections.

    Strong focus on:
    - Sugar beet industry history
    - 1,600+ historical photographs
    - Big Four founding families
    """

    name = "OxnardLibrary"
    base_url = "https://www.oxnardlibrary.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Oxnard Library collections."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        oxnard = VENTURA_RESOURCES["oxnard_library"]

        for key, resource in oxnard["resources"].items():
            url = resource.get("calisphere_url", self.base_url)
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"oxnard-{key}",
                    record_type="digital_collection",
                    url=url,
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

        # Add Calisphere search for Oxnard
        calisphere_url = f"https://calisphere.org/search/?q={quote_plus(f'{surname} Oxnard')}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"oxnard-calisphere-{surname}",
                record_type="photo_search",
                url=calisphere_url,
                raw_data={"type": "Calisphere search"},
                extracted_fields={
                    "search_type": "Oxnard on Calisphere",
                    "search_url": calisphere_url,
                    "description": "Search Oxnard photograph collection",
                    "record_count": "1,600+ images available",
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


class MuseumOfVenturaCountySource(BaseSource):
    """Museum of Ventura County Research Library.

    Key collections:
    - Journal of Ventura County History (40+ volumes on California Revealed)
    - 425+ oral history interviews
    - Oxnard Press-Courier morgue (clippings 1890s-1994)
    """

    name = "MuseumVenturaCounty"
    base_url = "https://venturamuseum.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Museum of Ventura County collections."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        museum = VENTURA_RESOURCES["museum_of_ventura_county"]

        for key, resource in museum["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"mvc-{key}",
                    record_type="archive_collection",
                    url=f"{self.base_url}/research-library/",
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

        # Add California Revealed search for Journal
        ca_revealed_url = f"https://californiarevealed.org/islandora/search/{quote_plus(surname)}?type=dismax"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"mvc-carevealed-{surname}",
                record_type="journal_search",
                url=ca_revealed_url,
                raw_data={"type": "California Revealed"},
                extracted_fields={
                    "resource_name": "Journal of Ventura County History",
                    "description": "40+ volumes of pioneer family biographies",
                    "search_url": ca_revealed_url,
                    "access": "Free online via California Revealed",
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


class VenturaCountySource(BaseSource):
    """Aggregator for all Ventura County genealogy sources.

    Combines:
    - Museum of Ventura County
    - Ventura County Genealogical Society (80,000+ death records)
    - Oxnard Public Library (1,600+ photos)
    - San Buenaventura Mission archives
    - CSUCI Digital Archives
    - Regional newspaper portals
    """

    name = "VenturaCounty"

    def __init__(self) -> None:
        super().__init__()
        self.vcgs = VenturaCountyGenealogySource()
        self.oxnard = OxnardLibrarySource()
        self.museum = MuseumOfVenturaCountySource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Ventura County sources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Search component sources
        sources = [
            ("VCGS", self.vcgs),
            ("Oxnard", self.oxnard),
            ("Museum", self.museum),
        ]

        for source_name, source in sources:
            try:
                source_records = await source.search(query)
                records.extend(source_records)
            except Exception as e:
                logger.debug(f"{source_name} search error: {e}")

        # Add Mission archives reference
        mission = VENTURA_RESOURCES["mission_archives"]
        records.append(
            RawRecord(
                source=self.name,
                record_id="ventura-mission",
                record_type="mission_records",
                url=mission["resources"]["sacramental_records"]["huntington_url"],
                raw_data={"type": "mission_archives"},
                extracted_fields={
                    "resource_name": "San Buenaventura Mission Archives",
                    "description": "Pre-1850 baptisms, marriages, burials",
                    "coverage": "Californio and Native American families",
                    "access": "Indexed in Huntington Library ECPP",
                    "search_tip": f"Search for '{surname}' in Early California Population Project",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add newspaper resources
        for paper in VENTURA_NEWSPAPERS:
            if "CDNC" in paper["access"]:
                cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&txq={quote_plus(surname)}&e=-------en--20--1--txt-txIN-{quote_plus(paper['name'].lower())}"
                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"ventura-paper-{paper['name'].replace(' ', '-').lower()}",
                        record_type="newspaper_search",
                        url=cdnc_url,
                        raw_data={"newspaper": paper},
                        extracted_fields={
                            "newspaper": paper["name"],
                            "coverage": paper["dates"],
                            "search_url": cdnc_url,
                            "access": paper["access"],
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
