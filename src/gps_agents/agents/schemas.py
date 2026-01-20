"""Agent pipeline schemas for GPS-compliant genealogical research.

Defines JSON schema contracts between agents in the agentic architecture:
- SearchPlan: Query planning with budgets and source ranking
- ExecutionResult: Results from source execution
- EntityClusters: Grouped person entities
- EvidenceScore: Evidence verification scoring
- Synthesis: Final synthesized output
- RunTrace: Full execution trace for observability
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Agent roles in the pipeline."""
    PLANNER = "planner"
    EXECUTOR = "executor"
    RESOLVER = "resolver"
    VERIFIER = "verifier"
    SYNTHESIZER = "synthesizer"
    BUDGET_POLICY = "budget_policy"
    MANAGER = "manager"


class TraceEventType(str, Enum):
    """Types of events in the run trace."""
    PLAN_CREATED = "plan_created"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    SOURCE_SEARCHED = "source_searched"
    SOURCE_FAILED = "source_failed"
    ENTITIES_RESOLVED = "entities_resolved"
    EVIDENCE_VERIFIED = "evidence_verified"
    SYNTHESIS_COMPLETED = "synthesis_completed"
    BUDGET_CHECK = "budget_check"
    ERROR = "error"


# ─────────────────────────────────────────────────────────────────────────────
# SearchPlan Schema
# ─────────────────────────────────────────────────────────────────────────────


class SourceBudget(BaseModel):
    """Budget allocation for a single source."""
    source_name: str
    priority: int = Field(default=5, ge=0, le=10, description="Priority score (0=lowest, 10=highest)")
    max_results: int = Field(default=50, ge=1)
    timeout_seconds: float = Field(default=30.0, ge=1.0)
    retry_count: int = Field(default=2, ge=0)


class SearchPlan(BaseModel):
    """Query plan with budgets and source ranking.

    Created by QueryPlannerAgent, consumed by SourceExecutor.
    """
    plan_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Query parameters
    surname: str
    surname_variants: list[str] = Field(default_factory=list)
    given_name: str | None = None
    birth_year: int | None = None
    birth_year_range: int = Field(default=5, ge=0, le=20)
    birth_place: str | None = None
    death_year: int | None = None
    record_types: list[str] = Field(default_factory=list)
    region: str | None = None

    # Budget and source configuration
    source_budgets: list[SourceBudget] = Field(default_factory=list)
    total_budget_seconds: float = Field(default=120.0, ge=10.0)
    max_total_results: int = Field(default=200, ge=1)

    # Two-pass configuration
    first_pass_enabled: bool = Field(default=True)
    first_pass_source_limit: int = Field(default=5)
    second_pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # Guardrails
    require_surname: bool = Field(default=True)
    min_identifiers: int = Field(default=1, ge=1)

    def get_sources_by_priority(self) -> list[str]:
        """Get source names ordered by priority (highest first)."""
        sorted_budgets = sorted(self.source_budgets, key=lambda b: -b.priority)
        return [b.source_name for b in sorted_budgets]


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionResult Schema
# ─────────────────────────────────────────────────────────────────────────────


class SourceExecutionResult(BaseModel):
    """Result from executing a search on a single source."""
    source_name: str
    success: bool
    records: list[dict] = Field(default_factory=list)
    total_count: int = 0
    search_time_ms: float = 0.0
    error: str | None = None
    error_type: str | None = None
    retry_count: int = 0


class ExecutionResult(BaseModel):
    """Combined results from SourceExecutor.

    Produced by SourceExecutor, consumed by EntityResolverAgent.
    """
    execution_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    plan_id: str
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Results by source
    source_results: list[SourceExecutionResult] = Field(default_factory=list)

    # Aggregated records
    all_records: list[dict] = Field(default_factory=list)
    total_records: int = 0

    # Execution stats
    sources_searched: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    total_execution_time_ms: float = 0.0

    # Pass information
    pass_number: int = Field(default=1, ge=1)
    confidence_after_pass: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def success_rate(self) -> float:
        """Calculate source success rate."""
        total = len(self.sources_searched) + len(self.sources_failed)
        if total == 0:
            return 0.0
        return len(self.sources_searched) / total


# ─────────────────────────────────────────────────────────────────────────────
# EntityClusters Schema
# ─────────────────────────────────────────────────────────────────────────────


class ResolvedEntity(BaseModel):
    """A resolved person entity from clustered records."""
    entity_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    fingerprint: str

    # Best estimate fields
    best_name: str | None = None
    best_birth_year: int | None = None
    best_birth_place: str | None = None
    best_death_year: int | None = None
    best_death_place: str | None = None

    # Source records
    record_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    record_count: int = 0
    source_count: int = 0

    # Confidence
    cluster_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    corroboration_boost: float = Field(default=0.0, ge=0.0, le=0.5)


class EntityClusters(BaseModel):
    """Grouped person entities from record clustering.

    Produced by EntityResolverAgent, consumed by EvidenceVerifierAgent.
    """
    resolver_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    execution_id: str
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Resolved entities
    entities: list[ResolvedEntity] = Field(default_factory=list)

    # Unresolved records (couldn't cluster)
    unresolved_record_ids: list[str] = Field(default_factory=list)

    # Stats
    total_input_records: int = 0
    total_entities: int = 0
    multi_source_entities: int = 0  # Entities with 2+ sources


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceScore Schema
# ─────────────────────────────────────────────────────────────────────────────


class FieldEvidence(BaseModel):
    """Evidence evaluation for a single field."""
    field_name: str

    # All values found
    values: list[dict] = Field(default_factory=list)  # [{value, source, confidence, source_type}]

    # Best value selection
    best_value: Any = None
    consensus_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Classification
    is_contested: bool = False
    is_consensus: bool = False


class EvidenceScore(BaseModel):
    """Evidence verification scores for an entity.

    Produced by EvidenceVerifierAgent, consumed by SynthesisAgent.
    """
    verifier_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    entity_id: str
    verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Field-level evidence
    field_evidence: list[FieldEvidence] = Field(default_factory=list)

    # Overall scores
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    gps_compliance_score: float = Field(default=0.0, ge=0.0, le=1.0)  # GPS standards adherence

    # Evidence classification
    direct_evidence_count: int = 0
    indirect_evidence_count: int = 0
    negative_evidence_count: int = 0

    # Source quality
    original_source_count: int = 0
    derivative_source_count: int = 0
    authored_source_count: int = 0

    # Flags
    requires_human_review: bool = False
    review_reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Synthesis Schema
# ─────────────────────────────────────────────────────────────────────────────


class ContestedFieldOutput(BaseModel):
    """A field with conflicting evidence in final output."""
    field: str
    best_value: Any
    alternative_values: list[dict] = Field(default_factory=list)  # [{value, source, confidence}]
    consensus_score: float
    resolution_method: str | None = None  # How conflict was resolved


class Synthesis(BaseModel):
    """Final synthesized output from the agent pipeline.

    Produced by SynthesisAgent, returned to caller.
    """
    synthesis_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    entity_id: str
    synthesized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Best estimate (GPS Pillar 4)
    best_estimate: dict = Field(default_factory=dict)

    # Supporting evidence
    supporting_citations: list[str] = Field(default_factory=list)

    # Contested fields
    contested_fields: list[ContestedFieldOutput] = Field(default_factory=list)

    # Consensus fields
    consensus_fields: list[str] = Field(default_factory=list)

    # Confidence
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Next steps recommendations
    next_steps: list[str] = Field(default_factory=list)

    # GPS compliance
    gps_compliant: bool = False
    gps_notes: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# RunTrace Schema
# ─────────────────────────────────────────────────────────────────────────────


class TraceEvent(BaseModel):
    """A single event in the run trace."""
    event_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: TraceEventType
    agent_role: AgentRole

    # Event data
    message: str
    data: dict = Field(default_factory=dict)

    # Timing
    duration_ms: float | None = None

    # Error info
    error: str | None = None


class RunTrace(BaseModel):
    """Full execution trace for observability.

    Maintained by Manager, returned with final result.
    """
    trace_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    # Input
    original_query: dict = Field(default_factory=dict)

    # Events
    events: list[TraceEvent] = Field(default_factory=list)

    # Intermediate artifacts
    search_plan: SearchPlan | None = None
    execution_result: ExecutionResult | None = None
    entity_clusters: EntityClusters | None = None
    evidence_scores: list[EvidenceScore] = Field(default_factory=list)

    # Final output
    synthesis: Synthesis | None = None

    # Aggregated stats
    total_duration_ms: float = 0.0
    total_sources_searched: int = 0
    total_records_found: int = 0
    total_entities_resolved: int = 0

    # Status
    success: bool = False
    error: str | None = None

    def add_event(
        self,
        event_type: TraceEventType,
        agent_role: AgentRole,
        message: str,
        data: dict | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> TraceEvent:
        """Add an event to the trace."""
        event = TraceEvent(
            event_type=event_type,
            agent_role=agent_role,
            message=message,
            data=data or {},
            duration_ms=duration_ms,
            error=error,
        )
        self.events.append(event)
        return event

    def finalize(self, success: bool, error: str | None = None) -> None:
        """Finalize the trace with completion status."""
        self.completed_at = datetime.now(UTC)
        self.success = success
        self.error = error

        if self.started_at and self.completed_at:
            self.total_duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000


# ─────────────────────────────────────────────────────────────────────────────
# Manager Response Schema
# ─────────────────────────────────────────────────────────────────────────────


class ManagerResponse(BaseModel):
    """Response from the Manager orchestrating the agent pipeline."""

    # Primary output
    synthesis: Synthesis | None = None

    # All entities found (if multiple)
    all_syntheses: list[Synthesis] = Field(default_factory=list)

    # Execution trace
    trace: RunTrace

    # Status
    success: bool = False
    error: str | None = None

    # Requires human input
    requires_human_decision: bool = False
    decision_context: dict | None = None
