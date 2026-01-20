"""Research orchestration for memory-aware genealogy searches."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from gps_agents.research.evaluator import (
    MatchConfidence,
    MatchScore,
    PersonProfile,
    RelevanceEvaluator,
    build_profile_from_facts,
)
from gps_agents.research.orchestrator import (
    ExtractedFact,
    OrchestratorConfig,
    ResearchOrchestrator,
    ResearchSession,
)

# LLM-enhanced evaluator (optional - requires additional dependencies)
try:
    from gps_agents.research.llm_evaluator import (
        EnhancedMatchScore,
        LLMMatchResult,
        LLMRelevanceEvaluator,
        get_available_features,
    )
    LLM_EVALUATOR_AVAILABLE = True
except ImportError:
    LLM_EVALUATOR_AVAILABLE = False
    EnhancedMatchScore = None
    LLMMatchResult = None
    LLMRelevanceEvaluator = None
    def get_available_features() -> dict[str, bool]:
        return {}

if TYPE_CHECKING:
    from gps_agents.sk.plugins.memory import MemoryPlugin
    from gps_agents.sources.router import SearchRouter

__all__ = [
    # Orchestrator
    "ResearchOrchestrator",
    "OrchestratorConfig",
    "ResearchSession",
    "ExtractedFact",
    # Evaluator
    "RelevanceEvaluator",
    "PersonProfile",
    "MatchScore",
    "MatchConfidence",
    "build_profile_from_facts",
    # LLM Evaluator
    "LLMRelevanceEvaluator",
    "EnhancedMatchScore",
    "LLMMatchResult",
    "get_available_features",
    "LLM_EVALUATOR_AVAILABLE",
    # Factory
    "create_orchestrator",
]


def create_orchestrator(
    router: "SearchRouter | None" = None,
    memory_dir: str | Path | None = None,
    research_dir: str | Path | None = None,
    config: OrchestratorConfig | None = None,
) -> ResearchOrchestrator:
    """Create a configured ResearchOrchestrator.

    This is the main entry point for using the research system.

    Args:
        router: Search router with registered sources. If None, creates default.
        memory_dir: Directory for ChromaDB persistence. If None, uses ./memory.
        research_dir: Directory for file-based research. If None, uses ./research.
        config: Orchestrator configuration. If None, uses defaults.

    Returns:
        Configured ResearchOrchestrator ready for use.

    Example:
        ```python
        from gps_agents.research import create_orchestrator
        from gps_agents.sources import FamilySearchSource, WikiTreeSource

        # Create orchestrator
        orchestrator = create_orchestrator()

        # Register sources
        orchestrator.router.register_source(FamilySearchSource())
        orchestrator.router.register_source(WikiTreeSource())

        # Research a person
        session = await orchestrator.research("Durham", "Archer")

        # Check results
        print(f"Found {len(session.discovered_facts)} new facts")
        for record, score in session.evaluated_records:
            print(f"  {record.source}: {score.confidence.value}")
        ```
    """
    from gps_agents.sk.plugins.memory import MemoryPlugin
    from gps_agents.sources.router import SearchRouter

    # Create router if not provided
    if router is None:
        router = SearchRouter()

    # Create memory plugin
    memory = None
    if memory_dir is not None or Path("memory").exists():
        mem_path = Path(memory_dir) if memory_dir else Path("memory")
        mem_path.mkdir(parents=True, exist_ok=True)
        try:
            memory = MemoryPlugin(str(mem_path))
        except Exception:
            pass  # Memory is optional

    # Create research directory
    res_path = Path(research_dir) if research_dir else Path("research")

    return ResearchOrchestrator(
        router=router,
        memory=memory,
        config=config or OrchestratorConfig(),
        research_dir=res_path,
    )
