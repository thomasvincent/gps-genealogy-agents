"""Semantic Kernel setup and configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    OpenAIChatCompletion,
    OpenAITextEmbedding,
)
from semantic_kernel.connectors.ai.anthropic import AnthropicChatCompletion

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.projections.sqlite_projection import SQLiteProjection
from gps_agents.sk.plugins.ledger import LedgerPlugin
from gps_agents.sk.plugins.sources import SourcesPlugin
from gps_agents.sk.plugins.gps import GPSPlugin
from gps_agents.sk.plugins.citation import CitationPlugin
from gps_agents.sk.plugins.memory import MemoryPlugin


@dataclass
class KernelConfig:
    """Configuration for the SK Kernel."""

    data_dir: Path = Path("./data")
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    use_azure: bool = False

    def __post_init__(self):
        self.openai_api_key = self.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = self.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.azure_openai_endpoint = self.azure_openai_endpoint or os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        )
        self.azure_openai_key = self.azure_openai_key or os.getenv("AZURE_OPENAI_KEY")


def create_kernel(config: KernelConfig | None = None) -> Kernel:
    """Create and configure the Semantic Kernel with all plugins."""
    if config is None:
        config = KernelConfig()

    kernel = Kernel()

    # Configure LLM services
    _configure_llm_services(kernel, config)

    # Initialize storage
    config.data_dir.mkdir(parents=True, exist_ok=True)
    ledger = FactLedger(str(config.data_dir / "ledger"))
    projection = SQLiteProjection(str(config.data_dir / "projection.db"))

    # Register plugins
    kernel.add_plugin(LedgerPlugin(ledger, projection), plugin_name="ledger")
    kernel.add_plugin(SourcesPlugin(), plugin_name="sources")
    kernel.add_plugin(GPSPlugin(ledger), plugin_name="gps")
    kernel.add_plugin(CitationPlugin(), plugin_name="citation")
    kernel.add_plugin(
        MemoryPlugin(str(config.data_dir / "chroma")), plugin_name="memory"
    )

    return kernel


def _configure_llm_services(kernel: Kernel, config: KernelConfig) -> None:
    """Configure LLM services on the kernel."""
    # OpenAI / Azure OpenAI for GPT-4
    if config.use_azure and config.azure_openai_endpoint:
        kernel.add_service(
            AzureChatCompletion(
                service_id="gpt4",
                deployment_name="gpt-4-turbo",
                endpoint=config.azure_openai_endpoint,
                api_key=config.azure_openai_key,
            )
        )
    elif config.openai_api_key:
        kernel.add_service(
            OpenAIChatCompletion(
                service_id="gpt4",
                ai_model_id="gpt-4-turbo",
                api_key=config.openai_api_key,
            )
        )

        # Embeddings for memory
        kernel.add_service(
            OpenAITextEmbedding(
                service_id="embedding",
                ai_model_id="text-embedding-3-small",
                api_key=config.openai_api_key,
            )
        )

    # Anthropic for Claude (reasoning agents)
    if config.anthropic_api_key:
        kernel.add_service(
            AnthropicChatCompletion(
                service_id="claude",
                ai_model_id="claude-3-opus-20240229",
                api_key=config.anthropic_api_key,
            )
        )


def get_service_id_for_agent(agent_name: str) -> str:
    """Get the appropriate LLM service ID for an agent.

    Claude is used for reasoning-heavy agents (GPS critics, synthesis).
    GPT-4 is used for structured data extraction and workflow.
    """
    reasoning_agents = {
        "gps_standards_critic",
        "gps_reasoning_critic",
        "synthesis_agent",
    }
    return "claude" if agent_name in reasoning_agents else "gpt4"
