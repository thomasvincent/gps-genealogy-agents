"""Workflow Agent - orchestrates the research process."""

import json
from datetime import UTC, datetime
from typing import Any

from uuid_utils import uuid7

from ..models.confidence import ConfidenceDelta
from ..models.fact import Annotation, Fact, FactStatus
from ..models.gps import GPSEvaluation
from ..models.provenance import Provenance, ProvenanceSource
from .base import BaseAgent


class WorkflowAgent(BaseAgent):
    """The Workflow Agent owns the research lifecycle.

    ONLY agent allowed to:
    - Write to the Fact Ledger
    - Apply confidence deltas
    - Set final Fact status
    """

    name = "workflow"
    prompt_file = "workflow_agent.txt"
    default_provider = "anthropic"

    def __init__(self, ledger=None, projection=None, **kwargs):
        """Initialize workflow agent.

        Args:
            ledger: FactLedger instance
            projection: SQLiteProjection instance
        """
        super().__init__(**kwargs)
        self.ledger = ledger
        self.projection = projection
        self.max_retries = 2

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process workflow state and make decisions.

        Args:
            state: Current workflow state

        Returns:
            Updated state with decisions
        """
        task = state.get("task", "")
        proposed_facts = state.get("proposed_facts", [])
        critic_feedback = state.get("critic_feedback", {})
        retry_count = state.get("retry_count", 0)

        # Build context for LLM decision
        context = {
            "task": task,
            "proposed_fact_count": len(proposed_facts),
            "retry_count": retry_count,
            "max_retries": self.max_retries,
        }

        if critic_feedback:
            context["standards_feedback"] = critic_feedback.get("standards", {})
            context["reasoning_feedback"] = critic_feedback.get("reasoning", {})

        # Ask LLM for decision
        decision_prompt = f"""
        Review the current research state and decide next action:

        Task: {task}
        Proposed Facts: {len(proposed_facts)}
        Retry Count: {retry_count}/{self.max_retries}

        Critic Feedback:
        {json.dumps(critic_feedback, indent=2, default=str)}

        Decide:
        1. ACCEPT - Facts meet GPS standards, write to ledger
        2. RETRY - Request additional research (if retries available)
        3. INCOMPLETE - Mark as incomplete, needs manual review
        4. CONTINUE - Proceed to next stage

        Respond with JSON: {{"action": "...", "reason": "...", "fact_indices": [...]}}
        """

        response = await self.invoke(decision_prompt, context)

        try:
            decision = json.loads(response)
        except json.JSONDecodeError:
            decision = {"action": "CONTINUE", "reason": "Could not parse decision"}

        state["workflow_decision"] = decision

        # Execute decision
        action = decision.get("action", "CONTINUE")

        if action == "ACCEPT":
            accepted_facts = await self._accept_facts(
                proposed_facts, decision.get("fact_indices", [])
            )
            state["accepted_facts"] = accepted_facts

        elif action == "RETRY" and retry_count < self.max_retries:
            state["retry_count"] = retry_count + 1
            state["needs_revision"] = True
            state["revision_request"] = decision.get("reason", "Additional research needed")

        elif action == "INCOMPLETE":
            incomplete_facts = await self._mark_incomplete(
                proposed_facts, decision.get("reason", "Incomplete research")
            )
            state["incomplete_facts"] = incomplete_facts

        return state

    async def _accept_facts(
        self, proposed_facts: list[Fact], indices: list[int]
    ) -> list[Fact]:
        """Accept facts and write to ledger.

        Args:
            proposed_facts: List of proposed facts
            indices: Indices to accept (empty = all)

        Returns:
            List of accepted facts
        """
        accepted = []

        if not indices:
            indices = list(range(len(proposed_facts)))

        for i in indices:
            if i >= len(proposed_facts):
                continue

            fact = proposed_facts[i]

            # Set status to ACCEPTED
            fact = fact.set_status(FactStatus.ACCEPTED)

            # Add acceptance annotation
            annotation = Annotation(
                author=self.name,
                content="Fact accepted after GPS evaluation",
                annotation_type="acceptance",
            )
            fact = fact.add_annotation(annotation)

            # Write to ledger
            if self.ledger:
                self.ledger.append(fact)
            if self.projection:
                self.projection.upsert_fact(fact)

            accepted.append(fact)

        return accepted

    async def _mark_incomplete(self, proposed_facts: list[Fact], reason: str) -> list[Fact]:
        """Mark facts as incomplete.

        Args:
            proposed_facts: Facts to mark
            reason: Reason for incomplete status

        Returns:
            List of incomplete facts
        """
        incomplete = []

        for fact in proposed_facts:
            fact = fact.set_status(FactStatus.INCOMPLETE)
            annotation = Annotation(
                author=self.name,
                content=f"Marked incomplete: {reason}",
                annotation_type="incomplete",
            )
            fact = fact.add_annotation(annotation)

            if self.ledger:
                self.ledger.append(fact)
            if self.projection:
                self.projection.upsert_fact(fact)

            incomplete.append(fact)

        return incomplete

    def create_fact(
        self,
        statement: str,
        sources: list = None,
        fact_type: str = "general",
        person_id: str | None = None,
    ) -> Fact:
        """Create a new proposed fact.

        Args:
            statement: The factual claim
            sources: Source citations
            fact_type: Type of fact
            person_id: Associated person ID

        Returns:
            New Fact instance
        """
        return Fact(
            statement=statement,
            sources=sources or [],
            provenance=Provenance(
                created_by=ProvenanceSource.RESEARCH_AGENT,
                agent_id=str(uuid7()),
                created_at=datetime.now(UTC),
            ),
            fact_type=fact_type,
            person_id=person_id,
            status=FactStatus.PROPOSED,
            gps_evaluation=GPSEvaluation(),
        )

    def apply_confidence_delta(
        self, fact: Fact, delta: float, reason: str, agent: str
    ) -> Fact:
        """Apply a confidence adjustment to a fact.

        Args:
            fact: Fact to adjust
            delta: Confidence change (+/-)
            reason: Reason for adjustment
            agent: Agent making the adjustment

        Returns:
            Updated fact
        """
        confidence_delta = ConfidenceDelta(
            agent=agent,
            delta=delta,
            reason=reason,
            previous_score=fact.confidence_score,
            new_score=max(0.0, min(1.0, fact.confidence_score + delta)),
        )
        return fact.apply_confidence_delta(confidence_delta)
