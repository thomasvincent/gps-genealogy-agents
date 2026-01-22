"""Pedigree query and result models for genealogical graph traversal.

Provides specialized models for genealogical queries:
- Ancestor/descendant traversal with generation tracking
- Kinship path computation (how are two people related?)
- Family unit reconstruction

Used by the CQRS projection layer for Neo4j queries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field


class RelationshipType(str, Enum):
    """Types of genealogical relationships."""
    FATHER = "father"
    MOTHER = "mother"
    PARENT = "parent"  # Gender unknown
    SON = "son"
    DAUGHTER = "daughter"
    CHILD = "child"  # Gender unknown
    HUSBAND = "husband"
    WIFE = "wife"
    SPOUSE = "spouse"  # Gender unknown
    BROTHER = "brother"
    SISTER = "sister"
    SIBLING = "sibling"  # Gender unknown

    # Extended relationships
    GRANDFATHER = "grandfather"
    GRANDMOTHER = "grandmother"
    GRANDSON = "grandson"
    GRANDDAUGHTER = "granddaughter"
    UNCLE = "uncle"
    AUNT = "aunt"
    NEPHEW = "nephew"
    NIECE = "niece"
    COUSIN = "cousin"

    # Step relationships
    STEPFATHER = "stepfather"
    STEPMOTHER = "stepmother"
    STEPSON = "stepson"
    STEPDAUGHTER = "stepdaughter"


class TraversalDirection(str, Enum):
    """Direction for pedigree traversal."""
    ANCESTORS = "ancestors"  # Go up the tree (parents, grandparents)
    DESCENDANTS = "descendants"  # Go down the tree (children, grandchildren)
    BOTH = "both"  # Both directions


@dataclass
class PersonSummary:
    """Lightweight person summary for traversal results."""
    person_id: UUID
    name: str
    birth_year: int | None = None
    death_year: int | None = None
    gender: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "person_id": str(self.person_id),
            "name": self.name,
            "birth_year": self.birth_year,
            "death_year": self.death_year,
            "gender": self.gender,
        }


@dataclass
class AncestorResult:
    """Single ancestor with generation distance."""
    person: PersonSummary
    generation: int  # 1=parent, 2=grandparent, etc.
    lineage: str  # "paternal", "maternal", or "both"
    relationship_path: list[RelationshipType] = field(default_factory=list)
    confidence: float = 1.0

    @property
    def relationship_label(self) -> str:
        """Human-readable relationship label."""
        if self.generation == 1:
            return "parent"
        elif self.generation == 2:
            return "grandparent"
        elif self.generation == 3:
            return "great-grandparent"
        else:
            greats = self.generation - 2
            return f"{'great-' * greats}grandparent"


@dataclass
class DescendantResult:
    """Single descendant with generation distance."""
    person: PersonSummary
    generation: int  # 1=child, 2=grandchild, etc.
    relationship_path: list[RelationshipType] = field(default_factory=list)
    confidence: float = 1.0

    @property
    def relationship_label(self) -> str:
        """Human-readable relationship label."""
        if self.generation == 1:
            return "child"
        elif self.generation == 2:
            return "grandchild"
        elif self.generation == 3:
            return "great-grandchild"
        else:
            greats = self.generation - 2
            return f"{'great-' * greats}grandchild"


@dataclass
class KinshipResult:
    """Result of kinship computation between two people."""
    person_a: PersonSummary
    person_b: PersonSummary
    relationship: str  # e.g., "first cousin", "second cousin once removed"
    common_ancestors: list[PersonSummary] = field(default_factory=list)
    path_length: int = 0
    path_description: list[str] = field(default_factory=list)
    confidence: float = 1.0

    # Kinship coefficients
    generations_to_common_ancestor_a: int = 0
    generations_to_common_ancestor_b: int = 0

    @property
    def degree_of_relationship(self) -> int:
        """Degree of relationship (sum of generations to common ancestor)."""
        return self.generations_to_common_ancestor_a + self.generations_to_common_ancestor_b

    @property
    def coefficient_of_relationship(self) -> float:
        """Coefficient of relationship (r) - probability of shared alleles.

        Full siblings = 0.5, Half siblings = 0.25, First cousins = 0.125
        """
        if self.degree_of_relationship == 0:
            return 1.0  # Same person
        return 0.5 ** self.degree_of_relationship


class PedigreeQuery(BaseModel):
    """Query for pedigree traversal."""
    root_person_id: UUID
    direction: TraversalDirection = TraversalDirection.ANCESTORS
    max_generations: int = Field(default=4, ge=1, le=20)
    include_spouses: bool = False
    include_siblings: bool = False
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    # Filtering
    include_living: bool = True
    birth_year_range: tuple[int, int] | None = None


class KinshipQuery(BaseModel):
    """Query to find relationship between two people."""
    person_a_id: UUID
    person_b_id: UUID
    max_generations: int = Field(default=8, ge=1, le=20)
    find_all_paths: bool = False  # If True, find all common ancestors


class FamilyUnitQuery(BaseModel):
    """Query to reconstruct a family unit."""
    person_id: UUID
    include_parents: bool = True
    include_children: bool = True
    include_spouse: bool = True
    include_siblings: bool = True


@dataclass
class FamilyUnit:
    """Reconstructed family unit centered on a person."""
    focal_person: PersonSummary
    father: PersonSummary | None = None
    mother: PersonSummary | None = None
    spouses: list[PersonSummary] = field(default_factory=list)
    children: list[PersonSummary] = field(default_factory=list)
    siblings: list[PersonSummary] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Check if family unit has both parents."""
        return self.father is not None and self.mother is not None

    @property
    def family_size(self) -> int:
        """Total number of people in this family unit."""
        count = 1  # focal person
        if self.father:
            count += 1
        if self.mother:
            count += 1
        count += len(self.spouses)
        count += len(self.children)
        count += len(self.siblings)
        return count


class PedigreeResult(BaseModel):
    """Result of a pedigree traversal query."""
    root_person_id: UUID
    direction: TraversalDirection
    generations_found: int = 0
    total_persons: int = 0

    # Results by generation
    ancestors: list[dict] = Field(default_factory=list)  # List of AncestorResult dicts
    descendants: list[dict] = Field(default_factory=list)  # List of DescendantResult dicts

    # Query metadata
    query_time_ms: float = 0.0
    truncated: bool = False  # True if results were limited

    @computed_field
    @property
    def ahnentafel_numbers(self) -> dict[str, int]:
        """Ahnentafel numbering for ancestors.

        Standard genealogical numbering where:
        - 1 = root person
        - 2 = father
        - 3 = mother
        - 2n = father of person n
        - 2n+1 = mother of person n
        """
        numbers = {str(self.root_person_id): 1}

        for ancestor in self.ancestors:
            # This would need to be computed during traversal
            # Placeholder for the concept
            pass

        return numbers


class ProjectionStatus(str, Enum):
    """Status of graph projection sync."""
    SYNCED = "synced"
    SYNCING = "syncing"
    STALE = "stale"
    ERROR = "error"


class ProjectionMetadata(BaseModel):
    """Metadata about the graph projection state."""
    status: ProjectionStatus = ProjectionStatus.STALE
    last_sync_at: datetime | None = None
    ledger_version: int = 0  # Version of source ledger
    projection_version: int = 0  # Version of projection
    total_nodes: int = 0
    total_edges: int = 0
    sync_duration_ms: float = 0.0
    error_message: str | None = None

    @computed_field
    @property
    def is_current(self) -> bool:
        """Check if projection is current with ledger."""
        return (
            self.status == ProjectionStatus.SYNCED and
            self.ledger_version == self.projection_version
        )


class SyncEvent(BaseModel):
    """Event for projection sync tracking."""
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str  # "node_added", "edge_added", "node_updated", etc.
    entity_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    old_version: int = 0
    new_version: int = 0
    changes: dict[str, Any] = Field(default_factory=dict)
