"""Relevance evaluator for determining if records match the research subject.

This is the critical component that answers: "Is this record about the same person?"

In genealogy, this is hard because:
- Names repeat across generations (Archer Durham Sr, Jr, III...)
- Spelling variations (Durham, Derham, Duram)
- Multiple people with same name in same era
- Records may have incomplete or conflicting data
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from gps_agents.models.search import RawRecord, SearchQuery

logger = logging.getLogger(__name__)


class MatchConfidence(str, Enum):
    """Confidence levels for record matching."""

    DEFINITE = "definite"  # 95%+ - Multiple strong matches
    LIKELY = "likely"  # 75-94% - Good evidence, minor gaps
    POSSIBLE = "possible"  # 50-74% - Some matches, some unknowns
    UNLIKELY = "unlikely"  # 25-49% - Weak evidence
    NOT_MATCH = "not_match"  # <25% - Conflicting evidence


@dataclass
class MatchScore:
    """Detailed scoring for a record match."""

    overall_score: float  # 0.0 to 1.0
    confidence: MatchConfidence
    name_score: float = 0.0
    date_score: float = 0.0
    location_score: float = 0.0
    relationship_score: float = 0.0
    match_reasons: list[str] = field(default_factory=list)
    conflict_reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_score(cls, score: float, reasons: list[str], conflicts: list[str]) -> "MatchScore":
        """Create a MatchScore from an overall score."""
        if score >= 0.95:
            confidence = MatchConfidence.DEFINITE
        elif score >= 0.75:
            confidence = MatchConfidence.LIKELY
        elif score >= 0.50:
            confidence = MatchConfidence.POSSIBLE
        elif score >= 0.25:
            confidence = MatchConfidence.UNLIKELY
        else:
            confidence = MatchConfidence.NOT_MATCH

        return cls(
            overall_score=score,
            confidence=confidence,
            match_reasons=reasons,
            conflict_reasons=conflicts,
        )


@dataclass
class PersonProfile:
    """Profile of the person being researched, built from known facts."""

    surname: str
    given_name: str | None = None
    surname_variants: list[str] = field(default_factory=list)
    birth_year: int | None = None
    birth_year_range: tuple[int, int] | None = None
    death_year: int | None = None
    death_year_range: tuple[int, int] | None = None
    birth_place: str | None = None
    death_place: str | None = None
    residence_places: list[str] = field(default_factory=list)
    spouse_names: list[str] = field(default_factory=list)
    parent_names: list[str] = field(default_factory=list)
    child_names: list[str] = field(default_factory=list)
    occupations: list[str] = field(default_factory=list)


class RelevanceEvaluator:
    """Evaluates whether a search result is relevant to the research subject.

    This is the "brain" that decides if a record found is actually about
    the person being researched, not a different person with the same name.

    Scoring factors:
    - Name match (40%): How well does the name match?
    - Date match (30%): Do dates align within tolerance?
    - Location match (20%): Are locations consistent?
    - Relationship match (10%): Do family members match?

    A conflict in any category can override positive matches.
    """

    # Scoring weights
    WEIGHT_NAME = 0.40
    WEIGHT_DATE = 0.30
    WEIGHT_LOCATION = 0.20
    WEIGHT_RELATIONSHIP = 0.10

    # Tolerances
    YEAR_TOLERANCE = 5  # ±5 years for birth/death dates
    YEAR_TOLERANCE_STRICT = 2  # ±2 years when we have exact dates

    def __init__(self, profile: PersonProfile) -> None:
        """Initialize with the target person's profile.

        Args:
            profile: Profile of the person being researched
        """
        self.profile = profile
        self._name_variants = self._build_name_variants()

    def _build_name_variants(self) -> set[str]:
        """Build set of acceptable name variants."""
        variants = {self.profile.surname.lower()}
        variants.update(v.lower() for v in self.profile.surname_variants)

        # Add common phonetic variants
        surname_lower = self.profile.surname.lower()

        # Soundex-like variants (simplified)
        if surname_lower.startswith("mc"):
            variants.add("mac" + surname_lower[2:])
        if surname_lower.startswith("mac"):
            variants.add("mc" + surname_lower[3:])

        # Double letter variants
        for i, char in enumerate(surname_lower):
            if i > 0 and char == surname_lower[i - 1]:
                variants.add(surname_lower[:i] + surname_lower[i + 1:])

        # Common substitutions
        if "ph" in surname_lower:
            variants.add(surname_lower.replace("ph", "f"))
        if "f" in surname_lower:
            variants.add(surname_lower.replace("f", "ph"))

        return variants

    def evaluate(self, record: RawRecord) -> MatchScore:
        """Evaluate if a record matches the research subject.

        Args:
            record: The search result record to evaluate

        Returns:
            MatchScore with detailed scoring
        """
        reasons = []
        conflicts = []

        # Score each category
        name_score, name_reasons, name_conflicts = self._score_name(record)
        date_score, date_reasons, date_conflicts = self._score_dates(record)
        location_score, location_reasons, location_conflicts = self._score_location(record)
        relationship_score, rel_reasons, rel_conflicts = self._score_relationships(record)

        reasons.extend(name_reasons)
        reasons.extend(date_reasons)
        reasons.extend(location_reasons)
        reasons.extend(rel_reasons)

        conflicts.extend(name_conflicts)
        conflicts.extend(date_conflicts)
        conflicts.extend(location_conflicts)
        conflicts.extend(rel_conflicts)

        # Calculate weighted score
        weighted_score = (
            name_score * self.WEIGHT_NAME
            + date_score * self.WEIGHT_DATE
            + location_score * self.WEIGHT_LOCATION
            + relationship_score * self.WEIGHT_RELATIONSHIP
        )

        # Apply conflict penalty
        # Each conflict reduces score significantly
        conflict_penalty = len(conflicts) * 0.15
        final_score = max(0.0, weighted_score - conflict_penalty)

        # A definite date conflict is disqualifying
        if any("definite" in c.lower() or "wrong person" in c.lower() for c in conflicts):
            final_score = min(final_score, 0.20)

        match = MatchScore(
            overall_score=final_score,
            confidence=self._score_to_confidence(final_score),
            name_score=name_score,
            date_score=date_score,
            location_score=location_score,
            relationship_score=relationship_score,
            match_reasons=reasons,
            conflict_reasons=conflicts,
        )

        return match

    def _score_name(self, record: RawRecord) -> tuple[float, list[str], list[str]]:
        """Score name match.

        Returns:
            (score, reasons, conflicts)
        """
        reasons = []
        conflicts = []
        score = 0.0

        extracted = record.extracted_fields
        raw = record.raw_data

        # Get name from record
        record_name = (
            extracted.get("name")
            or extracted.get("full_name")
            or raw.get("name")
            or ""
        )

        record_surname = extracted.get("surname") or ""
        record_given = extracted.get("given_name") or extracted.get("first_name") or ""

        if not record_name and not record_surname:
            return 0.5, ["No name in record"], []  # Neutral - can't evaluate

        # Parse name if full name given
        if record_name and not record_surname:
            parts = record_name.split()
            if len(parts) >= 2:
                record_given = parts[0]
                record_surname = parts[-1]
            elif len(parts) == 1:
                record_surname = parts[0]

        # Score surname match
        surname_lower = record_surname.lower() if record_surname else ""
        if surname_lower in self._name_variants:
            score += 0.6
            reasons.append(f"Surname match: {record_surname}")
        elif any(self._fuzzy_match(surname_lower, v) for v in self._name_variants):
            score += 0.4
            reasons.append(f"Surname fuzzy match: {record_surname}")
        elif record_surname:
            conflicts.append(f"Surname mismatch: {record_surname} vs {self.profile.surname}")

        # Score given name match
        if self.profile.given_name:
            profile_given_lower = self.profile.given_name.lower()
            record_given_lower = record_given.lower() if record_given else ""

            if record_given_lower == profile_given_lower:
                score += 0.4
                reasons.append(f"Given name exact match: {record_given}")
            elif record_given_lower and profile_given_lower:
                # Check initials
                if record_given_lower[0] == profile_given_lower[0]:
                    score += 0.2
                    reasons.append(f"Given name initial match: {record_given[0]}")
                # Check nicknames
                elif self._is_nickname_match(profile_given_lower, record_given_lower):
                    score += 0.3
                    reasons.append(f"Given name nickname match: {record_given}")
                else:
                    conflicts.append(f"Given name mismatch: {record_given} vs {self.profile.given_name}")

        return min(score, 1.0), reasons, conflicts

    def _score_dates(self, record: RawRecord) -> tuple[float, list[str], list[str]]:
        """Score date match.

        Returns:
            (score, reasons, conflicts)
        """
        reasons = []
        conflicts = []
        score = 0.0
        comparisons = 0

        extracted = record.extracted_fields
        raw = record.raw_data

        # Extract years from record
        record_birth_year = self._extract_year(
            extracted.get("birth_year")
            or extracted.get("birth_date")
            or raw.get("birth_year")
        )

        record_death_year = self._extract_year(
            extracted.get("death_year")
            or extracted.get("death_date")
            or raw.get("death_year")
        )

        # Score birth year
        if self.profile.birth_year and record_birth_year:
            comparisons += 1
            diff = abs(self.profile.birth_year - record_birth_year)

            if diff == 0:
                score += 0.5
                reasons.append(f"Birth year exact match: {record_birth_year}")
            elif diff <= self.YEAR_TOLERANCE_STRICT:
                score += 0.4
                reasons.append(f"Birth year close match: {record_birth_year} (±{diff})")
            elif diff <= self.YEAR_TOLERANCE:
                score += 0.3
                reasons.append(f"Birth year within tolerance: {record_birth_year} (±{diff})")
            elif diff <= 15:
                score += 0.1
                reasons.append(f"Birth year might be error: {record_birth_year} (±{diff})")
            else:
                conflicts.append(
                    f"Birth year conflict: record shows {record_birth_year}, "
                    f"expected ~{self.profile.birth_year} - likely different person"
                )

        # Score death year
        if self.profile.death_year and record_death_year:
            comparisons += 1
            diff = abs(self.profile.death_year - record_death_year)

            if diff == 0:
                score += 0.5
                reasons.append(f"Death year exact match: {record_death_year}")
            elif diff <= self.YEAR_TOLERANCE_STRICT:
                score += 0.4
                reasons.append(f"Death year close match: {record_death_year} (±{diff})")
            elif diff <= self.YEAR_TOLERANCE:
                score += 0.3
                reasons.append(f"Death year within tolerance: {record_death_year} (±{diff})")
            else:
                conflicts.append(
                    f"Death year conflict: record shows {record_death_year}, "
                    f"expected ~{self.profile.death_year}"
                )

        # Check for impossible date combinations
        if record_birth_year and record_death_year:
            if record_death_year < record_birth_year:
                conflicts.append("Impossible: death before birth")
            elif record_death_year - record_birth_year > 120:
                conflicts.append("Implausible: lived over 120 years")

        if comparisons == 0:
            return 0.5, ["No dates to compare"], []  # Neutral

        return min(score, 1.0), reasons, conflicts

    def _score_location(self, record: RawRecord) -> tuple[float, list[str], list[str]]:
        """Score location match.

        Returns:
            (score, reasons, conflicts)
        """
        reasons = []
        conflicts = []
        score = 0.0

        extracted = record.extracted_fields
        raw = record.raw_data

        # Get locations from record
        record_locations = []
        for key in ["location", "residence", "birth_place", "death_place", "state", "county"]:
            loc = extracted.get(key) or raw.get(key)
            if loc:
                record_locations.append(str(loc).lower())

        if not record_locations:
            return 0.5, ["No location in record"], []  # Neutral

        # Build profile locations
        profile_locations = []
        if self.profile.birth_place:
            profile_locations.append(self.profile.birth_place.lower())
        if self.profile.death_place:
            profile_locations.append(self.profile.death_place.lower())
        profile_locations.extend(p.lower() for p in self.profile.residence_places)

        if not profile_locations:
            return 0.5, ["No profile location to compare"], []  # Neutral

        # Check for matches
        for rec_loc in record_locations:
            for prof_loc in profile_locations:
                if prof_loc in rec_loc or rec_loc in prof_loc:
                    score += 0.3
                    reasons.append(f"Location match: {rec_loc}")
                    break
                # Check state abbreviation match
                if len(rec_loc) == 2 and rec_loc.upper() in prof_loc.upper():
                    score += 0.2
                    reasons.append(f"State match: {rec_loc.upper()}")
                    break

        return min(score, 1.0), reasons, conflicts

    def _score_relationships(self, record: RawRecord) -> tuple[float, list[str], list[str]]:
        """Score relationship match (spouse, parents).

        Returns:
            (score, reasons, conflicts)
        """
        reasons = []
        conflicts = []
        score = 0.0

        extracted = record.extracted_fields
        raw = record.raw_data

        # Check spouse
        record_spouse = extracted.get("spouse") or extracted.get("spouse_name") or raw.get("spouse")
        if record_spouse and self.profile.spouse_names:
            record_spouse_lower = str(record_spouse).lower()
            for spouse in self.profile.spouse_names:
                if self._name_in_text(spouse, record_spouse_lower):
                    score += 0.5
                    reasons.append(f"Spouse match: {record_spouse}")
                    break

        # Check father
        record_father = extracted.get("father") or extracted.get("father_name") or raw.get("father")
        if record_father and self.profile.parent_names:
            record_father_lower = str(record_father).lower()
            for parent in self.profile.parent_names:
                if self._name_in_text(parent, record_father_lower):
                    score += 0.3
                    reasons.append(f"Father match: {record_father}")
                    break

        # Check mother
        record_mother = extracted.get("mother") or extracted.get("mother_name") or raw.get("mother")
        if record_mother and self.profile.parent_names:
            record_mother_lower = str(record_mother).lower()
            for parent in self.profile.parent_names:
                if self._name_in_text(parent, record_mother_lower):
                    score += 0.3
                    reasons.append(f"Mother match: {record_mother}")
                    break

        if not any([record_spouse, record_father, record_mother]):
            return 0.5, ["No relationships in record"], []  # Neutral

        return min(score, 1.0), reasons, conflicts

    def _extract_year(self, value: Any) -> int | None:
        """Extract a year from a value."""
        if value is None:
            return None
        if isinstance(value, int):
            return value if 1500 <= value <= 2100 else None

        text = str(value)
        match = re.search(r"\b(1[789]\d{2}|20[0-2]\d)\b", text)
        return int(match.group(1)) if match else None

    def _fuzzy_match(self, s1: str, s2: str, threshold: float = 0.8) -> bool:
        """Simple fuzzy string matching."""
        if not s1 or not s2:
            return False
        if s1 == s2:
            return True

        # Levenshtein-like simple check
        if len(s1) < 3 or len(s2) < 3:
            return s1[0] == s2[0]

        # Check if one is substring of other
        if s1 in s2 or s2 in s1:
            return True

        # Count matching characters
        matches = sum(1 for c in s1 if c in s2)
        similarity = matches / max(len(s1), len(s2))
        return similarity >= threshold

    def _is_nickname_match(self, formal: str, informal: str) -> bool:
        """Check if two names are nickname variants."""
        nicknames = {
            "william": ["bill", "billy", "will", "willy", "willie"],
            "robert": ["bob", "bobby", "rob", "robbie"],
            "james": ["jim", "jimmy", "jamie"],
            "john": ["jack", "johnny"],
            "richard": ["dick", "rick", "ricky"],
            "michael": ["mike", "mick", "mickey"],
            "elizabeth": ["liz", "lizzy", "beth", "betty", "eliza"],
            "margaret": ["maggie", "meg", "peggy", "marge"],
            "catherine": ["kate", "katie", "cathy", "kitty"],
            "thomas": ["tom", "tommy"],
            "charles": ["charlie", "chuck"],
            "edward": ["ed", "eddie", "ted", "teddy"],
            "alexander": ["alex", "sandy"],
            "benjamin": ["ben", "benny"],
            "daniel": ["dan", "danny"],
            "samuel": ["sam", "sammy"],
            "joseph": ["joe", "joey"],
            "patrick": ["pat", "paddy"],
            "archer": ["archie", "arch"],  # Specific to our case!
        }

        formal_lower = formal.lower()
        informal_lower = informal.lower()

        # Check both directions
        if formal_lower in nicknames:
            if informal_lower in nicknames[formal_lower]:
                return True

        for full, nicks in nicknames.items():
            if informal_lower == full and formal_lower in nicks:
                return True
            if formal_lower == full and informal_lower in nicks:
                return True

        return False

    def _name_in_text(self, name: str, text: str) -> bool:
        """Check if a name appears in text."""
        name_lower = name.lower()
        # Check full name
        if name_lower in text:
            return True
        # Check surname only
        parts = name_lower.split()
        if len(parts) >= 2:
            surname = parts[-1]
            if surname in text:
                return True
        return False

    def _score_to_confidence(self, score: float) -> MatchConfidence:
        """Convert numeric score to confidence level."""
        if score >= 0.95:
            return MatchConfidence.DEFINITE
        elif score >= 0.75:
            return MatchConfidence.LIKELY
        elif score >= 0.50:
            return MatchConfidence.POSSIBLE
        elif score >= 0.25:
            return MatchConfidence.UNLIKELY
        else:
            return MatchConfidence.NOT_MATCH

    def evaluate_batch(
        self, records: list[RawRecord], min_confidence: MatchConfidence = MatchConfidence.POSSIBLE
    ) -> list[tuple[RawRecord, MatchScore]]:
        """Evaluate multiple records and filter by confidence.

        Args:
            records: List of records to evaluate
            min_confidence: Minimum confidence level to include

        Returns:
            List of (record, score) tuples that meet the threshold
        """
        results = []
        confidence_order = [
            MatchConfidence.DEFINITE,
            MatchConfidence.LIKELY,
            MatchConfidence.POSSIBLE,
            MatchConfidence.UNLIKELY,
            MatchConfidence.NOT_MATCH,
        ]
        min_index = confidence_order.index(min_confidence)

        for record in records:
            score = self.evaluate(record)
            score_index = confidence_order.index(score.confidence)
            if score_index <= min_index:
                results.append((record, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1].overall_score, reverse=True)
        return results


def build_profile_from_facts(
    surname: str,
    given_name: str | None,
    facts: list[dict],
) -> PersonProfile:
    """Build a PersonProfile from a list of facts.

    Args:
        surname: Subject's surname
        given_name: Subject's given name
        facts: List of fact dictionaries

    Returns:
        PersonProfile built from the facts
    """
    profile = PersonProfile(surname=surname, given_name=given_name)

    year_pattern = re.compile(r"\b(1[789]\d{2}|20[0-2]\d)\b")

    for fact in facts:
        statement = fact.get("statement", "").lower()
        confidence = fact.get("confidence", 0.5)

        if confidence < 0.6:  # Skip low confidence facts
            continue

        # Extract birth info
        if "born" in statement:
            years = year_pattern.findall(statement)
            if years and not profile.birth_year:
                profile.birth_year = int(years[0])

            # Extract place
            match = re.search(r"born[^,]*in ([^,.]+)", statement)
            if match and not profile.birth_place:
                profile.birth_place = match.group(1).strip()

        # Extract death info
        if "died" in statement or "death" in statement:
            years = year_pattern.findall(statement)
            if years and not profile.death_year:
                profile.death_year = int(years[0])

            match = re.search(r"(?:died|death)[^,]*in ([^,.]+)", statement)
            if match and not profile.death_place:
                profile.death_place = match.group(1).strip()

        # Extract spouse
        if "married" in statement or "wife" in statement or "husband" in statement:
            match = re.search(r"(?:married|wife|husband)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
            if match:
                profile.spouse_names.append(match.group(1))

        # Extract parents
        if "father" in statement or "son of" in statement:
            match = re.search(r"(?:father|son of)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
            if match:
                profile.parent_names.append(match.group(1))

        if "mother" in statement or "daughter of" in statement:
            match = re.search(r"(?:mother|daughter of)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
            if match:
                profile.parent_names.append(match.group(1))

        # Extract residence
        for state in ["california", "tennessee", "texas", "virginia", "new york"]:  # Common states
            if state in statement:
                if state not in [r.lower() for r in profile.residence_places]:
                    profile.residence_places.append(state.title())

    return profile
