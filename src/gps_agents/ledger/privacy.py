"""Privacy Engine for living person protection.

Implements the 100-Year Rule and other privacy safeguards for genealogical data:
- Assumes individuals are LIVING unless proven otherwise
- Requires death record OR birth date >100 years ago OR age-based heuristics
- Flags PII for encryption at rest when subject is potentially living
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.fact import Fact

logger = logging.getLogger(__name__)


class PrivacyStatus(str, Enum):
    """Privacy classification for a person/fact."""
    LIVING = "living"  # Assume living, restrict access
    DECEASED_VERIFIED = "deceased_verified"  # Death record exists
    DECEASED_PRESUMED = "deceased_presumed"  # >100 years since birth
    UNKNOWN = "unknown"  # Cannot determine, treat as living


class PrivacyViolation(str, Enum):
    """Types of privacy violations."""
    PII_UNREDACTED = "pii_unredacted"
    LIVING_PERSON_EXPOSED = "living_person_exposed"
    INSUFFICIENT_PROTECTION = "insufficient_protection"


@dataclass
class PrivacyCheckResult:
    """Result of privacy check on a fact."""
    status: PrivacyStatus
    is_restricted: bool  # True if PII should be encrypted/redacted
    violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    birth_year: int | None = None
    death_year: int | None = None


@dataclass
class PrivacyConfig:
    """Configuration for privacy engine."""
    # 100-Year Rule: persons born <100 years ago are assumed living
    living_threshold_years: int = 100
    # Maximum plausible lifespan for deceased_presumed status
    max_lifespan_years: int = 120
    # Require explicit death record for unrestricted access
    strict_mode: bool = True
    # PII patterns to detect
    pii_patterns: list[str] = field(default_factory=lambda: [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
        r"\b\d{9}\b",  # SSN without dashes
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
        r"\b\d{10}\b",  # Phone
        r"\(\d{3}\)\s*\d{3}-\d{4}",  # Phone with parens
    ])


class PrivacyEngine:
    """Engine for enforcing privacy rules on genealogical data.

    Implements the 100-Year Rule:
    - Person is LIVING unless:
      1. Death record exists
      2. Birth date is >100 years ago
      3. Age-based heuristics indicate deceased (birth + 120 years)
    """

    def __init__(self, config: PrivacyConfig | None = None):
        """Initialize privacy engine.

        Args:
            config: Privacy configuration (uses defaults if not provided)
        """
        self.config = config or PrivacyConfig()
        self._pii_patterns = [re.compile(p) for p in self.config.pii_patterns]

    def check_fact(self, fact: "Fact", context: dict | None = None) -> PrivacyCheckResult:
        """Check privacy status of a fact.

        Args:
            fact: The fact to check
            context: Optional context with birth/death info

        Returns:
            PrivacyCheckResult with status and recommendations
        """
        context = context or {}
        violations = []
        recommendations = []

        # Extract dates from fact or context
        birth_year = context.get("birth_year")
        death_year = context.get("death_year")

        # Try to extract from fact statement
        if birth_year is None:
            birth_year = self._extract_birth_year(fact)
        if death_year is None:
            death_year = self._extract_death_year(fact)

        # Determine status
        status = self._determine_status(birth_year, death_year)

        # Check for PII in statement
        if self._contains_pii(fact.statement):
            if status in (PrivacyStatus.LIVING, PrivacyStatus.UNKNOWN):
                violations.append(
                    f"PII detected in fact about potentially living person: {fact.fact_id}"
                )
            recommendations.append("Redact or encrypt PII before storage")

        # Set restriction flag
        is_restricted = status in (PrivacyStatus.LIVING, PrivacyStatus.UNKNOWN)

        if is_restricted:
            recommendations.append(
                "Flag for encryption at rest; restrict public access"
            )

        return PrivacyCheckResult(
            status=status,
            is_restricted=is_restricted,
            violations=violations,
            recommendations=recommendations,
            birth_year=birth_year,
            death_year=death_year,
        )

    def _determine_status(
        self, birth_year: int | None, death_year: int | None
    ) -> PrivacyStatus:
        """Determine privacy status based on dates.

        Args:
            birth_year: Year of birth (if known)
            death_year: Year of death (if known)

        Returns:
            PrivacyStatus classification
        """
        current_year = datetime.now(UTC).year

        # If death year is known, person is deceased
        if death_year is not None:
            return PrivacyStatus.DECEASED_VERIFIED

        # If birth year is known, apply rules
        if birth_year is not None:
            years_since_birth = current_year - birth_year

            # Born more than 100 years ago - presumed deceased
            if years_since_birth > self.config.living_threshold_years:
                return PrivacyStatus.DECEASED_PRESUMED

            # Born more than 120 years ago - definitely deceased
            if years_since_birth > self.config.max_lifespan_years:
                return PrivacyStatus.DECEASED_PRESUMED

            # Born within last 100 years - assume living
            return PrivacyStatus.LIVING

        # No date information - default to unknown (treated as living)
        return PrivacyStatus.UNKNOWN

    def _extract_birth_year(self, fact: "Fact") -> int | None:
        """Extract birth year from fact if it's a birth fact."""
        if fact.fact_type != "birth":
            return None

        # Try to find year in statement
        match = re.search(r"\b(1[6-9]\d{2}|20[0-2]\d)\b", fact.statement)
        if match:
            return int(match.group(1))
        return None

    def _extract_death_year(self, fact: "Fact") -> int | None:
        """Extract death year from fact if it's a death fact."""
        if fact.fact_type != "death":
            return None

        # Try to find year in statement
        match = re.search(r"\b(1[6-9]\d{2}|20[0-2]\d)\b", fact.statement)
        if match:
            return int(match.group(1))
        return None

    def _contains_pii(self, text: str) -> bool:
        """Check if text contains PII patterns."""
        for pattern in self._pii_patterns:
            if pattern.search(text):
                return True
        return False

    def should_restrict_fact(
        self,
        fact: "Fact",
        person_birth_year: int | None = None,
        person_death_year: int | None = None,
    ) -> bool:
        """Quick check if a fact should be restricted.

        Args:
            fact: The fact to check
            person_birth_year: Known birth year of the subject
            person_death_year: Known death year of the subject

        Returns:
            True if fact should be restricted/encrypted
        """
        result = self.check_fact(
            fact,
            context={
                "birth_year": person_birth_year,
                "death_year": person_death_year,
            },
        )
        return result.is_restricted

    def get_restriction_reason(
        self,
        fact: "Fact",
        person_birth_year: int | None = None,
        person_death_year: int | None = None,
    ) -> str | None:
        """Get human-readable reason for restriction.

        Returns:
            Reason string if restricted, None if not restricted
        """
        result = self.check_fact(
            fact,
            context={
                "birth_year": person_birth_year,
                "death_year": person_death_year,
            },
        )

        if not result.is_restricted:
            return None

        if result.status == PrivacyStatus.LIVING:
            return (
                f"Subject born {result.birth_year} is within 100-year living "
                f"person threshold"
            )
        elif result.status == PrivacyStatus.UNKNOWN:
            return "Cannot verify deceased status; treating as potentially living"

        return None


# Module-level default instance
_default_engine: PrivacyEngine | None = None


def get_privacy_engine() -> PrivacyEngine:
    """Get or create the default privacy engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = PrivacyEngine()
    return _default_engine


def set_privacy_engine(engine: PrivacyEngine) -> None:
    """Set the default privacy engine."""
    global _default_engine
    _default_engine = engine
