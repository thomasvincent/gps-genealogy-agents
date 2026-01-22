"""Publishing Manager models for GPS-compliant genealogical publishing.

Defines schemas for GPS grading, quorum-based review, integrity validation,
and Paper Trail of Doubt preservation.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, computed_field


def _utc_now() -> datetime:
    """Return current UTC time (for use as default_factory)."""
    return datetime.now(UTC)

from .config import CONFIG


class GPSPillar(str, Enum):
    """The five pillars of the Genealogical Proof Standard."""

    REASONABLY_EXHAUSTIVE_SEARCH = "reasonably_exhaustive_search"
    COMPLETE_CITATIONS = "complete_citations"
    ANALYSIS_AND_CORRELATION = "analysis_and_correlation"
    CONFLICT_RESOLUTION = "conflict_resolution"
    WRITTEN_CONCLUSION = "written_conclusion"


class Severity(str, Enum):
    """Severity levels for review issues."""

    CRITICAL = "critical"  # Blocks all publishing
    HIGH = "high"          # Blocks Wikipedia/Wikidata
    MEDIUM = "medium"      # Warning, may block some platforms
    LOW = "low"            # Informational


class PublishingStatus(str, Enum):
    """Status of a publishing pipeline."""

    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    BLOCKED = "blocked"
    PUBLISHED = "published"


class ReviewerType(str, Enum):
    """Types of reviewers in the quorum system."""

    LOGIC_REVIEWER = "logic_reviewer"
    SOURCE_REVIEWER = "source_reviewer"


class Verdict(str, Enum):
    """Review verdict outcomes."""

    PASS = "pass"
    FAIL = "fail"


class PublishingPlatform(str, Enum):
    """Supported publishing platforms."""

    WIKIPEDIA = "wikipedia"
    WIKIDATA = "wikidata"
    WIKITREE = "wikitree"
    GITHUB = "github"


# ─────────────────────────────────────────────────────────────────────────────
# GPS Grade Card Models
# ─────────────────────────────────────────────────────────────────────────────


class GPSPillarScore(BaseModel):
    """Score for a single GPS pillar."""

    pillar: GPSPillar
    score: float = Field(ge=1.0, le=10.0, description="Score from 1-10")
    rationale: str = Field(description="Explanation for the score")
    improvements_needed: list[str] = Field(
        default_factory=list,
        description="Specific improvements to raise the score",
    )


class GPSGradeCard(BaseModel):
    """GPS Grade Card with computed overall score and publication readiness.

    The GPS Grade Card evaluates research against the five GPS pillars
    and determines which platforms the research is ready for.
    """

    subject_id: str = Field(description="ID of the research subject (person)")
    pillar_scores: list[GPSPillarScore] = Field(
        min_length=5,
        max_length=5,
        description="Scores for all 5 GPS pillars",
    )
    graded_at: datetime = Field(default_factory=_utc_now)
    grader_model: str = Field(
        default="gps_grader_llm",
        description="Model/version that performed grading",
    )

    @computed_field
    @property
    def overall_score(self) -> float:
        """Compute overall score as average of pillar scores."""
        if not self.pillar_scores:
            return 0.0
        return sum(ps.score for ps in self.pillar_scores) / len(self.pillar_scores)

    @computed_field
    @property
    def letter_grade(self) -> str:
        """Compute letter grade from overall score.

        A: 9.0-10.0 - Wikipedia, Wikidata, WikiTree, GitHub
        B: 8.0-8.9  - WikiTree, GitHub only
        C: 7.0-7.9  - GitHub only
        D: 6.0-6.9  - Not publishable
        F: <6.0     - Not publishable

        Thresholds configurable via GPS_GRADE_*_THRESHOLD env vars.
        """
        return CONFIG.gps.score_to_grade(self.overall_score)

    @computed_field
    @property
    def is_publication_ready(self) -> bool:
        """Whether research meets minimum publication standard (Grade C+).

        Threshold configurable via GPS_MIN_PUBLISH_SCORE env var.
        """
        return self.overall_score >= CONFIG.min_publication_score

    @computed_field
    @property
    def allowed_platforms(self) -> list[PublishingPlatform]:
        """Platforms this research qualifies for based on grade."""
        grade = self.letter_grade
        if grade == "A":
            return [
                PublishingPlatform.WIKIPEDIA,
                PublishingPlatform.WIKIDATA,
                PublishingPlatform.WIKITREE,
                PublishingPlatform.GITHUB,
            ]
        elif grade == "B":
            return [PublishingPlatform.WIKITREE, PublishingPlatform.GITHUB]
        elif grade == "C":
            return [PublishingPlatform.GITHUB]
        else:
            return []

    def get_pillar_score(self, pillar: GPSPillar) -> Optional[GPSPillarScore]:
        """Get score for a specific pillar."""
        for ps in self.pillar_scores:
            if ps.pillar == pillar:
                return ps
        return None

    def get_lowest_pillar(self) -> Optional[GPSPillarScore]:
        """Get the pillar with the lowest score."""
        if not self.pillar_scores:
            return None
        return min(self.pillar_scores, key=lambda ps: ps.score)


# ─────────────────────────────────────────────────────────────────────────────
# Review and Quorum Models
# ─────────────────────────────────────────────────────────────────────────────


class ReviewIssue(BaseModel):
    """An issue identified during review."""

    severity: Severity
    description: str
    field: Optional[str] = Field(
        default=None,
        description="Specific field or area affected",
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested fix or improvement",
    )


class ReviewVerdict(BaseModel):
    """Verdict from a single reviewer with confidence scoring.

    Confidence scoring enables Bayesian consensus by allowing weighted
    combination of reviewer opinions. Higher confidence indicates stronger
    conviction in the verdict.
    """

    reviewer_type: ReviewerType
    verdict: Verdict
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default_factory=lambda: CONFIG.default_confidence,
        description="Confidence in verdict (0-1). 0.8+ = high, 0.5-0.8 = moderate, <0.5 = low",
    )
    issues: list[ReviewIssue] = Field(default_factory=list)
    rationale: str = Field(description="Explanation for the verdict")
    reviewed_at: datetime = Field(default_factory=_utc_now)
    reviewer_model: str = Field(description="Model/version that performed review")

    @computed_field
    @property
    def weighted_score(self) -> float:
        """Score weighted by confidence (1.0 for PASS, 0.0 for FAIL) * confidence."""
        base_score = 1.0 if self.verdict == Verdict.PASS else 0.0
        return base_score * self.confidence

    @computed_field
    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level.

        Thresholds configurable via QUORUM_HIGH_CONFIDENCE and
        QUORUM_MODERATE_CONFIDENCE env vars.
        """
        return CONFIG.quorum.confidence_level(self.confidence)


class QuorumDecision(BaseModel):
    """Decision from the dual-reviewer quorum system with Bayesian consensus.

    Both LogicReviewer AND SourceReviewer must PASS for quorum approval.
    Any CRITICAL or HIGH issues from either reviewer block publishing.

    Bayesian Consensus:
    - Combines weighted verdicts based on confidence levels
    - Detects disagreement requiring tiebreaker
    - Provides consensus strength metric (0-1)
    """

    logic_verdict: ReviewVerdict
    source_verdict: ReviewVerdict

    # Tiebreaker result (populated after tiebreaker runs)
    tiebreaker_verdict: Optional[ReviewVerdict] = Field(
        default=None,
        description="Verdict from tiebreaker reviewer (if triggered)",
    )
    tiebreaker_reason: Optional[str] = Field(
        default=None,
        description="Why tiebreaker was triggered",
    )

    # Reviewer weights for Bayesian calculation (configurable via env vars)
    logic_weight: float = Field(
        default_factory=lambda: CONFIG.logic_weight,
        ge=0.0,
        le=1.0,
        description="Weight for Logic Reviewer in consensus (0-1). Set via QUORUM_LOGIC_WEIGHT.",
    )
    source_weight: float = Field(
        default_factory=lambda: CONFIG.source_weight,
        ge=0.0,
        le=1.0,
        description="Weight for Source Reviewer in consensus (0-1). Set via QUORUM_SOURCE_WEIGHT.",
    )

    @computed_field
    @property
    def quorum_reached(self) -> bool:
        """Whether both reviewers have provided verdicts."""
        return (
            self.logic_verdict is not None
            and self.source_verdict is not None
        )

    @computed_field
    @property
    def approved(self) -> bool:
        """Whether quorum approved (both PASS or tiebreaker resolves)."""
        # If tiebreaker was used, it determines outcome
        if self.tiebreaker_verdict is not None:
            return self.tiebreaker_verdict.verdict == Verdict.PASS

        # Standard quorum: both must PASS
        return (
            self.logic_verdict.verdict == Verdict.PASS
            and self.source_verdict.verdict == Verdict.PASS
        )

    @computed_field
    @property
    def reviewers_agree(self) -> bool:
        """Whether both reviewers reached the same verdict."""
        return self.logic_verdict.verdict == self.source_verdict.verdict

    @computed_field
    @property
    def needs_tiebreaker(self) -> bool:
        """Whether reviewers disagree and tiebreaker is needed.

        Triggers when:
        1. Verdicts differ (one PASS, one FAIL), OR
        2. Both PASS but confidence is low on one side

        Threshold configurable via QUORUM_TIEBREAKER_THRESHOLD env var.
        """
        if not self.reviewers_agree:
            return self.tiebreaker_verdict is None

        # Also trigger if both PASS but one has low confidence
        if (self.logic_verdict.verdict == Verdict.PASS
            and self.source_verdict.verdict == Verdict.PASS):
            min_confidence = min(
                self.logic_verdict.confidence,
                self.source_verdict.confidence
            )
            if min_confidence < CONFIG.quorum.tiebreaker_threshold:
                return self.tiebreaker_verdict is None

        return False

    @computed_field
    @property
    def consensus_score(self) -> float:
        """Bayesian consensus score (0-1).

        Combines weighted reviewer scores:
        - Logic weighted_score * logic_weight
        - Source weighted_score * source_weight
        - Normalized by total weight
        """
        total_weight = self.logic_weight + self.source_weight
        if total_weight == 0:
            return 0.0

        weighted_sum = (
            self.logic_verdict.weighted_score * self.logic_weight
            + self.source_verdict.weighted_score * self.source_weight
        )
        return weighted_sum / total_weight

    @computed_field
    @property
    def consensus_strength(self) -> str:
        """Human-readable consensus strength."""
        score = self.consensus_score
        if self.reviewers_agree and score >= 0.8:
            return "strong"
        elif self.reviewers_agree and score >= 0.5:
            return "moderate"
        elif not self.reviewers_agree:
            return "disagreement"
        else:
            return "weak"

    @computed_field
    @property
    def blocking_issues(self) -> list[ReviewIssue]:
        """All CRITICAL and HIGH issues that block publishing."""
        blocking = []
        for issue in self.logic_verdict.issues:
            if issue.severity in (Severity.CRITICAL, Severity.HIGH):
                blocking.append(issue)
        for issue in self.source_verdict.issues:
            if issue.severity in (Severity.CRITICAL, Severity.HIGH):
                blocking.append(issue)
        return blocking

    @computed_field
    @property
    def all_issues(self) -> list[ReviewIssue]:
        """All issues from both reviewers."""
        return self.logic_verdict.issues + self.source_verdict.issues


# ─────────────────────────────────────────────────────────────────────────────
# Paper Trail of Doubt Models
# ─────────────────────────────────────────────────────────────────────────────


class ResearchNote(BaseModel):
    """A research note documenting methodology or findings."""

    note_id: str
    subject_id: str
    content: str
    source_refs: list[str] = Field(
        default_factory=list,
        description="References to source records",
    )
    created_at: datetime = Field(default_factory=_utc_now)
    author: str = Field(
        default="system",
        description="Author of the note (system or user)",
    )


class Uncertainty(BaseModel):
    """A documented uncertainty in the research.

    Uncertainties are preserved as part of the Paper Trail of Doubt
    to maintain intellectual honesty about research limitations.
    """

    uncertainty_id: str
    subject_id: str
    field: str = Field(description="Field or claim affected by uncertainty")
    description: str = Field(description="Nature of the uncertainty")
    confidence_level: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in current conclusion (0-1)",
    )
    alternative_interpretations: list[str] = Field(
        default_factory=list,
        description="Other possible interpretations of evidence",
    )
    additional_sources_needed: list[str] = Field(
        default_factory=list,
        description="Sources that could resolve uncertainty",
    )
    created_at: datetime = Field(default_factory=_utc_now)


class UnresolvedConflict(BaseModel):
    """A documented unresolved conflict between sources.

    Conflicts that cannot be definitively resolved are preserved
    as part of the Paper Trail of Doubt.
    """

    conflict_id: str
    subject_id: str
    field: str = Field(description="Field with conflicting values")
    competing_claims: list[dict] = Field(
        description="List of competing claims with source refs",
    )
    analysis_summary: str = Field(
        description="Summary of conflict analysis attempts",
    )
    chosen_value: Optional[str] = Field(
        default=None,
        description="Currently chosen value (if any)",
    )
    chosen_rationale: Optional[str] = Field(
        default=None,
        description="Rationale for chosen value",
    )
    remaining_doubt: str = Field(
        description="Explanation of why conflict remains unresolved",
    )
    created_at: datetime = Field(default_factory=_utc_now)


# ─────────────────────────────────────────────────────────────────────────────
# Publishing Pipeline Models
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Adjudication Gate Models
# ─────────────────────────────────────────────────────────────────────────────


class LedgerStatus(str, Enum):
    """Status for Fact Ledger writes."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISION_REQUIRED = "revision_required"


class PublishDecision(BaseModel):
    """Final adjudication decision from the GPS Adjudication Gate.

    This is the output of the Workflow Agent's adjudication logic,
    determining whether a research bundle can be published.

    GPS Pillar Mapping:
    - Quorum Check → Pillar 4: Resolution of Conflicting Evidence
    - Auto-Downgrade → Pillar 5: Soundly Written Conclusion
    - Search Revision → Pillar 1: Reasonably Exhaustive Research
    """

    decision_id: str = Field(description="Unique decision identifier")
    subject_id: str = Field(description="ID of the research subject")

    # Quorum results
    logic_verdict: Verdict = Field(description="PASS/FAIL from Logic Reviewer")
    source_verdict: Verdict = Field(description="PASS/FAIL from Source Reviewer")

    # Final decision
    is_approved: bool = Field(
        default=False,
        description="Whether research is approved for publishing",
    )

    # Integrity scoring
    integrity_score: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0,
        description="Overall integrity score (0-1)",
    )

    # Platform restrictions
    allowed_platforms: list[PublishingPlatform] = Field(
        default_factory=list,
        description="Platforms approved for publishing",
    )
    blocked_platforms: list[PublishingPlatform] = Field(
        default_factory=list,
        description="Platforms explicitly blocked",
    )

    # Issues tracking
    critical_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="CRITICAL issues that block all publishing",
    )
    high_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="HIGH issues that block Wikipedia/Wikidata",
    )
    medium_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="MEDIUM issues (warnings)",
    )
    low_issues: list[ReviewIssue] = Field(
        default_factory=list,
        description="LOW issues (informational)",
    )

    # Ledger write status
    ledger_status: LedgerStatus = Field(
        default=LedgerStatus.PENDING,
        description="Status for Fact Ledger write",
    )

    # Search revision trigger
    requires_search_revision: bool = Field(
        default=False,
        description="Whether Search Revision Agent should be triggered",
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Evidence identified as missing by GPS Standards Critic",
    )

    # Agent tracking
    agent_responsible: str = Field(
        default="workflow_agent",
        description="Agent that made this decision",
    )

    # Timestamps
    adjudicated_at: datetime = Field(default_factory=_utc_now)

    @computed_field
    @property
    def quorum_passed(self) -> bool:
        """Whether both reviewers passed (quorum condition)."""
        return (
            self.logic_verdict == Verdict.PASS
            and self.source_verdict == Verdict.PASS
        )

    @computed_field
    @property
    def has_blocking_issues(self) -> bool:
        """Whether there are CRITICAL or HIGH issues blocking publishing."""
        return len(self.critical_issues) > 0 or len(self.high_issues) > 0

    @computed_field
    @property
    def total_issues(self) -> int:
        """Total count of all issues."""
        return (
            len(self.critical_issues)
            + len(self.high_issues)
            + len(self.medium_issues)
            + len(self.low_issues)
        )


class SearchRevisionRequest(BaseModel):
    """Request to the Search Revision Agent for additional evidence.

    Generated when the GPS Standards Critic identifies missing evidence
    that would strengthen the research bundle.
    """

    request_id: str = Field(description="Unique request identifier")
    subject_id: str = Field(description="ID of the research subject")
    decision_id: str = Field(description="ID of the PublishDecision that triggered this")

    # Missing evidence details
    missing_sources: list[str] = Field(
        default_factory=list,
        description="Types of sources that should be searched",
    )
    missing_claims: list[str] = Field(
        default_factory=list,
        description="Claims that need additional corroboration",
    )
    search_queries: list[str] = Field(
        default_factory=list,
        description="Suggested search queries",
    )

    # Priority
    priority: str = Field(
        default="normal",
        description="Priority level: critical, high, normal, low",
    )

    # GPS Pillar linkage
    gps_pillar_gaps: list[str] = Field(
        default_factory=list,
        description="GPS pillars with identified gaps",
    )

    created_at: datetime = Field(default_factory=_utc_now)


class PublishingPipeline(BaseModel):
    """Complete publishing pipeline state for a research subject."""

    pipeline_id: str
    subject_id: str
    subject_name: str | None = Field(default=None, description="Name of the research subject")
    status: PublishingStatus = Field(default=PublishingStatus.DRAFT)

    # GPS Grading
    grade_card: Optional[GPSGradeCard] = None

    # Quorum Review
    quorum_decision: Optional[QuorumDecision] = None

    # Paper Trail of Doubt
    research_notes: list[ResearchNote] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)
    unresolved_conflicts: list[UnresolvedConflict] = Field(default_factory=list)

    # Publishing Results
    target_platforms: list[PublishingPlatform] = Field(default_factory=list)
    published_to: list[PublishingPlatform] = Field(default_factory=list)
    publish_errors: dict[str, str] = Field(
        default_factory=dict,
        description="Platform -> error message mapping",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @computed_field
    @property
    def is_blocked(self) -> bool:
        """Whether publishing is blocked by issues."""
        # No grade card means we can't publish
        if not self.grade_card:
            return True
        if not self.grade_card.is_publication_ready:
            return True
        if self.quorum_decision and self.quorum_decision.blocking_issues:
            return True
        return False

    @computed_field
    @property
    def effective_platforms(self) -> list[PublishingPlatform]:
        """Platforms that can actually be published to.

        Intersection of grade-allowed platforms and target platforms,
        minus any blocked by quorum issues.
        """
        if self.is_blocked:
            return []

        if not self.grade_card:
            return []

        allowed = set(self.grade_card.allowed_platforms)

        if self.target_platforms:
            allowed = allowed.intersection(set(self.target_platforms))

        return list(allowed)

    def has_paper_trail(self) -> bool:
        """Whether any Paper Trail of Doubt items exist."""
        return bool(
            self.research_notes
            or self.uncertainties
            or self.unresolved_conflicts
        )
