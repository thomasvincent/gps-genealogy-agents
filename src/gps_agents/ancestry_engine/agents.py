"""Agent implementations for The Ancestry Engine.

This module implements the four agents specified in the Z notation:
- The Lead: Task decomposition and state management
- The Scout: Tool-use specialist (Search/Browse/Scrape)
- The Analyst: Conflict resolution and Clue generation
- The Censor: PII/ToS compliance
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from .models import (
    AgentType,
    AncestryEngineState,
    ClueHypothesis,
    ConflictingClaim,
    ConflictResolution,
    EvidenceType,
    HypothesisStatus,
    LogEntry,
    Person,
    RawRecord,
    SourceCitation,
    SourceTier,
    Task,
    TaskType,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Base Agent
# =============================================================================

class BaseAgent(ABC):
    """Base class for all agents."""

    agent_type: AgentType

    def __init__(self, llm_client: Any = None):
        """Initialize the agent.

        Args:
            llm_client: Optional LLM client for reasoning tasks
        """
        self.llm_client = llm_client

    @abstractmethod
    async def execute(self, state: AncestryEngineState, **kwargs: Any) -> AncestryEngineState:
        """Execute the agent's primary operation.

        Args:
            state: Current engine state
            **kwargs: Operation-specific arguments

        Returns:
            Updated engine state
        """
        ...

    def log_action(
        self,
        state: AncestryEngineState,
        action_type: str,
        rationale: str,
        **kwargs: Any,
    ) -> LogEntry:
        """Create and add a log entry."""
        entry = LogEntry(
            agent=self.agent_type,
            action_type=action_type,
            rationale=rationale,
            **kwargs,
        )
        state.add_log_entry(entry)
        return entry


# =============================================================================
# The Lead (Orchestrator)
# =============================================================================

class LeadAgent(BaseAgent):
    """The Lead: Task decomposition and state management.

    Implements Z operations:
    - LeadSelectTask: Select and dispatch highest priority task
    - LeadCheckTermination: Check termination conditions
    """

    agent_type = AgentType.LEAD

    async def execute(self, state: AncestryEngineState, **kwargs: Any) -> AncestryEngineState:
        """Execute the Lead's primary orchestration loop."""
        state.active_agent = self.agent_type

        # Check termination first
        if self._check_termination(state):
            return state

        # Select next task
        task = self.select_task(state)
        if task:
            self.log_action(
                state,
                action_type="task_selection",
                rationale=f"Selected task: {task.description} (priority: {task.priority:.2f})",
                task_id=task.id,
            )

        return state

    def select_task(self, state: AncestryEngineState) -> Task | None:
        """Select the highest priority task from the frontier.

        Z Operation: LeadSelectTask
        - selectedTask! = head(sortByPriority(frontierQueue))
        """
        return state.pop_task()

    def decompose_query(self, query: str, seed_person: Person) -> list[Task]:
        """Decompose a research query into initial tasks.

        Args:
            query: The research query
            seed_person: The seed person to start research from

        Returns:
            List of initial tasks
        """
        tasks = []

        # Always start with searching for the seed person
        tasks.append(Task(
            task_type=TaskType.SEARCH,
            assigned_to=AgentType.SCOUT,
            priority=1.0,
            description=f"Search for {seed_person.full_name} in vital records",
            query=f"{seed_person.given_name} {seed_person.surname}",
            target_person=seed_person.id,
            source_constraints=[SourceTier.TIER_0],  # Start with free sources
        ))

        # Search census records
        if seed_person.birth_dates:
            birth_year = self._extract_year(seed_person.birth_dates[0])
            if birth_year:
                # Find applicable census years
                census_years = [y for y in [1950, 1940, 1930, 1920, 1910, 1900, 1890, 1880]
                              if y >= birth_year]
                for year in census_years[:3]:  # Limit to 3 most relevant
                    tasks.append(Task(
                        task_type=TaskType.SEARCH,
                        assigned_to=AgentType.SCOUT,
                        priority=0.9 - (0.05 * census_years.index(year)),
                        description=f"Search {year} census for {seed_person.full_name}",
                        query=f"{seed_person.given_name} {seed_person.surname} {year} census",
                        target_person=seed_person.id,
                        source_constraints=[SourceTier.TIER_0],
                    ))

        # Search death records
        tasks.append(Task(
            task_type=TaskType.SEARCH,
            assigned_to=AgentType.SCOUT,
            priority=0.8,
            description=f"Search death records for {seed_person.full_name}",
            query=f"{seed_person.given_name} {seed_person.surname} death",
            target_person=seed_person.id,
            source_constraints=[SourceTier.TIER_0],
        ))

        return tasks

    def prioritize_hypotheses(
        self,
        state: AncestryEngineState,
        hypotheses: list[ClueHypothesis],
    ) -> list[Task]:
        """Convert hypotheses to prioritized tasks.

        Args:
            state: Current state (for context)
            hypotheses: New hypotheses from Analyst

        Returns:
            Tasks to add to frontier
        """
        tasks = []
        for hypothesis in hypotheses:
            # Create appropriate task based on hypothesis type
            if "vital records" in hypothesis.statement.lower():
                task_type = TaskType.SEARCH
                assigned_to = AgentType.SCOUT
            elif "verify" in hypothesis.statement.lower():
                task_type = TaskType.VERIFY
                assigned_to = AgentType.ANALYST
            else:
                task_type = TaskType.SEARCH
                assigned_to = AgentType.SCOUT

            task = Task(
                task_type=task_type,
                assigned_to=assigned_to,
                priority=hypothesis.priority,
                hypothesis=hypothesis,
                description=hypothesis.statement,
                target_person=hypothesis.target_person,
                source_constraints=[SourceTier.TIER_0],
            )
            tasks.append(task)

        return tasks

    def _check_termination(self, state: AncestryEngineState) -> bool:
        """Check termination conditions.

        Z Operation: LeadCheckTermination
        - goalAchieved ∨ exhausted ∨ budgetExceeded ∨ gpsSatisfied
        """
        # Already terminated
        if state.terminated:
            return True

        # Exhausted: empty frontier and no actionable hypotheses
        # Z spec: exhausted == frontierQueue = ⟨⟩ ∧ hypotheses = ∅
        # Interpretation: "hypotheses = ∅" means no PENDING hypotheses to process.
        # Completed/rejected hypotheses are not actionable, so they don't block termination.
        exhausted = (
            not state.frontier_queue and
            not any(h.status == HypothesisStatus.PENDING for h in state.hypotheses)
        )

        # Budget exceeded
        budget_exceeded = len(state.research_log) > state.max_log_entries

        # GPS satisfied: all persons have primary + secondary sources
        gps_satisfied = self._check_gps_coverage(state)

        if exhausted or budget_exceeded or gps_satisfied:
            state.terminated = True
            if exhausted:
                state.termination_reason = "Exhausted: no more tasks or hypotheses"
            elif budget_exceeded:
                state.termination_reason = "Budget exceeded: max log entries reached"
            elif gps_satisfied:
                state.termination_reason = "GPS satisfied: adequate source coverage achieved"

            self.log_action(
                state,
                action_type="termination",
                rationale=state.termination_reason,
            )
            return True

        return False

    def _check_gps_coverage(self, state: AncestryEngineState) -> bool:
        """Check if GPS coverage is satisfied for all persons.

        Z: checkGPSCoverage - primary + secondary for each person
        """
        for person in state.knowledge_graph.values():
            has_primary = any(s.evidence_type == EvidenceType.PRIMARY for s in person.sources)
            has_secondary = any(s.evidence_type == EvidenceType.SECONDARY for s in person.sources)
            if not (has_primary and has_secondary):
                return False
        return len(state.knowledge_graph) > 0

    def _extract_year(self, date_str: str) -> int | None:
        """Extract year from a date string."""
        if not date_str:
            return None
        # Try YYYY format
        match = re.search(r"\b(\d{4})\b", date_str)
        if match:
            return int(match.group(1))
        return None


# =============================================================================
# The Scout (Tool Specialist)
# =============================================================================

class ScoutAgent(BaseAgent):
    """The Scout: Tool-use specialist for search/browse/scrape.

    Implements Z operations:
    - ScoutSearchSource: Search sources within permission tier
    - ScoutRevisitSource: Revisit a source with documented rationale
    """

    agent_type = AgentType.SCOUT

    # Source registry with tier classification
    SOURCE_REGISTRY: dict[str, SourceTier] = {
        "wikitree": SourceTier.TIER_0,
        "findagrave": SourceTier.TIER_0,
        "nara1940": SourceTier.TIER_0,
        "nara1950": SourceTier.TIER_0,
        "freebmd": SourceTier.TIER_0,
        "chronicling_america": SourceTier.TIER_0,
        "billiongraves": SourceTier.TIER_0,
        "accessgenealogy": SourceTier.TIER_0,
        "familysearch": SourceTier.TIER_1,
        "ancestry": SourceTier.TIER_2,
        "myheritage": SourceTier.TIER_2,
        "newspapers": SourceTier.TIER_2,
        "fold3": SourceTier.TIER_2,
    }

    async def execute(self, state: AncestryEngineState, **kwargs: Any) -> AncestryEngineState:
        """Execute a search task."""
        state.active_agent = self.agent_type

        task = kwargs.get("task")
        if not task:
            return state

        # Execute the search
        records = await self.search_sources(state, task)

        # Log the search
        self.log_action(
            state,
            action_type="source_access",
            rationale=f"Searched for: {task.query}",
            task_id=task.id,
            records_found=len(records),
            context=",".join(s.source for s in records) if records else "no sources",
        )

        # Store records for Analyst processing
        state._pending_records = records  # type: ignore

        return state

    async def search_sources(
        self,
        state: AncestryEngineState,
        task: Task,
    ) -> list[RawRecord]:
        """Search sources respecting permission tiers.

        Z Operation: ScoutSearchSource
        - Permission check: ∀ tier : task?.sourceConstraint • sourcePermissions(tier) = true
        """
        records = []
        allowed_tiers = task.source_constraints or [SourceTier.TIER_0]

        for source_name, tier in self.SOURCE_REGISTRY.items():
            # Check permission
            if tier not in allowed_tiers:
                continue
            if not state.source_permissions.is_tier_allowed(tier):
                logger.debug(f"Skipping {source_name}: tier {tier} not permitted")
                continue

            # Execute search (placeholder - would call actual source connector)
            try:
                source_records = await self._search_single_source(
                    source_name, tier, task.query or ""
                )
                records.extend(source_records)
            except Exception as e:
                logger.warning(f"Error searching {source_name}: {e}")
                continue

        return records

    async def _search_single_source(
        self,
        source_name: str,
        tier: SourceTier,
        query: str,
    ) -> list[RawRecord]:
        """Search a single source. Override in subclass for real implementation."""
        # This is a placeholder - real implementation would use source connectors
        # from gps_agents.sources.*
        return []

    async def revisit_source(
        self,
        state: AncestryEngineState,
        source: str,
        reason: str,
    ) -> list[RawRecord]:
        """Revisit a source with documented rationale.

        Z Operation: ScoutRevisitSource
        - Must have previous access to this source
        - Must provide rationale for revisit
        """
        # Validate reason
        valid_reasons = {
            "New hypothesis requires additional data",
            "Previous search parameters too narrow",
            "Conflict resolution requires corroboration",
            "Time-based record update check",
        }
        if reason not in valid_reasons:
            raise ValueError(f"Invalid revisit reason. Must be one of: {valid_reasons}")

        # Check previous access exists
        previous_access = any(
            entry.action_type == "source_access" and
            entry.context and source in entry.context
            for entry in state.research_log
        )
        if not previous_access:
            raise ValueError(f"No previous access to source: {source}")

        # Log the revisit
        self.log_action(
            state,
            action_type="revisit",
            rationale=reason,
            context=source,
            revisit_reason=[reason],
        )

        # Execute the revisit search
        tier = self.SOURCE_REGISTRY.get(source.lower(), SourceTier.TIER_0)
        return await self._search_single_source(source, tier, "")


# =============================================================================
# The Analyst (Intelligence)
# =============================================================================

class AnalystAgent(BaseAgent):
    """The Analyst: Conflict resolution and Clue generation.

    Implements Z operations:
    - AnalystGenerateHypotheses: Generate hypotheses from new records
    - AnalystResolveConflict: Resolve conflicting claims
    """

    agent_type = AgentType.ANALYST

    async def execute(self, state: AncestryEngineState, **kwargs: Any) -> AncestryEngineState:
        """Analyze records and generate hypotheses."""
        state.active_agent = self.agent_type

        records = kwargs.get("records", [])
        if hasattr(state, "_pending_records"):
            records = state._pending_records  # type: ignore
            delattr(state, "_pending_records")

        # Extract entities and generate hypotheses
        hypotheses = await self.generate_hypotheses(state, records)

        # Log the analysis
        self.log_action(
            state,
            action_type="analyze",
            rationale=f"Analyzed {len(records)} records, generated {len(hypotheses)} hypotheses",
            records_found=len(records),
        )

        return state

    async def generate_hypotheses(
        self,
        state: AncestryEngineState,
        records: list[RawRecord],
    ) -> list[ClueHypothesis]:
        """Generate hypotheses from new records.

        Z Operation: AnalystGenerateHypotheses
        - Extract entities from records
        - Generate hypotheses for new names
        - Generate hypotheses for new locations
        - Calculate priority based on information gain
        """
        hypotheses = []

        for record in records:
            # Extract entities
            names = self._extract_names(record)
            places = self._extract_places(record)
            dates = self._extract_dates(record)

            # Generate hypotheses for new names
            for name in names:
                if not self._name_in_graph(name, state):
                    priority = self._calculate_priority(name, state)
                    hypothesis = ClueHypothesis(
                        statement=f"Find vital records for {name}",
                        hypothesis_type="find_vital_records",
                        priority=priority,
                        suggested_sources=["wikitree", "findagrave", "freebmd"],
                    )
                    hypotheses.append(hypothesis)
                    state.add_hypothesis(hypothesis)

            # Generate hypotheses for places
            for place in places:
                priority = self._calculate_priority(place, state)
                hypothesis = ClueHypothesis(
                    statement=f"Search records in {place}",
                    hypothesis_type="search_location",
                    priority=priority * 0.8,  # Lower priority than names
                    suggested_sources=["nara1940", "chronicling_america"],
                )
                hypotheses.append(hypothesis)
                state.add_hypothesis(hypothesis)

        return hypotheses

    async def resolve_conflict(
        self,
        state: AncestryEngineState,
        person_id: UUID,
        field: str,
        claims: list[ConflictingClaim],
    ) -> ConflictResolution:
        """Resolve conflicting claims about a person.

        Z Operation: AnalystResolveConflict
        - Weight by evidence type and source tier
        - Select highest weighted claim

        Args:
            state: Current engine state
            person_id: UUID of the person with conflicting data
            field: Field name with conflict (e.g., "birth_date")
            claims: List of conflicting claims to resolve

        Returns:
            Resolution with selected claim and rationale
        """
        if len(claims) < 2:
            raise ValueError("Need at least 2 conflicting claims to resolve")

        # Calculate weights
        for claim in claims:
            claim.calculate_weight()

        # Sort by weight and select highest
        claims.sort(key=lambda c: c.weight, reverse=True)
        resolved = claims[0]

        # Create resolution record
        resolution = ConflictResolution(
            person_id=person_id,
            field=field,
            conflicting_claims=claims,
            resolved_claim=resolved,
            rationale=f"Selected claim '{resolved.claim}' with weight {resolved.weight:.3f} "
                     f"(evidence: {resolved.source.evidence_type.value}, "
                     f"tier: {resolved.source.tier.value}, "
                     f"confidence: {resolved.source.confidence:.2f})",
        )

        # Log the resolution
        self.log_action(
            state,
            action_type="conflict_resolution",
            rationale=resolution.rationale,
            context=f"{field} for person {person_id}",
        )

        return resolution

    def _extract_names(self, record: RawRecord) -> list[str]:
        """Extract person names from a record."""
        names = record.extracted_names.copy()

        # Also check extracted_fields
        for key in ["name", "given_name", "surname", "spouse", "parent", "child"]:
            if key in record.extracted_fields:
                value = record.extracted_fields[key]
                if isinstance(value, str) and value:
                    names.append(value)
                elif isinstance(value, list):
                    names.extend([v for v in value if isinstance(v, str)])

        return list(set(names))

    def _extract_places(self, record: RawRecord) -> list[str]:
        """Extract place names from a record."""
        places = record.extracted_places.copy()

        for key in ["place", "location", "birth_place", "death_place", "residence"]:
            if key in record.extracted_fields:
                value = record.extracted_fields[key]
                if isinstance(value, str) and value:
                    places.append(value)

        return list(set(places))

    def _extract_dates(self, record: RawRecord) -> list[str]:
        """Extract dates from a record."""
        dates = record.extracted_dates.copy()

        for key in ["date", "birth_date", "death_date", "marriage_date"]:
            if key in record.extracted_fields:
                value = record.extracted_fields[key]
                if isinstance(value, str) and value:
                    dates.append(value)

        return list(set(dates))

    def _name_in_graph(self, name: str, state: AncestryEngineState) -> bool:
        """Check if a name already exists in the knowledge graph."""
        name_lower = name.lower()
        for person in state.knowledge_graph.values():
            if name_lower in person.full_name.lower():
                return True
        return False

    def _calculate_priority(self, entity: str, state: AncestryEngineState) -> float:
        """Calculate priority based on information gain.

        Z: calculatePriority(e, g) = 1 - (existingEvidence / (existingEvidence + 1))
        """
        # Count existing evidence for this entity
        evidence_count = 0
        entity_lower = entity.lower()

        for person in state.knowledge_graph.values():
            if entity_lower in person.full_name.lower():
                evidence_count += len(person.sources)
            for place in person.birth_places + person.death_places:
                if entity_lower in place.lower():
                    evidence_count += 1

        # Information gain formula
        return 1 - (evidence_count / (evidence_count + 1))


# =============================================================================
# The Censor (Compliance)
# =============================================================================

class CensorAgent(BaseAgent):
    """The Censor: PII/ToS compliance.

    Implements Z operations:
    - CensorValidateOutput: Check and redact PII for living persons
    - CensorCheckSourceAccess: Validate ToS compliance for source access
    """

    agent_type = AgentType.CENSOR

    # Living person threshold (100 years)
    LIVING_PERSON_YEARS = 100

    # ToS rules per source
    TOS_RULES: dict[str, dict[str, list[str]]] = {
        "wikitree": {
            "allowed": ["search", "browse", "api_read"],
            "prohibited": ["bulk_scrape", "commercial_use"],
        },
        "findagrave": {
            "allowed": ["search", "browse"],
            "prohibited": ["bulk_scrape", "download_images"],
        },
        "ancestry": {
            "allowed": ["search", "browse", "download_record"],
            "prohibited": ["bulk_scrape", "redistribution"],
        },
        "familysearch": {
            "allowed": ["search", "browse", "api_read"],
            "prohibited": ["bulk_scrape", "commercial_use"],
        },
    }

    async def execute(self, state: AncestryEngineState, **kwargs: Any) -> AncestryEngineState:
        """Execute compliance validation."""
        state.active_agent = self.agent_type
        return state

    def validate_output(self, person: Person) -> tuple[Person, list[str]]:
        """Validate and redact PII for output.

        Z Operation: CensorValidateOutput
        - Check if person is living (born < 100 years ago, no death date)
        - Redact if living
        """
        violations = []
        current_year = datetime.now(UTC).year

        # Check if living person
        is_living = False
        if person.birth_dates and not person.death_dates:
            for birth_date in person.birth_dates:
                year = self._extract_year(birth_date)
                if year and (current_year - year) < self.LIVING_PERSON_YEARS:
                    is_living = True
                    break

        if is_living:
            # Redact PII
            violations.append("Living person PII redacted")
            person = self._redact_living_pii(person)

        return person, violations

    def check_source_access(
        self,
        state: AncestryEngineState,
        source: str,
        action: str,
    ) -> tuple[bool, str]:
        """Check if source access is permitted.

        Z Operation: CensorCheckSourceAccess
        - Check ToS rules for the source
        - Log compliance decision
        """
        source_lower = source.lower()
        rules = self.TOS_RULES.get(source_lower, {"allowed": ["search", "browse"], "prohibited": []})

        if action in rules.get("prohibited", []):
            reason = f"Action prohibited by ToS: {source}"
            self.log_action(
                state,
                action_type="compliance_check",
                rationale=reason,
                context=f"source={source}, action={action}",
                success=False,
            )
            return False, reason

        if action in rules.get("allowed", []):
            reason = "Action permitted"
            self.log_action(
                state,
                action_type="compliance_check",
                rationale=reason,
                context=f"source={source}, action={action}",
                success=True,
            )
            return True, reason

        # Default: allow with warning
        reason = f"Action not explicitly covered by ToS for {source}"
        return True, reason

    def _redact_living_pii(self, person: Person) -> Person:
        """Redact PII for a living person.

        Z: redactLivingPII - approximate decade, generalize place
        """
        # Create a copy with redacted data
        redacted = person.model_copy()

        # Approximate birth date to decade
        if redacted.birth_dates:
            new_dates = []
            for date in redacted.birth_dates:
                year = self._extract_year(date)
                if year:
                    decade = (year // 10) * 10
                    new_dates.append(f"{decade}s")
            redacted.birth_dates = new_dates if new_dates else ["[redacted]"]

        # Generalize birth place to state/country only
        if redacted.birth_places:
            new_places = []
            for place in redacted.birth_places:
                # Keep only state/country level
                parts = place.split(",")
                if len(parts) >= 2:
                    new_places.append(", ".join(parts[-2:]).strip())
                else:
                    new_places.append("[redacted]")
            redacted.birth_places = new_places

        return redacted

    def _extract_year(self, date_str: str) -> int | None:
        """Extract year from a date string."""
        if not date_str:
            return None
        match = re.search(r"\b(\d{4})\b", date_str)
        if match:
            return int(match.group(1))
        return None
