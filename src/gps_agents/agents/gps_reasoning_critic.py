"""GPS Reasoning Critic - evaluates Pillars 3 and 4."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..models.gps import Conflict, PillarStatus
from .base import BaseAgent

if TYPE_CHECKING:
    from ..models.fact import Fact


class GPSReasoningCritic(BaseAgent):
    """GPS Reasoning Critic evaluates GPS Pillars 3 and 4.

    Pillar 3: Analysis and correlation of evidence
    Pillar 4: Resolution of conflicting evidence

    Advises only - no veto power.
    """

    name = "gps_reasoning_critic"
    prompt_file = "gps_reasoning_critic.txt"
    default_provider = "anthropic"  # Claude for complex reasoning

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Evaluate facts against GPS Pillars 3 and 4.

        Args:
            state: Current workflow state

        Returns:
            Updated state with reasoning evaluation
        """
        proposed_facts = state.get("proposed_facts", [])
        quality_flags = state.get("quality_flags", [])

        evaluations = []
        for i, fact in enumerate(proposed_facts):
            flags = quality_flags[i] if i < len(quality_flags) else {}
            evaluation = await self._evaluate_fact(fact, flags)
            evaluations.append(evaluation)

        state["critic_feedback"] = state.get("critic_feedback", {})
        state["critic_feedback"]["reasoning"] = {
            "evaluations": evaluations,
            "overall_pillar_3": self._aggregate_pillar(evaluations, "pillar_3"),
            "overall_pillar_4": self._aggregate_pillar(evaluations, "pillar_4"),
        }

        return state

    async def _evaluate_fact(self, fact: Fact, quality_flags: dict) -> dict:
        """Evaluate a single fact for reasoning quality.

        Args:
            fact: Fact to evaluate
            quality_flags: Data quality flags

        Returns:
            Evaluation dictionary
        """
        evaluation = {
            "fact_id": str(fact.fact_id),
            "pillar_3": PillarStatus.PENDING.value,
            "pillar_4": PillarStatus.PENDING.value,
            "logical_fallacies": [],
            "conflicts": [],
            "informant_reliability": {},
            "confidence_delta": 0.0,
            "reasoning_narrative": "",
        }

        # Pillar 3: Analysis and correlation
        pillar_3_result = await self._evaluate_pillar_3(fact)
        evaluation.update(pillar_3_result)

        # Pillar 4: Conflict resolution
        pillar_4_result = await self._evaluate_pillar_4(fact, quality_flags)
        evaluation.update(pillar_4_result)

        # Calculate confidence delta
        delta = 0.0
        if evaluation["pillar_3"] == PillarStatus.FAILED.value:
            delta -= 0.2
        elif evaluation["pillar_3"] == PillarStatus.PARTIAL.value:
            delta -= 0.1

        if evaluation["pillar_4"] == PillarStatus.FAILED.value:
            delta -= 0.25  # Unresolved conflicts are serious
        elif evaluation["pillar_4"] == PillarStatus.PARTIAL.value:
            delta -= 0.1

        if evaluation["logical_fallacies"]:
            delta -= 0.05 * len(evaluation["logical_fallacies"])

        evaluation["confidence_delta"] = max(-0.5, delta)

        return evaluation

    async def _evaluate_pillar_3(self, fact: Fact) -> dict:
        """Evaluate Pillar 3: Analysis and correlation.

        Args:
            fact: Fact to evaluate

        Returns:
            Pillar 3 evaluation
        """
        sources_data = [
            {
                "repository": s.repository,
                "evidence_type": s.evidence_type.value,
                "record_type": s.record_type,
                "informant": s.informant,
                "informant_relationship": s.informant_relationship,
            }
            for s in fact.sources
        ]

        prompt = f"""
        Evaluate the analysis and correlation of evidence for this fact.

        Fact: {fact.statement}
        Sources: {json.dumps(sources_data, indent=2)}

        Analyze:
        1. Is each source properly weighted based on evidence type?
        2. Are informants' relationships to events considered?
        3. Do sources corroborate each other appropriately?
        4. Are there logical fallacies in the reasoning?

        Common genealogical fallacies to check:
        - Same name = same person (without other evidence)
        - Proximity assumption (living nearby = related)
        - Ancestor worship (assuming positive traits)
        - Single source dependency

        Return JSON:
        {{
            "pillar_3": "satisfied|partial|failed",
            "logical_fallacies": ["list of fallacies found"],
            "informant_reliability": {{"source_index": "high|medium|low|unknown"}},
            "evidence_correlation": "how sources support each other",
            "reasoning": "explanation of analysis quality"
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return {
                    "pillar_3": result.get("pillar_3", PillarStatus.PENDING.value),
                    "logical_fallacies": result.get("logical_fallacies", []),
                    "informant_reliability": result.get("informant_reliability", {}),
                    "evidence_correlation": result.get("evidence_correlation", ""),
                    "pillar_3_reasoning": result.get("reasoning", ""),
                }
        except json.JSONDecodeError:
            pass

        return {"pillar_3": PillarStatus.PENDING.value}

    async def _evaluate_pillar_4(self, fact: Fact, quality_flags: dict) -> dict:
        """Evaluate Pillar 4: Conflict resolution.

        Args:
            fact: Fact to evaluate
            quality_flags: Data quality issues

        Returns:
            Pillar 4 evaluation
        """
        # Check for existing conflicts in GPS evaluation
        existing_conflicts = []
        if fact.gps_evaluation:
            existing_conflicts = [
                c.model_dump() for c in fact.gps_evaluation.conflicts_identified
            ]

        contradictions = quality_flags.get("flags", {}).get("contradictions", [])

        prompt = f"""
        Evaluate conflict resolution for this genealogical fact.

        Fact: {fact.statement}
        Known Contradictions: {contradictions}
        Existing Conflicts: {json.dumps(existing_conflicts)}

        Identify:
        1. Are there conflicting sources?
        2. If conflicts exist, are they properly resolved?
        3. Is the resolution reasoning sound?
        4. Are there implicit conflicts that should be addressed?

        Return JSON:
        {{
            "pillar_4": "satisfied|partial|failed",
            "conflicts": [
                {{
                    "description": "what conflicts",
                    "sources_involved": ["list"],
                    "is_resolved": true/false,
                    "resolution": "how resolved or null",
                    "resolution_sound": true/false
                }}
            ],
            "reasoning": "explanation of conflict status"
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])

                # Convert conflicts to Conflict objects
                conflicts = []
                for c in result.get("conflicts", []):
                    conflict = Conflict(
                        conflict_id=f"conflict_{len(conflicts)}",
                        description=c.get("description", ""),
                        sources_involved=c.get("sources_involved", []),
                        resolution=c.get("resolution"),
                        is_resolved=c.get("is_resolved", False),
                    )
                    conflicts.append(conflict)

                return {
                    "pillar_4": result.get("pillar_4", PillarStatus.PENDING.value),
                    "conflicts": [c.model_dump() for c in conflicts],
                    "pillar_4_reasoning": result.get("reasoning", ""),
                }
        except json.JSONDecodeError:
            pass

        # No conflicts found = satisfied
        if not contradictions and not existing_conflicts:
            return {"pillar_4": PillarStatus.SATISFIED.value, "conflicts": []}

        return {"pillar_4": PillarStatus.PENDING.value}

    def _aggregate_pillar(self, evaluations: list[dict], pillar: str) -> str:
        """Aggregate pillar status across all facts."""
        statuses = [e.get(pillar, PillarStatus.PENDING.value) for e in evaluations]

        if PillarStatus.FAILED.value in statuses:
            return PillarStatus.FAILED.value
        if PillarStatus.PARTIAL.value in statuses:
            return PillarStatus.PARTIAL.value
        if all(s == PillarStatus.SATISFIED.value for s in statuses):
            return PillarStatus.SATISFIED.value

        return PillarStatus.PENDING.value
