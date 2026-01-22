"""Cyndi's List source for genealogy resource links.

Cyndi's List is a comprehensive directory of genealogy resources organized
by category, location, and record type. It aggregates links to free and
paid resources worldwide.

Coverage: Worldwide genealogy resources
Categories: BMD, Census, Military, Immigration, etc.
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


# Country to Cyndi's List URL path mapping
COUNTRY_PATHS = {
    # European countries
    "norway": "norway",
    "sweden": "sweden",
    "denmark": "denmark",
    "finland": "finland",
    "iceland": "iceland",
    "belgium": "belgium",
    "netherlands": "netherlands",
    "germany": "germany",
    "france": "france",
    "ireland": "ireland",
    "scotland": "scotland",
    "wales": "wales",
    "england": "england",
    "uk": "uk-and-ireland",
    "italy": "italy",
    "spain": "spain",
    "portugal": "portugal",
    "poland": "poland",
    "russia": "russia",
    "ukraine": "ukraine",
    "czech": "czech-republic",
    "austria": "austria",
    "switzerland": "switzerland",
    "hungary": "hungary",
    # Americas
    "usa": "us",
    "canada": "canada",
    "mexico": "mexico",
    "brazil": "brazil",
    "argentina": "argentina",
    # Other
    "australia": "australia",
    "new zealand": "new-zealand",
    "south africa": "south-africa",
    "israel": "israel",
    "india": "india",
    "china": "china",
    "japan": "japan",
}

# Record type to category path
RECORD_TYPE_PATHS = {
    "birth": "bmd",
    "marriage": "bmd",
    "death": "bmd",
    "vital": "bmd",
    "census": "census",
    "military": "military",
    "immigration": "immigration",
    "emigration": "immigration",
    "naturalization": "immigration",
    "church": "church-records",
    "parish": "church-records",
    "land": "land-property",
    "probate": "wills-probate",
    "newspaper": "newspapers",
    "obituary": "obituaries",
}


class CyndisListSource(BaseSource):
    """Cyndi's List genealogy resource directory.

    Cyndi's List provides categorized links to genealogy resources:
    - Birth, Marriage, Death (BMD) records by country
    - Census records
    - Immigration/Emigration records
    - Military records
    - Church/Parish records
    - And more...

    No authentication required - it's a link directory.
    """

    name = "CyndisList"
    base_url = "https://www.cyndislist.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Cyndi's List for genealogy resources.

        Args:
            query: Search parameters

        Returns:
            List of resource links relevant to the query
        """
        records: list[RawRecord] = []

        # Determine relevant categories based on query
        categories = self._determine_categories(query)

        for category_url in categories:
            try:
                category_records = await self._fetch_category_links(category_url, query)
                records.extend(category_records)
            except Exception as e:
                logger.debug(f"Cyndi's List category fetch error: {e}")

        return records

    def _determine_categories(self, query: SearchQuery) -> list[str]:
        """Determine which Cyndi's List categories to search."""
        urls: list[str] = []

        # Get country from query
        country = None
        if query.state:
            # US state - use US category
            country = "usa"
        elif query.birth_place:
            place_lower = query.birth_place.lower()
            for country_name, path in COUNTRY_PATHS.items():
                if country_name in place_lower:
                    country = country_name
                    break

        # Get record types from query
        record_types = query.record_types or ["vital", "census"]

        # Build category URLs
        if country:
            country_path = COUNTRY_PATHS.get(country, country.lower().replace(" ", "-"))

            for rt in record_types:
                rt_lower = rt.lower()
                if rt_lower in RECORD_TYPE_PATHS:
                    category = RECORD_TYPE_PATHS[rt_lower]
                    urls.append(f"{self.base_url}/{country_path}/{category}/")

            # Always include general country page
            urls.append(f"{self.base_url}/{country_path}/")

        # Add general categories if no country-specific
        if not urls:
            for rt in record_types:
                rt_lower = rt.lower()
                if rt_lower in RECORD_TYPE_PATHS:
                    category = RECORD_TYPE_PATHS[rt_lower]
                    urls.append(f"{self.base_url}/categories/{category}/")

        return urls[:5]  # Limit to 5 categories

    async def _fetch_category_links(
        self,
        url: str,
        query: SearchQuery,
    ) -> list[RawRecord]:
        """Fetch and parse links from a Cyndi's List category page."""
        records: list[RawRecord] = []

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")

                # Parse page title for category info
                title_el = soup.select_one("h1, title")
                category_name = title_el.get_text(strip=True) if title_el else "Cyndi's List Resources"

                # Find resource links
                # Cyndi's List typically has links in lists or definition lists
                link_containers = soup.select(
                    ".link-list a, .resources a, article a, .entry-content a, "
                    "dl a, ul.links a, .category-links a"
                )

                # Also try generic external links
                if not link_containers:
                    link_containers = soup.find_all("a", href=re.compile(r"^https?://(?!www\.cyndislist)"))

                surname_lower = (query.surname or "").lower()

                for link in link_containers[:50]:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    # Skip internal navigation links
                    if not href or len(text) < 5:
                        continue
                    if "cyndislist.com" in href and not href.endswith(".htm"):
                        continue
                    if any(skip in href.lower() for skip in ["javascript:", "mailto:", "#", "facebook", "twitter"]):
                        continue

                    # Get description if available (often in parent element)
                    parent = link.parent
                    description = ""
                    if parent:
                        # Look for description in sibling or parent text
                        parent_text = parent.get_text(" ", strip=True)
                        if len(parent_text) > len(text) + 10:
                            description = parent_text

                    records.append(
                        RawRecord(
                            source=self.name,
                            record_id=f"cyndis-{hash(href)}",
                            record_type="resource_link",
                            url=href,
                            raw_data={
                                "link_text": text,
                                "category_url": url,
                                "description": description[:500] if description else "",
                            },
                            extracted_fields={
                                "resource_title": text,
                                "category": category_name,
                                "description": description[:200] if description else "",
                                "note": "Resource from Cyndi's List - verify access requirements",
                            },
                            accessed_at=datetime.now(UTC),
                        )
                    )

        except httpx.HTTPError as e:
            logger.debug(f"Cyndi's List fetch error for {url}: {e}")

        # Add the category page itself as a resource
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"cyndis-cat-{hash(url)}",
                record_type="category_page",
                url=url,
                raw_data={"category_url": url},
                extracted_fields={
                    "resource_title": "Cyndi's List Category Page",
                    "search_url": url,
                    "note": "Browse this category for more genealogy resources",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def search_country_bmd(
        self,
        country: str,
        record_type: str = "bmd",
    ) -> list[RawRecord]:
        """Search for BMD records for a specific country.

        Args:
            country: Country name
            record_type: Type of record (bmd, census, etc.)

        Returns:
            List of resource links
        """
        country_lower = country.lower()
        country_path = COUNTRY_PATHS.get(country_lower, country_lower.replace(" ", "-"))

        url = f"{self.base_url}/{country_path}/{record_type}/"

        return await self._fetch_category_links(
            url,
            SearchQuery(surname="", record_types=[record_type]),
        )

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Not implemented - Cyndi's List is a directory."""
        return None


class NorwayBMDSource(BaseSource):
    """Norwegian vital records resources from Cyndi's List and direct sources.

    Norway has excellent digitized records through:
    - Digitalarkivet (National Archives)
    - Arkivverket
    - FamilySearch collections
    """

    name = "NorwayBMD"
    base_url = "https://www.digitalarkivet.no"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Norwegian vital records sources."""
        records: list[RawRecord] = []

        # Add direct links to Norwegian archives
        norwegian_resources = [
            {
                "url": "https://www.digitalarkivet.no/en/search/persons",
                "name": "Digitalarkivet Person Search",
                "description": "Norwegian National Archives - free digitized church records, census, emigration",
            },
            {
                "url": "https://www.arkivverket.no/en/search",
                "name": "Arkivverket (National Archives)",
                "description": "Norwegian National Archives search portal",
            },
            {
                "url": "https://www.familysearch.org/search/collection/list?page=1&countryId=1927071",
                "name": "FamilySearch Norway Collections",
                "description": "Free Norwegian records on FamilySearch",
            },
            {
                "url": "https://www.rhd.uit.no/indexeng.html",
                "name": "Registreringssentralen for historiske data",
                "description": "Historical Population Register for Northern Norway",
            },
        ]

        for resource in norwegian_resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"norway-{hash(resource['url'])}",
                    record_type="resource_link",
                    url=resource["url"],
                    raw_data=resource,
                    extracted_fields={
                        "resource_title": resource["name"],
                        "description": resource["description"],
                        "country": "Norway",
                        "note": "Free Norwegian genealogy resource",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Cyndi's List Norway BMD page
        records.append(
            RawRecord(
                source=self.name,
                record_id="norway-cyndis-bmd",
                record_type="category_page",
                url="https://www.cyndislist.com/norway/bmd/",
                raw_data={},
                extracted_fields={
                    "resource_title": "Cyndi's List - Norway BMD",
                    "description": "Directory of Norwegian birth, marriage, death record resources",
                    "country": "Norway",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class BelgiumBMDSource(BaseSource):
    """Belgian vital records resources.

    Belgium has records through:
    - State Archives (Rijksarchief/Archives de l'État)
    - FamilySearch collections
    - Regional archives
    """

    name = "BelgiumBMD"
    base_url = "https://www.arch.be"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Belgian vital records sources."""
        records: list[RawRecord] = []

        belgian_resources = [
            {
                "url": "https://search.arch.be/en/",
                "name": "Belgian State Archives Search",
                "description": "Search digitized Belgian archives including civil registration",
            },
            {
                "url": "https://www.familysearch.org/search/collection/list?page=1&countryId=1927064",
                "name": "FamilySearch Belgium Collections",
                "description": "Free Belgian records on FamilySearch",
            },
            {
                "url": "https://www.genealogie.be/",
                "name": "Genealogie.be",
                "description": "Belgian genealogy federation resources",
            },
            {
                "url": "https://www.odis.be/hercules/_eng_inleiding.php",
                "name": "ODIS Database",
                "description": "Database of intermediary structures in Flanders",
            },
        ]

        for resource in belgian_resources:
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"belgium-{hash(resource['url'])}",
                    record_type="resource_link",
                    url=resource["url"],
                    raw_data=resource,
                    extracted_fields={
                        "resource_title": resource["name"],
                        "description": resource["description"],
                        "country": "Belgium",
                        "note": "Free Belgian genealogy resource",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Add Cyndi's List Belgium BMD page
        records.append(
            RawRecord(
                source=self.name,
                record_id="belgium-cyndis-bmd",
                record_type="category_page",
                url="https://www.cyndislist.com/belgium/bmd/",
                raw_data={},
                extracted_fields={
                    "resource_title": "Cyndi's List - Belgium BMD",
                    "description": "Directory of Belgian birth, marriage, death record resources",
                    "country": "Belgium",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None
