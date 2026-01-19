"""Match-Merge logic for Gramps database to prevent duplicate records.

Implements intelligent matching algorithms to find potential duplicates
before creating new records, with configurable merge strategies.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field

from gps_agents.gramps.models import Event, Name, Person
from gps_agents.idempotency.exceptions import IdempotencyBlock
from gps_agents.gramps.upsert import upsert_person
from gps_agents.projections.sqlite_projection import SQLiteProjection

if TYPE_CHECKING:
    from collections.abc import Callable

    from gps_agents.gramps.client import GrampsClient


class MatchConfidence(str, Enum):
    """Confidence level for a potential match."""
    DEFINITE = "definite"      # 95%+ - auto-merge safe
    PROBABLE = "probable"      # 75-94% - suggest merge, ask user
    POSSIBLE = "possible"      # 50-74% - flag for review
    UNLIKELY = "unlikely"      # <50% - probably different people


class MergeStrategy(str, Enum):
    """Strategy for handling matched records."""
    AUTO_MERGE = "auto_merge"          # Merge definite matches automatically
    PROMPT_USER = "prompt_user"        # Always ask user before merging
    CREATE_NOTE = "create_note"        # Create new record with note about potential match
    SKIP_DUPLICATES = "skip_duplicates"  # Don't create if match found


class MatchResult(BaseModel):
    """Result of a match operation."""
    matched: bool = False
    confidence: MatchConfidence = MatchConfidence.UNLIKELY
    match_score: float = 0.0
    matched_person: Person | None = None
    matched_handle: str | None = None
    match_reasons: list[str] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)


class MergeResult(BaseModel):
    """Result of a merge operation."""
    action: str  # "merged", "created", "skipped", "needs_review"
    person: Person
    handle: str | None = None
    message: str = ""
    conflicts: list[str] = Field(default_factory=list)


class PersonMatcher:
    """
    Intelligent person matching to prevent duplicates in Gramps.

    Uses multiple signals:
    - Name similarity (Soundex, Levenshtein)
    - Date proximity
    - Place matching
    - Family relationships
    """

    # Scoring weights
    WEIGHTS: ClassVar[dict[str, int]] = {
        "exact_name": 40,
        "soundex_match": 25,
        "similar_name": 15,
        "birth_year_exact": 20,
        "birth_year_close": 10,  # within 2 years
        "birth_place": 15,
        "death_year_exact": 15,
        "death_year_close": 8,
        "death_place": 15,  # Match birth_place weight
        "sex_match": 5,
        "parent_match": 20,
        "spouse_match": 15,
    }

    # Negative signals
    CONFLICTS: ClassVar[dict[str, int]] = {
        "sex_mismatch": -50,
        "birth_year_far": -30,  # more than 10 years
        "death_before_birth": -100,
        "different_parents": -40,
    }

    def __init__(self, client: GrampsClient) -> None:
        """Initialize matcher with Gramps client."""
        self.client = client

    def find_matches(
        self,
        person: Person,
        threshold: float = 50.0,
        limit: int = 5,
    ) -> list[MatchResult]:
        """
        Find potential matches for a person in the database.

        Args:
            person: Person to find matches for
            threshold: Minimum score to consider a match
            limit: Maximum matches to return

        Returns:
            List of MatchResult ordered by confidence
        """
        if not person.primary_name:
            return []

        # Search by surname
        candidates = self.client.find_persons(
            surname=person.primary_name.surname,
            limit=100,
        )

        # Also search by Soundex variants
        soundex = self._soundex(person.primary_name.surname)
        for candidate in self.client.find_persons(limit=100):
            if (
                candidate.primary_name
                and self._soundex(candidate.primary_name.surname) == soundex
                and candidate not in candidates
            ):
                candidates.append(candidate)

        # Score each candidate
        results = []
        for candidate in candidates:
            result = self._score_match(person, candidate)
            if result.match_score >= threshold:
                results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.match_score, reverse=True)

        return results[:limit]

    def _score_match(self, person: Person, candidate: Person) -> MatchResult:
        """Score a potential match between two persons."""
        score = 0.0
        reasons = []
        conflicts = []

        # Name matching
        if person.primary_name and candidate.primary_name:
            name_score, name_reasons = self._score_names(
                person.primary_name,
                candidate.primary_name,
            )
            score += name_score
            reasons.extend(name_reasons)

        # Sex matching
        if person.sex and candidate.sex:
            if person.sex == candidate.sex:
                score += self.WEIGHTS["sex_match"]
                reasons.append(f"Sex matches: {person.sex}")
            elif person.sex != "U" and candidate.sex != "U":
                score += self.CONFLICTS["sex_mismatch"]
                conflicts.append(f"Sex mismatch: {person.sex} vs {candidate.sex}")

        # Birth date matching
        if person.birth and candidate.birth:
            birth_score, birth_reasons, birth_conflicts = self._score_events(
                person.birth, candidate.birth, "birth"
            )
            score += birth_score
            reasons.extend(birth_reasons)
            conflicts.extend(birth_conflicts)

        # Death date matching
        if person.death and candidate.death:
            death_score, death_reasons, death_conflicts = self._score_events(
                person.death, candidate.death, "death"
            )
            score += death_score
            reasons.extend(death_reasons)
            conflicts.extend(death_conflicts)

        # Determine confidence level
        if score >= 80:
            confidence = MatchConfidence.DEFINITE
        elif score >= 60:
            confidence = MatchConfidence.PROBABLE
        elif score >= 40:
            confidence = MatchConfidence.POSSIBLE
        else:
            confidence = MatchConfidence.UNLIKELY

        return MatchResult(
            matched=score >= 50,
            confidence=confidence,
            match_score=score,
            matched_person=candidate,
            matched_handle=candidate.gramps_id,
            match_reasons=reasons,
            conflict_reasons=conflicts,
        )

    def _score_names(
        self,
        name1: Name,
        name2: Name,
    ) -> tuple[float, list[str]]:
        """Score name similarity."""
        score = 0.0
        reasons = []

        # Surname comparison
        if name1.surname.lower() == name2.surname.lower():
            score += self.WEIGHTS["exact_name"] * 0.6
            reasons.append(f"Exact surname match: {name1.surname}")
        elif self._soundex(name1.surname) == self._soundex(name2.surname):
            score += self.WEIGHTS["soundex_match"] * 0.6
            reasons.append(f"Soundex surname match: {name1.surname} ~ {name2.surname}")

        # Given name comparison
        if name1.given.lower() == name2.given.lower():
            score += self.WEIGHTS["exact_name"] * 0.4
            reasons.append(f"Exact given name match: {name1.given}")
        elif self._soundex(name1.given) == self._soundex(name2.given):
            score += self.WEIGHTS["soundex_match"] * 0.4
            reasons.append(f"Soundex given name match: {name1.given} ~ {name2.given}")
        elif self._is_name_variant(name1.given, name2.given):
            score += self.WEIGHTS["similar_name"]
            reasons.append(f"Name variant match: {name1.given} ~ {name2.given}")

        return score, reasons

    def _score_events(
        self,
        event1: Event,
        event2: Event,
        event_type: str,
    ) -> tuple[float, list[str], list[str]]:
        """Score event similarity."""
        score = 0.0
        reasons = []
        conflicts = []

        if event1.date and event2.date:
            year1 = event1.date.year
            year2 = event2.date.year

            if year1 and year2:
                diff = abs(year1 - year2)

                if diff == 0:
                    score += self.WEIGHTS[f"{event_type}_year_exact"]
                    reasons.append(f"{event_type.title()} year exact match: {year1}")
                elif diff <= 2:
                    score += self.WEIGHTS[f"{event_type}_year_close"]
                    reasons.append(f"{event_type.title()} year close: {year1} vs {year2}")
                elif diff > 10:
                    score += self.CONFLICTS["birth_year_far"] if event_type == "birth" else 0
                    conflicts.append(f"{event_type.title()} years far apart: {year1} vs {year2}")

        if event1.place and event2.place and str(event1.place).lower() == str(event2.place).lower():
            place_weight = self.WEIGHTS.get(f"{event_type}_place", 10)  # Default weight if key missing
            score += place_weight
            reasons.append(f"{event_type.title()} place match: {event1.place}")

        return score, reasons, conflicts

    def _soundex(self, name: str) -> str:
        """Generate Soundex code for a name."""
        if not name:
            return ""

        name = name.upper()
        soundex = name[0]

        # Soundex mapping
        mapping = {
            "B": "1", "F": "1", "P": "1", "V": "1",
            "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
            "D": "3", "T": "3",
            "L": "4",
            "M": "5", "N": "5",
            "R": "6",
        }

        prev_code = mapping.get(name[0], "0")

        for char in name[1:]:
            code = mapping.get(char, "0")
            if code != "0" and code != prev_code:
                soundex += code
                prev_code = code
            if len(soundex) == 4:
                break

        return soundex.ljust(4, "0")

    def _is_name_variant(self, name1: str, name2: str) -> bool:
        """Check if names are common variants of each other."""
        variants = {
            "william": ["bill", "will", "willy", "billy", "liam"],
            "elizabeth": ["beth", "liz", "lizzy", "betty", "eliza", "bessie"],
            "robert": ["bob", "rob", "robbie", "bobby", "bert"],
            "james": ["jim", "jimmy", "jamie"],
            "john": ["jack", "johnny", "jon"],
            "margaret": ["peggy", "maggie", "meg", "marge", "margie"],
            "catherine": ["kate", "katie", "cathy", "kitty", "kathy"],
            "thomas": ["tom", "tommy", "thom"],
            "richard": ["rick", "dick", "rich", "ricky"],
            "joseph": ["joe", "joey", "jo"],
            "mary": ["marie", "maria", "molly", "polly"],
            "anne": ["ann", "anna", "annie", "nan", "nancy"],
            "jean": ["jan", "jane", "jeanne", "joan"],
        }

        n1 = name1.lower()
        n2 = name2.lower()

        for base, var_list in variants.items():
            all_names = [base, *var_list]
            if n1 in all_names and n2 in all_names:
                return True

        return False


class GrampsMerger:
    """
    Handles the merge logic for adding records to Gramps.

    Implements HITL (Human-in-the-Loop) for conflict resolution.
    """

    def __init__(
        self,
        client: GrampsClient,
        strategy: MergeStrategy = MergeStrategy.PROMPT_USER,
        on_conflict: Callable[[Person, MatchResult], str] | None = None,
        projection: SQLiteProjection | None = None,
    ) -> None:
        """
        Initialize merger.

        Args:
            client: GrampsClient instance
            strategy: Default merge strategy
            on_conflict: Callback for conflict resolution (returns "merge", "create", "skip")
        """
        self.client = client
        self.matcher = PersonMatcher(client)
        self.strategy = strategy
        self.on_conflict = on_conflict
        self.projection = projection

    def add_person(
        self,
        person: Person,
        strategy: MergeStrategy | None = None,
    ) -> MergeResult:
        """
        Add a person with intelligent duplicate detection.

        Args:
            person: Person to add
            strategy: Override default strategy

        Returns:
            MergeResult with action taken
        """
        strategy = strategy or self.strategy

        # Delegate to idempotent upsert which enforces fingerprint + matcher rules
        if not self.projection:
            raise RuntimeError("SQLiteProjection is required for idempotent upsert")
        result = upsert_person(self.client, self.projection, person, matcher_factory=lambda c: self.matcher)
        if result.created:
            return MergeResult(action="created", person=person, handle=result.handle, message="Created via upsert")
        return MergeResult(action="merged", person=person, handle=result.handle, message="Reused existing via upsert")

    def _merge_persons(self, new: Person, match: MatchResult) -> MergeResult:
        """Merge new person data into existing record."""
        if not match.matched_person or not match.matched_handle:
            # Can't merge without existing record
            handle = self.client.add_person(new)
            return MergeResult(
                action="created",
                person=new,
                handle=handle,
                message="Could not merge: no existing record found",
            )

        existing = match.matched_person

        # Merge names (add new names that don't exist)
        for name in new.names:
            if not any(self._names_equal(name, n) for n in existing.names):
                existing.names.append(name)

        # Merge events (add if missing)
        if new.birth and not existing.birth:
            existing.birth = new.birth
        if new.death and not existing.death:
            existing.death = new.death

        for event in new.events:
            if not any(self._events_equal(event, e) for e in existing.events):
                existing.events.append(event)

        # Note: We'd need to update the record in Gramps here
        # For now, return merged result
        return MergeResult(
            action="merged",
            person=existing,
            handle=match.matched_handle,
            message=f"Merged with existing record: {existing.display_name}",
        )

    def _names_equal(self, n1: Name, n2: Name) -> bool:
        """Check if two names are effectively equal."""
        return (
            n1.given.lower() == n2.given.lower() and
            n1.surname.lower() == n2.surname.lower()
        )

    def _events_equal(self, e1: Event, e2: Event) -> bool:
        """Check if two events are effectively equal."""
        if e1.event_type != e2.event_type:
            return False
        return not (e1.date and e2.date and e1.date.year != e2.date.year)


# Convenience function for adding persons with duplicate detection
def smart_add_person(
    client: GrampsClient,
    person: Person,
    strategy: MergeStrategy = MergeStrategy.CREATE_NOTE,
) -> MergeResult:
    """
    Add a person with duplicate detection.

    This is the recommended entry point for adding persons
    when duplicate detection is desired.

    Note: This is a synchronous function. For async contexts,
    use asyncio.to_thread() to run off the event loop.
    """
    merger = GrampsMerger(client, strategy)
    return merger.add_person(person)
