from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IdempotencyBlock(Exception):
    """Raised when an upsert cannot proceed automatically.

    Scenarios:
    - Probable match (0.80–0.95) requires human review
    - Timeline/logic impossible

    Include summaries to aid reviewers.
    """

    reason: str
    match_score: float | None = None
    existing_summary: str | None = None
    proposed_summary: str | None = None
    recommended_action: str = "review"

    def __str__(self) -> str:  # pragma: no cover - human readable
        base = self.reason
        if self.match_score is not None:
            base += f" (score={self.match_score:.2f})"
        return base
