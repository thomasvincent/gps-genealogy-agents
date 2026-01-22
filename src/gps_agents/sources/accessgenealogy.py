"""AccessGenealogy web scraper for genealogy records.

Supports:
- Native American records (Dawes Rolls, Cherokee, tribal)
- Cemetery records by state
- Census records with household member extraction
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from ..models.search import RawRecord, SearchQuery
from .base import BaseSource

logger = logging.getLogger(__name__)

# Census years available in US federal census
CENSUS_YEARS = [1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950]

# California counties for targeted census searches
CALIFORNIA_COUNTIES = [
    "alameda", "alpine", "amador", "butte", "calaveras", "colusa", "contra-costa",
    "del-norte", "el-dorado", "fresno", "glenn", "humboldt", "imperial", "inyo",
    "kern", "kings", "lake", "lassen", "los-angeles", "madera", "marin", "mariposa",
    "mendocino", "merced", "modoc", "mono", "monterey", "napa", "nevada", "orange",
    "placer", "plumas", "riverside", "sacramento", "san-benito", "san-bernardino",
    "san-diego", "san-francisco", "san-joaquin", "san-luis-obispo", "san-mateo",
    "santa-barbara", "santa-clara", "santa-cruz", "shasta", "sierra", "siskiyou",
    "solano", "sonoma", "stanislaus", "sutter", "tehama", "trinity", "tulare",
    "tuolumne", "ventura", "yolo", "yuba",
]

# US states for cemetery record URLs
US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming",
]


class AccessGenealogySource(BaseSource):
    """AccessGenealogy.com data source.

    Free resource with:
    - Native American genealogy (Dawes Rolls, Cherokee, tribal records)
    - Cemetery records by state
    - Census transcriptions
    """

    name = "AccessGenealogy"
    base_url = "https://www.accessgenealogy.com"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search AccessGenealogy for genealogy records.

        Args:
            query: Search parameters. Supported record_types:
                - "census" - Census transcriptions
                - "roll", "tribal", "native", "dawes" - Native American rolls
                - "cemetery", "burial", "grave" - Cemetery records

        Returns:
            List of matching records
        """
        import httpx

        records: list[RawRecord] = []

        # Build base search terms
        search_terms: list[str] = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        # Heuristics: if user asked for specific record types, bias keywords
        rt = {t.lower() for t in (query.record_types or [])}
        if "census" in rt:
            search_terms.append("census")
        # Rolls keywords capture Dawes/tribal enrollments
        if any(k in rt for k in {"roll", "rolls", "tribal", "native", "dawes"}):
            search_terms.extend(["roll", "enrollment", "dawes"])
        # Cemetery keywords
        if any(k in rt for k in {"cemetery", "burial", "grave", "death"}):
            search_terms.append("cemetery")

        if not search_terms:
            return []

        search_query = "+".join(search_terms)

        # Determine state for targeted searches
        query_state = getattr(query, "state", None)
        state_slug = self._normalize_state(query_state) if query_state else None

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                # 1) Site-wide search
                urls: list[str] = [f"{self.base_url}/?s={search_query}"]

                # 2) Targeted sections for Native American rolls
                targeted = [
                    f"{self.base_url}/native/dawes-rolls/?s={search_query}",
                    f"{self.base_url}/native/cherokee/?s={search_query}",
                    f"{self.base_url}/native/?s={search_query}",
                ]
                urls.extend(targeted)

                # 3) If census requested, hit census category pages
                if "census" in rt:
                    urls.append(f"{self.base_url}/census-records/?s={search_query}")

                # 4) Cemetery records - by state if specified, otherwise general
                if any(k in rt for k in {"cemetery", "burial", "grave", "death"}) or not rt:
                    if state_slug and state_slug in US_STATES:
                        urls.append(
                            f"{self.base_url}/{state_slug}/{state_slug}-cemetery-records.htm"
                        )
                        urls.append(f"{self.base_url}/{state_slug}/?s={search_query}")
                    else:
                        # Search general cemetery section
                        urls.append(f"{self.base_url}/cemetery/?s={search_query}")

                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")
                        # Use different parser for index pages vs search results
                        if "cemetery-records.htm" in url:
                            records.extend(self._parse_cemetery_index(soup, url))
                        else:
                            records.extend(self._parse_search_page(soup))
                    except Exception:
                        continue

        except Exception as e:
            logger.warning("AccessGenealogy search error: %s", e)

        # Post-process: classify record types by URL/title hints
        for r in records:
            lower_url = (r.url or "").lower()
            title = (r.raw_data.get("title") or "").lower()
            if any(k in lower_url for k in ["cemetery", "burial", "grave"]) or any(
                k in title for k in ["cemetery", "burial", "grave"]
            ):
                r.record_type = "cemetery"
            elif any(k in lower_url for k in ["dawes", "roll"]) or any(
                k in title for k in ["roll", "enrollment"]
            ):
                r.record_type = "roll"
            elif "census" in lower_url or "census" in title:
                r.record_type = "census"
        return records

    def _normalize_state(self, state: str) -> str | None:
        """Normalize state name to URL slug format.

        Args:
            state: State name (e.g., "California", "New York", "CA")

        Returns:
            URL slug (e.g., "california", "new-york") or None
        """
        if not state:
            return None

        # Handle abbreviations
        state_abbrevs = {
            "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
            "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
            "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
            "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
            "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
            "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
            "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
            "NH": "new-hampshire", "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
            "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio", "OK": "oklahoma",
            "OR": "oregon", "PA": "pennsylvania", "RI": "rhode-island", "SC": "south-carolina",
            "SD": "south-dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
            "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west-virginia",
            "WI": "wisconsin", "WY": "wyoming",
        }

        upper = state.upper().strip()
        if upper in state_abbrevs:
            return state_abbrevs[upper]

        # Convert full name to slug
        slug = state.lower().strip().replace(" ", "-")
        return slug if slug in US_STATES else None

    def _parse_cemetery_index(self, soup: BeautifulSoup, base_url: str) -> list[RawRecord]:
        """Parse a state cemetery index page.

        Args:
            soup: BeautifulSoup parsed page
            base_url: The URL of the index page

        Returns:
            List of cemetery records
        """
        records: list[RawRecord] = []

        # Cemetery index pages typically have lists of links to county/cemetery pages
        # Look for links in content area
        content = soup.find("div", class_="entry-content") or soup.find("article") or soup

        # Find all links that look like cemetery records
        for link in content.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Skip navigation, external, and non-cemetery links
            if not href or not text:
                continue
            if href.startswith("#") or "accessgenealogy.com" not in href.lower() and not href.startswith("/"):
                continue
            if any(skip in href.lower() for skip in ["facebook", "twitter", "pinterest", "email"]):
                continue

            # Look for cemetery-related content
            text_lower = text.lower()
            if any(k in text_lower for k in ["cemetery", "burial", "grave", "county"]) or any(
                k in href.lower() for k in ["cemetery", "burial"]
            ):
                record = RawRecord(
                    source=self.name,
                    record_id=href,
                    record_type="cemetery",
                    url=href if href.startswith("http") else f"{self.base_url}{href}",
                    raw_data={"title": text, "index_url": base_url},
                    extracted_fields={"title": text, "location": self._extract_location(text)},
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        return records[:50]  # Cap results

    def _extract_location(self, text: str) -> str:
        """Extract location (county) from cemetery title.

        Args:
            text: Cemetery title text

        Returns:
            Extracted location or empty string
        """
        # Common pattern: "County Name County Cemetery Records"
        text_lower = text.lower()
        if "county" in text_lower:
            parts = text.split()
            for i, part in enumerate(parts):
                if part.lower() == "county" and i > 0:
                    return " ".join(parts[:i + 1])
        return ""

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by URL path.

        Args:
            record_id: URL path or article identifier

        Returns:
            The record or None
        """
        import httpx

        url = record_id if record_id.startswith("http") else f"{self.base_url}/{record_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_article(soup, url)

        except Exception as e:
            logger.warning("AccessGenealogy get_record error: %s", e)
            return None

    def _parse_search_page(self, soup: BeautifulSoup) -> list[RawRecord]:
        """Parse search results page.

        Args:
            soup: BeautifulSoup parsed page

        Returns:
            List of records found
        """
        records: list[RawRecord] = []

        # Find article entries (typical WordPress structure)
        articles = soup.find_all("article") or soup.find_all("div", class_="post")

        for article in articles[:30]:  # Slightly higher cap
            title_elem = article.find("h2") or article.find("h3")
            link_elem = article.find("a")

            if not title_elem or not link_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = link_elem.get("href", "")

            # Extract snippet/summary
            excerpt = article.find("div", class_="entry-content") or article.find("p")
            summary = excerpt.get_text(strip=True)[:500] if excerpt else ""

            rtype = "article"
            tl = title.lower()
            if "census" in tl:
                rtype = "census"
            if "roll" in tl or "dawes" in tl or "enrollment" in tl:
                rtype = "roll"

            record = RawRecord(
                source=self.name,
                record_id=url,
                record_type=rtype,
                url=url,
                raw_data={"title": title, "summary": summary},
                extracted_fields={"title": title, "summary": summary},
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_article(self, soup: BeautifulSoup, url: str) -> RawRecord | None:
        """Parse a full article page.

        Args:
            soup: BeautifulSoup parsed page
            url: Article URL

        Returns:
            RawRecord or None
        """
        title_elem = soup.find("h1", class_="entry-title") or soup.find("h1")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)

        # Get content
        content_elem = soup.find("div", class_="entry-content") or soup.find("article")
        content = content_elem.get_text(strip=True)[:4000] if content_elem else ""

        # Try to extract structured data (names, dates, etc.)
        extracted: dict[str, str] = {"title": title, "content_preview": content[:800]}

        # Look for table data (common in rolls/census lists)
        tables = soup.find_all("table")
        if tables:
            extracted["has_tabular_data"] = "true"
            extracted["table_count"] = str(len(tables))
            # Pull a small preview of the first table
            first = tables[0]
            headers = [th.get_text(strip=True) for th in first.find_all("th")]
            rows = []
            for tr in first.find_all("tr")[1:6]:
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if headers:
                extracted["table_headers"] = ", ".join(headers[:10])
            if rows:
                extracted["table_rows_preview"] = "; ".join([" | ".join(r[:10]) for r in rows])

        # Guess record type
        rtype = "article"
        lower_url = url.lower()
        tl = title.lower()
        if any(k in lower_url for k in ["cemetery", "burial", "grave"]) or any(
            k in tl for k in ["cemetery", "burial", "grave"]
        ):
            rtype = "cemetery"
        elif "census" in lower_url or "census" in tl:
            rtype = "census"
        elif any(k in lower_url for k in ["dawes", "roll"]) or any(
            k in tl for k in ["roll", "enrollment"]
        ):
            rtype = "roll"

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=rtype,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields=extracted,
            accessed_at=datetime.now(UTC),
        )

    async def search_census(
        self,
        surname: str,
        given_name: str | None = None,
        state: str | None = None,
        county: str | None = None,
        year: int | None = None,
    ) -> list[RawRecord]:
        """Search specifically for census transcriptions.

        This method targets census-specific URLs and parses household data.

        Args:
            surname: Surname to search for
            given_name: Given name (optional)
            state: State to search (e.g., "California", "CA")
            county: County to search (e.g., "Los Angeles")
            year: Census year (e.g., 1930, 1940)

        Returns:
            List of census records with household members extracted
        """
        import httpx

        records: list[RawRecord] = []
        state_slug = self._normalize_state(state) if state else None

        # Build search terms
        search_terms = [surname]
        if given_name:
            search_terms.append(given_name)
        if year:
            search_terms.append(str(year))
        search_query = "+".join(search_terms)

        # Target census-specific URLs
        urls: list[str] = [
            f"{self.base_url}/census-records/?s={search_query}",
        ]

        # Add state-specific census URLs
        if state_slug:
            urls.extend([
                f"{self.base_url}/{state_slug}/census/?s={search_query}",
                f"{self.base_url}/{state_slug}/?s={search_query}+census",
            ])
            # Add year-specific if provided
            if year:
                urls.append(f"{self.base_url}/{state_slug}/{year}-census/?s={search_query}")

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")

                        # Parse census pages with household extraction
                        page_records = self._parse_census_page(soup, url, surname, given_name)
                        records.extend(page_records)

                    except Exception as e:
                        logger.debug("Census search error for %s: %s", url, e)
                        continue

        except Exception as e:
            logger.warning("AccessGenealogy census search error: %s", e)

        return records

    def _parse_census_page(
        self,
        soup: BeautifulSoup,
        url: str,
        surname: str,
        given_name: str | None = None,
    ) -> list[RawRecord]:
        """Parse a census transcription page for household data.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL
            surname: Surname to match
            given_name: Given name to match (optional)

        Returns:
            List of census records with household members
        """
        records: list[RawRecord] = []
        surname_lower = surname.lower()
        given_lower = given_name.lower() if given_name else None

        # Look for tables - census transcriptions are often tabular
        tables = soup.find_all("table")
        for table in tables:
            household = self._extract_household_from_table(table, surname_lower, given_lower)
            if household:
                record = RawRecord(
                    source=self.name,
                    record_id=f"{url}#household-{hash(str(household))}",
                    record_type="census",
                    url=url,
                    raw_data={"household": household, "source_url": url},
                    extracted_fields={
                        "household_head": household.get("head", ""),
                        "household_members": household.get("members", []),
                        "census_year": household.get("year", ""),
                        "location": household.get("location", ""),
                    },
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        # Also parse non-tabular content for census data
        content_records = self._parse_census_content(soup, url, surname_lower, given_lower)
        records.extend(content_records)

        return records

    def _extract_household_from_table(
        self,
        table: BeautifulSoup,
        surname_lower: str,
        given_lower: str | None = None,
    ) -> dict[str, Any] | None:
        """Extract household members from a census table.

        Args:
            table: BeautifulSoup table element
            surname_lower: Lowercase surname to match
            given_lower: Lowercase given name to match (optional)

        Returns:
            Household dict with head and members, or None
        """
        # Get headers
        headers: list[str] = []
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

        # Identify key columns
        name_col = next((i for i, h in enumerate(headers) if any(
            k in h for k in ["name", "surname", "head", "person"]
        )), 0)
        age_col = next((i for i, h in enumerate(headers) if "age" in h), -1)
        rel_col = next((i for i, h in enumerate(headers) if any(
            k in h for k in ["relation", "relationship", "rel"]
        )), -1)
        sex_col = next((i for i, h in enumerate(headers) if any(
            k in h for k in ["sex", "gender", "m/f"]
        )), -1)
        birthplace_col = next((i for i, h in enumerate(headers) if any(
            k in h for k in ["birthplace", "birth place", "born", "nativity"]
        )), -1)

        # Scan rows for surname match
        household: dict[str, Any] = {"members": [], "head": "", "year": "", "location": ""}
        found_match = False

        rows = table.find_all("tr")[1:]  # Skip header
        for i, row in enumerate(rows):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            # Check for surname match
            row_text = " ".join(cells).lower()
            if surname_lower in row_text:
                found_match = True

            # If we found our match, collect this household
            if found_match:
                member: dict[str, str] = {}

                # Extract name
                if name_col < len(cells):
                    member["name"] = cells[name_col]
                if age_col >= 0 and age_col < len(cells):
                    member["age"] = cells[age_col]
                if rel_col >= 0 and rel_col < len(cells):
                    member["relationship"] = cells[rel_col]
                if sex_col >= 0 and sex_col < len(cells):
                    member["sex"] = cells[sex_col]
                if birthplace_col >= 0 and birthplace_col < len(cells):
                    member["birthplace"] = cells[birthplace_col]

                if member.get("name"):
                    household["members"].append(member)

                    # First member with Head relationship is household head
                    if not household["head"]:
                        rel = member.get("relationship", "").lower()
                        if "head" in rel or "self" in rel or i == 0:
                            household["head"] = member["name"]

                # Stop after collecting ~15 members (typical household limit)
                if len(household["members"]) >= 15:
                    break

            # If we've moved to a new household (new "Head"), stop
            if found_match and len(household["members"]) > 1:
                rel = cells[rel_col].lower() if rel_col >= 0 and rel_col < len(cells) else ""
                if "head" in rel and household["head"]:
                    break

        if household["members"]:
            return household
        return None

    def _parse_census_content(
        self,
        soup: BeautifulSoup,
        url: str,
        surname_lower: str,
        given_lower: str | None = None,
    ) -> list[RawRecord]:
        """Parse non-tabular census content for household data.

        Some census transcriptions are formatted as text lists rather than tables.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL
            surname_lower: Lowercase surname to match
            given_lower: Lowercase given name to match (optional)

        Returns:
            List of census records
        """
        records: list[RawRecord] = []

        # Look for content areas with census data
        content = soup.find("div", class_="entry-content") or soup.find("article") or soup
        if not content:
            return records

        text = content.get_text(separator="\n")
        lines = text.split("\n")

        # Pattern for census entries: "Name, age, relationship, birthplace"
        # or "Name - age - M/F - birthplace"
        household_members: list[dict[str, str]] = []
        current_head = ""

        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue

            line_lower = line.lower()

            # Check for surname match
            if surname_lower in line_lower:
                # Try to parse this line as a census entry
                member = self._parse_census_line(line)
                if member:
                    household_members.append(member)
                    if not current_head:
                        current_head = member.get("name", "")

        if household_members:
            record = RawRecord(
                source=self.name,
                record_id=f"{url}#content-{hash(str(household_members))}",
                record_type="census",
                url=url,
                raw_data={"household_members": household_members, "source_url": url},
                extracted_fields={
                    "household_head": current_head,
                    "household_members": household_members,
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_census_line(self, line: str) -> dict[str, str] | None:
        """Parse a single census entry line.

        Args:
            line: Text line from census transcription

        Returns:
            Dict with name, age, relationship, etc., or None
        """
        # Common patterns:
        # "John Smith, 45, Head, NC"
        # "John Smith - 45 - M - NC"
        # "Smith, John  45  Head  North Carolina"

        member: dict[str, str] = {}

        # Try comma-separated
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            member["name"] = parts[0]
            # Look for age (numeric)
            for part in parts[1:]:
                if part.isdigit() or re.match(r"^\d{1,3}$", part):
                    member["age"] = part
                elif part.lower() in ("m", "f", "male", "female"):
                    member["sex"] = part
                elif part.lower() in ("head", "wife", "son", "daughter", "mother", "father", "boarder", "lodger", "servant"):
                    member["relationship"] = part
                elif len(part) > 2 and not part.isdigit():
                    # Likely birthplace
                    if "birthplace" not in member:
                        member["birthplace"] = part

        if member.get("name"):
            return member
        return None
