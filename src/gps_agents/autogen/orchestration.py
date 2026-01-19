"""AutoGen SelectorGroupChat orchestration for GPS Genealogy Agents.

Uses the modern autogen_agentchat teams API with intelligent agent selection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import SelectorGroupChat

from gps_agents.autogen.agents import (
    GPSAssistantAgent,
    create_all_agents,
    create_model_client,
)
from gps_agents.sk.kernel import KernelConfig, create_kernel

if TYPE_CHECKING:
    from autogen_agentchat.agents import BaseChatAgent
    from autogen_agentchat.base import TaskResult

GPS_COORDINATOR_PROMPT = """You are the GPS Research Coordinator managing genealogical research.

Your role is to select the most appropriate agent based on the current conversation state:

AGENT SELECTION RULES:
- research_agent: When new records need to be found or searches conducted
- data_quality_agent: When data needs validation or error checking
- gps_standards_critic: To evaluate GPS Pillars 1 (exhaustive search) and 2 (citations)
- gps_reasoning_critic: To evaluate GPS Pillars 3 (analysis) and 4 (conflicts)
- citation_agent: When citations need to be created or formatted
- synthesis_agent: To write proof arguments or research narratives
- translation_agent: When foreign language records need translation
- dna_agent: When DNA evidence needs interpretation
- workflow_agent: ONLY when ready to write to ledger (after GPS approval)

CRITICAL RULES:
1. Never select workflow_agent until ALL 5 GPS pillars are SATISFIED
2. Ensure research_agent searches multiple sources (FamilySearch, WikiTree, etc.)
3. GPS critics must evaluate EVERY proposed fact before acceptance
4. Conflicts must be resolved before facts can be accepted

Based on the conversation, select the single most appropriate next agent to speak."""


async def create_gps_research_team(
    kernel_config: KernelConfig | None = None,
    max_messages: int = 50,
) -> tuple[SelectorGroupChat, dict[str, GPSAssistantAgent]]:
    """Create the GPS research team with all agents using SelectorGroupChat.

    The SelectorGroupChat uses an LLM to intelligently select which agent
    should respond next based on the conversation context.

    Args:
        kernel_config: Configuration for the SK Kernel
        max_messages: Maximum messages before termination

    Returns:
        Tuple of (SelectorGroupChat team, dict of agents)
    """
    # Create shared kernel
    kernel = create_kernel(kernel_config)

    # Create all agents
    agents = create_all_agents(kernel)
    participant_list: list[BaseChatAgent] = list(agents.values())

    # Create model client for selector
    selector_model = create_model_client("openai", temperature=0.1)

    # Define termination conditions
    termination = MaxMessageTermination(max_messages) | TextMentionTermination("TERMINATE")

    # Create SelectorGroupChat
    team = SelectorGroupChat(
        participants=participant_list,
        model_client=selector_model,
        selector_prompt=GPS_COORDINATOR_PROMPT,
        termination_condition=termination,
    )

    return team, agents


async def run_research_session(
    query: str,
    kernel_config: KernelConfig | None = None,
    max_messages: int = 50,
) -> dict[str, Any]:
    """Run a complete research session for a genealogical query.

    Args:
        query: The research query (e.g., "Find birth records for John Smith born ~1842")
        kernel_config: Optional kernel configuration
        max_messages: Maximum conversation messages

    Returns:
        Dictionary with research results
    """
    team, _agents = await create_gps_research_team(kernel_config, max_messages)

    # Format initial message
    initial_task = f"""Research Request:
{query}

Please conduct a thorough genealogical research following GPS standards:
1. Search multiple sources (FamilySearch, WikiTree, FindMyPast, etc.)
2. Create proper Evidence Explained citations
3. Analyze and correlate all evidence
4. Resolve any conflicts found
5. Write a proof argument if evidence supports the conclusion

Begin by having the research_agent search for relevant records."""

    # Run the team
    result: TaskResult = await team.run(task=initial_task)

    # Extract messages from result
    messages = []
    for msg in result.messages:
        if isinstance(msg, TextMessage):
            messages.append({
                "source": msg.source,
                "content": msg.content,
            })

    return {
        "query": query,
        "messages": messages,
        "stop_reason": result.stop_reason if hasattr(result, "stop_reason") else None,
    }


async def create_focused_research_team(
    agent_names: list[str],
    kernel_config: KernelConfig | None = None,
    max_messages: int = 20,
) -> tuple[SelectorGroupChat, dict[str, GPSAssistantAgent]]:
    """Create a focused research team with specific agents.

    Useful for targeted tasks like citation-only or translation sessions.

    Args:
        agent_names: List of agent names to include
        kernel_config: Kernel configuration
        max_messages: Maximum messages

    Returns:
        Tuple of (SelectorGroupChat team, dict of selected agents)
    """
    kernel = create_kernel(kernel_config)
    all_agents = create_all_agents(kernel)

    # Select requested agents
    selected_agents = {
        name: agent
        for name, agent in all_agents.items()
        if name in agent_names
    }

    if not selected_agents:
        raise ValueError(f"No valid agents found in: {agent_names}")

    # Always include workflow_agent if doing GPS evaluation
    gps_agents = {"gps_standards_critic", "gps_reasoning_critic"}
    if any(name in agent_names for name in gps_agents) and "workflow_agent" not in selected_agents:
        selected_agents["workflow_agent"] = all_agents["workflow_agent"]

    participant_list: list[BaseChatAgent] = list(selected_agents.values())
    selector_model = create_model_client("openai", temperature=0.1)
    termination = MaxMessageTermination(max_messages) | TextMentionTermination("TERMINATE")

    team = SelectorGroupChat(
        participants=participant_list,
        model_client=selector_model,
        selector_prompt=f"Focused research session with agents: {', '.join(selected_agents.keys())}. Select the most appropriate next speaker.",
        termination_condition=termination,
    )

    return team, selected_agents


async def evaluate_fact_gps(
    fact_json: str,
    kernel_config: KernelConfig | None = None,
) -> dict[str, Any]:
    """Evaluate a fact against all GPS pillars.

    Args:
        fact_json: JSON representation of the Fact
        kernel_config: Kernel configuration

    Returns:
        GPS evaluation results with pillar assessments
    """
    team, _agents = await create_focused_research_team(
        ["gps_standards_critic", "gps_reasoning_critic", "workflow_agent"],
        kernel_config,
        max_messages=10,
    )

    task = f"""Please evaluate the following fact against all 5 GPS pillars:

{fact_json}

gps_standards_critic: Evaluate Pillars 1 and 2
gps_reasoning_critic: Evaluate Pillars 3 and 4
workflow_agent: Determine if fact can be accepted (Pillar 5)

Provide a final recommendation: ACCEPT, REJECT, or INCOMPLETE (needs more work)."""

    result: TaskResult = await team.run(task=task)

    messages = []
    for msg in result.messages:
        if isinstance(msg, TextMessage):
            messages.append({
                "source": msg.source,
                "content": msg.content,
            })

    return {
        "fact_json": fact_json,
        "evaluation": messages,
    }


async def translate_record(
    record_text: str,
    source_language: str,
    kernel_config: KernelConfig | None = None,
) -> dict[str, Any]:
    """Translate a genealogical record.

    Args:
        record_text: Text to translate
        source_language: Source language
        kernel_config: Kernel configuration

    Returns:
        Translation results with cultural context
    """
    team, _agents = await create_focused_research_team(
        ["translation_agent"],
        kernel_config,
        max_messages=5,
    )

    task = f"""Please translate the following genealogical record from {source_language} to English:

{record_text}

Preserve genealogical terminology and note any ambiguities."""

    result: TaskResult = await team.run(task=task)

    # Get the last message as translation
    translation = None
    for msg in reversed(result.messages):
        if isinstance(msg, TextMessage) and msg.source == "translation_agent":
            translation = msg.content
            break

    return {
        "original": record_text,
        "source_language": source_language,
        "translation": translation,
    }


async def create_citation(
    record_data: dict[str, Any],
    kernel_config: KernelConfig | None = None,
) -> dict[str, Any]:
    """Create an Evidence Explained citation from record data.

    Args:
        record_data: Dictionary with record information
        kernel_config: Kernel configuration

    Returns:
        Citation in Evidence Explained format
    """
    team, _agents = await create_focused_research_team(
        ["citation_agent"],
        kernel_config,
        max_messages=5,
    )

    task = f"""Create a proper Evidence Explained citation from this record data:

{record_data}

Include:
1. Full citation in Evidence Explained format
2. Evidence classification (direct, indirect, or negative)
3. Source classification (original or derivative)"""

    result: TaskResult = await team.run(task=task)

    citation = None
    for msg in reversed(result.messages):
        if isinstance(msg, TextMessage) and msg.source == "citation_agent":
            citation = msg.content
            break

    return {
        "record_data": record_data,
        "citation": citation,
    }


async def synthesize_proof(
    research_question: str,
    evidence: list[str],
    conclusion: str,
    kernel_config: KernelConfig | None = None,
) -> dict[str, Any]:
    """Create a proof argument synthesizing evidence.

    Args:
        research_question: The original research question
        evidence: List of evidence items
        conclusion: The proposed conclusion
        kernel_config: Kernel configuration

    Returns:
        Proof argument suitable for GPS Pillar 5
    """
    team, _agents = await create_focused_research_team(
        ["synthesis_agent", "gps_reasoning_critic"],
        kernel_config,
        max_messages=10,
    )

    evidence_text = "\n".join(f"- {e}" for e in evidence)
    task = f"""Write a proof argument for the following:

Research Question: {research_question}

Evidence:
{evidence_text}

Proposed Conclusion: {conclusion}

Create a coherent narrative explaining how the evidence supports the conclusion.
Address any potential conflicts or gaps in the evidence."""

    result: TaskResult = await team.run(task=task)

    proof = None
    for msg in reversed(result.messages):
        if isinstance(msg, TextMessage) and msg.source == "synthesis_agent":
            proof = msg.content
            break

    return {
        "research_question": research_question,
        "conclusion": conclusion,
        "proof_argument": proof,
    }
