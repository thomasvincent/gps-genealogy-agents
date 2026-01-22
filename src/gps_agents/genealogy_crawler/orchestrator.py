"""Orchestrator for the genealogical crawler.

Implements the iterative enrichment loop with:
- LLM-driven planning
- Queue management (Frontier, Clue, Revisit)
- Stop condition checking
- Revisit scheduling
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID, uuid4

from .llm import (
    LLMRegistry,
    PlannerInput,
    PlannerOutput,
    create_llm_registry,
)
from .models import (
    AuditActionType,
    ClueItem,
    CrawlerState,
    FrontierItem,
    HypothesisType,
    Person,
    QueueItemStatus,
    RevisitItem,
    SourceTier,
)

if TYPE_CHECKING:
    from .llm import LLMClient
    from .publishing import (
        GPSPillar,
        PublishingManager,
        PublishingPipeline,
        SearchRevisionAgentLLM,
        SearchRevisionInput,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# Stop Conditions
# =============================================================================


def check_budget_exhausted(state: CrawlerState) -> bool:
    """Check if budget is exhausted."""
    return state.budget_used >= state.budget_limit


def check_confidence_achieved(state: CrawlerState) -> bool:
    """Check if target confidence is met for required generations."""
    if not state.seed_person_id:
        return False

    seed = state.get_person(state.seed_person_id)
    if not seed:
        return False

    # Check if we've reached target generations with good confidence
    # This is a simplified check - real implementation would traverse tree
    return seed.confidence >= 0.9


def check_diminishing_returns(state: CrawlerState) -> bool:
    """Check for diminishing returns in discovery rate."""
    return (
        state.recent_discovery_rate < 0.1 and
        state.queries_since_last_discovery > 10
    )


def check_frontier_empty(state: CrawlerState) -> bool:
    """Check if all queues are empty."""
    return (
        len(state.frontier_queue) == 0 and
        len(state.clue_queue) == 0 and
        len(state.revisit_queue) == 0
    )


def check_max_iterations(state: CrawlerState) -> bool:
    """Check if max iterations reached."""
    return state.iteration_count >= state.max_iterations


# Default stop conditions
STOP_CONDITIONS: dict[str, Callable[[CrawlerState], bool]] = {
    "budget_exhausted": check_budget_exhausted,
    "confidence_achieved": check_confidence_achieved,
    "diminishing_returns": check_diminishing_returns,
    "frontier_empty": check_frontier_empty,
    "max_iterations": check_max_iterations,
}


# =============================================================================
# Revisit Scheduler
# =============================================================================


@dataclass
class RevisitScheduler:
    """Schedules revisits to sources based on new discoveries.

    Supports optional durable storage via SQLiteProjection for persistence
    across process restarts.
    """

    min_revisit_interval_hours: float = 24.0
    max_revisits_per_source: int = 3
    revisit_history: dict[str, list[datetime]] = field(default_factory=dict)
    _projection: Any = field(default=None, repr=False)  # SQLiteProjection for persistence

    def set_projection(self, projection: Any) -> None:
        """Set the SQLiteProjection for durable revisit history storage.

        Args:
            projection: SQLiteProjection instance with revisit_history table
        """
        self._projection = projection
        # Load existing history from projection
        if projection is not None:
            stored = projection.load_all_revisit_history()
            for source_key, timestamps in stored.items():
                self.revisit_history[source_key] = [
                    datetime.fromisoformat(ts) for ts in timestamps
                ]

    def should_revisit(
        self,
        source_id: UUID,
        state: CrawlerState,
    ) -> bool:
        """Determine if a source should be revisited.

        Args:
            source_id: The source record ID
            state: Current crawler state

        Returns:
            True if source should be revisited
        """
        source_key = str(source_id)

        # Check revisit history (use count from projection if available)
        if self._projection is not None:
            count = self._projection.get_revisit_count(source_key)
            if count >= self.max_revisits_per_source:
                return False
            # Load timestamps to check interval
            timestamps = self._projection.get_revisit_history(source_key)
            if timestamps:
                last_visit = datetime.fromisoformat(max(timestamps))
                hours_since = (datetime.now(UTC) - last_visit).total_seconds() / 3600
                if hours_since < self.min_revisit_interval_hours:
                    return False
        else:
            # Fallback to in-memory history
            history = self.revisit_history.get(source_key, [])
            if len(history) >= self.max_revisits_per_source:
                return False
            if history:
                last_visit = max(history)
                hours_since = (datetime.now(UTC) - last_visit).total_seconds() / 3600
                if hours_since < self.min_revisit_interval_hours:
                    return False

        return True

    def record_revisit(self, source_id: UUID) -> None:
        """Record a revisit to a source.

        Persists to SQLiteProjection if configured, otherwise stores in memory.
        """
        source_key = str(source_id)
        now = datetime.now(UTC)

        # Update in-memory cache
        if source_key not in self.revisit_history:
            self.revisit_history[source_key] = []
        self.revisit_history[source_key].append(now)

        # Persist to projection if available
        if self._projection is not None:
            self._projection.record_revisit(source_key, now.isoformat())

    def generate_revisit_item(
        self,
        source_id: UUID,
        original_query: str,
        improved_query: str,
        reason: str,
        triggering_clue_id: UUID | None = None,
    ) -> RevisitItem:
        """Generate a revisit queue item."""
        return RevisitItem(
            original_source_id=source_id,
            original_query=original_query,
            improved_query=improved_query,
            revisit_reason=reason,
            triggering_clue_id=triggering_clue_id,
            priority=0.6,  # Medium priority for revisits
        )


# =============================================================================
# Query Generator
# =============================================================================


def generate_person_queries(
    person: Person,
    context: dict[str, Any] | None = None,
) -> list[FrontierItem]:
    """Generate search queries for a person.

    Creates multiple query variants to maximize discovery potential.
    """
    queries: list[FrontierItem] = []
    context = context or {}

    # Base name queries
    name_variants = [person.canonical_name]
    name_variants.extend(person.name_variants)

    for name in name_variants[:5]:  # Limit variants
        # Standard name search
        queries.append(FrontierItem(
            target_entity_id=person.id,
            target_entity_type="person",
            query_string=name,
            source_tiers=[SourceTier.TIER_0],
            context={"query_type": "name_search", **context},
            priority=0.8,
        ))

        # Name + birth year
        if person.birth_date_earliest:
            birth_year = person.birth_date_earliest.year
            queries.append(FrontierItem(
                target_entity_id=person.id,
                target_entity_type="person",
                query_string=f"{name} born {birth_year}",
                source_tiers=[SourceTier.TIER_0],
                context={"query_type": "name_birth_search", **context},
                priority=0.85,
            ))

        # Name + death year
        if person.death_date_earliest:
            death_year = person.death_date_earliest.year
            queries.append(FrontierItem(
                target_entity_id=person.id,
                target_entity_type="person",
                query_string=f"{name} died {death_year}",
                source_tiers=[SourceTier.TIER_0],
                context={"query_type": "name_death_search", **context},
                priority=0.75,
            ))

        # Name + place
        if person.birth_place:
            queries.append(FrontierItem(
                target_entity_id=person.id,
                target_entity_type="person",
                query_string=f"{name} {person.birth_place}",
                source_tiers=[SourceTier.TIER_0],
                context={"query_type": "name_place_search", **context},
                priority=0.7,
            ))

    return queries


# =============================================================================
# Orchestrator
# =============================================================================


class Orchestrator:
    """Main orchestrator for the genealogical crawler.

    Implements the iterative enrichment loop:
    1. Pop from queues (Frontier > Clue > Revisit)
    2. Process item
    3. Update knowledge graph
    4. Generate new queue items
    5. Check stop conditions
    """

    def __init__(
        self,
        llm_registry: LLMRegistry | None = None,
        llm_client: "LLMClient | None" = None,
        stop_conditions: dict[str, Callable[[CrawlerState], bool]] | None = None,
        publishing_manager: "PublishingManager | None" = None,
        search_revision_agent: "SearchRevisionAgentLLM | None" = None,
        sqlite_projection: Any | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            llm_registry: Pre-configured LLM registry
            llm_client: LLM client (used if registry not provided)
            stop_conditions: Custom stop conditions (defaults to STOP_CONDITIONS)
            publishing_manager: Optional PublishingManager for finalizing research
            search_revision_agent: Optional SearchRevisionAgentLLM for Pillar 1 remediation
            sqlite_projection: Optional SQLiteProjection for durable revisit history
        """
        if llm_registry is None:
            llm_registry = create_llm_registry(client=llm_client)

        self._llm = llm_registry
        self._stop_conditions = stop_conditions or STOP_CONDITIONS
        self._revisit_scheduler = RevisitScheduler()
        self._publishing_manager = publishing_manager
        self._search_revision_agent = search_revision_agent

        # Wire up durable storage for revisit scheduler
        if sqlite_projection is not None:
            self._revisit_scheduler.set_projection(sqlite_projection)

    def initialize_from_seed(
        self,
        seed_person: Person,
        state: CrawlerState | None = None,
    ) -> CrawlerState:
        """Initialize crawler state from a seed person.

        Args:
            seed_person: The person to start research from
            state: Optional existing state to use

        Returns:
            Initialized CrawlerState
        """
        if state is None:
            state = CrawlerState()

        # Add seed person
        state.add_person(seed_person)
        state.seed_person_id = seed_person.id

        # Generate initial queries
        queries = generate_person_queries(seed_person)
        for query in queries:
            state.add_to_frontier(query)

        # Log initialization
        state.log_audit(
            action=AuditActionType.CREATE,
            entity_id=seed_person.id,
            entity_type="person",
            agent="orchestrator",
            rationale="Seed person initialization",
        )

        logger.info(
            f"Initialized crawler with seed person: {seed_person.canonical_name}, "
            f"generated {len(state.frontier_queue)} initial queries"
        )

        return state

    def check_stop_conditions(self, state: CrawlerState) -> tuple[bool, str | None]:
        """Check all stop conditions.

        Returns:
            Tuple of (should_stop, reason)
        """
        for name, condition in self._stop_conditions.items():
            if condition(state):
                return True, name
        return False, None

    def _build_planner_input(self, state: CrawlerState) -> PlannerInput:
        """Build input for the planner LLM."""
        return PlannerInput(
            current_state={
                "persons_discovered": len(state.persons),
                "assertions_made": len(state.assertions),
                "sources_queried": len(state.source_records),
                "budget_remaining": state.budget_limit - state.budget_used,
                "frontier_size": len(state.frontier_queue),
                "clue_queue_size": len(state.clue_queue),
                "iteration": state.iteration_count,
            },
            recent_discoveries=[
                {"person": p.canonical_name, "id": str(p.id)}
                for p in list(state.persons.values())[-5:]
            ],
            pending_clues=[
                {
                    "type": c.hypothesis_type.value,
                    "text": c.hypothesis_text,
                    "priority": c.priority,
                }
                for c in state.clue_queue[:10]
            ],
            stop_conditions={
                name: condition(state)
                for name, condition in self._stop_conditions.items()
            },
        )

    def _process_planner_output(
        self,
        output: PlannerOutput,
        state: CrawlerState,
    ) -> None:
        """Process planner output and update state."""
        for action in output.next_actions:
            if action.action == "fetch" and action.query:
                item = FrontierItem(
                    query_string=action.query,
                    source_tiers=[SourceTier(action.source_tier)],
                    priority=action.priority,
                    context={"planner_reason": action.reason},
                )
                state.add_to_frontier(item)

            elif action.action == "revisit" and action.target_id:
                # Find original source
                source_id = UUID(action.target_id)
                if self._revisit_scheduler.should_revisit(source_id, state):
                    revisit = self._revisit_scheduler.generate_revisit_item(
                        source_id=source_id,
                        original_query=action.query or "",
                        improved_query=action.query or "",
                        reason=action.reason or "Planner recommended revisit",
                    )
                    state.add_revisit(revisit)

        # Process revisit recommendations
        for rec in output.revisit_schedule:
            source_id = UUID(rec.source_id)
            if self._revisit_scheduler.should_revisit(source_id, state):
                revisit = self._revisit_scheduler.generate_revisit_item(
                    source_id=source_id,
                    original_query=rec.original_query,
                    improved_query=rec.improved_query,
                    reason=rec.reason,
                )
                revisit.priority = rec.priority
                state.add_revisit(revisit)

    def process_clue(self, clue: ClueItem, state: CrawlerState) -> None:
        """Process a clue from the ClueQueue.

        Generates new frontier items based on the hypothesis.
        """
        clue.status = QueueItemStatus.IN_PROGRESS

        # Generate queries from suggested queries
        for query in clue.suggested_queries:
            item = FrontierItem(
                target_entity_id=clue.related_person_id,
                target_entity_type="person" if clue.related_person_id else None,
                query_string=query,
                source_tiers=[SourceTier.TIER_0],
                context={
                    "from_clue": str(clue.id),
                    "hypothesis_type": clue.hypothesis_type.value,
                },
                priority=clue.priority,
            )
            state.add_to_frontier(item)

        # If hypothesis suggests a relationship, could trigger revisits
        if clue.hypothesis_type in (
            HypothesisType.PARENTAL_DISCOVERY,
            HypothesisType.SPOUSAL_DISCOVERY,
            HypothesisType.SIBLING_DISCOVERY,
        ):
            # Could revisit related sources with new context
            if clue.related_source_id:
                if self._revisit_scheduler.should_revisit(
                    clue.related_source_id, state
                ):
                    revisit = self._revisit_scheduler.generate_revisit_item(
                        source_id=clue.related_source_id,
                        original_query=clue.hypothesis_text,
                        improved_query=clue.suggested_queries[0] if clue.suggested_queries else "",
                        reason=f"Follow up on {clue.hypothesis_type.value} hypothesis",
                        triggering_clue_id=clue.id,
                    )
                    state.add_revisit(revisit)

        clue.status = QueueItemStatus.COMPLETED

    def run_planning_step(self, state: CrawlerState) -> PlannerOutput | None:
        """Run a planning step using the LLM planner.

        Returns:
            PlannerOutput if successful, None if should stop
        """
        # Build input
        planner_input = self._build_planner_input(state)

        # Call planner
        try:
            output = self._llm.planner.plan(planner_input)
        except ValueError as e:
            logger.error(f"Planner failed: {e}")
            return None

        # Check if planner says stop
        if output.should_stop:
            state.is_terminated = True
            state.termination_reason = output.stop_reason
            return output

        # Process output
        self._process_planner_output(output, state)

        return output

    def step(self, state: CrawlerState) -> bool:
        """Execute a single step of the crawler loop.

        Args:
            state: Current crawler state

        Returns:
            True if should continue, False if should stop
        """
        state.iteration_count += 1

        # Check stop conditions first
        should_stop, reason = self.check_stop_conditions(state)
        if should_stop:
            state.is_terminated = True
            state.termination_reason = reason
            logger.info(f"Stopping: {reason}")
            return False

        # Priority: Frontier > Clue > Revisit
        # In a real implementation, these would trigger crawl/verify cycles

        # Process frontier item
        frontier_item = state.pop_frontier()
        if frontier_item:
            logger.debug(f"Processing frontier item: {frontier_item.query_string}")
            # Mark as executed for novelty tracking
            for tier in frontier_item.source_tiers:
                state.novelty_guard.record_query(
                    frontier_item.query_string, tier
                )
            # Real implementation would: fetch -> parse -> verify -> resolve
            state.queries_since_last_discovery += 1
            return True

        # Process clue item
        clue_item = state.pop_clue()
        if clue_item:
            logger.debug(f"Processing clue: {clue_item.hypothesis_text[:50]}")
            self.process_clue(clue_item, state)
            return True

        # Process revisit item
        revisit_item = state.pop_revisit()
        if revisit_item:
            logger.debug(f"Processing revisit: {revisit_item.improved_query}")
            self._revisit_scheduler.record_revisit(revisit_item.original_source_id)
            # Add improved query to frontier
            item = FrontierItem(
                query_string=revisit_item.improved_query,
                source_tiers=[SourceTier.TIER_0],
                context={
                    "revisit_of": str(revisit_item.original_source_id),
                    "reason": revisit_item.revisit_reason,
                },
                priority=revisit_item.priority,
            )
            state.add_to_frontier(item)
            return True

        # All queues empty - run planner for more ideas
        logger.info("All queues empty, running planner for next steps")
        output = self.run_planning_step(state)
        if output is None or output.should_stop:
            return False

        # If planner added nothing, stop
        if (
            len(state.frontier_queue) == 0 and
            len(state.clue_queue) == 0 and
            len(state.revisit_queue) == 0
        ):
            state.is_terminated = True
            state.termination_reason = "frontier_empty"
            return False

        return True

    def run(
        self,
        state: CrawlerState,
        max_steps: int | None = None,
    ) -> CrawlerState:
        """Run the crawler loop until stop condition.

        Args:
            state: Initial crawler state
            max_steps: Optional maximum steps (overrides state.max_iterations)

        Returns:
            Final CrawlerState
        """
        state.is_running = True
        max_steps = max_steps or state.max_iterations

        logger.info(f"Starting crawler run, max_steps={max_steps}")

        while state.iteration_count < max_steps:
            if not self.step(state):
                break

        state.is_running = False
        logger.info(
            f"Crawler finished after {state.iteration_count} iterations. "
            f"Reason: {state.termination_reason}"
        )

        return state

    def finalize_research(
        self,
        state: CrawlerState,
        subject_id: str,
        subject_name: str,
    ) -> "PublishingPipeline | None":
        """Finalize research and prepare for publishing.

        Creates a publishing pipeline, grades research against GPS pillars,
        and returns the pipeline ready for quorum review.

        Args:
            state: Final crawler state with research results
            subject_id: ID of the person to publish
            subject_name: Name of the person

        Returns:
            PublishingPipeline if publishing_manager is configured, None otherwise
        """
        if not self._publishing_manager:
            logger.warning("No publishing_manager configured, cannot finalize")
            return None

        # Gather statistics from state
        source_count = len(state.source_records)
        source_tiers = {
            "tier_0": sum(1 for s in state.source_records.values() if s.tier == SourceTier.TIER_0),
            "tier_1": sum(1 for s in state.source_records.values() if s.tier == SourceTier.TIER_1),
            "tier_2": sum(1 for s in state.source_records.values() if s.tier == SourceTier.TIER_2),
        }

        # Count cited claims
        total_claims = len(state.assertions)
        citation_count = sum(
            1 for a in state.assertions.values()
            if a.evidence_claim_ids and len(a.evidence_claim_ids) > 0
        )

        # Count conflicts from merge clusters
        conflicts_found = sum(
            1 for mc in state.merge_clusters.values()
            if mc.competing_assertions and len(mc.competing_assertions) > 1
        )
        conflicts_resolved = sum(
            1 for mc in state.merge_clusters.values()
            if mc.resolved_winner_id is not None
        )

        # Prepare pipeline
        pipeline = self._publishing_manager.prepare_for_publishing(
            subject_id=subject_id,
            subject_name=subject_name,
            source_count=source_count,
            source_tiers=source_tiers,
            citation_count=citation_count,
            total_claims=total_claims,
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            uncertainties_documented=0,  # Would need Paper Trail tracking
            has_written_conclusion=False,  # Would need conclusion tracking
        )

        logger.info(
            f"Finalized research for {subject_name}: "
            f"Grade {pipeline.grade_card.letter_grade if pipeline.grade_card else 'N/A'}"
        )

        # Check if Pillar 1 (Reasonably Exhaustive Search) failed and trigger revision
        if pipeline.grade_card and self._search_revision_agent:
            pillar1_score = pipeline.grade_card.get_pillar_score("REASONABLY_EXHAUSTIVE_SEARCH")
            if pillar1_score and pillar1_score.score < 7.0:
                logger.info(
                    f"Pillar 1 score {pillar1_score.score:.1f} < 7.0, triggering search revision"
                )
                self._trigger_search_revision(
                    state=state,
                    subject_id=subject_id,
                    subject_name=subject_name,
                    pillar_feedback=pillar1_score.improvements_needed,
                )

        return pipeline

    def _trigger_search_revision(
        self,
        state: CrawlerState,
        subject_id: str,
        subject_name: str,
        pillar_feedback: list[str] | None = None,
    ) -> int:
        """Trigger Search Revision Agent when Pillar 1 fails.

        Generates tiebreaker search queries and adds them to the revisit queue
        with high priority.

        Args:
            state: Current crawler state
            subject_id: ID of the person being researched
            subject_name: Name of the person
            pillar_feedback: Feedback from GPS grader about missing sources

        Returns:
            Number of queries added to revisit queue
        """
        if not self._search_revision_agent:
            logger.warning("No search_revision_agent configured")
            return 0

        # Import here to avoid circular imports
        from .publishing import GPSPillar, MissingSourceClass, SearchRevisionInput

        # Robust category mapping with keyword synonyms and metadata
        # Each category has: keywords (list), priority (int), repositories (list)
        SOURCE_CATEGORY_RULES: list[tuple[str, list[str], int, list[str]]] = [
            (
                "vital_records",
                ["vital", "birth", "death", "marriage", "certificate", "registry", "civil registration"],
                1,
                ["FamilySearch", "Ancestry", "State Archives", "County Clerk"],
            ),
            (
                "census",
                ["census", "enumeration", "population schedule", "household"],
                2,
                ["Ancestry", "FamilySearch", "NARA", "MyHeritage"],
            ),
            (
                "military",
                ["military", "service record", "draft", "veteran", "enlistment", "pension", "regiment"],
                3,
                ["Fold3", "NARA", "Ancestry", "National Archives"],
            ),
            (
                "church_records",
                ["church", "parish", "baptism", "christening", "burial", "confirmation", "diocese"],
                2,
                ["FamilySearch", "Ancestry", "Diocesan Archives", "Local Parish"],
            ),
            (
                "newspapers",
                ["newspaper", "obituary", "announcement", "notice", "periodical", "gazette"],
                3,
                ["Newspapers.com", "Chronicling America", "GenealogyBank", "Ancestry"],
            ),
            (
                "probate",
                ["probate", "will", "estate", "inheritance", "testament", "intestate"],
                2,
                ["FamilySearch", "Ancestry", "County Courthouse", "State Archives"],
            ),
            (
                "land_records",
                ["land", "deed", "property", "tax", "mortgage", "grantor", "grantee"],
                3,
                ["FamilySearch", "BLM GLO Records", "County Recorder", "State Archives"],
            ),
            (
                "immigration",
                ["immigration", "emigration", "passenger", "naturalization", "ship manifest", "port"],
                2,
                ["Ancestry", "FamilySearch", "Ellis Island", "NARA"],
            ),
        ]

        def classify_feedback(feedback_text: str) -> MissingSourceClass:
            """Classify feedback into a source category using keyword matching."""
            feedback_lower = feedback_text.lower()

            for category, keywords, priority, repositories in SOURCE_CATEGORY_RULES:
                if any(keyword in feedback_lower for keyword in keywords):
                    return MissingSourceClass(
                        category=category,
                        description=feedback_text,
                        priority=priority,
                        suggested_repositories=repositories,
                    )

            # Fallback for unrecognized feedback
            return MissingSourceClass(
                category="other",
                description=feedback_text,
                priority=4,
                suggested_repositories=["FamilySearch", "Ancestry"],
            )

        # Parse pillar feedback to identify missing source classes
        missing_classes = [classify_feedback(fb) for fb in (pillar_feedback or [])]

        # Extract name parts from subject_name
        name_parts = subject_name.split()
        given_name = name_parts[0] if name_parts else ""
        surname = name_parts[-1] if len(name_parts) > 1 else name_parts[0] if name_parts else ""

        # Get birth/death years from seed person if available
        seed = state.get_person(state.seed_person_id) if state.seed_person_id else None
        birth_year = None
        death_year = None
        locations: list[str] = []

        if seed:
            for event in seed.events:
                if event.type.value == "birth" and event.date:
                    try:
                        birth_year = int(event.date[:4])
                    except (ValueError, IndexError):
                        pass
                    if event.place:
                        locations.append(event.place)
                elif event.type.value == "death" and event.date:
                    try:
                        death_year = int(event.date[:4])
                    except (ValueError, IndexError):
                        pass
                    if event.place:
                        locations.append(event.place)

        # Build search revision input
        revision_input = SearchRevisionInput(
            subject_id=subject_id,
            subject_name=subject_name,
            given_name=given_name,
            surname=surname,
            birth_year=birth_year,
            death_year=death_year,
            known_locations=locations,
            current_source_count=len(state.source_records),
            current_pillar1_score=7.0,  # Below threshold
            missing_source_classes=missing_classes,
            gps_feedback=pillar_feedback or [],
        )

        # Generate tiebreaker queries using the agent's helper methods
        name_variants = self._search_revision_agent.generate_name_variants(
            given_name=given_name,
            surname=surname,
        )
        date_ranges = self._search_revision_agent.generate_date_ranges(
            birth_year=birth_year,
            death_year=death_year,
        )
        archives = self._search_revision_agent.identify_regional_archives(
            locations=locations,
            country_of_origin=None,  # Could be inferred from location analysis
        )
        negative_targets = self._search_revision_agent.generate_negative_searches(
            subject_name=subject_name,
            known_locations=locations,
            birth_year=birth_year,
            death_year=death_year,
        )

        # Build search queries
        queries = self._search_revision_agent.build_search_queries(
            input_data=revision_input,
            name_variants=name_variants,
            date_ranges=date_ranges,
            archives=archives,
            negative_targets=negative_targets,
        )

        # Add queries to revisit queue with high priority
        added_count = 0
        for query in queries:
            revisit_item = RevisitItem(
                id=uuid4(),
                original_source_id=uuid4(),  # New search, no original
                original_query=subject_name,  # Base search was for subject
                improved_query=query.query_string,
                revisit_reason=f"Search Revision: {query.strategy.value} - {query.rationale}",
                context={
                    "strategy": query.strategy.value,
                    "target_repository": query.target_repository,
                    "location": query.location,
                },
                priority=0.9,  # High priority for search revision
            )
            state.add_revisit(revisit_item)
            added_count += 1

        logger.info(
            f"Search Revision Agent added {added_count} tiebreaker queries to revisit queue"
        )
        return added_count
