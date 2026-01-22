"""USGenWeb web scraper for free genealogy records.

USGenWeb is a volunteer-run project organizing genealogy records by state and county.
Records include census transcriptions, cemetery records, vital records, and more.
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

# State abbreviation to full name mapping for URL construction
STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "newhampshire", "NJ": "newjersey", "NM": "newmexico", "NY": "newyork",
    "NC": "northcarolina", "ND": "northdakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhodeisland", "SC": "southcarolina",
    "SD": "southdakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "westvirginia",
    "WI": "wisconsin", "WY": "wyoming",
}

# Reverse mapping
STATE_ABBREVS = {v: k for k, v in STATE_NAMES.items()}


class USGenWebSource(BaseSource):
    """USGenWeb.org data source.

    Free volunteer-run genealogy resource organized by state and county.
    Includes census transcriptions, cemetery records, vital records, and more.
    """

    name = "USGenWeb"
    base_url = "https://usgenweb.org"

    def requires_auth(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search USGenWeb for genealogy records.

        Args:
            query: Search parameters. Uses state/county if available.
                Supported record_types: census, cemetery, vital, military, land, court

        Returns:
            List of matching records
        """
        import httpx

        records: list[RawRecord] = []

        # Build search terms
        search_terms: list[str] = []
        if query.surname:
            search_terms.append(query.surname)
        if query.given_name:
            search_terms.append(query.given_name)

        if not search_terms:
            return []

        search_query = " ".join(search_terms)

        # Get state/county from query
        query_state = getattr(query, "state", None)
        query_county = getattr(query, "county", None)
        state_slug = self._normalize_state(query_state) if query_state else None

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                urls: list[str] = []

                # State-specific search if state provided
                if state_slug:
                    # USGenWeb state sites are typically at {state}.usgenweb.org
                    state_base = f"https://{state_slug}.usgenweb.org"
                    urls.append(state_base)

                    # Also try usgenweb.org/{state} pattern
                    urls.append(f"{self.base_url}/{state_slug}/")

                    # County-specific if provided
                    if query_county:
                        county_slug = query_county.lower().replace(" ", "").replace("county", "")
                        urls.append(f"{state_base}/{county_slug}/")

                # Main site search
                urls.append(self.base_url)

                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")
                        page_records = self._parse_page(soup, url, search_query)
                        records.extend(page_records)
                    except Exception as e:
                        logger.debug("USGenWeb fetch error for %s: %s", url, e)
                        continue

        except Exception as e:
            logger.warning("USGenWeb search error: %s", e)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_records: list[RawRecord] = []
        for r in records:
            if r.url and r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_records.append(r)

        return unique_records

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Get a specific record by URL.

        Args:
            record_id: URL or path identifier

        Returns:
            The record or None
        """
        import httpx

        url = record_id if record_id.startswith("http") else f"{self.base_url}/{record_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_record_page(soup, url)

        except Exception as e:
            logger.warning("USGenWeb get_record error: %s", e)
            return None

    def _normalize_state(self, state: str) -> str | None:
        """Normalize state input to USGenWeb URL format.

        Args:
            state: State name or abbreviation

        Returns:
            State slug or None
        """
        if not state:
            return None

        state = state.strip()

        # Check if it's an abbreviation
        upper = state.upper()
        if upper in STATE_NAMES:
            return STATE_NAMES[upper]

        # Check if it's already a full name
        lower = state.lower().replace(" ", "").replace("-", "")
        if lower in STATE_ABBREVS:
            return lower

        return None

    def _parse_page(
        self, soup: BeautifulSoup, base_url: str, search_query: str
    ) -> list[RawRecord]:
        """Parse a USGenWeb page for records and links.

        Args:
            soup: BeautifulSoup parsed page
            base_url: The page URL
            search_query: Search terms to match

        Returns:
            List of records found
        """
        records: list[RawRecord] = []
        search_terms = search_query.lower().split()

        # USGenWeb pages are highly variable - look for common patterns
        # 1. Look for links in the page content
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not href or not text or len(text) < 3:
                continue

            # Skip navigation and external links
            if any(skip in href.lower() for skip in [
                "mailto:", "javascript:", "facebook", "twitter",
                "#", "?", "google", "bing"
            ]):
                continue

            # Check if this link matches our search terms
            text_lower = text.lower()
            url_lower = href.lower()

            # Look for surname matches
            matches_search = any(term in text_lower for term in search_terms)

            # Look for genealogy-related content
            is_genealogy = any(kw in text_lower or kw in url_lower for kw in [
                "cemetery", "burial", "grave", "census", "birth", "death",
                "marriage", "vital", "military", "pension", "land", "deed",
                "probate", "court", "church", "obituar"
            ])

            if matches_search or is_genealogy:
                # Determine record type
                record_type = self._classify_record_type(text_lower, url_lower)

                # Build full URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    # Extract domain from base_url
                    from urllib.parse import urlparse
                    parsed = urlparse(base_url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    full_url = f"{base_url.rstrip('/')}/{href}"

                record = RawRecord(
                    source=self.name,
                    record_id=full_url,
                    record_type=record_type,
                    url=full_url,
                    raw_data={"title": text, "found_on": base_url},
                    extracted_fields={
                        "title": text,
                        "state": self._extract_state(base_url),
                    },
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        # 2. Look for tables with data
        for table in soup.find_all("table"):
            table_records = self._parse_table(table, base_url, search_terms)
            records.extend(table_records)

        return records[:100]  # Cap results

    def _parse_table(
        self, table: BeautifulSoup, base_url: str, search_terms: list[str]
    ) -> list[RawRecord]:
        """Parse a table for genealogy records.

        Args:
            table: BeautifulSoup table element
            base_url: Page URL
            search_terms: Search terms to match

        Returns:
            List of records from the table
        """
        records: list[RawRecord] = []

        # Get headers
        headers: list[str] = []
        header_row = table.find("tr")
        if header_row:
            headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

        # Look for name-like columns
        name_cols = [i for i, h in enumerate(headers) if any(
            kw in h for kw in ["name", "surname", "given", "person"]
        )]

        # Parse rows
        for row in table.find_all("tr")[1:20]:  # Skip header, limit rows
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            # Check if any cell matches search terms
            row_text = " ".join(cells).lower()
            if not any(term in row_text for term in search_terms):
                continue

            # Extract name
            name = ""
            if name_cols and name_cols[0] < len(cells):
                name = cells[name_cols[0]]
            elif cells:
                name = cells[0]

            record = RawRecord(
                source=self.name,
                record_id=f"{base_url}#row-{hash(row_text)}",
                record_type=self._classify_record_type(row_text, base_url.lower()),
                url=base_url,
                raw_data={"row_data": dict(zip(headers, cells)) if headers else cells},
                extracted_fields={
                    "name": name,
                    "raw_text": " | ".join(cells[:5]),
                },
                accessed_at=datetime.now(UTC),
            )
            records.append(record)

        return records

    def _parse_record_page(self, soup: BeautifulSoup, url: str) -> RawRecord | None:
        """Parse a full record page.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL

        Returns:
            RawRecord or None
        """
        # Get title
        title_elem = soup.find("title") or soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"

        # Get body content
        body = soup.find("body")
        content = body.get_text(strip=True)[:4000] if body else ""

        # Classify
        record_type = self._classify_record_type(title.lower(), url.lower())

        return RawRecord(
            source=self.name,
            record_id=url,
            record_type=record_type,
            url=url,
            raw_data={"title": title, "content": content},
            extracted_fields={
                "title": title,
                "state": self._extract_state(url),
                "content_preview": content[:500],
            },
            accessed_at=datetime.now(UTC),
        )

    def _classify_record_type(self, text: str, url: str) -> str:
        """Classify the record type based on text and URL.

        Args:
            text: Text content (lowercase)
            url: URL (lowercase)

        Returns:
            Record type string
        """
        combined = f"{text} {url}"

        if any(kw in combined for kw in ["cemetery", "burial", "grave", "interment"]):
            return "cemetery"
        if any(kw in combined for kw in ["census", "enumerat"]):
            return "census"
        if any(kw in combined for kw in ["birth", "death", "marriage", "vital", "divorce"]):
            return "vital"
        if any(kw in combined for kw in ["military", "soldier", "veteran", "pension", "war", "draft"]):
            return "military"
        if any(kw in combined for kw in ["land", "deed", "property"]):
            return "land"
        if any(kw in combined for kw in ["probate", "will", "estate", "court"]):
            return "court"
        if any(kw in combined for kw in ["church", "baptism", "christening"]):
            return "church"
        if "obituar" in combined:
            return "obituary"

        return "record"

    def _extract_state(self, url: str) -> str:
        """Extract state from URL.

        Args:
            url: URL to parse

        Returns:
            State abbreviation or empty string
        """
        url_lower = url.lower()

        # Check for state subdomain pattern: {state}.usgenweb.org
        match = re.search(r"(\w+)\.usgenweb\.org", url_lower)
        if match:
            state_slug = match.group(1)
            if state_slug in STATE_ABBREVS:
                return STATE_ABBREVS[state_slug]

        # Check for path pattern: usgenweb.org/{state}/
        match = re.search(r"usgenweb\.org/(\w+)", url_lower)
        if match:
            state_slug = match.group(1)
            if state_slug in STATE_ABBREVS:
                return STATE_ABBREVS[state_slug]

        return ""

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

        try:
            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                urls: list[str] = []

                # State-specific census URLs
                if state_slug:
                    state_base = f"https://{state_slug}.usgenweb.org"

                    # Look for census index pages
                    urls.append(f"{state_base}/census/")
                    urls.append(f"{state_base}/census.html")

                    # Year-specific
                    if year:
                        urls.append(f"{state_base}/census/{year}/")
                        urls.append(f"{state_base}/census{year}/")
                        urls.append(f"{state_base}/{year}census/")

                    # County-specific if provided
                    if county:
                        county_slug = county.lower().replace(" ", "").replace("county", "")
                        urls.append(f"{state_base}/{county_slug}/census/")
                        urls.append(f"{state_base}/{county_slug}/census.html")
                        if year:
                            urls.append(f"{state_base}/{county_slug}/census/{year}/")
                            urls.append(f"{state_base}/{county_slug}/{year}census/")

                # General census archives
                urls.append(f"{self.base_url}/census/")

                for url in urls:
                    try:
                        response = await client.get(url)
                        if response.status_code != 200:
                            continue
                        soup = BeautifulSoup(response.text, "html.parser")

                        # Parse census pages with household extraction
                        page_records = self._parse_census_page(soup, url, surname, given_name)
                        records.extend(page_records)

                        # Also look for links to surname-specific pages
                        surname_links = self._find_surname_census_links(soup, url, surname)
                        for link_url in surname_links[:5]:  # Limit to 5 follow-up links
                            try:
                                link_resp = await client.get(link_url)
                                if link_resp.status_code == 200:
                                    link_soup = BeautifulSoup(link_resp.text, "html.parser")
                                    link_records = self._parse_census_page(link_soup, link_url, surname, given_name)
                                    records.extend(link_records)
                            except Exception:
                                continue

                    except Exception as e:
                        logger.debug("Census search error for %s: %s", url, e)
                        continue

        except Exception as e:
            logger.warning("USGenWeb census search error: %s", e)

        return records

    def _find_surname_census_links(
        self, soup: BeautifulSoup, base_url: str, surname: str
    ) -> list[str]:
        """Find links that might contain census data for the surname.

        Args:
            soup: BeautifulSoup parsed page
            base_url: Current page URL
            surname: Surname to look for

        Returns:
            List of URLs to follow
        """
        from urllib.parse import urlparse, urljoin

        links: list[str] = []
        surname_lower = surname.lower()

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()

            # Look for census-related links
            if "census" in text or "census" in href.lower():
                # Check if it might have our surname or is a general census index
                if surname_lower in text or surname_lower[0].upper() == text[0:1].upper():
                    full_url = urljoin(base_url, href)
                    if full_url not in links:
                        links.append(full_url)

        return links

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

        # Extract census year from URL or page content
        census_year = self._extract_census_year(url, soup)

        # Look for tables - census transcriptions are often tabular
        tables = soup.find_all("table")
        for table in tables:
            household = self._extract_household_from_table(table, surname_lower, given_lower)
            if household:
                household["year"] = census_year
                household["location"] = self._extract_state(url)

                record = RawRecord(
                    source=self.name,
                    record_id=f"{url}#household-{hash(str(household))}",
                    record_type="census",
                    url=url,
                    raw_data={"household": household, "source_url": url},
                    extracted_fields={
                        "household_head": household.get("head", ""),
                        "household_members": household.get("members", []),
                        "census_year": census_year,
                        "location": household.get("location", ""),
                    },
                    accessed_at=datetime.now(UTC),
                )
                records.append(record)

        # Also parse pre-formatted text (common in older USGenWeb pages)
        pre_records = self._parse_preformatted_census(soup, url, surname_lower, census_year)
        records.extend(pre_records)

        return records

    def _extract_census_year(self, url: str, soup: BeautifulSoup) -> str:
        """Extract census year from URL or page content.

        Args:
            url: Page URL
            soup: BeautifulSoup parsed page

        Returns:
            Census year as string, or empty string
        """
        # Check URL for year patterns
        for year in CENSUS_YEARS:
            if str(year) in url:
                return str(year)

        # Check page title
        title = soup.find("title")
        if title:
            title_text = title.get_text()
            for year in CENSUS_YEARS:
                if str(year) in title_text:
                    return str(year)

        # Check h1/h2 headers
        for h in soup.find_all(["h1", "h2"]):
            h_text = h.get_text()
            for year in CENSUS_YEARS:
                if str(year) in h_text:
                    return str(year)

        return ""

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
        occupation_col = next((i for i, h in enumerate(headers) if any(
            k in h for k in ["occupation", "occup"]
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

                # Extract data from cells
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
                if occupation_col >= 0 and occupation_col < len(cells):
                    member["occupation"] = cells[occupation_col]

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

    def _parse_preformatted_census(
        self,
        soup: BeautifulSoup,
        url: str,
        surname_lower: str,
        census_year: str,
    ) -> list[RawRecord]:
        """Parse preformatted (PRE tag) census transcriptions.

        Older USGenWeb pages often use PRE tags for census data.

        Args:
            soup: BeautifulSoup parsed page
            url: Page URL
            surname_lower: Lowercase surname to match
            census_year: Extracted census year

        Returns:
            List of census records
        """
        records: list[RawRecord] = []

        # Find all PRE tags
        for pre in soup.find_all("pre"):
            text = pre.get_text()
            lines = text.split("\n")

            household_members: list[dict[str, str]] = []
            current_head = ""
            collecting = False

            for line in lines:
                line = line.strip()
                if not line or len(line) < 5:
                    continue

                line_lower = line.lower()

                # Check for surname match to start collecting
                if surname_lower in line_lower:
                    collecting = True

                if collecting:
                    # Try to parse this line
                    member = self._parse_census_line(line)
                    if member:
                        household_members.append(member)
                        if not current_head:
                            current_head = member.get("name", "")

                    # Stop collecting if we hit an empty line after finding members
                    # or if we've collected enough
                    if len(household_members) >= 15:
                        break

            if household_members:
                record = RawRecord(
                    source=self.name,
                    record_id=f"{url}#pre-{hash(str(household_members))}",
                    record_type="census",
                    url=url,
                    raw_data={"household_members": household_members, "source_url": url},
                    extracted_fields={
                        "household_head": current_head,
                        "household_members": household_members,
                        "census_year": census_year,
                        "location": self._extract_state(url),
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
        member: dict[str, str] = {}

        # Try multiple delimiters
        delimiters = [",", "|", "\t", "  "]  # Note: double space is common
        parts: list[str] = []

        for delim in delimiters:
            if delim in line:
                parts = [p.strip() for p in line.split(delim) if p.strip()]
                if len(parts) >= 2:
                    break

        # Whitespace-separated fallback
        if len(parts) < 2:
            parts = line.split()

        if len(parts) < 2:
            return None

        # First part is usually name
        member["name"] = parts[0]

        # Look through remaining parts
        for part in parts[1:]:
            part_clean = part.strip()
            part_lower = part_clean.lower()

            # Age (numeric, usually 1-3 digits)
            if re.match(r"^\d{1,3}$", part_clean):
                if "age" not in member:
                    member["age"] = part_clean
            # Sex
            elif part_lower in ("m", "f", "male", "female"):
                member["sex"] = part_clean
            # Relationship
            elif part_lower in (
                "head", "wife", "husband", "son", "daughter", "mother", "father",
                "brother", "sister", "boarder", "lodger", "servant", "inmate",
                "grandchild", "grandson", "granddaughter", "nephew", "niece",
                "aunt", "uncle", "cousin", "step-son", "step-daughter"
            ):
                member["relationship"] = part_clean
            # Single letter for marital status
            elif part_lower in ("s", "m", "w", "d") and len(part_clean) == 1:
                member["marital_status"] = part_clean
            # Birthplace (longer text, not numeric)
            elif len(part_clean) > 2 and not part_clean.isdigit():
                if "birthplace" not in member:
                    member["birthplace"] = part_clean

        if member.get("name"):
            return member
        return None
