"""Synthesis Agent - produces narratives and proof summaries."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..models.gps import PillarStatus
from .base import BaseAgent

if TYPE_CHECKING:
    from ..models.fact import Fact


class SynthesisAgent(BaseAgent):
    """Synthesis Agent produces narratives and proof summaries.

    Consumes ONLY ACCEPTED Facts.

    Does NOT:
    - Introduce evidence
    - Resolve conflicts
    - Hide uncertainty
    """

    name = "synthesis"
    prompt_file = "synthesis_agent.txt"
    default_provider = "anthropic"  # Claude for narrative generation

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate synthesis outputs.

        Args:
            state: Current workflow state

        Returns:
            Updated state with narratives
        """
        accepted_facts = state.get("accepted_facts", [])
        task = state.get("task", "")
        formatted_citations = state.get("formatted_citations", [])

        if not accepted_facts:
            state["synthesis"] = {
                "narrative": "No facts were accepted for this research query.",
                "proof_summary": None,
                "open_questions": ["Research did not yield accepted conclusions."],
            }
            return state

        # Generate proof summary
        proof_summary = await self._generate_proof_summary(accepted_facts, task)

        # Generate narrative
        narrative = await self._generate_narrative(
            accepted_facts, task, formatted_citations
        )

        # Identify open questions
        open_questions = await self._identify_open_questions(accepted_facts, task)

        state["synthesis"] = {
            "narrative": narrative,
            "proof_summary": proof_summary,
            "open_questions": open_questions,
        }

        # Update Pillar 5 status for each fact
        for fact in accepted_facts:
            if fact.gps_evaluation:
                fact.gps_evaluation.pillar_5 = PillarStatus.SATISFIED
                fact.gps_evaluation.proof_summary = proof_summary

        return state

    async def _generate_proof_summary(self, facts: list[Fact], task: str) -> str:
        """Generate a proof summary (GPS Pillar 5).

        Args:
            facts: Accepted facts
            task: Original research question

        Returns:
            Proof summary text
        """
        facts_data = [
            {
                "statement": f.statement,
                "confidence": f.confidence_score,
                "sources_count": len(f.sources),
                "evidence_types": [s.evidence_type.value for s in f.sources],
            }
            for f in facts
        ]

        prompt = f"""
        Write a proof summary for the following genealogical research.

        Research Question: {task}

        Accepted Facts:
        {json.dumps(facts_data, indent=2)}

        The proof summary must:
        1. State the conclusion clearly
        2. Summarize the evidence that supports it
        3. Explain how sources corroborate each other
        4. Acknowledge any limitations or caveats
        5. Be written in third person, past tense

        Format as a professional genealogical proof summary that would be
        suitable for publication in a genealogical journal.

        Keep it concise but complete (2-4 paragraphs).
        """

        return await self.invoke(prompt)

    async def _generate_narrative(
        self, facts: list[Fact], task: str, citations: list[dict]
    ) -> str:
        """Generate a readable narrative from accepted facts.

        Args:
            facts: Accepted facts
            task: Research context
            citations: Formatted citations

        Returns:
            Narrative text
        """
        facts_with_citations = []
        for fact in facts:
            fact_citations = [
                c for c in citations if c.get("fact_id") == str(fact.fact_id)
            ]
            facts_with_citations.append({
                "statement": fact.statement,
                "confidence": fact.confidence_score,
                "citations": fact_citations,
            })

        prompt = f"""
        Write a narrative account based on these accepted genealogical facts.

        Research Context: {task}

        Facts and Citations:
        {json.dumps(facts_with_citations, indent=2, default=str)}

        Requirements:
        1. Write in clear, engaging prose
        2. Include citation markers [1], [2], etc.
        3. Present facts in logical order (typically chronological)
        4. Clearly indicate uncertainty where confidence is below 0.9
        5. Do NOT add any information not in the facts
        6. Do NOT hide uncertainty or caveats

        Write the narrative:
        """

        return await self.invoke(prompt)

    async def _identify_open_questions(self, facts: list[Fact], task: str) -> list[str]:
        """Identify remaining open questions.

        Args:
            facts: Accepted facts
            task: Original research question

        Returns:
            List of open questions
        """
        facts_summary = [
            {"statement": f.statement, "confidence": f.confidence_score}
            for f in facts
        ]

        prompt = f"""
        Based on this genealogical research, identify open questions that remain.

        Research Question: {task}

        Facts Established:
        {json.dumps(facts_summary, indent=2)}

        Identify:
        1. What aspects of the original question are not fully answered?
        2. What new questions arise from these findings?
        3. What would strengthen the conclusions?

        Return JSON:
        {{
            "open_questions": [
                "Question 1",
                "Question 2",
                ...
            ]
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return result.get("open_questions", [])
        except json.JSONDecodeError:
            pass

        return []
