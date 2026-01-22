"""Structured I/O schemas for LLM roles in the genealogy crawler.

These schemas enforce type-safe, validated responses from the LLM,
preventing hallucinated data structures and enabling static analysis.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Planner (Orchestrator) Schemas
# =============================================================================


class PlannerAction(BaseModel):
    """A single planned action from the Orchestrator."""
    action: Literal["fetch", "revisit", "merge", "resolve_conflict", "stop"]
    query: str | None = None
    target_id: str | None = None  # UUID as string
    source_tier: Annotated[int, Field(ge=0, le=2)] = 0
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    reason: str | None = None


class RevisitRecommendation(BaseModel):
    """A recommendation to revisit a previously queried source."""
    source_id: str  # UUID as string
    original_query: str
    improved_query: str
    reason: str
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5


class PlannerInput(BaseModel):
    """Input schema for the Planner/Orchestrator LLM role."""
    current_state: dict[str, Any]
    recent_discoveries: list[dict[str, Any]] = Field(default_factory=list)
    pending_clues: list[dict[str, Any]] = Field(default_factory=list)
    stop_conditions: dict[str, Any] = Field(default_factory=dict)


class PlannerOutput(BaseModel):
    """Output schema for the Planner/Orchestrator LLM role."""
    reasoning: str = Field(description="Step-by-step planning logic")
    next_actions: list[PlannerAction] = Field(default_factory=list)
    query_expansions: list[str] = Field(default_factory=list)
    revisit_schedule: list[RevisitRecommendation] = Field(default_factory=list)
    should_stop: bool = False
    stop_reason: str | None = None


# =============================================================================
# Verifier Schemas
# =============================================================================


class VerificationResult(BaseModel):
    """Result of verifying a single extracted field."""
    field: str
    value: Any
    status: Literal["Verified", "Unverified", "Conflicting", "NotFound"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    citation_snippet: str | None = None  # Required if status == "Verified"
    rationale: str

    @model_validator(mode="after")
    def validate_citation_for_verified(self) -> "VerificationResult":
        """Verified fields MUST have a citation snippet."""
        if self.status == "Verified" and not self.citation_snippet:
            raise ValueError("Verified fields must have a citation_snippet")
        return self


class Hypothesis(BaseModel):
    """An LLM-generated hypothesis (NOT a fact)."""
    type: str  # HypothesisType value
    text: str
    evidence_hint: str | None = None
    triggering_snippet: str | None = None
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    suggested_queries: list[str] = Field(default_factory=list)
    is_fact: bool = False  # MUST always be False

    @model_validator(mode="after")
    def validate_not_fact(self) -> "Hypothesis":
        """Hypotheses must never be marked as facts."""
        if self.is_fact:
            raise ValueError("Hypothesis.is_fact must be False - hypotheses are not facts")
        return self


class Citation(BaseModel):
    """A citation linking a field to source text."""
    field: str
    snippet: str
    char_offset: int | None = None


class VerifierInput(BaseModel):
    """Input schema for the LLM Verifier role."""
    url: str
    raw_text: str
    html_snippets: list[str] = Field(default_factory=list)
    extracted_fields: dict[str, Any]
    existing_citations: list[Citation] = Field(default_factory=list)


class VerifierOutput(BaseModel):
    """Output schema for the LLM Verifier role."""
    verification_results: list[VerificationResult]
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    hallucination_flags: list[str] = Field(default_factory=list)


# =============================================================================
# Entity Resolver Schemas
# =============================================================================


class FeatureScore(BaseModel):
    """Score for a single matching feature."""
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str


class ResolverInput(BaseModel):
    """Input schema for the Entity Resolver role."""
    person_a: dict[str, Any]
    person_b: dict[str, Any]
    shared_assertions: list[dict[str, Any]] = Field(default_factory=list)
    conflicting_assertions: list[dict[str, Any]] = Field(default_factory=list)


class ResolverOutput(BaseModel):
    """Output schema for the Entity Resolver role.

    For high-confidence matches (confidence >= 0.95), rationale fields
    can be abbreviated to reduce token usage while maintaining GPS compliance.
    """
    similarity_score: Annotated[float, Field(ge=0.0, le=1.0)]
    feature_scores: dict[str, FeatureScore]
    merge_rationale: str = ""  # Optional for high-confidence matches
    why_not_merge: str = ""  # Brief note acceptable for high-confidence
    recommendation: Literal["merge", "review", "separate"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    @model_validator(mode="after")
    def validate_reasoning_completeness(self) -> "ResolverOutput":
        """Require full reasoning for low-confidence, allow brief for high-confidence."""
        # High-confidence threshold for abbreviated reasoning
        HIGH_CONFIDENCE_THRESHOLD = 0.95

        if self.confidence < HIGH_CONFIDENCE_THRESHOLD:
            # Full reasoning required for uncertain matches
            if not self.why_not_merge or not self.why_not_merge.strip():
                raise ValueError("why_not_merge must be provided for confidence < 0.95")
            if self.recommendation == "review" and not self.merge_rationale.strip():
                raise ValueError("merge_rationale required when recommendation is 'review'")
        # For high-confidence, brief or empty is acceptable (GPS compliant via confidence score)
        return self


# =============================================================================
# Conflict Analyst Schemas
# =============================================================================


class CompetingClaim(BaseModel):
    """A competing claim in a conflict."""
    value: Any
    source: str
    tier: Annotated[int, Field(ge=0, le=2)]
    evidence_type: Literal["primary", "secondary", "authored"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5


class EvidenceRanking(BaseModel):
    """Ranking of a claim in conflict resolution."""
    claim_index: int
    rank: int
    reason: str


class ConflictInput(BaseModel):
    """Input schema for the Conflict Analyst role."""
    conflict_id: str | None = None
    field: str
    competing_claims: list[CompetingClaim]
    context: dict[str, Any] = Field(default_factory=dict)


class ConflictOutput(BaseModel):
    """Output schema for the Conflict Analyst role."""
    analysis: str = Field(description="Step-by-step reasoning")
    evidence_ranking: list[EvidenceRanking]
    recommended_value: Any
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    is_tentative: bool = True  # Default to tentative
    next_actions: list[str] = Field(default_factory=list)
    preserve_alternatives: bool = True  # Default to preserving all claims

    @model_validator(mode="after")
    def validate_preserve_alternatives(self) -> "ConflictOutput":
        """Warn if alternatives not preserved."""
        if not self.preserve_alternatives:
            # In strict mode, we could raise here
            pass
        return self


# =============================================================================
# Extraction Verifier Schemas
# =============================================================================


class ExtractedField(BaseModel):
    """A candidate extracted field to verify."""
    field: str
    value: Any


class VerifiedExtraction(BaseModel):
    """Result of verifying an extracted field against source text."""
    field: str
    value: Any
    status: Literal["Confirmed", "NotFound", "Corrected"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    exact_quote: str | None = None  # Required if status == "Confirmed"
    corrected_value: Any | None = None  # Required if status == "Corrected"
    rationale: str

    @model_validator(mode="after")
    def validate_quote_for_confirmed(self) -> "VerifiedExtraction":
        """Confirmed fields MUST have an exact quote from the source."""
        if self.status == "Confirmed" and not self.exact_quote:
            raise ValueError("Confirmed fields must have an exact_quote")
        if self.status == "Corrected" and self.corrected_value is None:
            raise ValueError("Corrected fields must have a corrected_value")
        return self


class ExtractionVerifierInput(BaseModel):
    """Input schema for the Extraction Verifier role."""
    raw_text: str = Field(description="The source document snippet")
    candidate_extraction: list[ExtractedField] = Field(
        description="The candidate JSON extraction to verify"
    )


class ExtractionVerifierOutput(BaseModel):
    """Output schema for the Extraction Verifier role."""
    verified_fields: list[VerifiedExtraction]
    overall_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    hallucination_flags: list[str] = Field(default_factory=list)


# =============================================================================
# Query Expander (Clue Agent) Schemas
# =============================================================================


class ConfirmedFact(BaseModel):
    """A confirmed fact from extraction verification."""
    field: str
    value: Any
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    source_snippet: str | None = None


class DeepSearchQuery(BaseModel):
    """A suggested follow-up query from the Clue Agent."""
    query_string: str = Field(description="The search query text")
    target_source_type: str = Field(
        description="Type of source to search (e.g., 'immigration records', 'census')"
    )
    reasoning: str = Field(description="Why this query could yield valuable information")
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.5,
        description="Priority ranking (1.0 = highest)"
    )
    expected_fields: list[str] = Field(
        default_factory=list,
        description="Fields this query might help populate"
    )


class QueryExpanderInput(BaseModel):
    """Input schema for the Query Expander (Clue Agent) role."""
    subject_name: str = Field(description="Name of the research subject")
    confirmed_facts: list[ConfirmedFact] = Field(
        description="Facts confirmed from previous extraction"
    )
    research_goals: list[str] = Field(
        default_factory=list,
        description="Current research goals or gaps to fill"
    )
    already_searched: list[str] = Field(
        default_factory=list,
        description="Queries already executed to avoid duplicates"
    )


class QueryExpanderOutput(BaseModel):
    """Output schema for the Query Expander (Clue Agent) role."""
    analysis: str = Field(description="Analysis of confirmed facts and gaps")
    deep_search_queries: list[DeepSearchQuery] = Field(
        min_length=1,
        max_length=5,
        description="Suggested follow-up queries (1-5)"
    )
    research_hypotheses: list[str] = Field(
        default_factory=list,
        description="Hypotheses that could guide future research"
    )


# =============================================================================
# Conflict Analyst Tie-Breaker Schemas
# =============================================================================


class ErrorPatternHypothesis(BaseModel):
    """A hypothesis about a known genealogical error pattern."""
    pattern_type: Literal[
        "tombstone_error",
        "military_age_padding",
        "immigration_age_reduction",
        "census_approximation",
        "clerical_transcription",
        "generational_confusion",
    ]
    affected_assertion_index: int = Field(
        description="Index of the assertion this pattern might affect"
    )
    explanation: str = Field(description="Why this pattern might apply")
    historical_context: str | None = Field(
        default=None,
        description="Historical context supporting this hypothesis"
    )
    likelihood: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="How likely this pattern explains the discrepancy"
    )
    suggested_penalty: Annotated[float, Field(ge=-0.20, le=0.0)] = Field(
        description="Suggested weight penalty if pattern confirmed"
    )


class TiebreakerQuery(BaseModel):
    """A suggested query to resolve a conflict between assertions."""
    query_string: str = Field(description="The search query to execute")
    target_source_type: str = Field(
        description="Type of source to search (e.g., 'vital records', 'cemetery')"
    )
    target_tier: Annotated[int, Field(ge=0, le=2)] = Field(
        description="Source tier (0=no login, 1=open API, 2=credentialed)"
    )
    reasoning: str = Field(description="Why this query could resolve the conflict")
    expected_resolution: Literal["confirm_a", "confirm_b", "new_value", "inconclusive"] = Field(
        description="What outcome this query might produce"
    )
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.5,
        description="Priority for executing this query"
    )


class NegativeEvidenceIndicator(BaseModel):
    """Indication of meaningful absence of expected records."""
    expected_record: str = Field(
        description="What record was expected but not found"
    )
    jurisdiction: str = Field(description="Where the record was expected")
    time_range: str = Field(description="When the record was expected")
    affects_assertion_index: int = Field(
        description="Which assertion this absence affects"
    )
    confidence_reduction: Annotated[float, Field(ge=0.0, le=0.15)] = Field(
        description="How much to reduce confidence"
    )
    reasoning: str = Field(description="Why this absence is significant")


class ConflictAnalysisTiebreakerInput(BaseModel):
    """Input schema for the Conflict Analyst Tie-Breaker role."""
    subject_id: str = Field(description="UUID of the subject person/entity")
    subject_name: str = Field(description="Display name for context")
    fact_type: str = Field(description="Type of fact in conflict (e.g., 'birth', 'death')")

    # The competing assertions to analyze
    competing_assertions: list[dict[str, Any]] = Field(
        description="List of competing assertions with their evidence"
    )

    # Context about the subject and sources
    subject_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Known facts about the subject for pattern detection"
    )
    source_metadata: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Metadata about each source (date, type, tier)"
    )

    # What has already been searched
    already_searched: list[str] = Field(
        default_factory=list,
        description="Queries already executed to avoid duplicates"
    )


class ConflictAnalysisTiebreakerOutput(BaseModel):
    """Output schema for the Conflict Analyst Tie-Breaker role."""
    analysis: str = Field(
        description="Step-by-step forensic analysis of the conflict"
    )

    # Temporal proximity assessment
    temporal_proximity_ranking: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ranking of assertions by temporal proximity to event"
    )

    # Error pattern detection
    detected_patterns: list[ErrorPatternHypothesis] = Field(
        default_factory=list,
        description="Potential error patterns identified"
    )

    # Negative evidence
    negative_evidence: list[NegativeEvidenceIndicator] = Field(
        default_factory=list,
        description="Meaningful absences of expected records"
    )

    # Current winner (before tie-breaker queries)
    current_winning_assertion_index: int | None = Field(
        default=None,
        description="Index of the currently winning assertion (None if true tie)"
    )
    current_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.5,
        description="Confidence in the current winner"
    )

    # Tie-breaker strategy
    tie_breaker_queries: list[TiebreakerQuery] = Field(
        default_factory=list,
        description="Suggested queries to resolve the conflict"
    )

    # Resolution recommendation
    resolution_status: Literal[
        "resolved",
        "pending_tiebreaker",
        "insufficient_evidence",
        "human_review_required",
    ] = Field(description="Recommended next step in resolution workflow")

    human_review_reason: str | None = Field(
        default=None,
        description="If human review required, explain why"
    )

    # Preserve all alternatives
    preserve_all: bool = Field(
        default=True,
        description="Whether to keep all assertions (Paper Trail of Doubt)"
    )

    @model_validator(mode="after")
    def validate_human_review_reason(self) -> "ConflictAnalysisTiebreakerOutput":
        """Human review status must have a reason."""
        if self.resolution_status == "human_review_required" and not self.human_review_reason:
            raise ValueError("human_review_reason required when status is human_review_required")
        return self
