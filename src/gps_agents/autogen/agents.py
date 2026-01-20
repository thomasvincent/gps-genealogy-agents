"""AutoGen agent definitions for GPS Genealogy Agents.

Uses the modern autogen_agentchat API with SelectorGroupChat.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from autogen_agentchat.agents import AssistantAgent

from gps_agents.sk.kernel import get_service_id_for_agent

if TYPE_CHECKING:
    from autogen_core.models import ChatCompletionClient
    from semantic_kernel import Kernel


def _load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts directory."""
    prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
    prompt_path = prompts_dir / f"{prompt_name}.txt"

    if prompt_path.exists():
        return prompt_path.read_text()

    # Fallback to embedded prompts
    return _get_default_prompt(prompt_name)


def _get_default_prompt(prompt_name: str) -> str:
    """Get default prompt if file not found."""
    defaults = {
        "research_agent": """You are a genealogical research agent. Your role is to:
1. Search multiple genealogy sources for records
2. Propose new facts based on discovered evidence
3. Never directly modify the fact ledger - only propose facts

Use the sources plugin to search FamilySearch, WikiTree, and other databases.
Always classify evidence as direct, indirect, or negative.""",
        "data_quality_agent": """You are a data quality validation agent. Your role is to:
1. Verify mechanical accuracy of proposed facts
2. Check for data entry errors and inconsistencies
3. Validate dates, names, and locations
4. Flag potential transcription errors

You do NOT evaluate genealogical reasoning - only data quality.""",
        "gps_standards_critic": """You are a GPS Standards Critic evaluating Pillars 1 and 2.

PILLAR 1 - Reasonably Exhaustive Search:
- Were appropriate sources consulted?
- Was the search broad enough for the time period and location?

PILLAR 2 - Complete and Accurate Citations:
- Do citations follow Evidence Explained format?
- Are all sources properly identified?

Rate each pillar as SATISFIED, PARTIAL, or FAILED with justification.""",
        "gps_reasoning_critic": """You are a GPS Reasoning Critic evaluating Pillars 3 and 4.

PILLAR 3 - Analysis and Correlation:
- Has evidence been properly analyzed?
- Have sources been correlated?
- Is direct vs indirect evidence properly classified?

PILLAR 4 - Conflict Resolution:
- Have conflicting records been identified?
- Are conflicts resolved with reasoned explanation?

Rate each pillar as SATISFIED, PARTIAL, or FAILED with justification.""",
        "workflow_agent": """You are the Workflow Agent - the ONLY agent that can write to the fact ledger.

Your responsibilities:
1. Receive proposed facts from other agents
2. Verify GPS pillar requirements are met before acceptance
3. Write facts to the ledger with proper versioning
4. Update fact status (PROPOSED, ACCEPTED, REJECTED, INCOMPLETE)

CRITICAL: Never accept a fact unless ALL 5 GPS pillars are SATISFIED.""",
        "citation_agent": """You are the Citation Agent specializing in Evidence Explained format.

Your role:
1. Create proper citations from raw record data
2. Classify evidence type (direct, indirect, negative)
3. Format citations according to Evidence Explained standards
4. Validate citation completeness""",
        "synthesis_agent": """You are the Synthesis Agent creating proof arguments.

Your role:
1. Write coherent proof arguments connecting evidence to conclusions
2. Explain how conflicts were resolved
3. Create narratives suitable for GPS Pillar 5
4. Summarize research findings""",
        "translation_agent": """You are the Translation Agent for foreign language records.

Your role:
1. Translate genealogical records from any language to English
2. Preserve genealogical terminology accurately
3. Note any ambiguities in translation
4. Provide cultural context where relevant""",
        "dna_agent": """You are the DNA/Ethnicity Agent for genetic genealogy.

Your role:
1. Interpret DNA test results
2. Calculate relationship probabilities
3. Suggest search strategies based on ethnicity estimates
4. Note limitations of DNA evidence

Always express DNA-based conclusions with appropriate uncertainty.""",
    }
    return defaults.get(prompt_name, f"You are the {prompt_name}.")


def create_model_client(
    provider: str = "anthropic",
    model: str | None = None,
    temperature: float = 0.1,
) -> ChatCompletionClient:
    """Create a model client for the specified provider.

    Args:
        provider: LLM provider ("anthropic", "openai", "azure", "ollama")
        model: Specific model to use (defaults based on provider)
        temperature: Sampling temperature (0.0-1.0)

    Returns:
        ChatCompletionClient instance
    """
    provider = provider.lower()

    if provider == "anthropic":
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient

        return AnthropicChatCompletionClient(
            model=model or "claude-sonnet-4-20250514",
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            temperature=temperature,
        )

    if provider == "openai":
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        return OpenAIChatCompletionClient(
            model=model or "gpt-4o-mini",
            api_key=os.environ.get("OPENAI_API_KEY"),
            temperature=temperature,
        )

    if provider == "azure":
        from autogen_ext.models.openai import AzureOpenAIChatCompletionClient

        return AzureOpenAIChatCompletionClient(
            model=model or "gpt-4",
            azure_deployment=model or "gpt-4",
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-15-preview",
            temperature=temperature,
        )

    if provider == "ollama":
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        # Ollama uses OpenAI-compatible API
        return OpenAIChatCompletionClient(
            model=model or "llama3:70b",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",  # Ollama doesn't require real key
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider}. "
        f"Choose from: anthropic, openai, azure, ollama"
    )


def get_model_client_for_agent(agent_name: str) -> ChatCompletionClient:
    """Get the appropriate model client for an agent based on dual-LLM strategy.

    - Reasoning agents (critics, synthesis): Claude for nuanced reasoning
    - Structured agents (data quality, workflow): GPT-4 for consistency
    - Falls back to Anthropic if OpenAI not available
    """
    service_id = get_service_id_for_agent(agent_name)
    anthropic_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
    openai_available = bool(os.environ.get("OPENAI_API_KEY"))

    if service_id == "claude":
        return create_model_client("anthropic", temperature=0.1)
    # Prefer OpenAI for structured tasks, but fall back to Anthropic
    if openai_available and anthropic_available:
        # Use Anthropic for everything if OpenAI quota might be limited
        return create_model_client("anthropic", temperature=0.1)
    elif openai_available:
        return create_model_client("openai", temperature=0.1)
    return create_model_client("anthropic", temperature=0.1)


class GPSAssistantAgent(AssistantAgent):
    """Extended AssistantAgent with SK Kernel access for GPS genealogy research."""

    def __init__(
        self,
        name: str,
        kernel: Kernel,
        system_message: str,
        model_client: ChatCompletionClient | None = None,
        description: str = "",
    ) -> None:
        """Initialize GPS Assistant Agent.

        Args:
            name: Agent name
            kernel: Semantic Kernel instance for plugin access
            system_message: System prompt for the agent
            model_client: LLM client for the agent
            description: Agent description for team coordination
        """
        super().__init__(
            name=name,
            model_client=model_client or get_model_client_for_agent(name),
            system_message=system_message,
            description=description,
        )
        self.kernel = kernel

    async def invoke_plugin(
        self,
        plugin_name: str,
        function_name: str,
        **kwargs: Any,
    ) -> str:
        """Invoke a Semantic Kernel plugin function.

        Args:
            plugin_name: Name of the SK plugin
            function_name: Name of the function within the plugin
            **kwargs: Arguments to pass to the function

        Returns:
            String result from the plugin function
        """
        func = self.kernel.get_function(plugin_name, function_name)
        result = await func.invoke(self.kernel, **kwargs)
        return str(result)


def create_research_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the research agent."""
    return GPSAssistantAgent(
        name="research_agent",
        kernel=kernel,
        system_message=_load_prompt("research_agent"),
        description="Searches genealogy sources and proposes new facts",
    )


def create_data_quality_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the data quality agent."""
    return GPSAssistantAgent(
        name="data_quality_agent",
        kernel=kernel,
        system_message=_load_prompt("data_quality_agent"),
        description="Validates data accuracy and consistency",
    )


def create_gps_standards_critic(kernel: Kernel) -> GPSAssistantAgent:
    """Create the GPS standards critic (Pillars 1-2)."""
    return GPSAssistantAgent(
        name="gps_standards_critic",
        kernel=kernel,
        system_message=_load_prompt("gps_standards_critic"),
        description="Evaluates GPS Pillars 1 (exhaustive search) and 2 (citations)",
    )


def create_gps_reasoning_critic(kernel: Kernel) -> GPSAssistantAgent:
    """Create the GPS reasoning critic (Pillars 3-4)."""
    return GPSAssistantAgent(
        name="gps_reasoning_critic",
        kernel=kernel,
        system_message=_load_prompt("gps_reasoning_critic"),
        description="Evaluates GPS Pillars 3 (analysis) and 4 (conflicts)",
    )


def create_workflow_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the workflow agent (ledger writer)."""
    return GPSAssistantAgent(
        name="workflow_agent",
        kernel=kernel,
        system_message=_load_prompt("workflow_agent"),
        description="ONLY agent that writes to fact ledger - enforces GPS compliance",
    )


def create_citation_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the citation agent."""
    return GPSAssistantAgent(
        name="citation_agent",
        kernel=kernel,
        system_message=_load_prompt("citation_agent"),
        description="Creates Evidence Explained citations",
    )


def create_synthesis_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the synthesis agent."""
    return GPSAssistantAgent(
        name="synthesis_agent",
        kernel=kernel,
        system_message=_load_prompt("synthesis_agent"),
        description="Writes proof arguments and research narratives",
    )


def create_translation_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the translation agent."""
    return GPSAssistantAgent(
        name="translation_agent",
        kernel=kernel,
        system_message=_load_prompt("translation_agent"),
        description="Translates foreign language records",
    )


def create_dna_agent(kernel: Kernel) -> GPSAssistantAgent:
    """Create the DNA/ethnicity agent."""
    return GPSAssistantAgent(
        name="dna_agent",
        kernel=kernel,
        system_message=_load_prompt("dna_agent"),
        description="Interprets DNA results with appropriate uncertainty",
    )


def create_all_agents(kernel: Kernel) -> dict[str, GPSAssistantAgent]:
    """Create all GPS agents.

    Args:
        kernel: Semantic Kernel instance

    Returns:
        Dictionary mapping agent names to agent instances
    """
    return {
        "research_agent": create_research_agent(kernel),
        "data_quality_agent": create_data_quality_agent(kernel),
        "gps_standards_critic": create_gps_standards_critic(kernel),
        "gps_reasoning_critic": create_gps_reasoning_critic(kernel),
        "workflow_agent": create_workflow_agent(kernel),
        "citation_agent": create_citation_agent(kernel),
        "synthesis_agent": create_synthesis_agent(kernel),
        "translation_agent": create_translation_agent(kernel),
        "dna_agent": create_dna_agent(kernel),
    }


def validate_api_key(provider: str) -> bool:
    """Check if required API key is set for provider."""
    key_mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
        "ollama": None,  # No key required
    }

    env_var = key_mapping.get(provider)
    if env_var is None:
        return True  # No key required

    return bool(os.environ.get(env_var))


def get_available_providers() -> list[str]:
    """Get list of providers with valid API keys configured."""
    providers = ["anthropic", "openai", "azure", "ollama"]
    return [p for p in providers if validate_api_key(p)]
