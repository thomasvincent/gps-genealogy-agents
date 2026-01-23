"""North Carolina genealogy sources with birth/death indices.

State archives and vital records for North Carolina genealogy research:
- NC State Archives - vital records, land grants, military records, wills
- NC Death Certificates/Index (1906-present) - via FamilySearch/Ancestry
- NC Birth Index (1913-present) - restricted access
- NC Marriages (1741-present) - county records
- African American records - freedmen, slave schedules, church records

Coverage: North Carolina (colonial 1663-present)
Records: Vital records, land grants, wills, estate records, newspapers
Access: Mixed - NC Archives has significant free online collections
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import quote_plus

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# NC State Archives resources
NC_ARCHIVES_RESOURCES: dict[str, dict[str, Any]] = {
    "vital_records": {
        "name": "NC Vital Records Search",
        "description": "Death certificates 1906-1994, marriages, delayed births",
        "coverage": "1906-present",
        "access": "Free searchable index online; images via subscription",
        "url": "https://www.ancestry.com/search/collections/8781/",
    },
    "land_grants": {
        "name": "NC Land Grants",
        "description": "Colonial and state land grants 1663-1960",
        "coverage": "1663-1960",
        "access": "Free online via NC Archives",
        "url": "https://archives.ncdcr.gov/researchers/collections/land-grants",
    },
    "wills_estates": {
        "name": "Wills and Estate Records",
        "description": "Probate records, wills, estate inventories",
        "coverage": "Colonial to 20th century",
        "access": "FamilySearch (free) and NC Archives",
        "url": "https://www.familysearch.org/search/collection/1911121",
    },
    "military_records": {
        "name": "NC Military Records",
        "description": "Revolutionary War, Civil War, WWI/WWII records",
        "coverage": "1775-1945",
        "access": "NC Archives and Fold3",
        "url": "https://archives.ncdcr.gov/researchers/collections/military-records",
    },
    "newspapers": {
        "name": "NC Digital Newspaper Program",
        "description": "Historic NC newspapers via Chronicling America",
        "coverage": "1752-1963",
        "access": "Free online",
        "url": "https://www.digitalnc.org/newspapers/",
    },
}


# NC Vital Records (birth/death/marriage indices)
NC_VITAL_RECORDS: dict[str, dict[str, Any]] = {
    "death_certificates": {
        "name": "North Carolina Death Certificates",
        "description": "Statewide death certificates with cause of death, parents' names",
        "coverage": "1906-1994 (free index), 1995-present (restricted)",
        "access": "Free 1906-1994 via FamilySearch; Ancestry has images",
        "familysearch_url": "https://www.familysearch.org/search/collection/1678694",
    },
    "death_index": {
        "name": "North Carolina Death Index",
        "description": "Index to NC deaths",
        "coverage": "1908-2004",
        "access": "Free via Ancestry (name index only)",
        "url": "https://www.ancestry.com/search/collections/7839/",
    },
    "birth_index": {
        "name": "North Carolina Birth Index",
        "description": "Birth records index (state law restricts access)",
        "coverage": "1913-present (restricted by 100-year rule)",
        "access": "Pre-1913 available; later requires proof of relationship",
        "url": "https://vitalrecords.nc.gov/",
    },
    "marriages": {
        "name": "North Carolina Marriage Records",
        "description": "County marriage bonds, licenses, registers",
        "coverage": "1741-present",
        "access": "Free via FamilySearch (many counties)",
        "familysearch_url": "https://www.familysearch.org/search/collection/1726957",
    },
    "divorces": {
        "name": "North Carolina Divorce Records",
        "description": "Divorce index and records",
        "coverage": "1958-present",
        "access": "NC Vital Records office",
        "url": "https://vitalrecords.nc.gov/",
    },
}


# NC African American genealogy resources
NC_AFRICAN_AMERICAN: dict[str, dict[str, Any]] = {
    "freedmens_bureau": {
        "name": "NC Freedmen's Bureau Records",
        "description": "Labor contracts, marriage records, aid applications 1865-1872",
        "coverage": "Reconstruction era",
        "access": "Free via FamilySearch and Freedmen's Bureau Online",
        "familysearch_url": "https://www.familysearch.org/search/collection/1989155",
    },
    "slave_schedules": {
        "name": "NC Slave Schedules 1850-1860",
        "description": "Census slave schedules listing slaveholders",
        "coverage": "1850, 1860",
        "access": "Free via FamilySearch",
        "url": "https://www.familysearch.org/search/collection/1420440",
    },
    "cohabitation_records": {
        "name": "NC Cohabitation Records",
        "description": "Post-war records of formerly enslaved couples",
        "coverage": "1866",
        "access": "NC Archives",
        "url": "https://archives.ncdcr.gov/",
    },
    "church_records": {
        "name": "African American Church Records",
        "description": "Baptist, Methodist, and AME church records",
        "coverage": "1860s-present",
        "access": "Various archives and FamilySearch",
        "url": "https://www.familysearch.org/",
    },
}


# NC County resources (especially relevant for Durham/Wake area)
NC_COUNTY_RESOURCES: dict[str, dict[str, Any]] = {
    "wake_county": {
        "name": "Wake County Register of Deeds",
        "description": "Deeds, marriages, vital records for Raleigh area",
        "coverage": "1771-present",
        "access": "Online index and images",
        "url": "https://www.wakegov.com/rod",
        "notes": "Birthplace of Barney Durham",
    },
    "durham_county": {
        "name": "Durham County Register of Deeds",
        "description": "Deeds, marriages, vital records",
        "coverage": "1881-present (county formed 1881)",
        "access": "Online index and some images",
        "url": "https://dconc.gov/government/departments-a-e/register-of-deeds",
    },
    "granville_county": {
        "name": "Granville County Archives",
        "description": "Colonial records, early deeds",
        "coverage": "1746-present",
        "access": "NC Archives and FamilySearch",
        "url": "https://www.granvillecounty.org/",
    },
}


# NC newspapers
NC_NEWSPAPERS: ClassVar[list[dict[str, str]]] = [
    {
        "name": "Raleigh News & Observer",
        "dates": "1872-present",
        "access": "Newspapers.com / NewsBank",
        "notes": "Largest NC newspaper",
    },
    {
        "name": "Charlotte Observer",
        "dates": "1886-present",
        "access": "Newspapers.com",
        "notes": "Major Charlotte daily",
    },
    {
        "name": "The Carolinian",
        "dates": "1940-present",
        "access": "DigitalNC",
        "notes": "African American newspaper, Raleigh",
    },
    {
        "name": "Carolina Times",
        "dates": "1927-present",
        "access": "DigitalNC",
        "notes": "African American newspaper, Durham",
    },
    {
        "name": "Durham Morning Herald",
        "dates": "1893-1990s",
        "access": "Newspapers.com / Duke Libraries",
        "notes": "Durham County coverage",
    },
]


class NCStateArchivesSource(BaseSource):
    """North Carolina State Archives collections.

    Key resources:
    - Death certificates 1906-1994
    - Land grants 1663-1960
    - Wills and estate records
    - Military records
    """

    name = "NCStateArchives"
    base_url = "https://archives.ncdcr.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search NC Archives collections."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in NC_ARCHIVES_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ncarchives-{key}",
                    record_type="archive_collection",
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

        return records

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        return None


class NCVitalRecordsSource(BaseSource):
    """North Carolina vital records and death/birth indices.

    Key resources:
    - Death Certificates 1906-1994 (free via FamilySearch)
    - Marriage Records 1741-present
    - Birth records (restricted)
    """

    name = "NCVitalRecords"
    base_url = "https://vitalrecords.nc.gov"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search NC vital records indices."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        for key, resource in NC_VITAL_RECORDS.items():
            url = resource.get("familysearch_url", resource.get("url", self.base_url))
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"nc-vital-{key}",
                    record_type="vital_records",
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

        # Add FamilySearch NC Death Certificates search (priority)
        fs_death_url = f"https://www.familysearch.org/search/record/results?q.surname={quote_plus(surname)}&q.givenName={quote_plus(given_name)}&f.collectionId=1678694"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"nc-death-search-{surname}",
                record_type="death_certificate",
                url=fs_death_url,
                raw_data={"type": "FamilySearch Death Certificates"},
                extracted_fields={
                    "resource_name": "NC Death Certificates 1906-1994",
                    "search_url": fs_death_url,
                    "description": "Full death certificates with parents' names",
                    "coverage": "1906-1994",
                    "search_tip": f"Search for '{surname}' - includes cause of death and parents",
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


class NCAfricanAmericanSource(BaseSource):
    """North Carolina African American genealogy records.

    Critical for NC research:
    - Freedmen's Bureau records
    - Slave schedules 1850-1860
    - Cohabitation records 1866
    """

    name = "NCAfricanAmerican"
    base_url = "https://www.familysearch.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search African American records."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in NC_AFRICAN_AMERICAN.items():
            url = resource.get("familysearch_url", resource.get("url"))
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"nc-aa-{key}",
                    record_type="african_american_records",
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

        # Add Freedmen's Bureau search (priority for post-Civil War research)
        fb_url = f"https://www.familysearch.org/search/record/results?q.surname={quote_plus(surname)}&f.collectionId=1989155"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"nc-freedmen-search-{surname}",
                record_type="freedmens_bureau",
                url=fb_url,
                raw_data={"type": "Freedmen's Bureau search"},
                extracted_fields={
                    "resource_name": "NC Freedmen's Bureau Records",
                    "search_url": fb_url,
                    "description": "Labor contracts, marriages, assistance records 1865-1872",
                    "search_tip": f"Search for '{surname}' in Freedmen's Bureau records",
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


class NCCountyRecordsSource(BaseSource):
    """North Carolina county-level records.

    Focuses on Wake and Durham counties (Durham family origin area).
    """

    name = "NCCountyRecords"
    base_url = "https://www.wakegov.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search NC county records."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in NC_COUNTY_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"nc-county-{key}",
                    record_type="county_records",
                    url=resource["url"],
                    raw_data={"resource": resource},
                    extracted_fields={
                        "resource_name": resource["name"],
                        "description": resource["description"],
                        "coverage": resource["coverage"],
                        "access_method": resource["access"],
                        "notes": resource.get("notes", ""),
                        "search_surname": surname,
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


class NorthCarolinaGenealogySource(BaseSource):
    """Aggregator for all North Carolina genealogy sources.

    Combines:
    - NC State Archives
    - Vital Records (death/birth/marriage indices)
    - African American records (Freedmen's Bureau, slave schedules)
    - County records (Wake, Durham, Granville)
    - Newspaper archives
    """

    name = "NorthCarolinaGenealogy"

    COMPONENT_SOURCES: ClassVar[list[type[BaseSource]]] = [
        NCStateArchivesSource,
        NCVitalRecordsSource,
        NCAfricanAmericanSource,
        NCCountyRecordsSource,
    ]

    def __init__(self) -> None:
        super().__init__()
        self.archives = NCStateArchivesSource()
        self.vital = NCVitalRecordsSource()
        self.african_american = NCAfricanAmericanSource()
        self.county = NCCountyRecordsSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all North Carolina sources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Search component sources
        sources = [
            ("Archives", self.archives),
            ("Vital", self.vital),
            ("AfricanAmerican", self.african_american),
            ("County", self.county),
        ]

        for source_name, source in sources:
            try:
                source_records = await source.search(query)
                records.extend(source_records)
            except Exception as e:
                logger.debug(f"{source_name} search error: {e}")

        # Add DigitalNC newspaper search
        digitalnc_url = f"https://www.digitalnc.org/search/?q={quote_plus(surname)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"nc-newspapers-{surname}",
                record_type="newspaper_search",
                url=digitalnc_url,
                raw_data={"type": "DigitalNC"},
                extracted_fields={
                    "search_type": "North Carolina Newspapers",
                    "search_url": digitalnc_url,
                    "description": "Historic NC newspapers and documents",
                    "highlights": "Includes Carolina Times, The Carolinian (African American press)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add Chronicling America NC search
        ca_url = f"https://chroniclingamerica.loc.gov/search/pages/results/?state=North+Carolina&proxtext={quote_plus(surname)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"nc-chronicling-{surname}",
                record_type="newspaper_search",
                url=ca_url,
                raw_data={"type": "Chronicling America"},
                extracted_fields={
                    "search_type": "Chronicling America NC",
                    "search_url": ca_url,
                    "description": "Library of Congress NC newspapers",
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
