"""Oklahoma genealogy sources with birth/death indices.

State archives and vital records for Oklahoma genealogy research:
- Oklahoma Historical Society - newspapers, photographs, manuscripts
- Oklahoma State Archives - vital records, land records, military records
- Oklahoma Death Index (1908-present) - via FamilySearch/Ancestry
- Oklahoma Birth Index (various years) - limited access
- Oklahoma Marriages (1890-present) - county records
- OHS Dawes Rolls - searchable Final Rolls of Five Civilized Tribes (1898-1914)

Coverage: Oklahoma (1889-present, Indian Territory 1830s-1907)
Records: Vital records, newspapers, land allotments, Indian rolls
Access: Mixed - some free via FamilySearch, others require fee or library access
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
from ..utils.name_variants import generate_surname_variants, get_all_search_names
from .base import BaseSource

logger = logging.getLogger(__name__)


def parse_cross_references(note: str) -> list[dict[str, str]]:
    """Parse cross-references from Dawes Roll note fields.

    Common patterns:
    - "See Card 4135"
    - "See Cherokee Card 1209"
    - "See Creek Freedmen Card 123"
    - "Wife on Card 4136"
    - "Child of Card 4135"

    Args:
        note: The note text from a Dawes record

    Returns:
        List of dicts with 'card_number', 'tribe' (if mentioned), and 'relationship'
    """
    references: list[dict[str, str]] = []

    if not note:
        return references

    # Pattern for "See [Tribe] [Type] Card NNN"
    see_pattern = re.compile(
        r"See\s+(?:(Cherokee|Chickasaw|Choctaw|Creek|Muscogee|Seminole)\s+)?"
        r"(?:(Freedmen|by Blood|Intermarriage)\s+)?Card\s+(\d+)",
        re.IGNORECASE,
    )

    for match in see_pattern.finditer(note):
        tribe = match.group(1) or ""
        enrollment_type = match.group(2) or ""
        card_num = match.group(3)
        references.append({
            "card_number": card_num,
            "tribe": tribe,
            "enrollment_type": enrollment_type,
            "relationship": "referenced",
            "raw_match": match.group(0),
        })

    # Pattern for relationship mentions with card numbers
    rel_patterns = [
        (r"(?:Wife|Husband|Spouse)\s+(?:on\s+)?Card\s+(\d+)", "spouse"),
        (r"(?:Child|Son|Daughter)\s+(?:of\s+)?Card\s+(\d+)", "parent"),
        (r"(?:Parent|Father|Mother)\s+(?:on\s+)?Card\s+(\d+)", "child"),
        (r"(?:Brother|Sister|Sibling)\s+(?:on\s+)?Card\s+(\d+)", "sibling"),
    ]

    for pattern, relationship in rel_patterns:
        for match in re.finditer(pattern, note, re.IGNORECASE):
            card_num = match.group(1)
            # Don't duplicate if already found by "See Card" pattern
            if not any(r["card_number"] == card_num for r in references):
                references.append({
                    "card_number": card_num,
                    "tribe": "",
                    "enrollment_type": "",
                    "relationship": relationship,
                    "raw_match": match.group(0),
                })

    # Simple "Card NNN" references not caught above
    simple_pattern = re.compile(r"\bCard\s+(\d+)\b", re.IGNORECASE)
    for match in simple_pattern.finditer(note):
        card_num = match.group(1)
        if not any(r["card_number"] == card_num for r in references):
            references.append({
                "card_number": card_num,
                "tribe": "",
                "enrollment_type": "",
                "relationship": "mentioned",
                "raw_match": match.group(0),
            })

    return references


# Oklahoma Historical Society resources
OHS_RESOURCES: dict[str, dict[str, Any]] = {
    "newspapers": {
        "name": "Oklahoma Digital Newspaper Program",
        "description": "Historic Oklahoma newspapers via Chronicling America",
        "coverage": "1840s-1960s, 500,000+ pages",
        "access": "Free online",
        "url": "https://gateway.okhistory.org/explore/collections/ODNP/",
    },
    "photographs": {
        "name": "Oklahoma Historical Society Photo Archives",
        "description": "200,000+ historic photographs",
        "coverage": "1880s-present",
        "access": "Free searchable online",
        "url": "https://gateway.okhistory.org/explore/collections/PHOTOS/",
    },
    "encyclopedia": {
        "name": "Encyclopedia of Oklahoma History and Culture",
        "description": "2,000+ articles on Oklahoma history",
        "coverage": "State history and biography",
        "access": "Free online",
        "url": "https://www.okhistory.org/publications/enc",
    },
    "manuscripts": {
        "name": "Manuscript Collections",
        "description": "Family papers, diaries, correspondence",
        "coverage": "Pioneer families, Indian Territory era",
        "access": "On-site research",
        "url": "https://www.okhistory.org/research/manuscripts",
    },
}


# Oklahoma vital records sources
OKLAHOMA_VITAL_RECORDS: dict[str, dict[str, Any]] = {
    "death_index": {
        "name": "Oklahoma Death Index",
        "description": "Statewide death records index",
        "coverage": "1908-1969 (free), 1970-present (restricted)",
        "access": "Free 1908-1969 via FamilySearch; later years via VitalChek",
        "familysearch_url": "https://www.familysearch.org/search/collection/1320895",
    },
    "birth_index": {
        "name": "Oklahoma Birth Index",
        "description": "Birth records (restricted by state law)",
        "coverage": "1908-present (restricted access)",
        "access": "Certified copies only from OSDH",
        "url": "https://oklahoma.gov/health/birth-and-death-certificates.html",
    },
    "marriage_records": {
        "name": "Oklahoma Marriage Records",
        "description": "County-level marriage records",
        "coverage": "1890-present",
        "access": "FamilySearch (some years), county clerks",
        "familysearch_url": "https://www.familysearch.org/search/collection/1674643",
    },
    "divorce_records": {
        "name": "Oklahoma Divorce Records",
        "description": "Divorce index and records",
        "coverage": "1968-present",
        "access": "OSCN court records search",
        "url": "https://www.oscn.net/",
    },
}


# Oklahoma Native American records (important for OK genealogy)
OKLAHOMA_NATIVE_AMERICAN: dict[str, dict[str, Any]] = {
    "dawes_rolls": {
        "name": "Dawes Rolls (Final Rolls)",
        "description": "Census of Five Civilized Tribes members 1898-1914",
        "coverage": "Cherokee, Chickasaw, Choctaw, Creek, Seminole Nations",
        "access": "Free via Access Genealogy and NARA",
        "url": "https://www.accessgenealogy.com/native/final-rolls-of-citizens-and-freedmen-of-the-five-civilized-tribes.htm",
    },
    "indian_census_rolls": {
        "name": "Indian Census Rolls 1885-1940",
        "description": "Annual census of tribal members",
        "coverage": "Various Oklahoma tribes",
        "access": "Free via FamilySearch and NARA",
        "familysearch_url": "https://www.familysearch.org/search/collection/1914530",
    },
    "land_allotments": {
        "name": "Indian Land Allotment Records",
        "description": "Land patents issued to tribal members",
        "coverage": "1887-1934",
        "access": "NARA and BLM GLO Records",
        "url": "https://glorecords.blm.gov/",
    },
}


# Oklahoma newspapers on Chronicling America
OKLAHOMA_NEWSPAPERS: ClassVar[list[dict[str, str]]] = [
    {
        "name": "The Daily Oklahoman",
        "dates": "1894-present",
        "access": "Newspapers.com / NewsBank",
        "notes": "Largest OK newspaper",
    },
    {
        "name": "Tulsa World",
        "dates": "1905-present",
        "access": "Newspapers.com",
        "notes": "Major Tulsa daily",
    },
    {
        "name": "The Black Dispatch",
        "dates": "1915-1982",
        "access": "Chronicling America / OHS Gateway",
        "notes": "African American newspaper, Oklahoma City",
    },
    {
        "name": "Cherokee Advocate",
        "dates": "1844-1906",
        "access": "Chronicling America",
        "notes": "Cherokee Nation newspaper",
    },
    {
        "name": "Indian Journal",
        "dates": "1876-1914",
        "access": "Chronicling America",
        "notes": "Creek Nation newspaper",
    },
]


class OklahomaHistoricalSocietySource(BaseSource):
    """Oklahoma Historical Society research collections.

    Key resources:
    - Oklahoma Digital Newspaper Program (500,000+ pages)
    - Photo archives (200,000+ images)
    - Encyclopedia of Oklahoma History
    - Manuscript collections
    """

    name = "OklahomaHistoricalSociety"
    base_url = "https://www.okhistory.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search OHS collections."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in OHS_RESOURCES.items():
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ohs-{key}",
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

        # Add Gateway to Oklahoma History search
        gateway_url = f"https://gateway.okhistory.org/search/?q={quote_plus(surname)}"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"ohs-gateway-{surname}",
                record_type="digital_collection",
                url=gateway_url,
                raw_data={"type": "Gateway search"},
                extracted_fields={
                    "search_type": "Gateway to Oklahoma History",
                    "search_url": gateway_url,
                    "description": "Search newspapers, photos, and documents",
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


class OklahomaVitalRecordsSource(BaseSource):
    """Oklahoma vital records and death/birth indices.

    Key resources:
    - Death Index 1908-1969 (free via FamilySearch)
    - Marriage Records 1890-present
    - Birth certificates (restricted)
    """

    name = "OklahomaVitalRecords"
    base_url = "https://oklahoma.gov/health"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Oklahoma vital records."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname
        given_name = query.given_name or ""

        for key, resource in OKLAHOMA_VITAL_RECORDS.items():
            url = resource.get("familysearch_url", resource.get("url", self.base_url))
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ok-vital-{key}",
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

        # Add FamilySearch Oklahoma Death Index search
        fs_death_url = f"https://www.familysearch.org/search/record/results?q.surname={quote_plus(surname)}&q.givenName={quote_plus(given_name)}&f.collectionId=1320895"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"ok-death-search-{surname}",
                record_type="death_index",
                url=fs_death_url,
                raw_data={"type": "FamilySearch Death Index"},
                extracted_fields={
                    "resource_name": "Oklahoma Death Index 1908-1969",
                    "search_url": fs_death_url,
                    "description": "Free searchable death index",
                    "coverage": "1908-1969",
                    "search_tip": f"Search for '{surname}' in Oklahoma Death Index",
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


class OklahomaNativeAmericanSource(BaseSource):
    """Oklahoma Native American genealogy records.

    Critical for Oklahoma research:
    - Dawes Rolls (Five Civilized Tribes)
    - Indian Census Rolls 1885-1940
    - Land allotment records
    """

    name = "OklahomaNativeAmerican"
    base_url = "https://www.accessgenealogy.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search Native American records."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        for key, resource in OKLAHOMA_NATIVE_AMERICAN.items():
            url = resource.get("familysearch_url", resource.get("url"))
            records.append(
                RawRecord(
                    source=self.name,
                    record_id=f"ok-native-{key}",
                    record_type="tribal_records",
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

        # Add Access Genealogy Dawes Roll search
        dawes_url = f"https://www.accessgenealogy.com/search/?q={quote_plus(surname)}+dawes"
        records.insert(
            0,
            RawRecord(
                source=self.name,
                record_id=f"ok-dawes-search-{surname}",
                record_type="tribal_records",
                url=dawes_url,
                raw_data={"type": "Dawes Roll search"},
                extracted_fields={
                    "resource_name": "Dawes Rolls Search",
                    "search_url": dawes_url,
                    "description": "Five Civilized Tribes enrollment 1898-1914",
                    "search_tip": f"Search for '{surname}' in Dawes Rolls",
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


# Tribal nation codes for OHS Dawes Rolls search
DAWES_TRIBAL_NATIONS = {
    "all": "",
    "cherokee": "Cherokee",
    "chickasaw": "Chickasaw",
    "choctaw": "Choctaw",
    "creek": "Muscogee (Creek)",
    "muscogee": "Muscogee (Creek)",
    "seminole": "Seminole",
}


class OHSDawesRollsSource(BaseSource):
    """Oklahoma Historical Society Dawes Rolls searchable database.

    This source queries the official OHS Dawes Rolls database containing
    the Final Rolls of Citizens and Freedmen of the Five Civilized Tribes
    in Indian Territory (1898-1914).

    Key features:
    - Searches approved enrollees on the Final Rolls (1914 publication)
    - Returns structured data: name, age, sex, blood quantum, roll number,
      enrollment type (by Blood, Freedmen, Intermarriage), card number
    - Does NOT include rejected/denied applications (use FamilySearch
      collection 1852353 for enrollment applications including rejections)

    Coverage: Cherokee, Chickasaw, Choctaw, Muscogee (Creek), Seminole Nations
    Enrollment types: by Blood, Freedmen, Intermarriage, Adopted
    """

    name = "OHSDawesRolls"
    base_url = "https://www.okhistory.org/research/dawesresults"

    def requires_auth(self) -> bool:
        return False

    async def search(
        self,
        query: SearchQuery,
        tribe: str | None = None,
        roll_number: str | None = None,
        card_number: str | None = None,
    ) -> list[RawRecord]:
        """Search OHS Dawes Rolls database.

        Args:
            query: Search parameters (surname required, given_name optional)
            tribe: Filter by tribal nation (cherokee, chickasaw, choctaw,
                   creek/muscogee, seminole, or None for all)
            roll_number: Search by specific roll number if known
            card_number: Search by specific card number if known

        Returns:
            List of RawRecord objects with Dawes Roll enrollment data
        """
        records: list[RawRecord] = []

        # Build search parameters
        params = {
            "fname": query.given_name or "",
            "lname": query.surname or "",
            "tribe": DAWES_TRIBAL_NATIONS.get((tribe or "").lower(), ""),
            "rollnum": roll_number or "",
            "cardnum": card_number or "",
            "action": "Search",
        }

        # Require at least surname or roll/card number
        if not params["lname"] and not params["rollnum"] and not params["cardnum"]:
            return []

        search_url = f"{self.base_url}?{urlencode(params)}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(search_url)

                if resp.status_code != 200:
                    logger.warning(f"OHS Dawes Rolls returned status {resp.status_code}")
                    return []

                soup = BeautifulSoup(resp.text, "html.parser")

                # Check for "No matches found"
                no_match = soup.find("h2", string=re.compile(r"No matches found", re.I))
                if no_match:
                    logger.debug(f"No Dawes Roll matches for {query.surname}")
                    return []

                # Find result count
                result_count_el = soup.find("p", string=re.compile(r"returned \d+ results"))
                total_results = 0
                if result_count_el:
                    match = re.search(r"returned (\d+) results", result_count_el.get_text())
                    if match:
                        total_results = int(match.group(1))

                # Parse results table
                table = soup.find("table")
                if not table:
                    return []

                # Find all data rows (skip header)
                rows = table.find_all("tr")[1:]  # Skip header row

                for i, row in enumerate(rows):
                    cells = row.find_all("td")
                    if len(cells) < 8:
                        continue

                    try:
                        record = self._parse_dawes_row(cells, i, search_url)
                        if record:
                            records.append(record)
                    except Exception as e:
                        logger.debug(f"Error parsing Dawes row: {e}")
                        continue

                # Add metadata record with search summary
                if records:
                    records.insert(
                        0,
                        RawRecord(
                            source=self.name,
                            record_id=f"ohs-dawes-summary-{query.surname}",
                            record_type="search_summary",
                            url=search_url,
                            raw_data={"total_results": total_results or len(records)},
                            extracted_fields={
                                "search_type": "OHS Dawes Rolls Final Rolls",
                                "result_count": str(total_results or len(records)),
                                "search_surname": query.surname or "",
                                "search_given_name": query.given_name or "",
                                "note": "Final Rolls only - does not include rejected applications",
                            },
                            accessed_at=datetime.now(UTC),
                        ),
                    )

        except httpx.HTTPError as e:
            logger.warning(f"OHS Dawes Rolls HTTP error: {e}")
        except Exception as e:
            logger.warning(f"OHS Dawes Rolls error: {e}")

        return records

    def _parse_dawes_row(
        self, cells: list, index: int, search_url: str
    ) -> RawRecord | None:
        """Parse a single row from the Dawes Rolls results table.

        Table columns:
        0: Name
        1: Age
        2: Sex
        3: Blood Quantum
        4: Roll No.
        5: Enrollment/Card Group
        6: Note
        7: Card No. (with link)
        """
        # Extract cell text
        # Note: OHS HTML is sometimes malformed with nested <td> elements
        # Use separator=" " to preserve whitespace from <br/> tags
        name = cells[0].get_text(strip=True)
        age = cells[1].get_text(strip=True)
        sex = cells[2].get_text(strip=True)
        blood_quantum = cells[3].get_text(strip=True)
        roll_number = cells[4].get_text(strip=True)
        # Use separator for enrollment to preserve whitespace in malformed HTML
        enrollment_group = " ".join(cells[5].get_text(separator=" ").split())
        note = cells[6].get_text(strip=True) if len(cells) > 6 else ""
        card_info = cells[7].get_text(strip=True) if len(cells) > 7 else ""

        # Extract card number from link text (e.g., "Search card 1209")
        card_number = ""
        card_match = re.search(r"card\s*(\d+)", card_info, re.I)
        if card_match:
            card_number = card_match.group(1)

        # Parse enrollment type (e.g., "Creek by Blood" -> tribe="Creek", type="by Blood")
        # Clean up enrollment_group by removing any "Search card XXX" text
        # Note: HTML often lacks spaces, so match "Search" even when concatenated
        clean_enrollment = re.sub(r"Search\s*card\s*\d+", "", enrollment_group, flags=re.I).strip()

        # Handle case where HTML lacks spaces (e.g., "Creekby Blood" instead of "Creek by Blood")
        # Add space before "by Blood", "Freedmen", "Intermarriage" if missing
        clean_enrollment = re.sub(r"(\w)(by\s*Blood)", r"\1 by Blood", clean_enrollment)
        clean_enrollment = re.sub(r"(\w)(Freedmen)", r"\1 Freedmen", clean_enrollment)
        clean_enrollment = re.sub(r"(\w)(Intermarriage)", r"\1 Intermarriage", clean_enrollment)

        tribe = ""
        enrollment_type = ""
        # Handle "Creek by Blood", "Cherokee Freedmen", etc.
        if "by Blood" in clean_enrollment:
            tribe = clean_enrollment.replace("by Blood", "").strip()
            enrollment_type = "by Blood"
        elif "Freedmen" in clean_enrollment:
            tribe = clean_enrollment.replace("Freedmen", "").strip()
            enrollment_type = "Freedmen"
        elif "Intermarriage" in clean_enrollment:
            tribe = clean_enrollment.replace("Intermarriage", "").strip()
            enrollment_type = "Intermarriage"
        else:
            # Fallback: first word is tribe, rest is type
            enrollment_parts = clean_enrollment.split()
            if enrollment_parts:
                tribe = enrollment_parts[0]
                enrollment_type = " ".join(enrollment_parts[1:]) if len(enrollment_parts) > 1 else ""

        # Parse name into given/surname
        name_parts = name.split()
        given_name = name_parts[0] if name_parts else ""
        surname = name_parts[-1] if len(name_parts) > 1 else ""

        # Build record ID
        record_id = f"dawes-{roll_number}" if roll_number else f"dawes-{index}"

        # Parse cross-references from note field
        cross_refs = parse_cross_references(note)

        return RawRecord(
            source=self.name,
            record_id=record_id,
            record_type="dawes_enrollment",
            url=search_url,
            raw_data={
                "name": name,
                "age": age,
                "sex": sex,
                "blood_quantum": blood_quantum,
                "roll_number": roll_number,
                "enrollment_group": enrollment_group,
                "note": note,
                "card_number": card_number,
                "cross_references": cross_refs,
            },
            extracted_fields={
                "full_name": name,
                "given_name": given_name,
                "surname": surname,
                "age_at_enrollment": age,
                "sex": sex,
                "blood_quantum": blood_quantum,
                "roll_number": roll_number,
                "tribal_nation": tribe,
                "enrollment_type": enrollment_type,
                "card_number": card_number,
                "note": note,
                "cross_reference_cards": ", ".join(ref["card_number"] for ref in cross_refs) if cross_refs else "",
                "source_database": "OHS Dawes Rolls Final Rolls 1898-1914",
            },
            accessed_at=datetime.now(UTC),
        )

    async def search_with_variants(
        self,
        query: SearchQuery,
        tribe: str | None = None,
        include_phonetic: bool = True,
    ) -> list[RawRecord]:
        """Search Dawes Rolls with automatic name variant expansion.

        Automatically generates and searches for:
        - Common spelling variants (Sorrell -> Sorrel, Sorel, Sorrill)
        - Phonetically similar names via Soundex/Metaphone
        - Historical nickname mappings

        Args:
            query: Search parameters (surname required)
            tribe: Filter by tribal nation (optional)
            include_phonetic: Whether to include phonetic matches (default True)

        Returns:
            Deduplicated list of RawRecord objects from all variant searches
        """
        if not query.surname:
            return []

        # Generate surname variants
        surname_variants_obj = generate_surname_variants(
            query.surname,
            include_soundex_matches=include_phonetic,
        )
        surname_variants = surname_variants_obj.all_variants
        # Always include the original name
        if query.surname.lower() not in [v.lower() for v in surname_variants]:
            surname_variants = [query.surname] + list(surname_variants)

        # Generate given name variants if provided
        given_variants: list[str] = []
        if query.given_name:
            given_variants = list(
                get_all_search_names(query.given_name, query.surname).get(
                    "given_names", [query.given_name]
                )
            )

        all_records: list[RawRecord] = []
        seen_roll_numbers: set[str] = set()

        # Search each surname variant
        for surname in surname_variants:
            # If we have given name variants, search each combination
            if given_variants:
                for given in given_variants:
                    variant_query = SearchQuery(
                        surname=surname,
                        given_name=given,
                        birth_place=query.birth_place,
                        birth_year=query.birth_year,
                    )
                    try:
                        records = await self.search(variant_query, tribe=tribe)
                        for rec in records:
                            # Deduplicate by roll number
                            roll_num = rec.extracted_fields.get("roll_number", "")
                            if roll_num and roll_num not in seen_roll_numbers:
                                seen_roll_numbers.add(roll_num)
                                # Mark as variant match if different from original
                                if surname.lower() != query.surname.lower():
                                    rec.extracted_fields["matched_via_variant"] = surname
                                all_records.append(rec)
                    except Exception as e:
                        logger.debug(f"Variant search error for {surname}/{given}: {e}")
            else:
                # Search surname only
                variant_query = SearchQuery(
                    surname=surname,
                    birth_place=query.birth_place,
                    birth_year=query.birth_year,
                )
                try:
                    records = await self.search(variant_query, tribe=tribe)
                    for rec in records:
                        roll_num = rec.extracted_fields.get("roll_number", "")
                        if roll_num and roll_num not in seen_roll_numbers:
                            seen_roll_numbers.add(roll_num)
                            if surname.lower() != query.surname.lower():
                                rec.extracted_fields["matched_via_variant"] = surname
                            all_records.append(rec)
                except Exception as e:
                    logger.debug(f"Variant search error for {surname}: {e}")

        # Add summary record at the beginning
        if all_records:
            variants_list = list(surname_variants) if isinstance(surname_variants, (list, tuple, set)) else [surname_variants]
            variant_summary = RawRecord(
                source=self.name,
                record_id=f"ohs-dawes-variants-{query.surname}",
                record_type="search_summary",
                url=self.base_url,
                raw_data={
                    "original_surname": query.surname,
                    "variants_searched": variants_list,
                    "total_unique_results": len(all_records),
                },
                extracted_fields={
                    "search_type": "OHS Dawes Rolls (with variants)",
                    "original_search": query.surname,
                    "variants_searched": ", ".join(variants_list),
                    "result_count": str(len(all_records)),
                    "note": "Results include spelling variants and phonetic matches",
                },
                accessed_at=datetime.now(UTC),
            )
            all_records.insert(0, variant_summary)

        return all_records

    async def fetch_related_cards(
        self,
        record: RawRecord,
        tribe: str | None = None,
    ) -> list[RawRecord]:
        """Fetch all related cards referenced in a Dawes record's notes.

        Parses cross-references like "See Card 4135" and fetches those cards.

        Args:
            record: A Dawes enrollment record with potential cross-references
            tribe: Tribe to use for lookups (inferred from record if not provided)

        Returns:
            List of RawRecord objects for all referenced cards
        """
        related_records: list[RawRecord] = []

        # Get cross-references from raw_data or parse from note
        cross_refs = record.raw_data.get("cross_references", [])
        if not cross_refs:
            note = record.extracted_fields.get("note", "")
            cross_refs = parse_cross_references(note)

        if not cross_refs:
            return []

        # Determine tribe from record if not specified
        if not tribe:
            tribe = record.extracted_fields.get("tribal_nation", "").lower()

        for ref in cross_refs:
            card_num = ref.get("card_number")
            ref_tribe = ref.get("tribe", "").lower() or tribe

            if not card_num:
                continue

            try:
                card_records = await self.search_by_card(card_num, ref_tribe)
                for card_rec in card_records:
                    # Add relationship context
                    card_rec.extracted_fields["referenced_from"] = record.record_id
                    card_rec.extracted_fields["reference_relationship"] = ref.get(
                        "relationship", "referenced"
                    )
                    related_records.append(card_rec)
            except Exception as e:
                logger.debug(f"Error fetching related card {card_num}: {e}")

        return related_records

    async def search_by_card(self, card_number: str, tribe: str) -> list[RawRecord]:
        """Search for all individuals on a specific Dawes enrollment card.

        Cards typically list household members together.

        Args:
            card_number: The Dawes card number
            tribe: Tribal nation (cherokee, chickasaw, choctaw, creek, seminole)

        Returns:
            List of RawRecord objects for individuals on the card
        """
        query = SearchQuery(surname="")  # Empty surname, search by card
        return await self.search(query, tribe=tribe, card_number=card_number)

    async def get_record(
        self,
        record_id: str,  # noqa: ARG002 - required by base interface
    ) -> RawRecord | None:
        """Get record by ID not supported - use search instead."""
        return None


class OklahomaGenealogySource(BaseSource):
    """Aggregator for all Oklahoma genealogy sources.

    Combines:
    - Oklahoma Historical Society
    - Vital Records (death/birth/marriage indices)
    - Native American records (Dawes Rolls, Indian Census)
    - OHS Dawes Rolls searchable database (Final Rolls 1898-1914)
    - Newspaper archives
    """

    name = "OklahomaGenealogy"

    COMPONENT_SOURCES: ClassVar[list[type[BaseSource]]] = [
        OklahomaHistoricalSocietySource,
        OklahomaVitalRecordsSource,
        OklahomaNativeAmericanSource,
        OHSDawesRollsSource,
    ]

    def __init__(self) -> None:
        super().__init__()
        self.ohs = OklahomaHistoricalSocietySource()
        self.vital = OklahomaVitalRecordsSource()
        self.native = OklahomaNativeAmericanSource()
        self.dawes = OHSDawesRollsSource()

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search all Oklahoma sources."""
        records: list[RawRecord] = []

        if not query.surname:
            return []

        surname = query.surname

        # Search component sources
        sources = [
            ("OHS", self.ohs),
            ("Vital", self.vital),
            ("Native", self.native),
            ("Dawes", self.dawes),
        ]

        for source_name, source in sources:
            try:
                source_records = await source.search(query)
                records.extend(source_records)
            except Exception as e:
                logger.debug(f"{source_name} search error: {e}")

        # Add newspaper search via Chronicling America
        ca_url = f"https://chroniclingamerica.loc.gov/search/pages/results/?state=Oklahoma&proxtext={quote_plus(surname)}"
        records.append(
            RawRecord(
                source=self.name,
                record_id=f"ok-newspapers-{surname}",
                record_type="newspaper_search",
                url=ca_url,
                raw_data={"type": "Chronicling America"},
                extracted_fields={
                    "search_type": "Oklahoma Newspapers",
                    "search_url": ca_url,
                    "description": "Historic Oklahoma newspapers",
                    "highlights": "Includes Cherokee Advocate, Black Dispatch, Indian Journal",
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
