"""Data Quality Agent - performs mechanical validation."""

import json
import re
from typing import Any

from ..models.fact import Fact
from .base import BaseAgent


class DataQualityAgent(BaseAgent):
    """The Data Quality Agent performs fast, mechanical validation.

    Checks:
    - Date consistency
    - Name alignment
    - Geographic plausibility
    - Internal contradictions
    - Source agreement

    Does NOT:
    - Judge plausibility
    - Resolve conflicts
    - Block workflow
    """

    name = "data_quality"
    prompt_file = "data_quality_agent.txt"
    default_provider = "openai"  # GPT-4 for structured validation

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate proposed facts.

        Args:
            state: Current workflow state

        Returns:
            Updated state with quality flags
        """
        proposed_facts = state.get("proposed_facts", [])
        quality_flags = []

        for i, fact in enumerate(proposed_facts):
            flags = await self._validate_fact(fact)
            quality_flags.append({"fact_index": i, "flags": flags})

        state["quality_flags"] = quality_flags
        return state

    async def _validate_fact(self, fact: Fact) -> dict[str, Any]:
        """Validate a single fact.

        Args:
            fact: Fact to validate

        Returns:
            Dictionary of validation flags
        """
        flags: dict[str, Any] = {
            "date_issues": [],
            "name_issues": [],
            "geographic_issues": [],
            "contradictions": [],
            "source_issues": [],
            "is_valid": True,
        }

        # Check dates in statement
        dates = self._extract_dates(fact.statement)
        for date in dates:
            issues = self._validate_date(date)
            if issues:
                flags["date_issues"].extend(issues)

        # Check for impossible date ranges
        if len(dates) >= 2:
            sorted_dates = sorted(dates)
            for i in range(len(sorted_dates) - 1):
                if sorted_dates[i + 1] - sorted_dates[i] > 120:
                    flags["date_issues"].append(
                        f"Unusual time span: {sorted_dates[i + 1] - sorted_dates[i]} years"
                    )

        # Check source agreement
        if len(fact.sources) > 1:
            source_issues = await self._check_source_agreement(fact)
            flags["source_issues"] = source_issues

        # LLM-based validation for complex checks
        llm_flags = await self._llm_validate(fact)
        flags["name_issues"] = llm_flags.get("name_issues", [])
        flags["geographic_issues"] = llm_flags.get("geographic_issues", [])
        flags["contradictions"] = llm_flags.get("contradictions", [])

        # Set overall validity
        flags["is_valid"] = not any(
            [
                flags["date_issues"],
                flags["contradictions"],
            ]
        )

        return flags

    def _extract_dates(self, text: str) -> list[int]:
        """Extract years from text.

        Args:
            text: Text to search

        Returns:
            List of years found
        """
        # Match 4-digit years between 1500 and 2100
        years = re.findall(r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b", text)
        return [int(y) for y in years]

    def _validate_date(self, year: int) -> list[str]:
        """Validate a single year.

        Args:
            year: Year to validate

        Returns:
            List of issues found
        """
        issues = []
        current_year = 2026

        if year < 1500:
            issues.append(f"Year {year} is unusually early for documented genealogy")
        elif year > current_year:
            issues.append(f"Year {year} is in the future")

        return issues

    async def _check_source_agreement(self, fact: Fact) -> list[str]:
        """Check if sources agree on key details.

        Args:
            fact: Fact with multiple sources

        Returns:
            List of disagreement issues
        """
        issues = []

        # Group sources by repository
        repos = {s.repository for s in fact.sources}
        if len(repos) > 1:
            # Multiple independent sources - good for corroboration
            pass
        elif len(fact.sources) > 1:
            # Multiple records from same source
            issues.append("All sources from same repository - consider independent verification")

        return issues

    async def _llm_validate(self, fact: Fact) -> dict:
        """Use LLM for complex validation.

        Args:
            fact: Fact to validate

        Returns:
            Dictionary of issues by category
        """
        sources_summary = [
            {"repo": s.repository, "type": s.record_type} for s in fact.sources
        ]

        prompt = f"""
        Perform mechanical validation on this genealogical fact.
        DO NOT judge whether the fact is true or likely.
        Only flag clear data quality issues.

        Fact: {fact.statement}
        Sources: {json.dumps(sources_summary)}

        Check for:
        1. Name issues: Inconsistent spellings, impossible characters
        2. Geographic issues: Non-existent places, anachronistic names
        3. Contradictions: Internal logical contradictions

        Return JSON:
        {{
            "name_issues": ["list of issues or empty"],
            "geographic_issues": ["list of issues or empty"],
            "contradictions": ["list of issues or empty"]
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

        return {"name_issues": [], "geographic_issues": [], "contradictions": []}
