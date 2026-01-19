"""Research Agent - discovers records and proposes facts."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from uuid_utils import uuid7

from ..models.fact import Fact, FactStatus
from ..models.gps import GPSEvaluation
from ..models.provenance import Provenance, ProvenanceSource
from ..models.search import RawRecord, SearchQuery
from ..models.source import EvidenceType, SourceCitation
from .base import BaseAgent


class ResearchAgent(BaseAgent):
    """The Research Agent discovers records and proposes candidate Facts.

    Does NOT:
    - Accept or reject Facts
    - Resolve conflicts
    - Adjust confidence
    """

    name = "research"
    prompt_file = "research_agent.txt"
    default_provider = "openai"  # GPT-4 for structured search tasks

    def __init__(self, sources: list | None = None, **kwargs) -> None:
        """Initialize research agent.

        Args:
            sources: List of GenealogySource instances
        """
        super().__init__(**kwargs)
        self.sources = sources or []

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process research task.

        Args:
            state: Current workflow state

        Returns:
            Updated state with proposed facts
        """
        task = state.get("task", "")
        existing_facts = state.get("existing_facts", [])

        # Parse task into search query
        query = await self._parse_task_to_query(task)
        state["search_query"] = query.model_dump()

        # Search all configured sources
        all_records = await self._search_all_sources(query)
        state["raw_records"] = [r.model_dump() for r in all_records]
        state["sources_searched"] = list({r.source for r in all_records})

        # Analyze records and propose facts
        proposed_facts = await self._analyze_and_propose(task, all_records, existing_facts)
        state["proposed_facts"] = proposed_facts

        return state

    async def _parse_task_to_query(self, task: str) -> SearchQuery:
        """Parse natural language task into SearchQuery.

        Args:
            task: Natural language research task

        Returns:
            Structured SearchQuery
        """
        prompt = f"""
        Parse this genealogical research task into structured search parameters.

        Task: {task}

        Extract and return as JSON:
        {{
            "given_name": "first/given name or null",
            "surname": "family name or null",
            "surname_variants": ["list", "of", "variant", "spellings"],
            "birth_year": year as integer or null,
            "birth_year_range": range to search (default 5),
            "birth_place": "location or null",
            "death_year": year as integer or null,
            "death_place": "location or null",
            "residence": "known residence or null",
            "spouse_name": "spouse name or null",
            "father_name": "father name or null",
            "mother_name": "mother name or null",
            "record_types": ["birth", "death", "marriage", "census", etc.]
        }}
        """

        response = await self.invoke(prompt)

        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return SearchQuery(**data)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: extract basic info
        return SearchQuery(record_types=["birth", "death", "census"])

    async def _search_all_sources(self, query: SearchQuery) -> list[RawRecord]:
        """Search all configured sources.

        Args:
            query: Search parameters

        Returns:
            Combined list of records from all sources
        """
        all_records = []

        # Run searches in parallel
        tasks = []
        for source in self.sources:
            if source.is_configured():
                tasks.append(self._search_source_safe(source, query))

        if tasks:
            results = await asyncio.gather(*tasks)
            for records in results:
                all_records.extend(records)

        return all_records

    async def _search_source_safe(self, source, query: SearchQuery) -> list[RawRecord]:
        """Search a source with error handling.

        Args:
            source: Data source
            query: Search query

        Returns:
            Records found (empty list on error)
        """
        try:
            return await source.search(query)
        except Exception as e:
            print(f"Error searching {source.name}: {e}")
            return []

    async def _analyze_and_propose(
        self, task: str, records: list[RawRecord], _existing_facts: list[Fact]
    ) -> list[Fact]:
        """Analyze records and propose facts.

        Args:
            task: Original research task
            records: Raw records found
            existing_facts: Already known facts

        Returns:
            List of proposed Fact objects
        """
        if not records:
            return []

        # Prepare record summaries for LLM
        record_summaries = []
        for i, record in enumerate(records[:20]):  # Limit to prevent token overflow
            summary = {
                "index": i,
                "source": record.source,
                "type": record.record_type,
                "fields": record.extracted_fields,
            }
            record_summaries.append(summary)

        prompt = f"""
        Analyze these genealogical records and propose facts.

        Research Task: {task}

        Records Found:
        {json.dumps(record_summaries, indent=2)}

        For each distinct fact you can support, provide:
        {{
            "facts": [
                {{
                    "statement": "Clear factual statement",
                    "record_indices": [list of supporting record indices],
                    "evidence_type": "direct|indirect|negative",
                    "confidence_hint": 0.0-1.0,
                    "reasoning": "Why this fact is supported"
                }}
            ]
        }}

        Rules:
        - Only propose facts directly supported by evidence
        - Separate evidence from inference
        - Note any conflicts between sources
        - Do NOT resolve conflicts (that's for critics)
        """

        response = await self.invoke(prompt)

        # Parse proposed facts
        proposed = []
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                for fact_data in data.get("facts", []):
                    fact = self._create_fact_from_proposal(fact_data, records)
                    if fact:
                        proposed.append(fact)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing fact proposals: {e}")

        return proposed

    def _create_fact_from_proposal(
        self, proposal: dict, records: list[RawRecord]
    ) -> Fact | None:
        """Create a Fact from a proposal.

        Args:
            proposal: Proposed fact data
            records: Available records

        Returns:
            Fact instance or None
        """
        statement = proposal.get("statement")
        if not statement:
            return None

        # Build source citations
        sources = []
        for idx in proposal.get("record_indices", []):
            if idx < len(records):
                record = records[idx]
                evidence_type_str = proposal.get("evidence_type", "direct")
                try:
                    evidence_type = EvidenceType(evidence_type_str)
                except ValueError:
                    evidence_type = EvidenceType.DIRECT

                citation = SourceCitation(
                    repository=record.source,
                    record_id=record.record_id,
                    url=record.url,
                    evidence_type=evidence_type,
                    record_type=record.record_type,
                    accessed_at=record.accessed_at,
                )
                sources.append(citation)

        # Initial confidence from hint
        confidence = proposal.get("confidence_hint", 0.5)

        return Fact(
            fact_id=uuid7(),
            statement=statement,
            sources=sources,
            provenance=Provenance(
                created_by=ProvenanceSource.RESEARCH_AGENT,
                agent_id=self.name,
                query_context=statement,
                created_at=datetime.now(UTC),
            ),
            confidence_score=confidence,
            status=FactStatus.PROPOSED,
            gps_evaluation=GPSEvaluation(),
        )
