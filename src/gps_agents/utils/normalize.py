"""Normalization utilities for genealogical data.

Provides consistent normalization for names, places, and dates
to improve matching and deduplication accuracy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


@dataclass
class ParsedDate:
    """Structured date with precision tracking."""

    year: int | None = None
    month: int | None = None
    day: int | None = None
    circa: bool = False  # Approximate date
    before: bool = False  # Date is "before" qualifier
    after: bool = False  # Date is "after" qualifier
    original: str = ""  # Original string for reference

    @property
    def precision(self) -> str:
        """Return date precision level."""
        if self.day and self.month and self.year:
            return "exact"
        elif self.month and self.year:
            return "month"
        elif self.year:
            return "year"
        return "unknown"

    def to_iso(self) -> str | None:
        """Convert to ISO format string (YYYY-MM-DD or partial)."""
        if not self.year:
            return None
        if self.month and self.day:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        elif self.month:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}"


# Month name mappings
MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

# Common name prefixes to strip
NAME_PREFIXES = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "rev", "hon",
    "sir", "lord", "lady", "capt", "captain", "col", "colonel",
    "gen", "general", "maj", "major", "lt", "lieutenant",
    "sgt", "sergeant", "pvt", "private", "cpl", "corporal",
}

# Common name suffixes to strip
NAME_SUFFIXES = {
    "jr", "sr", "i", "ii", "iii", "iv", "v",
    "esq", "phd", "md", "dds", "jd",
}


def normalize_name(name: str, keep_case: bool = False) -> str:
    """Normalize a personal name for comparison.

    - Removes common prefixes (Mr., Mrs., Dr., etc.)
    - Removes common suffixes (Jr., Sr., III, etc.)
    - Normalizes whitespace
    - Optionally lowercases
    - Strips punctuation

    Args:
        name: The name to normalize
        keep_case: If True, preserve original case

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    # Strip and normalize whitespace
    result = " ".join(name.split())

    # Remove punctuation except hyphens and apostrophes in names
    result = re.sub(r"[^\w\s\-']", " ", result)

    # Split into parts
    parts = result.split()

    # Remove prefixes
    while parts and parts[0].lower().rstrip(".") in NAME_PREFIXES:
        parts.pop(0)

    # Remove suffixes
    while parts and parts[-1].lower().rstrip(".") in NAME_SUFFIXES:
        parts.pop()

    result = " ".join(parts)

    if not keep_case:
        result = result.lower()

    return result.strip()


def normalize_place(place: str, keep_case: bool = False) -> str:
    """Normalize a place name for comparison.

    - Normalizes whitespace
    - Expands common abbreviations (St. -> Saint, Co. -> County)
    - Standardizes separator formatting
    - Optionally lowercases

    Args:
        place: The place to normalize
        keep_case: If True, preserve original case

    Returns:
        Normalized place string
    """
    if not place:
        return ""

    # Strip and normalize whitespace
    result = " ".join(place.split())

    # Common abbreviation expansions
    abbreviations = {
        r"\bst\.\s*": "saint ",
        r"\bmt\.\s*": "mount ",
        r"\bco\.\s*": "county ",
        r"\btwp\.\s*": "township ",
        r"\btwsp\.\s*": "township ",
        r"\bprov\.\s*": "province ",
        r"\bpvnc\.\s*": "province ",
    }

    # US state abbreviations (common ones for genealogy)
    us_states = {
        r"\bny\b": "new york",
        r"\bca\b": "california",
        r"\btx\b": "texas",
        r"\bpa\b": "pennsylvania",
        r"\bma\b": "massachusetts",
        r"\bva\b": "virginia",
        r"\boh\b": "ohio",
        r"\bil\b": "illinois",
        r"\bga\b": "georgia",
        r"\bnc\b": "north carolina",
        r"\bsc\b": "south carolina",
        r"\bmd\b": "maryland",
        r"\bnj\b": "new jersey",
        r"\bct\b": "connecticut",
        r"\bmi\b": "michigan",
        r"\bmo\b": "missouri",
        r"\bfl\b": "florida",
        r"\bky\b": "kentucky",
        r"\btn\b": "tennessee",
        r"\bin\b": "indiana",
        r"\bwi\b": "wisconsin",
        r"\bmn\b": "minnesota",
        r"\bia\b": "iowa",
        r"\bla\b": "louisiana",
        r"\bal\b": "alabama",
        r"\bms\b": "mississippi",
        r"\bar\b": "arkansas",
        r"\bme\b": "maine",
        r"\bnh\b": "new hampshire",
        r"\bvt\b": "vermont",
        r"\bri\b": "rhode island",
        r"\bde\b": "delaware",
        r"\bwv\b": "west virginia",
    }

    result_lower = result.lower()
    for pattern, replacement in abbreviations.items():
        result_lower = re.sub(pattern, replacement, result_lower)

    # Expand state abbreviations (only when they appear as standalone tokens)
    for pattern, replacement in us_states.items():
        result_lower = re.sub(pattern, replacement, result_lower)

    if keep_case:
        # Try to preserve case by matching positions
        result = result_lower.title()
    else:
        result = result_lower

    # Normalize commas and spaces
    result = re.sub(r"\s*,\s*", ", ", result)

    return result.strip()


def parse_date(date_str: str) -> ParsedDate:
    """Parse a date string into structured components.

    Handles multiple formats:
    - ISO: 1932-06-09
    - GEDCOM: 9 JUN 1932
    - US: June 9, 1932 or 6/9/1932
    - European: 9/6/1932 or 9.6.1932
    - Qualifiers: ABT, BEF, AFT, c., ca., circa, about, before, after

    Args:
        date_str: Date string in various formats

    Returns:
        ParsedDate with extracted components
    """
    if not date_str:
        return ParsedDate(original=date_str)

    result = ParsedDate(original=date_str)
    text = date_str.strip().upper()

    # Check for qualifiers
    qualifiers = {
        "ABT": "circa",
        "ABOUT": "circa",
        "CIRCA": "circa",
        "CA": "circa",
        "CA.": "circa",
        "C.": "circa",
        "BEF": "before",
        "BEFORE": "before",
        "AFT": "after",
        "AFTER": "after",
    }

    for qual, qual_type in qualifiers.items():
        if text.startswith(qual + " ") or text.startswith(qual + "."):
            text = text[len(qual):].strip().lstrip(".")
            if qual_type == "circa":
                result.circa = True
            elif qual_type == "before":
                result.before = True
            elif qual_type == "after":
                result.after = True
            break

    # Try ISO format: YYYY-MM-DD or YYYY-MM or YYYY
    iso_match = re.match(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$", text)
    if iso_match:
        result.year = int(iso_match.group(1))
        if iso_match.group(2):
            result.month = int(iso_match.group(2))
        if iso_match.group(3):
            result.day = int(iso_match.group(3))
        return result

    # Try GEDCOM format: 9 JUN 1932
    gedcom_match = re.match(r"^(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})$", text)
    if gedcom_match:
        result.day = int(gedcom_match.group(1))
        month_name = gedcom_match.group(2).lower()
        result.month = MONTH_NAMES.get(month_name)
        result.year = int(gedcom_match.group(3))
        return result

    # Try GEDCOM month-year: JUN 1932
    gedcom_my_match = re.match(r"^([A-Z]{3,9})\s+(\d{4})$", text)
    if gedcom_my_match:
        month_name = gedcom_my_match.group(1).lower()
        result.month = MONTH_NAMES.get(month_name)
        result.year = int(gedcom_my_match.group(2))
        return result

    # Try US format with month name: June 9, 1932
    us_match = re.match(r"^([A-Z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", text)
    if us_match:
        month_name = us_match.group(1).lower()
        result.month = MONTH_NAMES.get(month_name)
        result.day = int(us_match.group(2))
        result.year = int(us_match.group(3))
        return result

    # Try numeric formats: M/D/YYYY or D/M/YYYY or D.M.YYYY
    numeric_match = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", text)
    if numeric_match:
        a, b, year = int(numeric_match.group(1)), int(numeric_match.group(2)), int(numeric_match.group(3))
        result.year = year
        # Heuristic: if a > 12, it's the day (European format)
        if a > 12:
            result.day = a
            result.month = b
        elif b > 12:
            result.month = a
            result.day = b
        else:
            # Ambiguous - assume M/D/YYYY (US format)
            result.month = a
            result.day = b
        return result

    # Try year only
    year_match = re.match(r"^(\d{4})$", text)
    if year_match:
        result.year = int(year_match.group(1))
        return result

    return result


def dates_match(date1: ParsedDate, date2: ParsedDate, tolerance_years: int = 0) -> bool:
    """Check if two parsed dates match within tolerance.

    Args:
        date1: First date
        date2: Second date
        tolerance_years: Allow this many years difference (for circa dates)

    Returns:
        True if dates match within tolerance
    """
    if not date1.year or not date2.year:
        return False

    # Apply tolerance for approximate dates
    effective_tolerance = tolerance_years
    if date1.circa or date2.circa:
        effective_tolerance = max(effective_tolerance, 2)

    year_diff = abs(date1.year - date2.year)
    if year_diff > effective_tolerance:
        return False

    # If both have months and they match exactly, check day
    if date1.month and date2.month:
        if date1.month != date2.month:
            return year_diff == 0 and effective_tolerance > 0
        if date1.day and date2.day:
            return date1.day == date2.day or effective_tolerance > 0

    return True


def names_match(name1: str, name2: str, fuzzy: bool = False) -> bool:
    """Check if two names match after normalization.

    Args:
        name1: First name
        name2: Second name
        fuzzy: If True, allow partial matches

    Returns:
        True if names match
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if n1 == n2:
        return True

    if not fuzzy:
        return False

    # Fuzzy: check if one contains the other
    if n1 in n2 or n2 in n1:
        return True

    # Check if surnames match (last word)
    parts1 = n1.split()
    parts2 = n2.split()
    if parts1 and parts2 and parts1[-1] == parts2[-1]:
        # Surnames match - check if first names are similar
        if len(parts1) > 1 and len(parts2) > 1:
            # Check first initial
            if parts1[0][0] == parts2[0][0]:
                return True

    return False
