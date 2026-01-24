"""German genealogy sources.

German genealogical records include:
- Church records (Kirchenbücher): Protestant, Catholic, Jewish
- Civil registration (Standesamtsregister): from 1876 nationwide, earlier in some regions
- Census and population registers (Einwohnermeldekartei)
- Military records, guild records, emigration lists

Key challenges:
- Records in old German script (Kurrent/Sütterlin)
- Territorial changes (Prussia, various German states)
- Two World Wars caused record losses

Free sources:
- Archion (Protestant church books - some free)
- Matricula (Catholic church books - free)
- Familysearch (indexed German records)
- Regional archives (Landesarchive)
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


# German civil registration began 1876 nationwide
# Earlier in some regions: Prussia 1874, Rhineland 1798 (French occupation)
GERMAN_CIVIL_REG_START = 1876


class ArchionSource(BaseSource):
    """Archion - German Protestant church records portal.

    Provides digitized images of Protestant (Evangelisch) church books:
    - Baptisms (Taufen)
    - Marriages (Trauungen)
    - Deaths/Burials (Bestattungen/Beerdigungen)
    - Confirmations (Konfirmationen)

    Some indexed records are free; most images require subscription.
    """

    name = "Archion"
    base_url = "https://www.archion.de"

    def requires_auth(self) -> bool:
        return False  # Catalog/index search is free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Archion catalog."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Archion has a church book catalog (Kirchenbuchverzeichnis)
        # and some indexed names
        search_params = {
            "searchterm": query.surname,
        }
        if query.given_name:
            search_params["searchterm"] = f"{query.given_name} {query.surname}"

        search_url = f"{self.base_url}/suche"
        manual_url = f"{search_url}?{urlencode(search_params)}"

        # Try to search location index if birth_place specified
        location_hint = ""
        if query.birth_place:
            location_hint = self._map_place_to_region(query.birth_place.lower())

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "GPS-Genealogy-Agents/0.2.0 (genealogy research)",
                    "Accept": "text/html",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url, params=search_params)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    parsed = self._parse_results(soup, query)
                    records.extend(parsed)

        except httpx.HTTPError as e:
            logger.debug(f"Archion search error: {e}")

        # Add manual search link
        records.append(
            RawRecord(
                source=self.name,
                record_id="archion-search",
                record_type="search_url",
                url=manual_url,
                raw_data={"query": search_params},
                extracted_fields={
                    "search_type": "Archion Protestant Church Books",
                    "search_url": manual_url,
                    "note": "German Protestant church records (Taufen, Trauungen, Bestattungen)",
                    "region_hint": location_hint or "Germany-wide",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        return records

    def _map_place_to_region(self, place: str) -> str:
        """Map German place names to Archion regions."""
        region_keywords = {
            "Württemberg": ["stuttgart", "württemberg", "baden-württemberg", "ulm", "tübingen"],
            "Bayern": ["bayern", "bavaria", "münchen", "munich", "nürnberg", "augsburg"],
            "Hessen": ["hessen", "frankfurt", "wiesbaden", "kassel", "darmstadt"],
            "Niedersachsen": ["niedersachsen", "hannover", "braunschweig", "oldenburg"],
            "Rheinland": ["rheinland", "köln", "cologne", "düsseldorf", "bonn"],
            "Westfalen": ["westfalen", "münster", "dortmund", "bielefeld"],
            "Sachsen": ["sachsen", "saxony", "dresden", "leipzig", "chemnitz"],
            "Brandenburg": ["brandenburg", "potsdam"],
            "Berlin": ["berlin"],
            "Preußen": ["preußen", "prussia", "ostpreußen", "westpreußen", "pommern"],
            "Schlesien": ["schlesien", "silesia", "breslau", "wrocław"],
        }

        for region, keywords in region_keywords.items():
            for kw in keywords:
                if kw in place:
                    return region

        return ""

    def _parse_results(self, soup: BeautifulSoup, query: SearchQuery) -> list[RawRecord]:
        """Parse Archion search results."""
        records: list[RawRecord] = []

        results = soup.select(".search-result, .result-item, .treffer")
        for result in results[:20]:
            try:
                link = result.select_one("a")
                if not link:
                    continue

                text = result.get_text(" ", strip=True)
                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Extract church/location if present
                extracted: dict[str, str] = {"summary": text[:200]}

                # Try to identify record type from German text
                text_lower = text.lower()
                if "tauf" in text_lower:
                    record_type = "baptism"
                elif "trau" in text_lower or "heirat" in text_lower:
                    record_type = "marriage"
                elif "bestat" in text_lower or "beerd" in text_lower or "tod" in text_lower:
                    record_type = "burial"
                elif "konfirm" in text_lower:
                    record_type = "confirmation"
                else:
                    record_type = "church_book"

                records.append(
                    RawRecord(
                        source=self.name,
                        record_id=f"archion-{hash(url)}",
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
        return None  # Most records require subscription


class MatriculaSource(BaseSource):
    """Matricula - Catholic church records from German-speaking Europe.

    Free access to digitized Catholic parish registers:
    - Germany (various dioceses)
    - Austria
    - Poland (formerly German territories)
    - Slovenia, Serbia (Habsburg territories)

    Includes baptisms, marriages, deaths from ~1600 onwards.
    """

    name = "Matricula"
    base_url = "https://data.matricula-online.eu"

    def requires_auth(self) -> bool:
        return False  # Fully free

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Matricula catalog."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # Matricula has location-based browsing, not name search
        # Provide search tips and browsing links
        location = query.birth_place or ""
        diocese_hint = self._suggest_diocese(location.lower()) if location else ""

        # Main catalog URL
        catalog_url = f"{self.base_url}/de/browse"

        records.append(
            RawRecord(
                source=self.name,
                record_id="matricula-browse",
                record_type="search_url",
                url=catalog_url,
                raw_data={"surname": query.surname, "location": location},
                extracted_fields={
                    "search_type": "Matricula Catholic Church Books",
                    "browse_url": catalog_url,
                    "note": "Free Catholic church records - browse by location/diocese",
                    "diocese_suggestion": diocese_hint or "Browse by country/diocese",
                    "tip": f"Look for surname '{query.surname}' in parish registers of {location or 'relevant area'}",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # If we have a location, provide direct diocese link
        if diocese_hint:
            diocese_url = f"{self.base_url}/de/suchen/{diocese_hint.lower().replace(' ', '-')}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"matricula-{diocese_hint}",
                    record_type="search_url",
                    url=diocese_url,
                    raw_data={"diocese": diocese_hint},
                    extracted_fields={
                        "search_type": f"Matricula - Diocese of {diocese_hint}",
                        "browse_url": diocese_url,
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    def _suggest_diocese(self, location: str) -> str:
        """Suggest Catholic diocese based on location."""
        diocese_map = {
            "Köln": ["köln", "cologne", "bonn", "aachen"],
            "München-Freising": ["münchen", "munich", "freising"],
            "Regensburg": ["regensburg", "bayern", "bavaria"],
            "Würzburg": ["würzburg", "franken", "franconia"],
            "Mainz": ["mainz", "hessen"],
            "Trier": ["trier", "mosel"],
            "Freiburg": ["freiburg", "baden"],
            "Rottenburg-Stuttgart": ["rottenburg", "stuttgart", "württemberg"],
            "Paderborn": ["paderborn", "westfalen"],
            "Münster": ["münster"],
            "Wien": ["wien", "vienna"],
            "Salzburg": ["salzburg"],
            "Linz": ["linz", "oberösterreich"],
            "Graz": ["graz", "steiermark"],
        }

        for diocese, keywords in diocese_map.items():
            for kw in keywords:
                if kw in location:
                    return diocese

        return ""

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class GenealogyNetSource(BaseSource):
    """Genealogy.net (Verein für Computergenealogie).

    German genealogical society portal with:
    - GEDBAS (uploaded family trees)
    - Ortsfamilienbücher (local family books)
    - GOV (Genealogical Gazetteer)
    - Address books and other databases
    """

    name = "GenealogyNet"
    base_url = "https://www.genealogy.net"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Genealogy.net databases."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        # GEDBAS - Family tree database
        gedbas_url = f"https://gedbas.genealogy.net/search/simple"
        gedbas_params = {
            "nachname": query.surname,
        }
        if query.given_name:
            gedbas_params["vorname"] = query.given_name

        records.append(
            RawRecord(
                source=self.name,
                record_id="gedbas-search",
                record_type="search_url",
                url=f"{gedbas_url}?{urlencode(gedbas_params)}",
                raw_data={"database": "GEDBAS"},
                extracted_fields={
                    "search_type": "GEDBAS Family Trees",
                    "search_url": f"{gedbas_url}?{urlencode(gedbas_params)}",
                    "note": "Uploaded family trees from German researchers",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # Ortsfamilienbücher - Local family books
        ofb_url = "http://www.online-ofb.de/namelist.php"
        ofb_params = {"nachname": query.surname}

        records.append(
            RawRecord(
                source=self.name,
                record_id="ofb-search",
                record_type="search_url",
                url=f"{ofb_url}?{urlencode(ofb_params)}",
                raw_data={"database": "OFB"},
                extracted_fields={
                    "search_type": "Ortsfamilienbücher (Local Family Books)",
                    "search_url": f"{ofb_url}?{urlencode(ofb_params)}",
                    "note": "Transcribed local family histories",
                },
                accessed_at=datetime.now(UTC),
            )
        )

        # GOV - Genealogical Gazetteer
        if query.birth_place:
            gov_url = "http://gov.genealogy.net/search/index"
            gov_params = {"searchterm": query.birth_place}

            records.append(
                RawRecord(
                    source=self.name,
                    record_id="gov-search",
                    record_type="search_url",
                    url=f"{gov_url}?{urlencode(gov_params)}",
                    raw_data={"database": "GOV"},
                    extracted_fields={
                        "search_type": "GOV Gazetteer",
                        "search_url": f"{gov_url}?{urlencode(gov_params)}",
                        "note": "Historical place information and jurisdictions",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class FamilienkundeSource(BaseSource):
    """German genealogical societies and resources.

    Provides links to:
    - Regional genealogical societies (Vereine)
    - Local archives (Stadtarchive, Kreisarchive)
    - State archives (Landesarchive)
    """

    name = "Familienkunde"
    base_url = "https://wiki.genealogy.net"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Provide German genealogical society resources."""
        records: list[RawRecord] = []

        if query.birth_place:
            # Wiki search for the location
            place = query.birth_place.split(",")[0].strip()  # First part of place
            wiki_url = f"{self.base_url}/wiki/{place.replace(' ', '_')}"

            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"wiki-{place}",
                    record_type="search_url",
                    url=wiki_url,
                    raw_data={"place": place},
                    extracted_fields={
                        "search_type": f"GenWiki: {place}",
                        "wiki_url": wiki_url,
                        "note": "Local genealogy resources, archive info",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        # General surname search in Wiki
        if query.surname:
            surname_url = f"{self.base_url}/wiki/Familienname_{query.surname}"
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"wiki-surname-{query.surname}",
                    record_type="search_url",
                    url=surname_url,
                    raw_data={"surname": query.surname},
                    extracted_fields={
                        "search_type": f"GenWiki Surname: {query.surname}",
                        "wiki_url": surname_url,
                        "note": "Surname origins and distribution",
                    },
                    accessed_at=datetime.now(UTC),
                )
            )

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


class GermanGenealogyAggregateSource(BaseSource):
    """Aggregate source for all German genealogy searches.

    Combines:
    - Archion (Protestant records)
    - Matricula (Catholic records)
    - Genealogy.net (GEDBAS, OFB, GOV)
    - Familienkunde (societies, archives)
    """

    name = "GermanGenealogy"

    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(api_key)
        self._archion = ArchionSource()
        self._matricula = MatriculaSource()
        self._gennet = GenealogyNetSource()
        self._famkunde = FamilienkundeSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all German sources."""
        records: list[RawRecord] = []

        for source in [self._archion, self._matricula, self._gennet, self._famkunde]:
            try:
                results = await source.search(query)
                records.extend(results)
            except Exception as e:
                logger.debug(f"German sub-source {source.name} error: {e}")

        return records

    async def get_record(self, record_id: str) -> RawRecord | None:
        return None


# German name substitutions for variant searches
GERMAN_NAME_SUBSTITUTIONS = {
    # Common given name variants
    "Johann": ["Johannes", "Hans", "Jan"],
    "Maria": ["Marie", "Marianne"],
    "Wilhelm": ["Willi", "Will", "William"],
    "Friedrich": ["Fritz", "Frederick", "Fred"],
    "Heinrich": ["Heinz", "Henry"],
    "Karl": ["Carl", "Charles"],
    "Elisabeth": ["Elise", "Liesel", "Bettina", "Elizabeth"],
    "Katharina": ["Katharine", "Catherine", "Käthe"],
    "Margarethe": ["Margarete", "Grete", "Margaret"],
    "Anna": ["Anne", "Anny", "Hannah"],
    # Common surname patterns
    "ß": ["ss"],  # Eszett
    "ue": ["ü"],
    "oe": ["ö"],
    "ae": ["ä"],
}


# German state abbreviations
GERMAN_STATES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}
