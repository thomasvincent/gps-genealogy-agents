"""Probabilistic Linkage models for GPS-compliant entity resolution.

Implements Fellegi-Sunter model concepts with Pydantic schemas for:
- Pairwise comparisons with feature-level match weights
- Clustering decisions with reversibility support
- Full provenance for GPS Pillar 4 (Conflict Resolution)
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


# =============================================================================
# Enums
# =============================================================================


class ComparisonType(str, Enum):
    """Type of field comparison in record linkage."""

    EXACT = "exact"  # Exact string match
    JARO_WINKLER = "jaro_winkler"  # Edit distance for names
    SOUNDEX = "soundex"  # Phonetic encoding
    DAMERAU_LEVENSHTEIN = "damerau_levenshtein"  # Edit with transpositions
    NUMERIC_DISTANCE = "numeric_distance"  # For years, ages
    ARRAY_INTERSECTION = "array_intersection"  # For name variants
    NULL_HANDLING = "null_handling"  # Special handling for missing data


class MatchConfidence(str, Enum):
    """Confidence level for a linkage decision."""

    DEFINITE_MATCH = "definite_match"  # >0.95 probability
    PROBABLE_MATCH = "probable_match"  # 0.85-0.95
    POSSIBLE_MATCH = "possible_match"  # 0.70-0.85
    UNCERTAIN = "uncertain"  # 0.50-0.70
    PROBABLE_NON_MATCH = "probable_non_match"  # 0.20-0.50
    DEFINITE_NON_MATCH = "definite_non_match"  # <0.20


class ClusterDecision(str, Enum):
    """Decision for a cluster merge operation."""

    MERGE = "merge"  # Records represent same person
    NO_MERGE = "no_merge"  # Records are different people
    NEEDS_REVIEW = "needs_review"  # Human review required
    SPLIT = "split"  # Previously merged records should be separated


# =============================================================================
# Feature Comparison
# =============================================================================


class FeatureComparison(BaseModel):
    """Result of comparing a single feature between two records.

    Implements Fellegi-Sunter partial match weights.
    """

    feature_name: str = Field(description="Name of the compared field")
    comparison_type: ComparisonType

    # Values compared
    value_left: Any = Field(description="Value from record 1")
    value_right: Any = Field(description="Value from record 2")

    # Fellegi-Sunter weights
    similarity_score: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="Raw similarity (0-1)"
    )
    match_weight: float = Field(
        description="Log-likelihood ratio for match (m/u ratio)"
    )
    non_match_weight: float = Field(
        description="Log-likelihood ratio for non-match"
    )

    # GPS audit trail
    rationale: str | None = Field(
        default=None,
        description="Explanation of the comparison result",
    )

    @computed_field
    @property
    def is_match(self) -> bool:
        """Whether this feature comparison is a match (>0.8 similarity)."""
        return self.similarity_score >= 0.8

    @computed_field
    @property
    def contributes_evidence(self) -> bool:
        """Whether this comparison provides meaningful evidence."""
        return self.value_left is not None and self.value_right is not None


# =============================================================================
# Match Candidate
# =============================================================================


class MatchCandidate(BaseModel):
    """A potential match between two records.

    Generated during the comparison phase before clustering decisions.
    """

    candidate_id: UUID = Field(default_factory=uuid4)

    # Record identifiers
    record_id_left: UUID = Field(description="First record ID")
    record_id_right: UUID = Field(description="Second record ID")

    # Identification hints for debugging
    name_left: str | None = Field(default=None)
    name_right: str | None = Field(default=None)

    # Comparison results
    feature_comparisons: list[FeatureComparison] = Field(default_factory=list)

    # Aggregate scores
    overall_probability: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="Probability that records represent the same entity"
    )
    confidence: MatchConfidence

    # Blocking info
    blocking_key: str | None = Field(
        default=None,
        description="Key used to block these records together",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def match_weight_sum(self) -> float:
        """Sum of match weights from all feature comparisons."""
        return sum(fc.match_weight for fc in self.feature_comparisons)

    @computed_field
    @property
    def non_match_weight_sum(self) -> float:
        """Sum of non-match weights from all feature comparisons."""
        return sum(fc.non_match_weight for fc in self.feature_comparisons)

    @computed_field
    @property
    def feature_summary(self) -> dict[str, float]:
        """Summary of feature comparison results."""
        return {
            fc.feature_name: fc.similarity_score
            for fc in self.feature_comparisons
        }

    def get_strongest_evidence(self) -> list[FeatureComparison]:
        """Get features that most strongly support the match."""
        return sorted(
            [fc for fc in self.feature_comparisons if fc.contributes_evidence],
            key=lambda fc: fc.match_weight,
            reverse=True,
        )[:3]


# =============================================================================
# Linkage Provenance
# =============================================================================


class LinkageProvenance(BaseModel):
    """Full provenance for a linkage decision (GPS Pillar 4 compliance)."""

    provenance_id: UUID = Field(default_factory=uuid4)

    # Algorithm info
    algorithm: str = Field(
        default="splink",
        description="Algorithm used for linkage",
    )
    algorithm_version: str = Field(default="3.0.0")
    model_name: str | None = Field(
        default=None,
        description="Specific model configuration name",
    )

    # Thresholds used
    match_threshold: float = Field(
        description="Probability threshold for match decision"
    )
    review_threshold: float | None = Field(
        default=None,
        description="Threshold below which human review is requested",
    )

    # Blocking strategy
    blocking_rules: list[str] = Field(
        default_factory=list,
        description="SQL-like blocking rules used",
    )

    # Training info (if model was trained)
    training_labels_count: int | None = Field(default=None)
    em_iterations: int | None = Field(
        default=None,
        description="EM algorithm iterations for weight estimation",
    )

    # Execution
    records_compared: int = Field(default=0)
    candidates_generated: int = Field(default=0)
    matches_found: int = Field(default=0)

    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int | None = None


# =============================================================================
# Linkage Decision
# =============================================================================


class LinkageDecision(BaseModel):
    """A final linkage decision for a pair of records.

    This is the output of the entity resolver, documenting why
    two records were (or were not) merged.
    """

    decision_id: UUID = Field(default_factory=uuid4)

    # Records involved
    record_id_left: UUID
    record_id_right: UUID

    # Decision
    decision: ClusterDecision
    probability: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence: MatchConfidence

    # Supporting evidence
    match_candidate: MatchCandidate | None = Field(
        default=None,
        description="The candidate comparison that led to this decision",
    )

    # GPS Pillar 4: Conflict Resolution audit
    conflicts_identified: list[str] = Field(
        default_factory=list,
        description="Conflicting values between records",
    )
    conflict_resolution: str | None = Field(
        default=None,
        description="How conflicts were resolved",
    )

    # Reversibility
    is_reversible: bool = Field(
        default=True,
        description="Whether this merge can be undone",
    )
    reversal_reason: str | None = Field(
        default=None,
        description="Reason for reversal if split",
    )

    # Agent attribution
    decided_by: str = Field(
        default="splink_resolver",
        description="Agent that made this decision",
    )

    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def is_merge(self) -> bool:
        """Whether this decision results in a merge."""
        return self.decision == ClusterDecision.MERGE

    @computed_field
    @property
    def needs_human_review(self) -> bool:
        """Whether human review is needed."""
        return self.decision == ClusterDecision.NEEDS_REVIEW


# =============================================================================
# Entity Cluster
# =============================================================================


class EntityCluster(BaseModel):
    """A cluster of records representing the same entity.

    After resolution, all records in a cluster are believed to
    represent the same real-world person.
    """

    cluster_id: UUID = Field(default_factory=uuid4)

    # Canonical representation
    canonical_id: UUID = Field(
        description="ID of the canonical record for this cluster"
    )
    canonical_name: str = Field(
        description="Canonical name for display"
    )

    # Member records
    member_ids: list[UUID] = Field(
        default_factory=list,
        description="All record IDs in this cluster",
    )

    # Merge history
    linkage_decisions: list[LinkageDecision] = Field(
        default_factory=list,
        description="Decisions that formed this cluster",
    )

    # Cluster quality
    internal_cohesion: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.0,
        description="Average pairwise similarity within cluster",
    )
    has_conflicts: bool = Field(
        default=False,
        description="Whether cluster contains unresolved conflicts",
    )

    # Best values (resolved from multiple records)
    best_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Best value for each field across records",
    )
    value_sources: dict[str, UUID] = Field(
        default_factory=dict,
        description="Which record provided each best value",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def size(self) -> int:
        """Number of records in this cluster."""
        return len(self.member_ids)

    @computed_field
    @property
    def is_singleton(self) -> bool:
        """Whether cluster has only one record."""
        return len(self.member_ids) == 1

    def add_member(
        self,
        record_id: UUID,
        decision: LinkageDecision,
    ) -> None:
        """Add a record to this cluster with the linkage decision."""
        if record_id not in self.member_ids:
            self.member_ids.append(record_id)
        self.linkage_decisions.append(decision)
        self.updated_at = datetime.now(UTC)


# =============================================================================
# Linkage Result
# =============================================================================

T = TypeVar("T", bound=BaseModel)


class LinkageResult(BaseModel, Generic[T]):
    """Result of an entity resolution operation.

    Wraps clusters with full provenance for GPS compliance.
    """

    success: bool
    error: str | None = None

    # Output clusters
    clusters: list[EntityCluster] = Field(default_factory=list)

    # Statistics
    total_records_input: int = Field(default=0)
    total_clusters_output: int = Field(default=0)
    singleton_clusters: int = Field(default=0)
    merged_records: int = Field(default=0)

    # Review queue
    needs_review: list[MatchCandidate] = Field(
        default_factory=list,
        description="Candidates requiring human review",
    )

    # Provenance
    provenance: LinkageProvenance

    @computed_field
    @property
    def reduction_ratio(self) -> float:
        """How much the record count was reduced by merging."""
        if self.total_records_input == 0:
            return 0.0
        return 1 - (self.total_clusters_output / self.total_records_input)

    @classmethod
    def success_result(
        cls,
        clusters: list[EntityCluster],
        provenance: LinkageProvenance,
        needs_review: list[MatchCandidate] | None = None,
    ) -> "LinkageResult":
        """Create a successful linkage result."""
        provenance.completed_at = datetime.now(UTC)
        if provenance.started_at:
            delta = provenance.completed_at - provenance.started_at
            provenance.duration_ms = int(delta.total_seconds() * 1000)

        total_input = sum(c.size for c in clusters)
        singletons = sum(1 for c in clusters if c.is_singleton)
        merged = total_input - len(clusters)

        provenance.matches_found = merged

        return cls(
            success=True,
            clusters=clusters,
            total_records_input=total_input,
            total_clusters_output=len(clusters),
            singleton_clusters=singletons,
            merged_records=merged,
            needs_review=needs_review or [],
            provenance=provenance,
        )

    @classmethod
    def failure_result(
        cls,
        error: str,
        provenance: LinkageProvenance,
    ) -> "LinkageResult":
        """Create a failed linkage result."""
        provenance.completed_at = datetime.now(UTC)
        return cls(
            success=False,
            error=error,
            provenance=provenance,
        )
