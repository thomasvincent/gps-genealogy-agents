"""DNA/Ethnicity Agent - provides probabilistic interpretations."""
from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent


class DNAAgent(BaseAgent):
    """DNA/Ethnicity Agent provides probabilistic interpretations only.

    Does NOT:
    - Assert lineage definitively
    - Override documentary evidence
    - Create accepted Facts
    """

    name = "dna"
    prompt_file = "ethnicity_dna_agent.txt"
    default_provider = "openai"  # GPT-4 for structured analysis

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process DNA/ethnicity data.

        Args:
            state: Current workflow state

        Returns:
            Updated state with DNA interpretations
        """
        dna_data = state.get("dna_data", {})

        if not dna_data:
            return state

        interpretation = await self._interpret_dna(dna_data)
        state["dna_interpretation"] = interpretation

        return state

    async def _interpret_dna(self, dna_data: dict) -> dict:
        """Interpret DNA data with appropriate caveats.

        Args:
            dna_data: Raw DNA/ethnicity data

        Returns:
            Interpretation with limitations noted
        """
        prompt = f"""
        Interpret this DNA/ethnicity data for genealogical purposes.

        Data:
        {json.dumps(dna_data, indent=2)}

        IMPORTANT: You must:
        1. Use probabilistic language ("suggests", "consistent with", "may indicate")
        2. Explicitly state limitations of DNA ethnicity estimates
        3. Note that ethnicity percentages are estimates with confidence intervals
        4. Explain that DNA matches require documentary evidence to confirm relationships
        5. Never claim definitive lineage based on DNA alone

        Return JSON:
        {{
            "interpretation": "narrative interpretation",
            "confidence_level": "low|medium|high",
            "limitations": ["list of caveats"],
            "suggested_research": ["documentary research to pursue"],
            "cannot_determine": ["what DNA cannot tell us in this case"]
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                result["is_low_certainty"] = True  # Always flag DNA as low certainty
                return result
        except json.JSONDecodeError:
            pass

        return {
            "interpretation": "Unable to interpret DNA data",
            "confidence_level": "low",
            "limitations": ["Interpretation could not be completed"],
            "is_low_certainty": True,
        }

    async def interpret_match(self, match_data: dict) -> dict:
        """Interpret a DNA match.

        Args:
            match_data: DNA match information

        Returns:
            Match interpretation
        """
        prompt = f"""
        Interpret this DNA match for genealogical research.

        Match Data:
        {json.dumps(match_data, indent=2)}

        Provide:
        1. Estimated relationship range (NOT a definitive relationship)
        2. Number of generations back to common ancestor (range)
        3. Documentary evidence needed to confirm
        4. Alternative relationship possibilities

        Return JSON:
        {{
            "estimated_relationships": ["list of possible relationships"],
            "generations_range": {{"min": X, "max": Y}},
            "cm_shared": amount,
            "documentation_needed": ["specific records to find"],
            "important_caveats": ["limitations to note"]
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError:
            pass

        return {"error": "Could not interpret match"}
