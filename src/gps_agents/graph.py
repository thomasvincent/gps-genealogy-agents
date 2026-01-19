"""LangGraph workflow for GPS genealogy research."""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .agents.citation import CitationAgent
from .agents.data_quality import DataQualityAgent
from .agents.dna import DNAAgent
from .agents.gps_reasoning_critic import GPSReasoningCritic
from .agents.gps_standards_critic import GPSStandardsCritic
from .agents.research import ResearchAgent
from .agents.synthesis import SynthesisAgent
from .agents.translation import TranslationAgent
from .agents.workflow import WorkflowAgent
from .sources.accessgenealogy import AccessGenealogySource
from .sources.familysearch import FamilySearchSource
from .sources.gedcom import GedcomSource
from .sources.jerripedia import JerripediaSource
from .sources.wikitree import WikiTreeSource

if TYPE_CHECKING:
    from .ledger.fact_ledger import FactLedger
    from .projections.sqlite_projection import SQLiteProjection


class ResearchState(TypedDict):
    """State passed through the research workflow."""

    # Input
    task: str
    messages: Annotated[list, add_messages]

    # Research phase
    search_query: dict
    raw_records: list[dict]
    sources_searched: list[str]
    translations: list[dict]

    # Fact processing
    proposed_facts: list
    quality_flags: list[dict]
    existing_facts: list

    # Critic feedback
    critic_feedback: dict

    # Workflow control
    workflow_decision: dict
    retry_count: int
    needs_revision: bool
    revision_request: str

    # Output
    accepted_facts: list
    incomplete_facts: list
    formatted_citations: list[dict]
    synthesis: dict

    # DNA (optional)
    dna_data: dict
    dna_interpretation: dict


def create_research_graph(
    ledger: FactLedger | None = None,
    projection: SQLiteProjection | None = None,
    sources: list | None = None,
) -> StateGraph:
    """Create the LangGraph research workflow.

    Args:
        ledger: FactLedger instance for persistence
        projection: SQLiteProjection for queries
        sources: List of data sources to use

    Returns:
        Compiled StateGraph
    """
    # Initialize default sources if not provided
    if sources is None:
        sources = [
            FamilySearchSource(),
            WikiTreeSource(),
            AccessGenealogySource(),
            JerripediaSource(),
            GedcomSource(),
        ]

    # Initialize agents
    workflow_agent = WorkflowAgent(ledger=ledger, projection=projection)
    research_agent = ResearchAgent(sources=sources)
    data_quality_agent = DataQualityAgent()
    standards_critic = GPSStandardsCritic()
    reasoning_critic = GPSReasoningCritic()
    translation_agent = TranslationAgent()
    citation_agent = CitationAgent()
    synthesis_agent = SynthesisAgent()
    dna_agent = DNAAgent()

    # Create graph
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("research", research_agent.process)
    graph.add_node("translate", translation_agent.process)
    graph.add_node("data_quality", data_quality_agent.process)
    graph.add_node("standards_critic", standards_critic.process)
    graph.add_node("reasoning_critic", reasoning_critic.process)
    graph.add_node("workflow_decision", workflow_agent.process)
    graph.add_node("citation", citation_agent.process)
    graph.add_node("synthesis", synthesis_agent.process)
    graph.add_node("dna", dna_agent.process)

    # Define edges
    graph.set_entry_point("research")

    # Research -> Check if translation needed
    graph.add_conditional_edges(
        "research",
        _needs_translation,
        {
            True: "translate",
            False: "data_quality",
        },
    )

    # Translation -> Data Quality
    graph.add_edge("translate", "data_quality")

    # Data Quality -> Critics (parallel would be better but sequential for clarity)
    graph.add_edge("data_quality", "standards_critic")
    graph.add_edge("standards_critic", "reasoning_critic")

    # Critics -> Workflow Decision
    graph.add_edge("reasoning_critic", "workflow_decision")

    # Workflow Decision -> Conditional routing
    graph.add_conditional_edges(
        "workflow_decision",
        _route_workflow_decision,
        {
            "accept": "citation",
            "retry": "research",
            "incomplete": END,
            "continue": "citation",
        },
    )

    # Citation -> DNA check
    graph.add_conditional_edges(
        "citation",
        _has_dna_data,
        {
            True: "dna",
            False: "synthesis",
        },
    )

    # DNA -> Synthesis
    graph.add_edge("dna", "synthesis")

    # Synthesis -> End
    graph.add_edge("synthesis", END)

    return graph.compile()


def _needs_translation(state: ResearchState) -> bool:
    """Check if any records need translation."""
    raw_records = state.get("raw_records", [])
    return any(r.get("needs_translation", False) for r in raw_records)


def _route_workflow_decision(state: ResearchState) -> str:
    """Route based on workflow decision."""
    decision = state.get("workflow_decision", {})
    action = decision.get("action", "continue").lower()

    retry_count = state.get("retry_count", 0)

    if action == "accept":
        return "accept"
    if action == "retry" and retry_count < 2:
        return "retry"
    if action == "incomplete":
        return "incomplete"
    return "continue"


def _has_dna_data(state: ResearchState) -> bool:
    """Check if DNA data is present."""
    return bool(state.get("dna_data"))


async def run_research(
    task: str,
    ledger: FactLedger | None = None,
    projection: SQLiteProjection | None = None,
    sources: list | None = None,
    existing_facts: list | None = None,
    dna_data: dict | None = None,
) -> ResearchState:
    """Run a genealogical research task.

    Args:
        task: Natural language research query
        ledger: FactLedger for persistence
        projection: SQLiteProjection for queries
        sources: Data sources to search
        existing_facts: Already known facts
        dna_data: Optional DNA data to interpret

    Returns:
        Final research state with results
    """
    graph = create_research_graph(ledger, projection, sources)

    initial_state: ResearchState = {
        "task": task,
        "messages": [],
        "search_query": {},
        "raw_records": [],
        "sources_searched": [],
        "translations": [],
        "proposed_facts": [],
        "quality_flags": [],
        "existing_facts": existing_facts or [],
        "critic_feedback": {},
        "workflow_decision": {},
        "retry_count": 0,
        "needs_revision": False,
        "revision_request": "",
        "accepted_facts": [],
        "incomplete_facts": [],
        "formatted_citations": [],
        "synthesis": {},
        "dna_data": dna_data or {},
        "dna_interpretation": {},
    }

    # Run the graph
    return await graph.ainvoke(initial_state)



def create_simple_pipeline(sources: list | None = None):
    """Create a simple research pipeline without persistence.

    Args:
        sources: Data sources to use

    Returns:
        Async function to run research
    """

    async def research(task: str, **kwargs) -> dict:
        """Run research and return results."""
        state = await run_research(task, sources=sources, **kwargs)
        return {
            "task": task,
            "accepted_facts": [
                {"statement": f.statement, "confidence": f.confidence_score}
                for f in state.get("accepted_facts", [])
            ],
            "synthesis": state.get("synthesis", {}),
            "sources_searched": state.get("sources_searched", []),
        }

    return research
