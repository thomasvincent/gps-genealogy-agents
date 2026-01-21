"""Pydantic data layer for The Ancestry Engine.

This module implements the formal Z notation specification as Python models.
All models are validated to maintain the invariants defined in the specification.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# Basic Types (from Z specification)
# =============================================================================

class SourceTier(str, Enum):
    """Source tier classification for permission gating."""
    TIER_0 = "tier_0"  # Free, no auth (WikiTree, FindAGrave, NARA)
    TIER_1 = "tier_1"  # Free, auth required (FamilySearch)
    TIER_2 = "tier_2"  # Paid subscription (Ancestry, MyHeritage)


class AgentType(str, Enum):
    """Agent type identifiers."""
    LEAD = "lead"
    SCOUT = "scout"
    ANALYST = "analyst"
    CENSOR = "censor"


class TaskType(str, Enum):
    """Task type classification."""
    SEARCH = "search"
    ANALYZE = "analyze"
    VERIFY = "verify"
    RESOLVE = "resolve"


class HypothesisStatus(str, Enum):
    """Status of a clue hypothesis."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class EvidenceType(str, Enum):
    """Classification of evidence quality."""
    PRIMARY = "primary"      # Original records created at time of event
    SECONDARY = "secondary"  # Derivative/indexed records
    AUTHORED = "authored"    # User-submitted/compiled genealogies


class Decision(str, Enum):
    """Decision outcomes."""
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"


# =============================================================================
# Source Citation (Z: SourceCitation schema)
# =============================================================================

class SourceCitation(BaseModel):
    """A citation to a genealogical source.

    Z Specification:
    ┌─ SourceCitation ─────────────────────────────────────┐
    │ id : UUID                                            │
    │ repository : TEXT                                    │
    │ tier : TIER                                          │
    │ url : URL                                            │
    │ accessedAt : DATE                                    │
    │ evidenceType : EVIDENCE_TYPE                         │
    │ originalText : ℙ TEXT                                │
    │ confidence : ℝ                                       │
    ├──────────────────────────────────────────────────────┤
    │ 0 ≤ confidence ≤ 1                                   │
    └──────────────────────────────────────────────────────┘
    """
    id: UUID = Field(default_factory=uuid4)
    repository: str
    tier: SourceTier
    url: str | None = None
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence_type: EvidenceType
    original_text: str | None = None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    record_type: str | None = None  # e.g., "census", "birth", "death"
    # Note: confidence range [0,1] is enforced by Field(ge=0.0, le=1.0)


# =============================================================================
# Person (Z: Person schema)
# =============================================================================

class Person(BaseModel):
    """A person in the knowledge graph.

    Z Specification:
    ┌─ Person ─────────────────────────────────────────────┐
    │ id : UUID                                            │
    │ givenName : NAME                                     │
    │ surname : NAME                                       │
    │ birthDate : ℙ DATE                                   │
    │ deathDate : ℙ DATE                                   │
    │ birthPlace : ℙ PLACE                                 │
    │ deathPlace : ℙ PLACE                                 │
    │ parents : ℙ UUID                                     │
    │ spouses : ℙ UUID                                     │
    │ children : ℙ UUID                                    │
    │ sources : ℙ SourceCitation                           │
    ├──────────────────────────────────────────────────────┤
    │ #parents ≤ 2                                         │
    │ id ∉ parents ∪ spouses ∪ children                   │
    └──────────────────────────────────────────────────────┘
    """
    id: UUID = Field(default_factory=uuid4)
    given_name: str
    surname: str
    middle_name: str | None = None

    # Dates can have multiple values (uncertainty)
    birth_dates: list[str] = Field(default_factory=list)  # ISO format or partial
    death_dates: list[str] = Field(default_factory=list)

    # Places can have multiple values (uncertainty)
    birth_places: list[str] = Field(default_factory=list)
    death_places: list[str] = Field(default_factory=list)

    # Relationships (UUIDs of related persons)
    parents: list[UUID] = Field(default_factory=list)
    spouses: list[UUID] = Field(default_factory=list)
    children: list[UUID] = Field(default_factory=list)

    # Evidence
    sources: list[SourceCitation] = Field(default_factory=list)

    # Metadata
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_invariants(self) -> "Person":
        """Validate Z specification invariants."""
        # Invariant: #parents ≤ 2
        if len(self.parents) > 2:
            raise ValueError("A person cannot have more than 2 parents")

        # Invariant: id ∉ parents ∪ spouses ∪ children
        all_relatives = set(self.parents) | set(self.spouses) | set(self.children)
        if self.id in all_relatives:
            raise ValueError("A person cannot be their own relative")

        return self

    @property
    def full_name(self) -> str:
        """Return full name."""
        parts = [self.given_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.surname)
        return " ".join(parts)

    def to_jsonld(self) -> dict[str, Any]:
        """Convert to JSON-LD format compatible with schema.org/Person."""
        result: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Person",
            "@id": f"urn:uuid:{self.id}",
            "givenName": self.given_name,
            "familyName": self.surname,
            "name": self.full_name,
        }

        if self.middle_name:
            result["additionalName"] = self.middle_name

        if self.birth_dates:
            result["birthDate"] = self.birth_dates[0]
        if self.death_dates:
            result["deathDate"] = self.death_dates[0]
        if self.birth_places:
            result["birthPlace"] = {
                "@type": "Place",
                "name": self.birth_places[0],
            }
        if self.death_places:
            result["deathPlace"] = {
                "@type": "Place",
                "name": self.death_places[0],
            }

        if self.parents:
            result["parent"] = [f"urn:uuid:{p}" for p in self.parents]
        if self.spouses:
            result["spouse"] = [f"urn:uuid:{s}" for s in self.spouses]
        if self.children:
            result["children"] = [f"urn:uuid:{c}" for c in self.children]

        return result


# =============================================================================
# Clue Hypothesis (Z: ClueHypothesis schema)
# =============================================================================

class ClueHypothesis(BaseModel):
    """A hypothesis generated by the Analyst for further research.

    Z Specification:
    ┌─ ClueHypothesis ──────────────────────────────────────┐
    │ id : UUID                                             │
    │ statement : TEXT                                      │
    │ targetPerson : ℙ UUID                                 │
    │ suggestedSources : ℙ TEXT                             │
    │ priority : ℝ                                          │
    │ status : HYPOTHESIS_STATUS                            │
    │ generatedBy : AGENT                                   │
    │ evidence : ℙ SourceCitation                           │
    ├───────────────────────────────────────────────────────┤
    │ 0 ≤ priority ≤ 1                                      │
    │ generatedBy = Analyst                                 │
    └───────────────────────────────────────────────────────┘
    """
    id: UUID = Field(default_factory=uuid4)
    statement: str  # e.g., "Find vital records for John Smith"
    target_person: UUID | None = None  # Person this hypothesis relates to
    suggested_sources: list[str] = Field(default_factory=list)
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    status: HypothesisStatus = HypothesisStatus.PENDING
    generated_by: AgentType = AgentType.ANALYST  # Z invariant: always Analyst
    evidence: list[SourceCitation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Hypothesis type for classification
    hypothesis_type: str = "general"  # e.g., "find_vital_records", "search_location", "verify_relationship"

    @field_validator("generated_by")
    @classmethod
    def validate_generated_by(cls, v: AgentType) -> AgentType:
        """Z Invariant: generatedBy = Analyst."""
        if v != AgentType.ANALYST:
            raise ValueError("ClueHypothesis must be generated by Analyst")
        return v


# =============================================================================
# Task (Z: Task schema)
# =============================================================================

class Task(BaseModel):
    """A task to be executed by an agent.

    Z Specification:
    ┌─ Task ────────────────────────────────────────────────┐
    │ id : UUID                                             │
    │ taskType : TASK_TYPE                                  │
    │ priority : ℝ                                          │
    │ assignedTo : ℙ AGENT                                  │
    │ hypothesis : ℙ ClueHypothesis                         │
    │ sourceConstraint : ℙ TIER                             │
    │ completed : 𝔹                                         │
    ├───────────────────────────────────────────────────────┤
    │ 0 ≤ priority ≤ 1                                      │
    │ taskType = SearchTask ⇒ assignedTo = {Scout}          │
    │ taskType = AnalyzeTask ⇒ assignedTo = {Analyst}       │
    └───────────────────────────────────────────────────────┘
    """
    id: UUID = Field(default_factory=uuid4)
    task_type: TaskType
    priority: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    assigned_to: AgentType
    hypothesis: ClueHypothesis | None = None
    source_constraints: list[SourceTier] = Field(default_factory=list)
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Task description and context
    description: str = ""
    query: str | None = None  # Search query if applicable
    target_person: UUID | None = None

    @model_validator(mode="after")
    def validate_assignment(self) -> "Task":
        """Validate task type implies correct agent assignment."""
        if self.task_type == TaskType.SEARCH and self.assigned_to != AgentType.SCOUT:
            raise ValueError("Search tasks must be assigned to Scout")
        if self.task_type == TaskType.ANALYZE and self.assigned_to != AgentType.ANALYST:
            raise ValueError("Analyze tasks must be assigned to Analyst")
        return self


# =============================================================================
# Log Entry (Z: LogEntry schema)
# =============================================================================

class LogEntry(BaseModel):
    """An entry in the research log.

    Z Specification:
    ┌─ LogEntry ────────────────────────────────────────────┐
    │ id : UUID                                             │
    │ timestamp : DATE                                      │
    │ agent : AGENT                                         │
    │ actionType : TEXT                                     │
    │ rationale : TEXT                                      │
    │ context : TEXT                                        │
    │ revisitReason : ℙ TEXT                                │
    ├───────────────────────────────────────────────────────┤
    │ actionType = "revisit" ⇒ revisitReason ≠ ∅           │
    └───────────────────────────────────────────────────────┘
    """
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: AgentType
    action_type: str  # e.g., "search", "analyze", "revisit", "compliance_check"
    rationale: str
    context: str | None = None  # Additional context (source name, etc.)
    revisit_reason: list[str] = Field(default_factory=list)

    # Additional metadata
    task_id: UUID | None = None
    hypothesis_id: UUID | None = None
    source_accessed: str | None = None
    records_found: int = 0
    success: bool = True
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_revisit_reason(self) -> "LogEntry":
        """Z Invariant: actionType = "revisit" ⇒ revisitReason ≠ ∅."""
        if self.action_type == "revisit" and not self.revisit_reason:
            raise ValueError("Revisit actions must have a documented reason")
        return self


# =============================================================================
# Source Permission (Z: sourcePermissions)
# =============================================================================

class SourcePermissions(BaseModel):
    """Source tier permissions configuration.

    Z Invariant: sourcePermissions(Tier0) = true
    """
    tier_0_enabled: bool = True  # Always true per Z spec
    tier_1_enabled: bool = False
    tier_1_token: str | None = None
    tier_2_enabled: bool = False
    tier_2_credentials: dict[str, str] = Field(default_factory=dict)

    @field_validator("tier_0_enabled")
    @classmethod
    def validate_tier_0(cls, v: bool) -> bool:
        """Z Invariant: Tier 0 is always enabled."""
        if not v:
            raise ValueError("Tier 0 sources must always be enabled")
        return True

    def is_tier_allowed(self, tier: SourceTier) -> bool:
        """Check if a tier is allowed."""
        if tier == SourceTier.TIER_0:
            return True
        elif tier == SourceTier.TIER_1:
            return self.tier_1_enabled
        elif tier == SourceTier.TIER_2:
            return self.tier_2_enabled
        return False


# =============================================================================
# Ancestry Engine State (Z: AncestryEngineState schema)
# =============================================================================

class AncestryEngineState(BaseModel):
    """The complete state of the Ancestry Engine.

    Z Specification:
    ┌─ AncestryEngineState ─────────────────────────────────┐
    │ knowledgeGraph : UUID ⇸ Person                        │
    │ frontierQueue : seq Task                              │
    │ completedTasks : ℙ Task                               │
    │ hypotheses : ℙ ClueHypothesis                         │
    │ researchLog : seq LogEntry                            │
    │ sourcePermissions : TIER → 𝔹                          │
    │ activeAgent : ℙ AGENT                                 │
    │ terminated : 𝔹                                        │
    ├───────────────────────────────────────────────────────┤
    │ ∀ t : ran frontierQueue • ¬ t.completed               │
    │ ∀ t : completedTasks • t.completed                    │
    │ sourcePermissions(Tier0) = true                       │
    │ terminated ⇒ frontierQueue = ⟨⟩                       │
    └───────────────────────────────────────────────────────┘
    """
    # Session metadata
    session_id: UUID = Field(default_factory=uuid4)
    query: str = ""
    seed_person: Person | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Core state
    knowledge_graph: dict[str, Person] = Field(default_factory=dict)  # UUID string -> Person
    frontier_queue: list[Task] = Field(default_factory=list)
    completed_tasks: list[Task] = Field(default_factory=list)
    hypotheses: list[ClueHypothesis] = Field(default_factory=list)
    research_log: list[LogEntry] = Field(default_factory=list)

    # Permissions
    source_permissions: SourcePermissions = Field(default_factory=SourcePermissions)

    # Runtime state
    active_agent: AgentType | None = None
    terminated: bool = False
    termination_reason: str | None = None

    # Configuration
    max_iterations: int = 500
    max_log_entries: int = 10000

    @model_validator(mode="after")
    def validate_invariants(self) -> "AncestryEngineState":
        """Validate Z specification invariants."""
        # Invariant: ∀ t : ran frontierQueue • ¬ t.completed
        for task in self.frontier_queue:
            if task.completed:
                raise ValueError("Frontier queue cannot contain completed tasks")

        # Invariant: ∀ t : completedTasks • t.completed
        for task in self.completed_tasks:
            if not task.completed:
                raise ValueError("Completed tasks must be marked as completed")

        # Invariant: terminated ⇒ frontierQueue = ⟨⟩
        if self.terminated and self.frontier_queue:
            raise ValueError("Terminated state must have empty frontier queue")

        return self

    def add_person(self, person: Person) -> None:
        """Add a person to the knowledge graph."""
        self.knowledge_graph[str(person.id)] = person

    def get_person(self, person_id: UUID | str) -> Person | None:
        """Get a person from the knowledge graph."""
        return self.knowledge_graph.get(str(person_id))

    def add_task(self, task: Task) -> None:
        """Add a task to the frontier queue, maintaining priority order."""
        if task.completed:
            raise ValueError("Cannot add completed task to frontier")
        self.frontier_queue.append(task)
        self.frontier_queue.sort(key=lambda t: t.priority, reverse=True)

    def pop_task(self) -> Task | None:
        """Pop the highest priority task from the frontier."""
        if not self.frontier_queue:
            return None
        return self.frontier_queue.pop(0)

    def complete_task(self, task: Task) -> None:
        """Mark a task as completed."""
        task.completed = True
        if task in self.frontier_queue:
            self.frontier_queue.remove(task)
        self.completed_tasks.append(task)

    def add_hypothesis(self, hypothesis: ClueHypothesis) -> None:
        """Add a hypothesis."""
        self.hypotheses.append(hypothesis)

    def add_log_entry(self, entry: LogEntry) -> None:
        """Add an entry to the research log."""
        self.research_log.append(entry)

    def to_jsonld(self) -> dict[str, Any]:
        """Export the knowledge graph as JSON-LD."""
        return {
            "@context": "https://schema.org",
            "@graph": [
                person.to_jsonld() for person in self.knowledge_graph.values()
            ],
            "dateCreated": self.started_at.isoformat(),
            "name": f"Genealogy Research: {self.query}",
        }


# =============================================================================
# Raw Record (intermediate representation from sources)
# =============================================================================

class RawRecord(BaseModel):
    """A raw record extracted by the Scout before analysis."""
    id: UUID = Field(default_factory=uuid4)
    source: str
    source_tier: SourceTier
    url: str | None = None
    record_type: str  # e.g., "census", "birth", "death", "marriage"
    raw_data: dict[str, Any] = Field(default_factory=dict)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Extracted entities (populated by Analyst)
    extracted_names: list[str] = Field(default_factory=list)
    extracted_dates: list[str] = Field(default_factory=list)
    extracted_places: list[str] = Field(default_factory=list)


# =============================================================================
# Conflict (for Analyst conflict resolution)
# =============================================================================

class ConflictingClaim(BaseModel):
    """A conflicting claim to be resolved by the Analyst."""
    claim: str
    source: SourceCitation
    weight: float = 0.0  # Calculated weight based on evidence type and tier

    def calculate_weight(self) -> float:
        """Calculate weight per Z specification:
        weight = evidenceWeight(src.evidenceType) × tierWeight(src.tier) × src.confidence
        """
        evidence_weights = {
            EvidenceType.PRIMARY: 1.0,
            EvidenceType.SECONDARY: 0.7,
            EvidenceType.AUTHORED: 0.4,
        }
        tier_weights = {
            SourceTier.TIER_0: 0.8,
            SourceTier.TIER_1: 0.9,
            SourceTier.TIER_2: 1.0,
        }
        self.weight = (
            evidence_weights.get(self.source.evidence_type, 0.5) *
            tier_weights.get(self.source.tier, 0.8) *
            self.source.confidence
        )
        return self.weight


class ConflictResolution(BaseModel):
    """Result of conflict resolution by the Analyst."""
    person_id: UUID
    field: str  # e.g., "birth_date", "death_place"
    conflicting_claims: list[ConflictingClaim]
    resolved_claim: ConflictingClaim
    rationale: str
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
