"""LangGraph Plan-and-Execute loop for The Ancestry Engine.

This module implements the orchestration graph as specified in Z notation:
┌─ PlanAndExecuteLoop ──────────────────────────────────┐
│ ── Loop body (one iteration)                          │
│ LeadSelectTask ;                                      │
│ (ScoutSearchSource ∨ AnalystGenerateHypotheses) ;     │
│ CensorValidateOutput ;                                │
│ LeadUpdateState ;                                     │
│ LeadCheckTermination                                  │
└───────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from .agents import AnalystAgent, CensorAgent, LeadAgent, ScoutAgent
from .models import (
    AgentType,
    AncestryEngineState,
    ClueHypothesis,
    HypothesisStatus,
    LogEntry,
    Person,
    RawRecord,
    Task,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Extended State for Graph (adds transient fields)
# =============================================================================


class GraphState(AncestryEngineState):
    """Extended state with transient fields for graph execution.

    Adds fields needed for passing data between nodes that shouldn't
    persist in the core AncestryEngineState.
    """
    # Transient fields for inter-node communication
    current_task: Task | None = None
    pending_records: list[RawRecord] = Field(default_factory=list)

    class Config:
        # Allow extra fields for LangGraph compatibility
        extra = "allow"


# =============================================================================
# Shared Agent Instances (fixes instantiation antipattern)
# =============================================================================


class AgentRegistry:
    """Registry of shared agent instances."""

    _lead: LeadAgent | None = None
    _scout: ScoutAgent | None = None
    _analyst: AnalystAgent | None = None
    _censor: CensorAgent | None = None
    _llm_client: Any = None

    @classmethod
    def initialize(cls, llm_client: Any = None) -> None:
        """Initialize all agents with optional LLM client."""
        cls._llm_client = llm_client
        cls._lead = LeadAgent(llm_client)
        cls._scout = ScoutAgent(llm_client)
        cls._analyst = AnalystAgent(llm_client)
        cls._censor = CensorAgent(llm_client)

    @classmethod
    def lead(cls) -> LeadAgent:
        if cls._lead is None:
            cls._lead = LeadAgent(cls._llm_client)
        return cls._lead

    @classmethod
    def scout(cls) -> ScoutAgent:
        if cls._scout is None:
            cls._scout = ScoutAgent(cls._llm_client)
        return cls._scout

    @classmethod
    def analyst(cls) -> AnalystAgent:
        if cls._analyst is None:
            cls._analyst = AnalystAgent(cls._llm_client)
        return cls._analyst

    @classmethod
    def censor(cls) -> CensorAgent:
        if cls._censor is None:
            cls._censor = CensorAgent(cls._llm_client)
        return cls._censor


# =============================================================================
# Node Functions (LangGraph nodes mapping to Z operations)
# =============================================================================


async def lead_select_task(state: GraphState) -> dict[str, Any]:
    """Z Operation: LeadSelectTask.

    Peek at the highest priority task for routing decisions.
    Does NOT pop the task - that happens in the execution node.
    """
    lead = AgentRegistry.lead()

    # Check termination conditions first (doesn't modify queue)
    terminated = lead._check_termination(state)

    # Peek at highest priority task for routing (don't pop yet)
    selected_task = None
    if state.frontier_queue and not terminated:
        # Sort to ensure highest priority is first
        sorted_queue = sorted(state.frontier_queue, key=lambda t: t.priority, reverse=True)
        selected_task = sorted_queue[0]

    # Log the selection
    if selected_task:
        lead.log_action(
            state,
            action_type="task_selection",
            rationale=f"Selected task: {selected_task.description} (priority: {selected_task.priority:.2f})",
            task_id=selected_task.id,
        )

    return {
        "active_agent": AgentType.LEAD,
        "terminated": state.terminated,
        "termination_reason": state.termination_reason,
        "research_log": list(state.research_log),  # Return copy to avoid mutation
    }


async def scout_search(state: GraphState) -> dict[str, Any]:
    """Z Operation: ScoutSearchSource.

    Pop and execute the highest priority search task.
    """
    scout = AgentRegistry.scout()

    # Pop the task now (this is the only place we pop)
    if not state.frontier_queue:
        return {"active_agent": AgentType.SCOUT, "pending_records": []}

    # Sort and pop highest priority
    sorted_queue = sorted(state.frontier_queue, key=lambda t: t.priority, reverse=True)
    task = sorted_queue[0]
    remaining_queue = sorted_queue[1:]

    # Execute search
    records = await scout.search_sources(state, task)

    # Log the search
    scout.log_action(
        state,
        action_type="source_access",
        rationale=f"Searched for: {task.query}",
        task_id=task.id,
        records_found=len(records),
        context=",".join(r.source for r in records) if records else "no sources",
    )

    return {
        "active_agent": AgentType.SCOUT,
        "frontier_queue": remaining_queue,  # Return updated queue
        "current_task": task,
        "pending_records": records,
        "research_log": list(state.research_log),
    }


async def analyst_analyze(state: GraphState) -> dict[str, Any]:
    """Z Operation: AnalystGenerateHypotheses.

    Analyze records, extract entities, generate hypotheses.
    """
    analyst = AgentRegistry.analyst()

    # Get pending records from state
    records = state.pending_records or []

    # Generate hypotheses from records
    new_hypotheses = await analyst.generate_hypotheses(state, records)

    # Merge with existing hypotheses
    all_hypotheses = list(state.hypotheses) + new_hypotheses

    # Log the analysis
    analyst.log_action(
        state,
        action_type="analyze",
        rationale=f"Analyzed {len(records)} records, generated {len(new_hypotheses)} hypotheses",
        records_found=len(records),
    )

    return {
        "active_agent": AgentType.ANALYST,
        "hypotheses": all_hypotheses,
        "pending_records": [],  # Clear after processing
        "research_log": list(state.research_log),
    }


async def censor_validate(state: GraphState) -> dict[str, Any]:
    """Z Operation: CensorValidateOutput.

    Validate PII compliance and source ToS for all persons in graph.
    """
    censor = AgentRegistry.censor()

    # Validate each person in knowledge graph
    validated_graph: dict[str, Person] = {}
    all_violations: list[str] = []

    for person_id, person in state.knowledge_graph.items():
        validated_person, violations = censor.validate_output(person)
        validated_graph[person_id] = validated_person
        all_violations.extend(violations)

    # Log violations if any
    if all_violations:
        censor.log_action(
            state,
            action_type="compliance_validation",
            rationale=f"Validated {len(state.knowledge_graph)} persons, {len(all_violations)} redactions",
            context="; ".join(all_violations[:5]),
        )

    return {
        "active_agent": AgentType.CENSOR,
        "knowledge_graph": validated_graph,
        "research_log": list(state.research_log),
    }


async def lead_update_state(state: GraphState) -> dict[str, Any]:
    """Z Operation: LeadUpdateState.

    Update state after task execution:
    - Move completed task to completed_tasks
    - Convert new hypotheses to tasks
    - Re-prioritize frontier queue
    """
    lead = AgentRegistry.lead()

    # Build updated completed tasks list
    updated_completed = list(state.completed_tasks)
    current_task = state.current_task
    if current_task:
        # Create a completed copy
        completed_task = current_task.model_copy(update={"completed": True})
        updated_completed.append(completed_task)

    # Convert pending hypotheses to tasks
    pending_hypotheses = [h for h in state.hypotheses
                         if h.status == HypothesisStatus.PENDING]
    new_tasks = lead.prioritize_hypotheses(state, pending_hypotheses)

    # Build updated frontier queue (add new tasks)
    updated_queue = list(state.frontier_queue)
    for task in new_tasks:
        if not task.completed:
            updated_queue.append(task)

    # Sort by priority
    updated_queue.sort(key=lambda t: t.priority, reverse=True)

    # Update hypothesis statuses (create new list with updated statuses)
    updated_hypotheses = []
    for h in state.hypotheses:
        if h.status == HypothesisStatus.PENDING:
            updated_hypotheses.append(h.model_copy(update={"status": HypothesisStatus.IN_PROGRESS}))
        else:
            updated_hypotheses.append(h)

    lead.log_action(
        state,
        action_type="state_update",
        rationale=f"Updated state: {len(new_tasks)} new tasks, "
                  f"{len(updated_queue)} in queue, "
                  f"{len(updated_completed)} completed",
    )

    return {
        "frontier_queue": updated_queue,
        "completed_tasks": updated_completed,
        "hypotheses": updated_hypotheses,
        "current_task": None,  # Clear transient field
        "research_log": list(state.research_log),
    }


async def lead_check_termination(state: GraphState) -> dict[str, Any]:
    """Z Operation: LeadCheckTermination.

    Check termination conditions:
    - goalAchieved ∨ exhausted ∨ budgetExceeded ∨ gpsSatisfied
    """
    lead = AgentRegistry.lead()
    terminated = lead._check_termination(state)

    return {
        "terminated": state.terminated,
        "termination_reason": state.termination_reason,
        "research_log": list(state.research_log),
    }


# =============================================================================
# Routing Functions
# =============================================================================


def route_after_task_selection(
    state: GraphState,
) -> Literal["scout_search", "analyst_analyze", "end"]:
    """Route after LeadSelectTask.

    Z: (ScoutSearchSource ∨ AnalystGenerateHypotheses)
    """
    # Check termination
    if state.terminated:
        return "end"

    # Check if there's a task to execute
    if not state.frontier_queue:
        return "end"

    # Peek at highest priority task
    sorted_queue = sorted(state.frontier_queue, key=lambda t: t.priority, reverse=True)
    task = sorted_queue[0]

    if task.assigned_to == AgentType.ANALYST:
        return "analyst_analyze"
    else:
        # Default to scout for SEARCH, VERIFY, RESOLVE tasks
        return "scout_search"


def route_after_termination_check(
    state: GraphState,
) -> Literal["lead_select_task", "end"]:
    """Route after termination check - continue loop or end."""
    if state.terminated:
        return "end"
    if not state.frontier_queue:
        return "end"
    return "lead_select_task"


# =============================================================================
# Graph Builder
# =============================================================================


def build_ancestry_engine_graph() -> CompiledStateGraph:
    """Build the LangGraph Plan-and-Execute graph.

    Implements the Z specification:
    ┌─ PlanAndExecuteLoop ──────────────────────────────────┐
    │ LeadSelectTask ;                                      │
    │ (ScoutSearchSource ∨ AnalystGenerateHypotheses) ;     │
    │ CensorValidateOutput ;                                │
    │ LeadUpdateState ;                                     │
    │ LeadCheckTermination                                  │
    └───────────────────────────────────────────────────────┘
    """
    # Create state graph with GraphState
    graph = StateGraph(GraphState)

    # Add nodes (Z operations)
    graph.add_node("lead_select_task", lead_select_task)
    graph.add_node("scout_search", scout_search)
    graph.add_node("analyst_analyze", analyst_analyze)
    graph.add_node("censor_validate", censor_validate)
    graph.add_node("lead_update_state", lead_update_state)
    graph.add_node("lead_check_termination", lead_check_termination)

    # Set entry point
    graph.set_entry_point("lead_select_task")

    # Add conditional edges after task selection
    # Z: LeadSelectTask ; (ScoutSearchSource ∨ AnalystGenerateHypotheses)
    graph.add_conditional_edges(
        "lead_select_task",
        route_after_task_selection,
        {
            "scout_search": "scout_search",
            "analyst_analyze": "analyst_analyze",
            "end": END,
        },
    )

    # Scout -> Analyst (always analyze after search)
    # Z: Scout produces records, Analyst generates hypotheses
    graph.add_edge("scout_search", "analyst_analyze")

    # Analyst -> Censor
    # Z: ; CensorValidateOutput
    graph.add_edge("analyst_analyze", "censor_validate")

    # After Censor, go to state update
    # Z: ; LeadUpdateState
    graph.add_edge("censor_validate", "lead_update_state")

    # After state update, check termination
    # Z: ; LeadCheckTermination
    graph.add_edge("lead_update_state", "lead_check_termination")

    # After termination check, either loop or end
    graph.add_conditional_edges(
        "lead_check_termination",
        route_after_termination_check,
        {
            "lead_select_task": "lead_select_task",
            "end": END,
        },
    )

    # Compile the graph
    return graph.compile()


# =============================================================================
# Engine Runner
# =============================================================================


class AncestryEngine:
    """High-level interface for running the Ancestry Engine.

    Usage:
        engine = AncestryEngine()
        result = await engine.run(
            query="Find ancestors of John Smith",
            seed_person=Person(given_name="John", surname="Smith", birth_dates=["1920"]),
        )
    """

    def __init__(self, llm_client: Any = None):
        """Initialize the engine.

        Args:
            llm_client: Optional LLM client for reasoning tasks
        """
        # Initialize shared agents with LLM client
        AgentRegistry.initialize(llm_client)
        self.graph = build_ancestry_engine_graph()
        self.llm_client = llm_client

    async def run(
        self,
        query: str,
        seed_person: Person,
        tier_1_enabled: bool = False,
        tier_1_token: str | None = None,
        tier_2_enabled: bool = False,
        tier_2_credentials: dict[str, str] | None = None,
        max_iterations: int = 500,
    ) -> AncestryEngineState:
        """Run the ancestry engine.

        Args:
            query: Research query (e.g., "Find ancestors of John Smith")
            seed_person: Starting person for research
            tier_1_enabled: Enable Tier 1 sources (requires auth)
            tier_1_token: Auth token for Tier 1 sources
            tier_2_enabled: Enable Tier 2 sources (paid)
            tier_2_credentials: Credentials for Tier 2 sources
            max_iterations: Maximum loop iterations

        Returns:
            Final engine state with knowledge graph
        """
        from .models import SourcePermissions

        # Initialize state using GraphState (extended state)
        state = GraphState(
            query=query,
            seed_person=seed_person,
            source_permissions=SourcePermissions(
                tier_1_enabled=tier_1_enabled,
                tier_1_token=tier_1_token,
                tier_2_enabled=tier_2_enabled,
                tier_2_credentials=tier_2_credentials or {},
            ),
            max_iterations=max_iterations,
        )

        # Add seed person to knowledge graph
        state.add_person(seed_person)

        # Create initial tasks from query
        lead = AgentRegistry.lead()
        initial_tasks = lead.decompose_query(query, seed_person)
        for task in initial_tasks:
            state.add_task(task)

        # Log session start
        lead.log_action(
            state,
            action_type="session_start",
            rationale=f"Starting research: {query}",
            context=f"Seed: {seed_person.full_name}",
        )

        # Run the graph with ainvoke (not astream + ainvoke)
        # This properly executes until termination or max iterations
        config = {"recursion_limit": max_iterations}
        final_state = await self.graph.ainvoke(state, config=config)

        logger.info(
            f"Engine completed: {len(final_state.knowledge_graph)} persons, "
            f"{len(final_state.completed_tasks)} tasks completed, "
            f"{len(final_state.research_log)} log entries"
        )

        return final_state

    def export_jsonld(self, state: AncestryEngineState) -> dict[str, Any]:
        """Export the knowledge graph as JSON-LD.

        Args:
            state: Engine state to export

        Returns:
            JSON-LD compatible dictionary
        """
        return state.to_jsonld()


# =============================================================================
# Convenience function
# =============================================================================


async def run_ancestry_research(
    query: str,
    seed_given_name: str,
    seed_surname: str,
    seed_birth_year: int | None = None,
    seed_birth_place: str | None = None,
    **kwargs: Any,
) -> AncestryEngineState:
    """Convenience function to run ancestry research.

    Args:
        query: Research query
        seed_given_name: Seed person's given name
        seed_surname: Seed person's surname
        seed_birth_year: Optional birth year
        seed_birth_place: Optional birth place
        **kwargs: Additional arguments for AncestryEngine.run()

    Returns:
        Final engine state
    """
    # Create seed person
    seed_person = Person(
        given_name=seed_given_name,
        surname=seed_surname,
        birth_dates=[str(seed_birth_year)] if seed_birth_year else [],
        birth_places=[seed_birth_place] if seed_birth_place else [],
    )

    # Run engine
    engine = AncestryEngine()
    return await engine.run(query, seed_person, **kwargs)
