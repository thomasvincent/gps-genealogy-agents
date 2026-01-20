"""Agent implementations."""
from __future__ import annotations

from .base import BaseAgent
from .citation import CitationAgent
from .data_quality import DataQualityAgent
from .dna import DNAAgent
from .gps_reasoning_critic import GPSReasoningCritic
from .gps_standards_critic import GPSStandardsCritic
from .research import ResearchAgent
from .search_orchestrator import SearchOrchestratorAgent
from .synthesis import SynthesisAgent
from .translation import TranslationAgent
from .workflow import WorkflowAgent

__all__ = [
    "BaseAgent",
    "CitationAgent",
    "DNAAgent",
    "DataQualityAgent",
    "GPSReasoningCritic",
    "GPSStandardsCritic",
    "ResearchAgent",
    "SearchOrchestratorAgent",
    "SynthesisAgent",
    "TranslationAgent",
    "WorkflowAgent",
]


# Agentic pipeline components are available via direct import:
# from gps_agents.agents.pipeline import AgentPipelineManager, ...
# from gps_agents.agents.schemas import SearchPlan, ...
