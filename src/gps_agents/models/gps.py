"""GPS (Genealogical Proof Standard) evaluation models."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PillarStatus(str, Enum):
    """Status of a GPS pillar evaluation."""

    SATISFIED = "satisfied"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"


class Conflict(BaseModel):
    """Represents a conflict between sources or facts."""

    conflict_id: str = Field(description="Unique identifier for this conflict")
    description: str = Field(description="Description of the conflict")
    sources_involved: list[str] = Field(description="Source citation IDs involved")
    fact_ids_involved: list[str] = Field(default_factory=list, description="Related fact IDs")
    resolution: str | None = Field(default=None, description="How the conflict was resolved")
    resolution_reasoning: str | None = Field(
        default=None, description="Explanation of why this resolution is preferred"
    )
    is_resolved: bool = Field(default=False)


class GPSEvaluation(BaseModel):
    """Complete GPS evaluation for a fact."""

    # Pillar 1: Reasonably Exhaustive Search
    pillar_1: PillarStatus = Field(default=PillarStatus.PENDING)
    sources_searched: list[str] = Field(
        default_factory=list, description="Repositories that were searched"
    )
    sources_missing: list[str] = Field(
        default_factory=list, description="Major source classes NOT yet checked"
    )
    search_exhaustive: bool = Field(default=False)
    pillar_1_notes: str | None = Field(default=None)

    # Pillar 2: Complete & Accurate Citations
    pillar_2: PillarStatus = Field(default=PillarStatus.PENDING)
    citations_valid: bool = Field(default=False)
    evidence_explained_compliant: bool = Field(
        default=False, description="Citations follow Evidence Explained standards"
    )
    citation_issues: list[str] = Field(default_factory=list)
    pillar_2_notes: str | None = Field(default=None)

    # Pillar 3: Analysis & Correlation
    pillar_3: PillarStatus = Field(default=PillarStatus.PENDING)
    evidence_correlation: str | None = Field(
        default=None, description="How sources corroborate each other"
    )
    informant_reliability: dict[str, str] = Field(
        default_factory=dict, description="Source ID → reliability assessment"
    )
    analysis_complete: bool = Field(default=False)
    pillar_3_notes: str | None = Field(default=None)

    # Pillar 4: Conflict Resolution
    pillar_4: PillarStatus = Field(default=PillarStatus.PENDING)
    conflicts_identified: list[Conflict] = Field(default_factory=list)
    conflicts_resolved: bool = Field(default=True)  # True if no conflicts OR all resolved
    resolution_reasoning: str | None = Field(default=None)
    pillar_4_notes: str | None = Field(default=None)

    # Pillar 5: Written Conclusion
    pillar_5: PillarStatus = Field(default=PillarStatus.PENDING)
    proof_summary: str | None = Field(
        default=None, description="Written proof argument/narrative"
    )
    pillar_5_notes: str | None = Field(default=None)

    def all_satisfied(self) -> bool:
        """Check if all pillars are satisfied."""
        return all(
            getattr(self, f"pillar_{i}") == PillarStatus.SATISFIED for i in range(1, 6)
        )

    def get_failed_pillars(self) -> list[int]:
        """Return list of pillar numbers that have failed."""
        return [
            i
            for i in range(1, 6)
            if getattr(self, f"pillar_{i}") == PillarStatus.FAILED
        ]

    def get_pending_pillars(self) -> list[int]:
        """Return list of pillar numbers still pending evaluation."""
        return [
            i
            for i in range(1, 6)
            if getattr(self, f"pillar_{i}") == PillarStatus.PENDING
        ]

    def suggest_confidence_delta(self) -> float:
        """Suggest confidence adjustment based on GPS evaluation."""
        delta = 0.0

        # Penalties for failed pillars
        failed = self.get_failed_pillars()
        delta -= 0.15 * len(failed)

        # Penalties for partial pillars
        for i in range(1, 6):
            if getattr(self, f"pillar_{i}") == PillarStatus.PARTIAL:
                delta -= 0.05

        # Bonus for all satisfied
        if self.all_satisfied():
            delta += 0.1

        return max(-0.5, min(0.2, delta))
