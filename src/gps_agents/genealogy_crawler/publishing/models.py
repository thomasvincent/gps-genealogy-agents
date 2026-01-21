"""Publishing Manager models for GPS-compliant genealogical publishing.

Defines schemas for GPS grading, quorum-based review, integrity validation,
and Paper Trail of Doubt preservation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


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
    graded_at: datetime = Field(default_factory=datetime.utcnow)
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
        """
        score = self.overall_score
        if score >= 9.0:
            return "A"
        elif score >= 8.0:
            return "B"
        elif score >= 7.0:
            return "C"
        elif score >= 6.0:
            return "D"
        else:
            return "F"

    @computed_field
    @property
    def is_publication_ready(self) -> bool:
        """Whether research meets minimum publication standard (Grade C+)."""
        return self.overall_score >= 7.0

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
    """Verdict from a single reviewer."""

    reviewer_type: ReviewerType
    verdict: Verdict
    issues: list[ReviewIssue] = Field(default_factory=list)
    rationale: str = Field(description="Explanation for the verdict")
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    reviewer_model: str = Field(description="Model/version that performed review")


class QuorumDecision(BaseModel):
    """Decision from the dual-reviewer quorum system.

    Both LogicReviewer AND SourceReviewer must PASS for quorum approval.
    Any CRITICAL or HIGH issues from either reviewer block publishing.
    """

    logic_verdict: ReviewVerdict
    source_verdict: ReviewVerdict

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
        """Whether quorum approved (both PASS)."""
        return (
            self.logic_verdict.verdict == Verdict.PASS
            and self.source_verdict.verdict == Verdict.PASS
        )

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
    created_at: datetime = Field(default_factory=datetime.utcnow)
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
    created_at: datetime = Field(default_factory=datetime.utcnow)


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
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Publishing Pipeline Models
# ─────────────────────────────────────────────────────────────────────────────


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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
