"""The Ancestry Engine - Multi-agent system for autonomous genealogical research.

This package implements a LangGraph-based orchestration system with four specialized agents:
- The Lead: Task decomposition and state management
- The Scout: Tool-use specialist (Search/Browse/Scrape)
- The Analyst: Conflict resolution and Clue generation
- The Censor: PII/ToS compliance

Architecture follows the Z notation formal specification in docs/architecture/ancestry-engine.md.
"""
from .agents import AnalystAgent, BaseAgent, CensorAgent, LeadAgent, ScoutAgent
from .graph import (
    AgentRegistry,
    AncestryEngine,
    GraphState,
    build_ancestry_engine_graph,
    run_ancestry_research,
)
from .jsonld import (
    export_compact,
    export_knowledge_graph,
    export_to_file,
    validate_jsonld,
)
from .models import (
    AgentType,
    AncestryEngineState,
    ClueHypothesis,
    ConflictingClaim,
    ConflictResolution,
    Decision,
    EvidenceType,
    HypothesisStatus,
    LogEntry,
    Person,
    RawRecord,
    SourceCitation,
    SourcePermissions,
    SourceTier,
    Task,
    TaskType,
)

__all__ = [
    # Engine
    "AncestryEngine",
    "AgentRegistry",
    "GraphState",
    "build_ancestry_engine_graph",
    "run_ancestry_research",
    # Agents
    "BaseAgent",
    "LeadAgent",
    "ScoutAgent",
    "AnalystAgent",
    "CensorAgent",
    # Models
    "AncestryEngineState",
    "Person",
    "SourceCitation",
    "ClueHypothesis",
    "Task",
    "LogEntry",
    "RawRecord",
    "ConflictingClaim",
    "ConflictResolution",
    "SourcePermissions",
    # Enums
    "SourceTier",
    "AgentType",
    "TaskType",
    "HypothesisStatus",
    "EvidenceType",
    "Decision",
    # JSON-LD Export
    "export_knowledge_graph",
    "export_to_file",
    "export_compact",
    "validate_jsonld",
]
