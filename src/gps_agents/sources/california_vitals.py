"""California Vital Records source for genealogy research.

Provides access to California's public vital records indexes:
- California Death Index (1905-1997, 1999-2020+)
- California Birth Index (1905-1995)

These indexes are publicly available through various sources:
- FamilySearch (free with account) - most comprehensive
- RootsWeb/Ancestry (partial free access)
- Volunteer transcription sites

Note: Full certificates require ordering from California CDPH.
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


# California county codes used in vital records
CA_COUNTIES = {
    "001": "Alameda", "003": "Alpine", "005": "Amador", "007": "Butte",
    "009": "Calaveras", "011": "Colusa", "013": "Contra Costa", "015": "Del Norte",
    "017": "El Dorado", "019": "Fresno", "021": "Glenn", "023": "Humboldt",
    "025": "Imperial", "027": "Inyo", "029": "Kern", "031": "Kings",
    "033": "Lake", "035": "Lassen", "037": "Los Angeles", "039": "Madera",
    "041": "Marin", "043": "Mariposa", "045": "Mendocino", "047": "Merced",
    "049": "Modoc", "051": "Mono", "053": "Monterey", "055": "Napa",
    "057": "Nevada", "059": "Orange", "061": "Placer", "063": "Plumas",
    "065": "Riverside", "067": "Sacramento", "069": "San Benito",
    "071": "San Bernardino", "073": "San Diego", "075": "San Francisco",
    "077": "San Joaquin", "079": "San Luis Obispo", "081": "San Mateo",
    "083": "Santa Barbara", "085": "Santa Clara", "087": "Santa Cruz",
    "089": "Shasta", "091": "Sierra", "093": "Siskiyou", "095": "Solano",
    "097": "Sonoma", "099": "Stanislaus", "101": "Sutter", "103": "Tehama",
    "105": "Trinity", "107": "Tulare", "109": "Tuolumne", "111": "Ventura",
    "113": "Yolo", "115": "Yuba",
}


class CaliforniaVitalsSource(BaseSource):
    """California vital records index source.

    Searches California Death Index and Birth Index through available
    free sources. Primary approach is FamilySearch collections.

    Coverage:
    - Death Index: 1905-1997, 1999-2020+ (gap in 1998)
    - Birth Index: 1905-1995

    Fields typically available:
    - Full name
    - Birth date (month/year or full date)
    - Death date (for death index)
    - County of event
    - Mother's maiden name (birth index)
    - State file number
    """

    name = "CaliforniaVitals"
    base_url = "https://www.familysearch.org"

    # FamilySearch collection IDs
    DEATH_INDEX_COLLECTION = "1932433"  # California Death Index 1905-1939
    DEATH_INDEX_COLLECTION_2 = "1934585"  # California Death Index 1940-1997
    BIRTH_INDEX_COLLECTION = "1932380"  # California Birth Index 1905-1995

    def requires_auth(self) -> bool:
        """FamilySearch requires free account for search results."""
        return False  # Search is free, but detailed results need account

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search California vital records indexes.

        Args:
            query: Search parameters

        Returns:
            List of matching index records
        """
        records: list[RawRecord] = []

        # Determine which indexes to search based on record_types
        rt = {t.lower() for t in (query.record_types or [])}
        search_death = not rt or "death" in rt or "vital" in rt
        search_birth = not rt or "birth" in rt or "vital" in rt

        if search_death:
            death_records = await self._search_death_index(query)
            records.extend(death_records)

        if search_birth:
            birth_records = await self._search_birth_index(query)
            records.extend(birth_records)

        return records

    async def _search_death_index(self, query: SearchQuery) -> list[RawRecord]:
        """Search California Death Index via FamilySearch."""
        records: list[RawRecord] = []

        # Determine which collection based on year
        collections = []
        if query.death_year:
            if query.death_year <= 1939:
                collections.append(self.DEATH_INDEX_COLLECTION)
            elif query.death_year <= 1997:
                collections.append(self.DEATH_INDEX_COLLECTION_2)
            else:
                # Post-1997 not in FamilySearch free index
                collections.append(self.DEATH_INDEX_COLLECTION_2)
        else:
            # Search both if no year specified
            collections = [self.DEATH_INDEX_COLLECTION, self.DEATH_INDEX_COLLECTION_2]

        for collection_id in collections:
            try:
                coll_records = await self._search_familysearch_collection(
                    collection_id,
                    query,
                    "death",
                )
                records.extend(coll_records)
            except Exception as e:
                logger.debug(f"California Death Index search error: {e}")

        # Also try Rootsweb/USGenWeb California death records
        rootsweb_records = await self._search_rootsweb_california(query, "death")
        records.extend(rootsweb_records)

        return records

    async def _search_birth_index(self, query: SearchQuery) -> list[RawRecord]:
        """Search California Birth Index via FamilySearch."""
        records: list[RawRecord] = []

        try:
            coll_records = await self._search_familysearch_collection(
                self.BIRTH_INDEX_COLLECTION,
                query,
                "birth",
            )
            records.extend(coll_records)
        except Exception as e:
            logger.debug(f"California Birth Index search error: {e}")

        return records

    async def _search_familysearch_collection(
        self,
        collection_id: str,
        query: SearchQuery,
        record_type: str,
    ) -> list[RawRecord]:
        """Search a FamilySearch collection.

        Note: Full search results require FamilySearch account.
        This returns what's available without authentication.
        """
        records: list[RawRecord] = []

        # Build FamilySearch search URL
        params: dict[str, str] = {
            "count": "20",
            "offset": "0",
        }

        if query.given_name:
            params["q.givenName"] = query.given_name
        if query.surname:
            params["q.surname"] = query.surname

        # Year range for birth/death
        if record_type == "death" and query.death_year:
            yr = query.death_year
            params["q.deathLikeDate.from"] = str(yr - 2)
            params["q.deathLikeDate.to"] = str(yr + 2)
        elif record_type == "birth" and query.birth_year:
            yr = query.birth_year
            params["q.birthLikeDate.from"] = str(yr - 2)
            params["q.birthLikeDate.to"] = str(yr + 2)

        url = f"{self.base_url}/search/collection/{collection_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, params=params)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    records = self._parse_familysearch_results(soup, collection_id, record_type)

        except httpx.HTTPError as e:
            logger.debug(f"FamilySearch collection {collection_id} error: {e}")

        # Generate search URL record for manual follow-up
        search_url = f"{url}?{'&'.join(f'{k}={quote_plus(v)}' for k, v in params.items())}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ca-{record_type}-search-{query.surname or 'unknown'}",
                record_type="search_url",
                url=search_url,
                raw_data={"collection": collection_id, "query": query.model_dump()},
                extracted_fields={
                    "search_type": f"California {record_type.title()} Index",
                    "search_url": search_url,
                    "note": f"Open this URL to search California {record_type.title()} Index on FamilySearch (free account required)",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _parse_familysearch_results(
        self,
        soup: BeautifulSoup,
        collection_id: str,
        record_type: str,
    ) -> list[RawRecord]:
        """Parse FamilySearch search results HTML."""
        records: list[RawRecord] = []

        # FamilySearch result selectors
        result_selectors = [
            "[data-testid='searchResult']",
            ".result-item",
            ".search-result",
            "tr.result",
        ]

        items = []
        for selector in result_selectors:
            items = soup.select(selector)
            if items:
                break

        for item in items[:20]:
            try:
                # Extract link and name
                link = item.select_one("a[href*='/ark:/']") or item.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                name = link.get_text(strip=True)

                # Extract record ID from ARK
                record_id = ""
                ark_match = re.search(r"/ark:/61903/1:1:([A-Z0-9-]+)", href)
                if ark_match:
                    record_id = ark_match.group(1)

                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Extract additional data from item text
                item_text = item.get_text(" ", strip=True)
                extracted = self._extract_vital_fields(item_text, name, record_type)

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=record_id or f"ca-{record_type}-{hash(name)}",
                        record_type=record_type,
                        url=url,
                        raw_data={"html_text": item_text[:500], "collection": collection_id},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )

            except Exception as e:
                logger.debug(f"Failed to parse result item: {e}")
                continue

        return records

    def _extract_vital_fields(
        self,
        text: str,
        name: str,
        record_type: str,
    ) -> dict[str, str]:
        """Extract vital record fields from text."""
        extracted: dict[str, str] = {
            "full_name": name,
            "state": "California",
        }

        # Look for date patterns
        date_pattern = r"(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4})"

        if record_type == "death":
            # Death date
            death_match = re.search(rf"(?:died|death|d\.?)\s*{date_pattern}", text, re.I)
            if death_match:
                extracted["death_date"] = death_match.group(1)

            # Birth date (often in death records)
            birth_match = re.search(rf"(?:born|birth|b\.?)\s*{date_pattern}", text, re.I)
            if birth_match:
                extracted["birth_date"] = birth_match.group(1)

        elif record_type == "birth":
            # Birth date
            birth_match = re.search(date_pattern, text)
            if birth_match:
                extracted["birth_date"] = birth_match.group(1)

            # Mother's maiden name (common in birth index)
            mother_match = re.search(r"mother[:\s]+([A-Za-z]+)", text, re.I)
            if mother_match:
                extracted["mother_maiden_name"] = mother_match.group(1)

        # County
        for code, county in CA_COUNTIES.items():
            if county.lower() in text.lower():
                extracted["county"] = county
                break

        # State file number
        sfn_match = re.search(r"(?:sfn|file|cert)[:\s#]*(\d+)", text, re.I)
        if sfn_match:
            extracted["state_file_number"] = sfn_match.group(1)

        return extracted

    async def _search_rootsweb_california(
        self,
        query: SearchQuery,
        record_type: str,
    ) -> list[RawRecord]:
        """Search RootsWeb California vital records."""
        records: list[RawRecord] = []

        # RootsWeb California death records
        if record_type == "death":
            url = "https://sites.rootsweb.com/~cagenweb/deathindex.htm"
        else:
            return []  # Birth index not on RootsWeb

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")

                # Look for links to county-specific death records
                surname_initial = (query.surname or "")[:1].upper() if query.surname else ""

                for link in soup.find_all("a", href=True):
                    href = link.get("href", "")
                    text = link.get_text(strip=True)

                    # Look for alphabetical or county links
                    if surname_initial and surname_initial in text[:2].upper():
                        full_url = href if href.startswith("http") else f"https://sites.rootsweb.com/~cagenweb/{href}"
                        records.append(
                            RawRecord(
                                source=self.name,
                                record_id=f"rootsweb-ca-death-{text}",
                                record_type="death_index_link",
                                url=full_url,
                                raw_data={"link_text": text},
                                extracted_fields={
                                    "search_type": "RootsWeb California Death Records",
                                    "link_text": text,
                                    "note": "Follow this link for volunteer-transcribed death records",
                                },
                                accessed_at=datetime.now(UTC),
                            )
                        )

        except Exception as e:
            logger.debug(f"RootsWeb California search error: {e}")

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific California vital record by ID."""
        if record_id.startswith("http"):
            url = record_id
        else:
            url = f"{self.base_url}/ark:/61903/1:1:{record_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extract name from title
                title_el = soup.select_one("h1, .person-name, title")
                name = title_el.get_text(strip=True) if title_el else "Unknown"

                # Determine record type from URL/content
                url_lower = url.lower()
                if "death" in url_lower or "1932433" in url or "1934585" in url:
                    record_type = "death"
                else:
                    record_type = "birth"

                extracted = self._extract_vital_fields(soup.get_text(" "), name, record_type)

                return RawRecord(
                    source=self.name,
                    record_id=record_id,
                    record_type=record_type,
                    url=url,
                    raw_data={"name": name},
                    extracted_fields=extracted,
                    accessed_at=datetime.now(UTC),
                )

        except Exception as e:
            logger.warning(f"Failed to fetch California vital record: {e}")
            return None


class CaliforniaDeathIndexSource(CaliforniaVitalsSource):
    """Convenience class specifically for California Death Index."""

    name = "CaliforniaDeathIndex"

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search only the Death Index."""
        # Force death record type
        modified_query = query.model_copy()
        modified_query.record_types = ["death"]
        return await super().search(modified_query)


class CaliforniaBirthIndexSource(CaliforniaVitalsSource):
    """Convenience class specifically for California Birth Index."""

    name = "CaliforniaBirthIndex"

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search only the Birth Index."""
        # Force birth record type
        modified_query = query.model_copy()
        modified_query.record_types = ["birth"]
        return await super().search(modified_query)
