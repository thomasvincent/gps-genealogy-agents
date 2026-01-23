"""California Gold Country (Highway 49 Corridor) genealogy sources.

Specialized archives for the Mother Lode mining region along Highway 49:
- El Dorado County (Placerville/"Hangtown") - 27,000+ photographs
- Tuolumne County (Sonora/Columbia) - 35,000+ photographs, CHISPA archives
- Placer County (Auburn) - 20,000+ photographs, Placer Herald (1852+)
- Mariposa County - California Revealed collection, Mariposa Gazette (1854+)
- Nevada County (Grass Valley/Nevada City) - Searls Index 265,000+ names

Coverage: California's Gold Rush mining region (1848-present)
Records: Mining claims, court records, photographs, newspapers, land records
Access: Mixed - some free online, some require research requests
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote_plus

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# Gold Country county information
GOLD_COUNTRY_COUNTIES: dict[str, dict[str, Any]] = {
    "el_dorado": {
        "name": "El Dorado County",
        "seat": "Placerville",
        "nickname": "Hangtown",
        "resources": {
            "museum_archives": {
                "name": "El Dorado County Museum Archives",
                "url": "https://eldoradolibrary.org/museum-archives-and-research-room/",
                "records": "27,000+ photographs, maps, court records, genealogical data",
                "coverage": "1849-present",
                "access": "Research requests via email/phone",
            },
            "historical_society": {
                "name": "El Dorado County Historical Society",
                "url": "https://edchs.org/",
                "records": "Fountain-Tallman Museum, historical photographs",
                "access": "Free online galleries",
            },
            "mountain_democrat": {
                "name": "Mountain Democrat Newspaper",
                "url": "https://cdnc.ucr.edu/",
                "records": "1854-present (one of CA's oldest papers)",
                "coverage": "CDNC has deep archives",
                "access": "Free searchable via CDNC",
            },
        },
    },
    "tuolumne": {
        "name": "Tuolumne County",
        "seat": "Sonora",
        "resources": {
            "historical_society": {
                "name": "Tuolumne County Historical Society",
                "url": "https://tchistory.org/",
                "records": "35,000+ photographs, local history collection",
                "coverage": "1850s-present",
                "access": "Research center, some online via CatalogIt",
            },
            "catalogit_hub": {
                "name": "TCHS CatalogIt Collection",
                "url": "https://hub.catalogit.app/tuolumne-county-historical-society",
                "records": "Digitized photos grouped by topic",
                "access": "Free online browsing",
            },
            "genealogical_society": {
                "name": "Tuolumne County Genealogical Society",
                "url": "https://tcgen.org/",
                "records": "Cemetery records, family files, CHISPA quarterly",
                "access": "Member resources + free indices",
            },
            "columbia_archives": {
                "name": "Columbia State Historic Park Archives",
                "url": "https://www.parks.ca.gov/?page_id=552",
                "records": "Mining journals, merchant ledgers, water flume maps",
                "access": "On-site research",
            },
        },
    },
    "placer": {
        "name": "Placer County",
        "seat": "Auburn",
        "resources": {
            "archives": {
                "name": "Placer County Archives & Research Center",
                "url": "https://www.placer.ca.gov/3393/County-Archive-and-Museum-Collections",
                "records": "20,000+ photographs, land claims, homesteads, deeds",
                "coverage": "Gold Rush era to present",
                "access": "By appointment (Mon-Tue); digital portal expanding",
            },
            "digital_collections": {
                "name": "Placer County Museums Digital Collections",
                "url": "https://placer.access.preservica.com/",
                "records": "Land claims, homesteads, deeds, official records",
                "access": "Free online (expanding)",
            },
            "placer_herald": {
                "name": "Placer Herald Newspaper",
                "url": "https://cdnc.ucr.edu/",
                "records": "1852-present (original bound copies in archives)",
                "access": "CDNC + physical archives",
            },
            "genealogy_society": {
                "name": "Placer County Genealogical Society",
                "url": "https://www.placergenealogy.org/",
                "records": "Cemetery, vital records, newspaper indices",
                "access": "Free record indices online",
            },
        },
    },
    "mariposa": {
        "name": "Mariposa County",
        "seat": "Mariposa",
        "resources": {
            "museum": {
                "name": "Mariposa Museum & History Center",
                "url": "https://www.mariposamuseum.com/",
                "records": "Court records, naturalization, census, assessor rolls",
                "coverage": "1850s-present",
                "access": "On-site research + California Revealed",
            },
            "california_revealed": {
                "name": "Mariposa on California Revealed",
                "url": "https://californiarevealed.org/partner/mariposa-museum-and-history-center",
                "records": "Newspapers, oral histories, photographs, moving images",
                "access": "Free online",
            },
            "calisphere": {
                "name": "Mariposa on Calisphere",
                "url": "https://calisphere.org/institution/326/collections/",
                "records": "Digitized photographs and documents",
                "access": "Free online",
            },
            "mariposa_gazette": {
                "name": "Mariposa Gazette",
                "url": "https://cdnc.ucr.edu/",
                "records": "1854-present (oldest continuous paper in CA)",
                "access": "CDNC searchable",
            },
        },
    },
    "nevada": {
        "name": "Nevada County",
        "seat": "Nevada City",
        "resources": {
            "searls_library": {
                "name": "Searls Historical Library",
                "url": "https://nevadacountyhistory.org/",
                "records": "265,000+ names in General Index, court cases, wills",
                "coverage": "1856-present (wills), business ledgers",
                "access": "Searchable card catalog online",
            },
            "doris_foley": {
                "name": "Doris Foley Library",
                "url": "https://www.mynevadacounty.com/2060/Doris-Foley-Library",
                "records": "Wyckoff Collection (3,000+ photos), Sanborn maps",
                "access": "ContentDM digital collection",
            },
            "grass_valley_union": {
                "name": "Grass Valley Daily Union",
                "url": "https://cdnc.ucr.edu/",
                "records": "1865-1916 fully searchable",
                "access": "CDNC free access",
            },
            "mining_indices": {
                "name": "Mining Company Records",
                "url": "https://nevadacountyhistory.org/",
                "records": "Idaho-Maryland Mine personnel files, North Star records",
                "access": "Indexed at Nevada County Historical Society",
            },
        },
    },
}


class ElDoradoCountySource(BaseSource):
    """El Dorado County (Placerville) historical archives.

    Home to "Hangtown" - a major hub for the Southern Mines and
    the Carson Trail crossing. The Museum Archives contain 27,000+
    photographs and extensive Gold Rush era records.
    """

    name = "ElDoradoCounty"
    base_url = "https://eldoradolibrary.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search El Dorado County resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        county_info = GOLD_COUNTRY_COUNTIES["el_dorado"]

        # Add each resource
        for key, resource in county_info["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"eldorado-{key}",
                    record_type="archive_reference",
                    url=resource["url"],
                    raw_data={"resource": resource, "county": county_info},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "records_available": resource["records"],
                        "coverage": resource.get("coverage", "Various dates"),
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "county": "El Dorado County, California",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add CDNC search for Mountain Democrat
        cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1&txq={quote_plus(surname)}&e=-------en--20--1--txt-txIN-mountain+democrat"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"eldorado-cdnc-{surname}",
                record_type="newspaper_search",
                url=cdnc_url,
                raw_data={"newspaper": "Mountain Democrat", "surname": surname},
                extracted_fields={
                    "search_type": "CDNC Newspaper Search",
                    "newspaper": "Mountain Democrat (1854-present)",
                    "search_url": cdnc_url,
                    "description": "One of California's oldest continuously published newspapers",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """El Dorado archives require manual access."""
        return None


class TuolumneCountySource(BaseSource):
    """Tuolumne County (Sonora/Columbia) historical archives.

    Heart of the "Southern Mines" with diverse immigrant history
    (Chilean, French, Italian). TCHS maintains 35,000+ photographs.
    """

    name = "TuolumneCounty"
    base_url = "https://tchistory.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Tuolumne County resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        county_info = GOLD_COUNTRY_COUNTIES["tuolumne"]

        for key, resource in county_info["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"tuolumne-{key}",
                    record_type="archive_reference",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "records_available": resource["records"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "county": "Tuolumne County, California",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add CatalogIt Hub direct search
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"tuolumne-catalogit-{surname}",
                record_type="photo_collection",
                url="https://hub.catalogit.app/tuolumne-county-historical-society",
                raw_data={"collection": "TCHS Photos"},
                extracted_fields={
                    "resource_name": "TCHS Photo Collection on CatalogIt",
                    "description": "Browse 30,000+ historical photos by topic",
                    "search_tip": f"Search for '{surname}' in the collection",
                    "access": "Free online browsing",
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


class PlacerCountySource(BaseSource):
    """Placer County (Auburn) historical archives.

    Unique as both a Gold Rush town and major railroad hub.
    Archives contain 20,000+ photographs and the Placer Herald (1852+).
    """

    name = "PlacerCounty"
    base_url = "https://www.placer.ca.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Placer County resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        county_info = GOLD_COUNTRY_COUNTIES["placer"]

        for key, resource in county_info["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"placer-{key}",
                    record_type="archive_reference",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "records_available": resource["records"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "county": "Placer County, California",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Placer digital collections direct link
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"placer-digital-{surname}",
                record_type="digital_collection",
                url="https://placer.access.preservica.com/",
                raw_data={"type": "Preservica digital archive"},
                extracted_fields={
                    "resource_name": "Placer County Digital Collections",
                    "description": "Land claims, homesteads, deeds, official records",
                    "search_tip": f"Search for '{surname}' in land/property records",
                    "access": "Free online - collection expanding",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add CDNC Placer Herald search
        cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1&txq={quote_plus(surname)}&e=-------en--20--1--txt-txIN-placer+herald"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"placer-cdnc-{surname}",
                record_type="newspaper_search",
                url=cdnc_url,
                raw_data={"newspaper": "Placer Herald"},
                extracted_fields={
                    "search_type": "CDNC Newspaper Search",
                    "newspaper": "Placer Herald (1852-present)",
                    "search_url": cdnc_url,
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


class MariposaCountySource(BaseSource):
    """Mariposa County historical archives.

    Southernmost tip of the Mother Lode, includes the Fremont Grant.
    Strong digitization via California Revealed with newspapers,
    oral histories, and the Mariposa Gazette (1854+).
    """

    name = "MariposaCounty"
    base_url = "https://www.mariposamuseum.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Mariposa County resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        county_info = GOLD_COUNTRY_COUNTIES["mariposa"]

        for key, resource in county_info["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"mariposa-{key}",
                    record_type="archive_reference",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "records_available": resource["records"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "county": "Mariposa County, California",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add California Revealed search
        ca_revealed_url = f"https://californiarevealed.org/islandora/search/{quote_plus(surname)}?type=dismax"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"mariposa-carevealed-{surname}",
                record_type="digital_collection",
                url=ca_revealed_url,
                raw_data={"type": "California Revealed"},
                extracted_fields={
                    "resource_name": "Mariposa on California Revealed",
                    "description": "Newspapers, oral histories, photographs, moving images",
                    "search_url": ca_revealed_url,
                    "access": "Free online",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add CDNC Mariposa Gazette search
        cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1&txq={quote_plus(surname)}&e=-------en--20--1--txt-txIN-mariposa+gazette"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"mariposa-cdnc-{surname}",
                record_type="newspaper_search",
                url=cdnc_url,
                raw_data={"newspaper": "Mariposa Gazette"},
                extracted_fields={
                    "search_type": "CDNC Newspaper Search",
                    "newspaper": "Mariposa Gazette (1854-present)",
                    "description": "Oldest continuously published paper in California",
                    "search_url": cdnc_url,
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


class NevadaCountySource(BaseSource):
    """Nevada County (Grass Valley/Nevada City) historical archives.

    The "Twin Cities" of the Northern Mother Lode - center of
    California's hard-rock mining industry. The Searls Library
    General Index contains 265,000+ searchable names.
    """

    name = "NevadaCounty"
    base_url = "https://nevadacountyhistory.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Nevada County resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        county_info = GOLD_COUNTRY_COUNTIES["nevada"]

        # Searls Library is the crown jewel - highlight first
        records.append(
            RawRecord(
                source=self.name,
                record_id="nevada-searls-index",
                record_type="master_index",
                url="https://nevadacountyhistory.org/",
                raw_data={"type": "Searls General Index"},
                extracted_fields={
                    "resource_name": "Searls Historical Library General Index",
                    "record_count": "265,000+",
                    "description": (
                        "Master index of names from business ledgers, journals, "
                        "court cases, wills, and local history books"
                    ),
                    "coverage": "1856-present",
                    "search_tip": f"Search for '{surname}' in the card catalog",
                    "access": "Searchable online card catalog",
                    "recommendation": "START HERE for Nevada County research",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        for key, resource in county_info["resources"].items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"nevada-{key}",
                    record_type="archive_reference",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "records_available": resource["records"],
                        "access_method": resource["access"],
                        "search_surname": surname,
                        "county": "Nevada County, California",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add CDNC Grass Valley Union search
        cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1&txq={quote_plus(surname)}&e=-------en--20--1--txt-txIN-grass+valley"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"nevada-cdnc-{surname}",
                record_type="newspaper_search",
                url=cdnc_url,
                raw_data={"newspaper": "Grass Valley Daily Union"},
                extracted_fields={
                    "search_type": "CDNC Newspaper Search",
                    "newspaper": "Grass Valley Daily Union (1865-1916)",
                    "search_url": cdnc_url,
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


class GoldCountrySource(BaseSource):
    """Aggregator for California Gold Country (Highway 49) archives.

    Combines resources from all Mother Lode counties:
    - El Dorado (Placerville)
    - Tuolumne (Sonora/Columbia)
    - Placer (Auburn)
    - Mariposa
    - Nevada (Grass Valley/Nevada City)

    Total indexed records: 400,000+ names across all county indices.
    """

    name = "GoldCountry"

    # County sources
    COUNTY_SOURCES: ClassVar[list[type[BaseSource]]] = [
        ElDoradoCountySource,
        TuolumneCountySource,
        PlacerCountySource,
        MariposaCountySource,
        NevadaCountySource,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sources = [src() for src in self.COUNTY_SOURCES]

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Gold Country county archives."""
        records: list[RawRecord] = []

        # Search each county source
        for source in self._sources:
            try:
                county_records = await source.search(query)
                records.extend(county_records)
            except Exception as e:
                logger.debug(f"{source.name} search error: {e}")

        # Add CDNC aggregate search for all Gold Country papers
        if query.surname:
            cdnc_url = f"https://cdnc.ucr.edu/?a=q&hs=1&r=1&results=1&txq={quote_plus(query.surname)}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"goldcountry-cdnc-all-{query.surname}",
                    record_type="newspaper_search",
                    url=cdnc_url,
                    raw_data={"type": "CDNC aggregate"},
                    extracted_fields={
                        "search_type": "CDNC - All California Newspapers",
                        "description": "Search across all Gold Country newspapers at once",
                        "search_url": cdnc_url,
                        "coverage": "Mountain Democrat, Placer Herald, Mariposa Gazette, Union, etc.",
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
