"""Unified configuration for publishing thresholds and settings.

All hardcoded thresholds are centralized here for maintainability and
environment-based override support.

Environment Variables:
    GPS_GRADE_A_THRESHOLD: Minimum score for Grade A (default 9.0)
    GPS_GRADE_B_THRESHOLD: Minimum score for Grade B (default 8.0)
    GPS_GRADE_C_THRESHOLD: Minimum score for Grade C (default 7.0)
    GPS_GRADE_D_THRESHOLD: Minimum score for Grade D (default 6.0)
    GPS_MIN_PUBLISH_SCORE: Minimum score for any publishing (default 7.0)

    QUORUM_LOGIC_WEIGHT: Weight for Logic Reviewer (default 0.5)
    QUORUM_SOURCE_WEIGHT: Weight for Source Reviewer (default 0.5)
    QUORUM_HIGH_CONFIDENCE: Threshold for "high" confidence (default 0.8)
    QUORUM_MODERATE_CONFIDENCE: Threshold for "moderate" confidence (default 0.5)
    QUORUM_TIEBREAKER_THRESHOLD: When to trigger tiebreaker (default 0.5)

    REVIEWER_DEFAULT_CONFIDENCE: Default confidence for verdicts (default 0.8)
    FACT_MIN_ACCEPTANCE_CONFIDENCE: Min confidence for fact acceptance (default 0.9)

    PRIVACY_LIVING_PERSON_YEARS: Years for 100-year rule (default 100)

Example:
    >>> from gps_agents.genealogy_crawler.publishing.config import CONFIG
    >>> CONFIG.grade_a_threshold
    9.0
    >>> # Override via environment
    >>> import os
    >>> os.environ["GPS_GRADE_A_THRESHOLD"] = "9.5"
    >>> # Reload config if needed
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _f(name: str, default: float) -> float:
    """Parse float from environment variable with fallback."""
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    """Parse int from environment variable with fallback."""
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


@dataclass(frozen=True)
class GPSGradingConfig:
    """GPS Grade thresholds and publication eligibility."""

    # Letter grade thresholds (inclusive lower bound)
    grade_a_threshold: float = _f("GPS_GRADE_A_THRESHOLD", 9.0)
    grade_b_threshold: float = _f("GPS_GRADE_B_THRESHOLD", 8.0)
    grade_c_threshold: float = _f("GPS_GRADE_C_THRESHOLD", 7.0)
    grade_d_threshold: float = _f("GPS_GRADE_D_THRESHOLD", 6.0)

    # Minimum score for any publishing (Grade C or better)
    min_publication_score: float = _f("GPS_MIN_PUBLISH_SCORE", 7.0)

    # Individual pillar passing threshold
    pillar_passing_threshold: float = _f("GPS_PILLAR_PASSING_THRESHOLD", 7.0)

    def score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= self.grade_a_threshold:
            return "A"
        elif score >= self.grade_b_threshold:
            return "B"
        elif score >= self.grade_c_threshold:
            return "C"
        elif score >= self.grade_d_threshold:
            return "D"
        else:
            return "F"

    def grade_allows_publishing(self, grade: str) -> bool:
        """Check if grade allows any publishing."""
        return grade in ("A", "B", "C")


@dataclass(frozen=True)
class QuorumConfig:
    """Quorum consensus weights and thresholds."""

    # Reviewer weights for Bayesian consensus
    logic_weight: float = _f("QUORUM_LOGIC_WEIGHT", 0.5)
    source_weight: float = _f("QUORUM_SOURCE_WEIGHT", 0.5)

    # Confidence level thresholds
    high_confidence_threshold: float = _f("QUORUM_HIGH_CONFIDENCE", 0.8)
    moderate_confidence_threshold: float = _f("QUORUM_MODERATE_CONFIDENCE", 0.5)

    # Tiebreaker trigger threshold (consensus below this triggers tiebreaker)
    tiebreaker_threshold: float = _f("QUORUM_TIEBREAKER_THRESHOLD", 0.5)

    # Minimum consensus for approval without tiebreaker
    min_consensus_for_approval: float = _f("QUORUM_MIN_CONSENSUS", 0.6)

    def confidence_level(self, confidence: float) -> str:
        """Convert confidence score to human-readable level."""
        if confidence >= self.high_confidence_threshold:
            return "high"
        elif confidence >= self.moderate_confidence_threshold:
            return "moderate"
        else:
            return "low"

    def needs_tiebreaker(
        self,
        logic_pass: bool,
        source_pass: bool,
        min_confidence: float,
    ) -> bool:
        """Determine if tiebreaker is needed based on reviewer results."""
        # Disagreement always triggers tiebreaker
        if logic_pass != source_pass:
            return True
        # Low confidence on both passing triggers tiebreaker
        if logic_pass and source_pass and min_confidence < self.tiebreaker_threshold:
            return True
        return False


@dataclass(frozen=True)
class ReviewerConfig:
    """Reviewer-specific thresholds and defaults."""

    # Default confidence when not explicitly set
    default_confidence: float = _f("REVIEWER_DEFAULT_CONFIDENCE", 0.8)

    # Minimum confidence for fact acceptance in LinguistLLM
    fact_acceptance_min_confidence: float = _f("FACT_MIN_ACCEPTANCE_CONFIDENCE", 0.9)

    # Media agent confidence thresholds
    media_high_confidence: float = _f("MEDIA_HIGH_CONFIDENCE", 0.9)
    media_moderate_confidence: float = _f("MEDIA_MODERATE_CONFIDENCE", 0.7)

    # Tiebreaker reviewer default confidence
    tiebreaker_default_confidence: float = _f("TIEBREAKER_DEFAULT_CONFIDENCE", 0.7)


@dataclass(frozen=True)
class PrivacyConfig:
    """Privacy engine configuration (100-year rule)."""

    # Years since birth to presume deceased (100-year rule)
    living_person_years: int = _i("PRIVACY_LIVING_PERSON_YEARS", 100)

    # Age at which person is definitely deceased (safety margin)
    max_lifespan_years: int = _i("PRIVACY_MAX_LIFESPAN", 120)

    # Minimum age for death record to be considered (avoid infant deaths flagging)
    min_death_age_for_privacy_lift: int = _i("PRIVACY_MIN_DEATH_AGE", 0)


@dataclass(frozen=True)
class PlatformEligibilityConfig:
    """Platform-specific publishing requirements."""

    # Minimum grades for each platform
    # Format: (min_grade, [platforms])
    platform_grade_requirements: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
        ("A", ("WIKIPEDIA", "WIKIDATA", "WIKITREE", "GITHUB")),
        ("B", ("WIKITREE", "GITHUB")),
        ("C", ("GITHUB",)),
    )

    def allowed_platforms(self, grade: str) -> List[str]:
        """Get list of allowed platforms for a grade."""
        for min_grade, platforms in self.platform_grade_requirements:
            if grade == min_grade:
                return list(platforms)
        return []


@dataclass(frozen=True)
class PublishingConfig:
    """Unified publishing configuration combining all sub-configs."""

    gps: GPSGradingConfig = GPSGradingConfig()
    quorum: QuorumConfig = QuorumConfig()
    reviewer: ReviewerConfig = ReviewerConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    platform: PlatformEligibilityConfig = PlatformEligibilityConfig()

    # Shortcut properties for commonly used values
    @property
    def grade_a_threshold(self) -> float:
        return self.gps.grade_a_threshold

    @property
    def grade_b_threshold(self) -> float:
        return self.gps.grade_b_threshold

    @property
    def grade_c_threshold(self) -> float:
        return self.gps.grade_c_threshold

    @property
    def grade_d_threshold(self) -> float:
        return self.gps.grade_d_threshold

    @property
    def min_publication_score(self) -> float:
        return self.gps.min_publication_score

    @property
    def default_confidence(self) -> float:
        return self.reviewer.default_confidence

    @property
    def logic_weight(self) -> float:
        return self.quorum.logic_weight

    @property
    def source_weight(self) -> float:
        return self.quorum.source_weight

    @property
    def living_person_years(self) -> int:
        return self.privacy.living_person_years


# Global singleton for easy access
CONFIG = PublishingConfig()


# Export individual configs for targeted imports
GPS_CONFIG = CONFIG.gps
QUORUM_CONFIG = CONFIG.quorum
REVIEWER_CONFIG = CONFIG.reviewer
PRIVACY_CONFIG = CONFIG.privacy
PLATFORM_CONFIG = CONFIG.platform
