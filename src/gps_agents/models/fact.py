"""Core Fact model - the central entity of the genealogical research system."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field
from uuid_utils import uuid7 as _uuid7

from .confidence import ConfidenceDelta
from .gps import GPSEvaluation
from .provenance import Provenance
from .source import SourceCitation


def uuid7() -> UUID:
    """Generate a UUID7 compatible with stdlib UUID."""
    return UUID(str(_uuid7()))


class FactStatus(str, Enum):
    """Status of a fact in the research lifecycle."""

    PROPOSED = "proposed"  # Newly discovered, not yet validated
    ACCEPTED = "accepted"  # Passed all GPS pillars
    REJECTED = "rejected"  # Failed validation or contradicted
    INCOMPLETE = "incomplete"  # Missing required sources or information


class Annotation(BaseModel):
    """An annotation or note attached to a fact."""

    annotation_id: str = Field(default_factory=lambda: str(uuid7()))
    author: str = Field(description="Agent or user who added this")
    content: str
    annotation_type: str = Field(default="note", description="note, warning, question, etc.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Fact(BaseModel):
    """An immutable, versioned genealogical fact.

    Facts are the core unit of the system. They are append-only and versioned,
    meaning updates create new versions rather than modifying existing ones.
    """

    fact_id: UUID = Field(default_factory=uuid7)
    version: int = Field(default=1, ge=1)
    statement: str = Field(description="The factual claim, e.g., 'John Smith born 1842'")

    # Evidence chain
    sources: list[SourceCitation] = Field(default_factory=list)
    provenance: Provenance

    # Confidence tracking
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_history: list[ConfidenceDelta] = Field(default_factory=list)

    # Status and evaluation
    status: FactStatus = Field(default=FactStatus.PROPOSED)
    gps_evaluation: GPSEvaluation | None = Field(default=None)

    # Metadata
    annotations: list[Annotation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    related_fact_ids: list[UUID] = Field(
        default_factory=list, description="Other facts this one relates to"
    )
    supersedes_fact_id: UUID | None = Field(
        default=None, description="If this is a correction, the fact it replaces"
    )

    # Subject identification
    person_id: str | None = Field(
        default=None, description="Identifier for the person this fact is about"
    )
    fact_type: str = Field(
        default="general",
        description="birth, death, marriage, residence, occupation, etc.",
    )

    def apply_confidence_delta(self, delta: ConfidenceDelta) -> Fact:
        """Create a new version of this fact with adjusted confidence.

        Returns a new Fact instance (facts are immutable).
        """
        new_score = max(0.0, min(1.0, self.confidence_score + delta.delta))
        delta_with_scores = delta.model_copy(
            update={"previous_score": self.confidence_score, "new_score": new_score}
        )

        return self.model_copy(
            update={
                "version": self.version + 1,
                "confidence_score": new_score,
                "confidence_history": [*self.confidence_history, delta_with_scores],
                "updated_at": datetime.now(UTC),
            }
        )

    def add_source(self, source: SourceCitation) -> Fact:
        """Create a new version with an additional source."""
        return self.model_copy(
            update={
                "version": self.version + 1,
                "sources": [*self.sources, source],
                "updated_at": datetime.now(UTC),
            }
        )

    def set_status(self, status: FactStatus) -> Fact:
        """Create a new version with updated status."""
        return self.model_copy(
            update={
                "version": self.version + 1,
                "status": status,
                "updated_at": datetime.now(UTC),
            }
        )

    def add_annotation(self, annotation: Annotation) -> Fact:
        """Create a new version with an additional annotation."""
        return self.model_copy(
            update={
                "version": self.version + 1,
                "annotations": [*self.annotations, annotation],
                "updated_at": datetime.now(UTC),
            }
        )

    def can_accept(self) -> bool:
        """Check if this fact meets criteria for ACCEPTED status."""
        if self.gps_evaluation is None:
            return False
        return self.gps_evaluation.all_satisfied() and self.confidence_score >= 0.7

    def needs_revision(self) -> bool:
        """Check if this fact requires additional research."""
        return self.confidence_score < 0.7 or (
            self.gps_evaluation is not None
            and len(self.gps_evaluation.get_failed_pillars()) > 0
        )

    def ledger_key(self) -> str:
        """Generate the RocksDB key for this fact version."""
        return f"{self.fact_id}:{self.version}"
