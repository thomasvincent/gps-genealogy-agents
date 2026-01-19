"""Citation Agent - formats citations to Evidence Explained standards."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .base import BaseAgent

if TYPE_CHECKING:
    from ..models.fact import Fact


class CitationAgent(BaseAgent):
    """Citation Agent formats ACCEPTED Facts into Evidence Explained citations.

    Does NOT:
    - Alter content
    - Adjust confidence
    - Evaluate evidence
    """

    name = "citation"
    prompt_file = "citation_agent.txt"
    default_provider = "openai"  # GPT-4 for structured formatting

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Format citations for accepted facts.

        Args:
            state: Current workflow state

        Returns:
            Updated state with formatted citations
        """
        accepted_facts = state.get("accepted_facts", [])
        formatted_citations = []

        for fact in accepted_facts:
            citations = await self._format_citations(fact)
            formatted_citations.append({
                "fact_id": str(fact.fact_id),
                "statement": fact.statement,
                "citations": citations,
            })

        state["formatted_citations"] = formatted_citations
        return state

    async def _format_citations(self, fact: Fact) -> list[dict]:
        """Format all citations for a fact.

        Args:
            fact: Fact with sources to format

        Returns:
            List of formatted citation dicts
        """
        formatted = []

        for source in fact.sources:
            citation = await self._format_single_citation(source, fact.statement)
            formatted.append(citation)

        return formatted

    async def _format_single_citation(self, source, statement: str) -> dict:
        """Format a single citation to Evidence Explained standards.

        Args:
            source: SourceCitation object
            statement: The fact statement for context

        Returns:
            Formatted citation dict
        """
        source_data = {
            "repository": source.repository,
            "record_id": source.record_id,
            "url": source.url,
            "evidence_type": source.evidence_type.value,
            "record_type": source.record_type,
            "accessed_at": source.accessed_at.strftime("%d %B %Y"),
            "informant": source.informant,
        }

        prompt = f"""
        Format this genealogical source citation according to Evidence Explained
        (Elizabeth Shown Mills) standards.

        Source Information:
        {json.dumps(source_data, indent=2)}

        For Fact: {statement}

        Create three citation formats:
        1. Reference Note (full citation for first use)
        2. Short Note (subsequent references)
        3. Source List Entry (bibliography format)

        Follow Evidence Explained layered citation format:
        - Source of the Source (where you found it)
        - Source Itself (the actual record)
        - Specific Item (exact entry)

        Return JSON:
        {{
            "reference_note": "Full citation text",
            "short_note": "Abbreviated citation",
            "source_list_entry": "Bibliography entry",
            "evidence_type_explanation": "Why classified as direct/indirect/negative",
            "informant_note": "Note about informant reliability if applicable"
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return {
                    "source_id": source.record_id,
                    "repository": source.repository,
                    **result,
                }
        except json.JSONDecodeError:
            pass

        # Fallback: generate basic citation
        return {
            "source_id": source.record_id,
            "repository": source.repository,
            "reference_note": source.to_evidence_explained(),
            "short_note": f"{source.repository}, {source.record_id}",
            "source_list_entry": source.to_evidence_explained(),
        }
