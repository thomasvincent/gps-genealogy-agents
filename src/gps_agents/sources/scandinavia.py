"""Scandinavian genealogy sources.

Scandinavian countries have excellent genealogical records because:
- Lutheran church records from 1600s onwards
- Early census records (Denmark 1787, Sweden 1749, Norway 1801)
- Extensive emigration records (millions emigrated 1850-1920)
- Digitization projects by national archives

Naming conventions:
- Patronymic system: Johan Eriksson = Johan, son of Erik
- Farm names in Norway: Per Olsen from Haugen = Per Olsen Haugen

Key sources:
- ArkivDigital (Sweden - subscription with some free)
- Digitalarkivet (Norway - free)
- Arkivalier Online (Denmark - free)
- Geneanet Scandinavian collections
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)


# Census years by country
SWEDISH_CENSUS_YEARS = [1890, 1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990]
NORWEGIAN_CENSUS_YEARS = [1801, 1815, 1825, 1835, 1845, 1855, 1865, 1875, 1885, 1891, 1900, 1910]
DANISH_CENSUS_YEARS = [1787, 1801, 1834, 1840, 1845, 1850, 1855, 1860, 1870, 1880, 1890, 1901, 1906, 1911, 1916, 1921]


class DigitalarkivetSource(BaseSource):
    """Digitalarkivet - Norwegian National Archives digital portal.

    FREE access to:
    - Church records (kirkebøker): baptisms, marriages, burials from 1600s
    - Census records (folketellinger): 1801, 1865, 1875, 1885, 1891, 1900, 1910
    - Emigration records: 1825-1930
    - Military records, probate, land records

    All records freely accessible without login.
    """

    name = "Digitalarkivet"
    base_url = "https://www.digitalarkivet.no"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Norwegian Digitalarkivet."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Convert patronymic endings for Norwegian (-sen, -son)
        surnames = self._get_norwegian_variants(query.surname)

        # Main person search
        search_url = f"{self.base_url}/en/search/persons"
        params: dict[str, str] = {
            "lastname": query.surname,
        }
        if query.given_name:
            params["firstname"] = query.given_name
        if query.birth_year:
            params["from_year"] = str(query.birth_year - 5)
            params["to_year"] = str(query.birth_year + 5)

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url, params=params)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    parsed = self._parse_results(soup, query)
                    records.extend(parsed)

        except httpx.HTTPError as e:
            logger.debug(f"Digitalarkivet search error: {e}")

        # Manual search URL
        manual_url = f"{search_url}?{urlencode(params)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id="digitalarkivet-search",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": params},
                extracted_fields={
                    "search_type": "Digitalarkivet Person Search",
                    "search_url": manual_url,
                    "note": "Free Norwegian church, census, emigration records",
                    "surname_variants": ", ".join(surnames),
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Emigration search if relevant years
        if query.birth_year and 1820 <= query.birth_year <= 1910:
            emigration_url = f"{self.base_url}/en/search/emigration"
            emig_params = {"lastname": query.surname}
            if query.given_name:
                emig_params["firstname"] = query.given_name

            records.append(
                RawRecord(
                    source=self.name,
                    record_id="digitalarkivet-emigration",
                    record_type="search_url",
                    url=f"{emigration_url}?{urlencode(emig_params)}",
                    raw_data={"type": "emigration"},
                    extracted_fields={
                        "search_type": "Norwegian Emigration Records",
                        "search_url": f"{emigration_url}?{urlencode(emig_params)}",
                        "note": "Norwegian emigrants 1825-1930",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _get_norwegian_variants(self, surname: str) -> list[str]:
        """Get Norwegian patronymic variants."""
        variants = [surname]

        # Common -sen/-son interchange
        if surname.endswith("sen"):
            variants.append(surname[:-3] + "son")
        elif surname.endswith("son"):
            variants.append(surname[:-3] + "sen")

        # Double consonant variants
        if "ss" in surname:
            variants.append(surname.replace("ss", "s"))
        if "tt" in surname:
            variants.append(surname.replace("tt", "t"))

        return list(set(variants))

    def _parse_results(self, soup: BeautifulSoup, query: SearchQuery) -> list[RawRecord]:
        """Parse Digitalarkivet search results."""
        records: list[RawRecord] = []

        results = soup.select(".search-result, .result-item, tr.result")
        for result in results[:25]:
            try:
                link = result.select_one("a")
                if not link:
                    continue

                text = result.get_text(" ", strip=True)
                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                extracted: dict[str, str] = {"summary": text[:200]}

                # Determine record type from URL or text
                text_lower = text.lower()
                if "kirkebok" in text_lower or "baptism" in text_lower or "dåp" in text_lower:
                    record_type = "baptism"
                elif "vielse" in text_lower or "marriage" in text_lower:
                    record_type = "marriage"
                elif "begrav" in text_lower or "burial" in text_lower:
                    record_type = "burial"
                elif "folketelling" in text_lower or "census" in text_lower:
                    record_type = "census"
                elif "emigrant" in text_lower:
                    record_type = "emigration"
                else:
                    record_type = "norwegian_record"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"digitalarkivet-{hash(url)}",
                        record_type=record_type,
                        url=url,
                        raw_data={"text": text},
                        extracted_fields=extracted,
                        accessed_at=datetime.now(UTC),
                    )
                )
            except Exception:
                continue

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        if record_id.startswith("http"):
            return None
        return None


class ArkivDigitalSource(BaseSource):
    """ArkivDigital - Swedish genealogy source.

    Swedish church and historical records:
    - Church records (kyrkoböcker): births, marriages, deaths
    - Moving records (husförhörslängder): household examination rolls
    - Census and population registers
    - Military rolls (generalmönsterrullor)

    Some indexed records free; images require subscription.
    """

    name = "ArkivDigital"
    base_url = "https://www.arkivdigital.se"

    def requires_auth(self) -> bool:
        return False  # Index search is free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search ArkivDigital."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Get Swedish patronymic variants
        surnames = self._get_swedish_variants(query.surname)

        search_url = f"{self.base_url}/search"
        params: dict[str, str] = {
            "lastname": query.surname,
        }
        if query.given_name:
            params["firstname"] = query.given_name
        if query.birth_year:
            params["birthyear"] = str(query.birth_year)

        manual_url = f"{search_url}?{urlencode(params)}"

        records.append(
            RawRecord(
                source=self.name,
                record_id="arkivdigital-search",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": params},
                extracted_fields={
                    "search_type": "ArkivDigital Swedish Records",
                    "search_url": manual_url,
                    "note": "Swedish church, census, military records",
                    "surname_variants": ", ".join(surnames),
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # SVAR (National Archives) free index
        svar_url = "https://sok.riksarkivet.se/sbl"
        svar_params = {"namn": query.surname}
        records.append(
            RawRecord(
                source=self.name,
                record_id="svar-search",
                record_type="search_url",
                url=f"{svar_url}?{urlencode(svar_params)}",
                raw_data={"database": "SVAR"},
                extracted_fields={
                    "search_type": "Swedish National Archives",
                    "search_url": f"{svar_url}?{urlencode(svar_params)}",
                    "note": "Free Swedish archival indexes",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Swedish Emigration Portal
        if query.birth_year and 1840 <= query.birth_year <= 1920:
            emig_url = "https://emiweb.se/Search/Search"
            emig_params = {"lastName": query.surname}
            if query.given_name:
                emig_params["firstName"] = query.given_name

            records.append(
                RawRecord(
                    source=self.name,
                    record_id="emiweb-search",
                    record_type="search_url",
                    url=f"{emig_url}?{urlencode(emig_params)}",
                    raw_data={"type": "emigration"},
                    extracted_fields={
                        "search_type": "Swedish Emigration Records",
                        "search_url": f"{emig_url}?{urlencode(emig_params)}",
                        "note": "Swedish emigrants to North America",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _get_swedish_variants(self, surname: str) -> list[str]:
        """Get Swedish patronymic variants."""
        variants = [surname]

        # Swedish -sson/-son variants
        if surname.endswith("sson"):
            variants.append(surname[:-4] + "son")
            variants.append(surname[:-4] + "sen")  # Danish influence
        elif surname.endswith("son"):
            variants.append(surname[:-3] + "sson")
            variants.append(surname[:-3] + "sen")

        # Common vowel variants
        for old, new in [("ö", "o"), ("ä", "a"), ("å", "a"), ("é", "e")]:
            if old in surname:
                variants.append(surname.replace(old, new))

        return list(set(variants))

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class DanishArchivesSource(BaseSource):
    """Danish National Archives (Rigsarkivet) sources.

    FREE access to:
    - Church records (kirkebøger): 1600s-1960
    - Census records (folketællinger): 1787-1940
    - Police registers (politiets registerblade): Copenhagen 1890-1923
    - Military levying rolls (lægdsruller)

    Most records digitized and free via Arkivalieronline.
    """

    name = "DanishArchives"
    base_url = "https://www.sa.dk"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Danish archives."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Get Danish name variants
        surnames = self._get_danish_variants(query.surname)

        # Arkivalieronline - main digitized records portal
        ao_url = "https://www.sa.dk/ao-soegesider/da/billedviser"
        ao_params = {"efternavn": query.surname}
        if query.given_name:
            ao_params["fornavn"] = query.given_name

        records.append(
            RawRecord(
                source=self.name,
                record_id="ao-search",
                record_type="search_url",
                url=f"{self.base_url}/ao-soegesider/",
                raw_data={"query": ao_params},
                extracted_fields={
                    "search_type": "Arkivalieronline (Danish Archives)",
                    "search_url": f"{self.base_url}/ao-soegesider/",
                    "note": "Free Danish church, census, police records",
                    "surname_variants": ", ".join(surnames),
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Danish census search
        census_url = "https://www.danishfamilysearch.com/census/"
        census_params = {"lastname": query.surname}
        if query.given_name:
            census_params["firstname"] = query.given_name

        records.append(
            RawRecord(
                source=self.name,
                record_id="danish-census-search",
                record_type="search_url",
                url=f"{census_url}?{urlencode(census_params)}",
                raw_data={"type": "census"},
                extracted_fields={
                    "search_type": "Danish Census Records",
                    "search_url": f"{census_url}?{urlencode(census_params)}",
                    "note": f"Census years: {', '.join(map(str, DANISH_CENSUS_YEARS[:10]))}...",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Copenhagen Police Register (1890-1923)
        if query.birth_place and "copenhagen" in query.birth_place.lower():
            police_url = "https://www.politietsregisterblade.dk"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="copenhagen-police",
                    record_type="search_url",
                    url=police_url,
                    raw_data={"type": "police_register"},
                    extracted_fields={
                        "search_type": "Copenhagen Police Register",
                        "search_url": police_url,
                        "note": "Copenhagen residents 1890-1923 with photos",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # Danish Emigration Archives
        if query.birth_year and 1850 <= query.birth_year <= 1920:
            emig_url = "https://www.emigration.dk"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="danish-emigration",
                    record_type="search_url",
                    url=emig_url,
                    raw_data={"type": "emigration"},
                    extracted_fields={
                        "search_type": "Danish Emigration Archives",
                        "search_url": emig_url,
                        "note": "Danish emigrants (free database)",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _get_danish_variants(self, surname: str) -> list[str]:
        """Get Danish patronymic variants."""
        variants = [surname]

        # Danish -sen variants
        if surname.endswith("sen"):
            variants.append(surname[:-3] + "son")
        elif surname.endswith("son"):
            variants.append(surname[:-3] + "sen")

        # Common Danish spelling variants
        for old, new in [("ø", "o"), ("æ", "ae"), ("å", "aa"), ("aa", "å")]:
            if old in surname:
                variants.append(surname.replace(old, new))

        return list(set(variants))

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class FinnishArchivesSource(BaseSource):
    """Finnish National Archives (Kansallisarkisto) sources.

    FREE access to:
    - Church records (kirkonkirjat): from 1600s
    - Census and population registers
    - Military records
    - Digitized via Digitaaliarkisto

    Finnish records use Finnish AND Swedish names (bilingual country).
    """

    name = "FinnishArchives"
    base_url = "https://astia.narc.fi"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Finnish archives."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Astia - National Archives search
        search_url = f"{self.base_url}/uusiastia/en/"
        params = {"searchTerm": query.surname}

        records.append(
            RawRecord(
                source=self.name,
                record_id="astia-search",
                record_type="search_url",
                url=search_url,
                raw_data={"query": params},
                extracted_fields={
                    "search_type": "Finnish National Archives (Astia)",
                    "search_url": search_url,
                    "note": "Free Finnish church, census records",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Sukuhistoria - Finnish genealogy portal
        suku_url = "https://www.sukuhistoria.fi/sshy/sivut/haku.htm"
        records.append(
            RawRecord(
                source=self.name,
                record_id="sukuhistoria-search",
                record_type="search_url",
                url=suku_url,
                raw_data={"type": "genealogy_portal"},
                extracted_fields={
                    "search_type": "Sukuhistoria (Finnish Genealogy)",
                    "search_url": suku_url,
                    "note": "Finnish genealogical society indexes",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Emigration to North America
        if query.birth_year and 1860 <= query.birth_year <= 1930:
            emig_url = "https://www.migrationinstitute.fi/databases/"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id="finnish-emigration",
                    record_type="search_url",
                    url=emig_url,
                    raw_data={"type": "emigration"},
                    extracted_fields={
                        "search_type": "Finnish Emigration Records",
                        "search_url": emig_url,
                        "note": "Finnish emigrants to North America",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class IcelandicArchivesSource(BaseSource):
    """Icelandic genealogy sources.

    Iceland has exceptional genealogical records:
    - Patronymic naming (still used today)
    - Church records from 1600s
    - Íslendingabók - database of all Icelanders

    Most Icelanders can trace ancestry to settlement period (874 AD).
    """

    name = "IcelandicArchives"
    base_url = "https://www.skjalasafn.is"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Icelandic genealogy resources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Íslendingabók - Book of Icelanders (genealogy database)
        islbok_url = "https://www.islendingabok.is"
        records.append(
            RawRecord(
                source=self.name,
                record_id="islendingabok",
                record_type="search_url",
                url=islbok_url,
                raw_data={"type": "genealogy_database"},
                extracted_fields={
                    "search_type": "Íslendingabók (Book of Icelanders)",
                    "search_url": islbok_url,
                    "note": "Database of all Icelanders - login required for full access",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # National Archives
        records.append(
            RawRecord(
                source=self.name,
                record_id="skjalasafn-search",
                record_type="search_url",
                url=self.base_url,
                raw_data={"surname": query.surname},
                extracted_fields={
                    "search_type": "Icelandic National Archives",
                    "search_url": self.base_url,
                    "note": "Church records, censuses, emigration",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class ScandinavianGenealogyAggregateSource(BaseSource):
    """Aggregate source for all Scandinavian genealogy searches.

    Combines:
    - Digitalarkivet (Norway)
    - ArkivDigital/Riksarkivet (Sweden)
    - Danish Archives/Arkivalieronline (Denmark)
    - Finnish National Archives (Finland)
    - Icelandic resources (Iceland)
    """

    name = "ScandinavianGenealogy"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key)
        self._norway = DigitalarkivetSource()
        self._sweden = ArkivDigitalSource()
        self._denmark = DanishArchivesSource()
        self._finland = FinnishArchivesSource()
        self._iceland = IcelandicArchivesSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Scandinavian sources."""
        records: list[RawRecord] = []

        # Determine which countries to search based on place hints
        countries_to_search = self._detect_countries(query)

        for country, source in [
            ("Norway", self._norway),
            ("Sweden", self._sweden),
            ("Denmark", self._denmark),
            ("Finland", self._finland),
            ("Iceland", self._iceland),
        ]:
            if not countries_to_search or country in countries_to_search:
                try:
                    results = await source.search(query)
                    records.extend(results)
                except Exception as e:
                    logger.debug(f"Scandinavian source {source.name} error: {e}")

        return records

    def _detect_countries(self, query: SearchQuery) -> set[str]:
        """Detect relevant Scandinavian countries from query."""
        countries: set[str] = set()

        if not query.birth_place:
            return countries  # Empty = search all

        place = query.birth_place.lower()

        country_keywords = {
            "Norway": ["norway", "norge", "oslo", "bergen", "trondheim", "norwegian"],
            "Sweden": ["sweden", "sverige", "stockholm", "göteborg", "malmö", "swedish"],
            "Denmark": ["denmark", "danmark", "copenhagen", "københavn", "danish"],
            "Finland": ["finland", "suomi", "helsinki", "turku", "finnish"],
            "Iceland": ["iceland", "ísland", "reykjavik", "icelandic"],
        }

        for country, keywords in country_keywords.items():
            if any(kw in place for kw in keywords):
                countries.add(country)

        return countries

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


# Patronymic name patterns
SCANDINAVIAN_PATRONYMICS = {
    "Swedish": {
        "male_suffix": "sson",
        "female_suffix": "sdotter",
        "common_given": ["Erik", "Johan", "Anders", "Per", "Olof", "Lars", "Karl", "Nils"],
    },
    "Norwegian": {
        "male_suffix": "sen",
        "female_suffix": "sdatter",
        "common_given": ["Ole", "Johan", "Anders", "Hans", "Per", "Lars", "Erik", "Ola"],
    },
    "Danish": {
        "male_suffix": "sen",
        "female_suffix": "sdatter",
        "common_given": ["Hans", "Jens", "Niels", "Lars", "Peter", "Anders", "Christen"],
    },
    "Icelandic": {
        "male_suffix": "son",
        "female_suffix": "dóttir",
        "common_given": ["Jón", "Sigurður", "Guðmundur", "Ólafur", "Kristján"],
    },
}
