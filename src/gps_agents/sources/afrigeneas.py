"""African American genealogy sources.

Includes:
- Afrigeneas.org - community and resources
- Freedman's Bureau records (NARA)
- Slave schedules and manumission records
- African American newspapers
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


class AfrigeneaSourc(BaseSource):
    """Afrigeneas.org - African American genealogy community.

    Afrigeneas provides:
    - Surname databases
    - Slave data collection
    - Message boards
    - Research guides

    Free to use, community-driven.
    """

    name = "Afrigeneas"
    base_url = "https://www.afrigeneas.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Afrigeneas resources.

        Args:
            query: Search parameters

        Returns:
            List of resource links and records
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Afrigeneas surname search
        surname_url = f"{self.base_url}/aasurname.htm"

        # Add search URLs for different databases
        resources = [
            {
                "name": "Afrigeneas Surname Database",
                "url": f"{self.base_url}/aasurname.htm",
                "description": "Search African American surname registry",
            },
            {
                "name": "Slave Data Collection",
                "url": f"{self.base_url}/slavedata/index.html",
                "description": "Slave schedules, wills, inventories mentioning enslaved persons",
            },
            {
                "name": "Afrigeneas Forum",
                "url": f"{self.base_url}/forum/",
                "description": "Community message boards for research help",
            },
            {
                "name": "Obituary Database",
                "url": f"{self.base_url}/aaobit.htm",
                "description": "African American obituary submissions",
            },
        ]

        for resource in resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"afrigeneas-{hash(resource['name'])}",
                    record_type="resource_link",
                    url=resource["url"],
                    raw_data=resource,
                    extracted_fields={
                        "resource_title": resource["name"],
                        "description": resource["description"],
                        "note": "Free African American genealogy resource",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class FreedmansBureauSource(BaseSource):
    """Freedman's Bureau records from NARA and FamilySearch.

    The Bureau of Refugees, Freedmen, and Abandoned Lands (1865-1872)
    created records vital for African American genealogy:
    - Labor contracts
    - Marriage records
    - Ration records
    - Hospital records
    - School records
    - Land records

    Records are free on FamilySearch and NARA.
    """

    name = "FreedmansBureau"
    base_url = "https://www.familysearch.org"

    # FamilySearch collection IDs for Freedmen's Bureau
    COLLECTIONS = {
        "freedmens_bureau": "1989155",  # Main collection
        "labor_contracts": "2426245",
        "marriage_records": "1803968",
        "field_office_records": "2140102",
    }

    def requires_auth(self) -> bool:
        return False  # FamilySearch search is free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Freedman's Bureau records.

        Args:
            query: Search parameters

        Returns:
            List of records and search links
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Build search parameters
        params: list[str] = []
        if query.surname:
            params.append(f"q.surname={quote_plus(query.surname)}")
        if query.given_name:
            params.append(f"q.givenName={quote_plus(query.given_name)}")

        # State filter
        state = None
        if query.state:
            state = query.state
        elif query.birth_place:
            parts = query.birth_place.split(",")
            if len(parts) >= 2:
                state = parts[-1].strip()

        # Search each relevant collection
        for coll_name, coll_id in self.COLLECTIONS.items():
            url = f"{self.base_url}/search/collection/{coll_id}"
            if params:
                url += "?" + "&".join(params)

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"freedmen-{coll_name}",
                    record_type="search_url",
                    url=url,
                    raw_data={"collection": coll_name, "collection_id": coll_id},
                    extracted_fields={
                        "search_type": f"Freedmen's Bureau - {coll_name.replace('_', ' ').title()}",
                        "search_url": url,
                        "description": "Free Freedmen's Bureau records on FamilySearch",
                        "note": "Records of freed slaves 1865-1872",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Freedmen's Bureau page at NARA
        nara_url = "https://www.archives.gov/research/african-americans/freedmens-bureau"
        records.append(
            RawRecord(
                source=self.name,
                record_id="freedmen-nara",
                record_type="resource_link",
                url=nara_url,
                raw_data={},
                extracted_fields={
                    "resource_title": "NARA Freedmen's Bureau Records",
                    "description": "National Archives guide to Freedmen's Bureau records",
                    "note": "Research guide for accessing original records",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add Freedmen and Southern Society Project
        fssp_url = "https://freedmen.umd.edu/"
        records.append(
            RawRecord(
                source=self.name,
                record_id="freedmen-fssp",
                record_type="resource_link",
                url=fssp_url,
                raw_data={},
                extracted_fields={
                    "resource_title": "Freedmen and Southern Society Project",
                    "description": "University of Maryland documentary history project",
                    "note": "Scholarly documentation of emancipation",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class SlaveSchedulesSource(BaseSource):
    """US Slave Schedules from 1850 and 1860 censuses.

    The slave schedules list enslaved persons by:
    - Slaveholder name (not enslaved person's name typically)
    - Age, sex, color
    - Number of slaves owned
    - State/county

    Available free on FamilySearch and Ancestry (with library access).
    """

    name = "SlaveSchedules"
    base_url = "https://www.familysearch.org"

    # FamilySearch collections for slave schedules
    COLLECTIONS = {
        "1850_slave_schedules": "1420440",
        "1860_slave_schedules": "1473181",
    }

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search slave schedule records.

        Note: Slave schedules typically list slaveholder names, not
        enslaved persons. Search by potential slaveholder surname.

        Args:
            query: Search parameters

        Returns:
            List of search links
        """
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Search slave schedules by slaveholder surname
        params: list[str] = [f"q.surname={quote_plus(query.surname)}"]

        for year, coll_id in self.COLLECTIONS.items():
            url = f"{self.base_url}/search/collection/{coll_id}?" + "&".join(params)

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"slave-schedules-{year}",
                    record_type="search_url",
                    url=url,
                    raw_data={"year": year, "collection_id": coll_id},
                    extracted_fields={
                        "search_type": f"US Slave Schedules {year[:4]}",
                        "search_url": url,
                        "description": f"Search {year[:4]} federal slave schedule by slaveholder name",
                        "note": "Enslaved persons listed by age/sex under slaveholder name",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class AfricanAmericanGenealogySource(BaseSource):
    """Aggregator for African American genealogy sources.

    Combines:
    - Afrigeneas
    - Freedmen's Bureau
    - Slave Schedules
    - African American newspapers
    - Colored Troops records
    """

    name = "AfricanAmericanGenealogy"

    def __init__(self) -> None:
        super().__init__()
        self.afrigeneas = AfrigeneaSourc()
        self.freedmens = FreedmansBureauSource()
        self.slave_schedules = SlaveSchedulesSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all African American genealogy sources."""
        records: list[RawRecord] = []

        # Search each sub-source
        try:
            records.extend(await self.afrigeneas.search(query))
        except Exception as e:
            logger.debug(f"Afrigeneas search error: {e}")

        try:
            records.extend(await self.freedmens.search(query))
        except Exception as e:
            logger.debug(f"Freedmen's Bureau search error: {e}")

        try:
            records.extend(await self.slave_schedules.search(query))
        except Exception as e:
            logger.debug(f"Slave schedules search error: {e}")

        # Add USCT records (US Colored Troops)
        usct_url = f"https://www.familysearch.org/search/collection/1932402?q.surname={quote_plus(query.surname or '')}"
        records.append(
            RawRecord(
                source=self.name,
                record_id="usct-civil-war",
                record_type="search_url",
                url=usct_url,
                raw_data={},
                extracted_fields={
                    "search_type": "US Colored Troops Civil War Records",
                    "search_url": usct_url,
                    "description": "Service records of African American soldiers in Civil War",
                    "note": "Free on FamilySearch",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Add African American Newspapers
        aa_newspapers_url = f"https://chroniclingamerica.loc.gov/search/pages/results/?andtext={quote_plus(query.surname or '')}&ethnicity=African+American"
        records.append(
            RawRecord(
                source=self.name,
                record_id="aa-newspapers",
                record_type="search_url",
                url=aa_newspapers_url,
                raw_data={},
                extracted_fields={
                    "search_type": "African American Newspapers",
                    "search_url": aa_newspapers_url,
                    "description": "Historic African American newspapers (Library of Congress)",
                    "note": "Free via Chronicling America",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
