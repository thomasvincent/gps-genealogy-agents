"""GPS Standards Critic - evaluates Pillars 1 and 2."""

import json
from typing import Any

from ..models.fact import Fact
from ..models.gps import PillarStatus
from .base import BaseAgent


class GPSStandardsCritic(BaseAgent):
    """GPS Standards Critic evaluates GPS Pillars 1 and 2.

    Pillar 1: Reasonably exhaustive research
    Pillar 2: Complete and accurate citations

    Advises only - no veto power.
    """

    name = "gps_standards_critic"
    prompt_file = "gps_standards_critic.txt"
    default_provider = "anthropic"  # Claude for complex reasoning

    # Major source classes by region/time
    MAJOR_SOURCE_CLASSES = {
        "us_1850_plus": [
            "federal_census",
            "state_census",
            "vital_records",
            "church_records",
            "military_records",
        ],
        "us_pre_1850": [
            "church_records",
            "land_records",
            "tax_records",
            "probate_records",
            "military_records",
        ],
        "uk_ireland": [
            "civil_registration",
            "parish_records",
            "census",
            "griffith_valuation",
            "tithe_applotment",
        ],
        "europe": [
            "church_records",
            "civil_registration",
            "census",
            "military_records",
        ],
    }

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Evaluate facts against GPS Pillars 1 and 2.

        Args:
            state: Current workflow state

        Returns:
            Updated state with standards evaluation
        """
        proposed_facts = state.get("proposed_facts", [])
        sources_searched = state.get("sources_searched", [])

        evaluations = []
        for fact in proposed_facts:
            evaluation = await self._evaluate_fact(fact, sources_searched)
            evaluations.append(evaluation)

        state["critic_feedback"] = state.get("critic_feedback", {})
        state["critic_feedback"]["standards"] = {
            "evaluations": evaluations,
            "overall_pillar_1": self._aggregate_pillar(evaluations, "pillar_1"),
            "overall_pillar_2": self._aggregate_pillar(evaluations, "pillar_2"),
        }

        return state

    async def _evaluate_fact(self, fact: Fact, sources_searched: list[str]) -> dict:
        """Evaluate a single fact.

        Args:
            fact: Fact to evaluate
            sources_searched: List of sources that were searched

        Returns:
            Evaluation dictionary
        """
        evaluation = {
            "fact_id": str(fact.fact_id),
            "pillar_1": PillarStatus.PENDING.value,
            "pillar_2": PillarStatus.PENDING.value,
            "missing_sources": [],
            "citation_issues": [],
            "confidence_delta": 0.0,
            "recommendations": [],
        }

        # Pillar 1: Reasonably exhaustive research
        pillar_1_result = await self._evaluate_pillar_1(fact, sources_searched)
        evaluation.update(pillar_1_result)

        # Pillar 2: Complete and accurate citations
        pillar_2_result = await self._evaluate_pillar_2(fact)
        evaluation.update(pillar_2_result)

        # Calculate confidence delta
        delta = 0.0
        if evaluation["pillar_1"] == PillarStatus.FAILED.value:
            delta -= 0.2
        elif evaluation["pillar_1"] == PillarStatus.PARTIAL.value:
            delta -= 0.1

        if evaluation["pillar_2"] == PillarStatus.FAILED.value:
            delta -= 0.15
        elif evaluation["pillar_2"] == PillarStatus.PARTIAL.value:
            delta -= 0.05

        if (
            evaluation["pillar_1"] == PillarStatus.SATISFIED.value
            and evaluation["pillar_2"] == PillarStatus.SATISFIED.value
        ):
            delta += 0.05

        evaluation["confidence_delta"] = delta

        return evaluation

    async def _evaluate_pillar_1(self, fact: Fact, sources_searched: list[str]) -> dict:
        """Evaluate Pillar 1: Reasonably exhaustive research.

        Args:
            fact: Fact to evaluate
            sources_searched: Sources that were searched

        Returns:
            Pillar 1 evaluation
        """
        prompt = f"""
        Evaluate whether the research for this fact was reasonably exhaustive.

        Fact: {fact.statement}
        Sources Used: {[s.repository for s in fact.sources]}
        Sources Searched: {sources_searched}

        Consider:
        - What major record classes are relevant for this fact's time/place?
        - Were the primary source types searched?
        - What critical sources might be missing?

        Return JSON:
        {{
            "pillar_1": "satisfied|partial|failed",
            "sources_searched_adequate": true/false,
            "missing_major_sources": ["list of missing source classes"],
            "reasoning": "explanation",
            "recommendations": ["specific searches to conduct"]
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return {
                    "pillar_1": result.get("pillar_1", PillarStatus.PENDING.value),
                    "missing_sources": result.get("missing_major_sources", []),
                    "pillar_1_reasoning": result.get("reasoning", ""),
                    "recommendations": result.get("recommendations", []),
                }
        except json.JSONDecodeError:
            pass

        return {"pillar_1": PillarStatus.PENDING.value}

    async def _evaluate_pillar_2(self, fact: Fact) -> dict:
        """Evaluate Pillar 2: Complete and accurate citations.

        Args:
            fact: Fact to evaluate

        Returns:
            Pillar 2 evaluation
        """
        citations_data = [
            {
                "repository": s.repository,
                "record_id": s.record_id,
                "url": s.url,
                "evidence_type": s.evidence_type.value,
                "record_type": s.record_type,
            }
            for s in fact.sources
        ]

        prompt = f"""
        Evaluate whether citations for this fact are complete and accurate
        according to Evidence Explained standards.

        Fact: {fact.statement}
        Citations: {json.dumps(citations_data, indent=2)}

        Check:
        - Are all elements present (repository, location, record type, date accessed)?
        - Is the evidence type correctly classified?
        - Could someone find this record using this citation?

        Return JSON:
        {{
            "pillar_2": "satisfied|partial|failed",
            "citations_complete": true/false,
            "evidence_explained_compliant": true/false,
            "citation_issues": ["list of specific issues"],
            "reasoning": "explanation"
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return {
                    "pillar_2": result.get("pillar_2", PillarStatus.PENDING.value),
                    "citation_issues": result.get("citation_issues", []),
                    "pillar_2_reasoning": result.get("reasoning", ""),
                }
        except json.JSONDecodeError:
            pass

        return {"pillar_2": PillarStatus.PENDING.value}

    def _aggregate_pillar(self, evaluations: list[dict], pillar: str) -> str:
        """Aggregate pillar status across all facts.

        Args:
            evaluations: List of evaluation dicts
            pillar: Pillar key to aggregate

        Returns:
            Aggregate status
        """
        statuses = [e.get(pillar, PillarStatus.PENDING.value) for e in evaluations]

        if PillarStatus.FAILED.value in statuses:
            return PillarStatus.FAILED.value
        if PillarStatus.PARTIAL.value in statuses:
            return PillarStatus.PARTIAL.value
        if all(s == PillarStatus.SATISFIED.value for s in statuses):
            return PillarStatus.SATISFIED.value

        return PillarStatus.PENDING.value
