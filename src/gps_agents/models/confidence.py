"""Confidence scoring models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ConfidenceDelta(BaseModel):
    """Records a change to a fact's confidence score."""

    agent: str = Field(description="Agent that made the adjustment")
    delta: float = Field(description="Change in confidence (+/-)", ge=-1.0, le=1.0)
    previous_score: float = Field(description="Score before adjustment", ge=0.0, le=1.0)
    new_score: float = Field(description="Score after adjustment", ge=0.0, le=1.0)
    reason: str = Field(description="Explanation for the adjustment")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    pillar_affected: int | None = Field(
        default=None, description="GPS pillar that triggered this adjustment (1-5)"
    )


def calculate_confidence(
    base_evidence_type: str,
    source_count: int,
    has_conflicts: bool,
    informant_reliability: str = "unknown",
) -> float:
    """Calculate initial confidence score based on evidence characteristics.

    Args:
        base_evidence_type: 'direct', 'indirect', or 'negative'
        source_count: Number of corroborating sources
        has_conflicts: Whether conflicting evidence exists
        informant_reliability: 'high', 'medium', 'low', or 'unknown'

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Base score from evidence type
    base_scores = {"direct": 0.7, "indirect": 0.5, "negative": 0.3}
    score = base_scores.get(base_evidence_type, 0.4)

    # Boost for multiple sources (diminishing returns)
    if source_count > 1:
        score += min(0.15, 0.05 * (source_count - 1))

    # Penalty for conflicts
    if has_conflicts:
        score -= 0.2

    # Adjust for informant reliability
    reliability_adjustments = {"high": 0.1, "medium": 0.0, "low": -0.1, "unknown": -0.05}
    score += reliability_adjustments.get(informant_reliability, 0.0)

    return max(0.0, min(1.0, score))
