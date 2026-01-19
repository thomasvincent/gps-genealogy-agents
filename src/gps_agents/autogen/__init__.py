"""AutoGen multi-agent orchestration for GPS Genealogy Agents.

Uses the modern autogen_agentchat API with SelectorGroupChat for intelligent
agent coordination in genealogical research.
"""

from gps_agents.autogen.agents import (
    GPSAssistantAgent,
    create_all_agents,
    create_citation_agent,
    create_data_quality_agent,
    create_dna_agent,
    create_gps_reasoning_critic,
    create_gps_standards_critic,
    create_model_client,
    create_research_agent,
    create_synthesis_agent,
    create_translation_agent,
    create_workflow_agent,
    get_available_providers,
    validate_api_key,
)
from gps_agents.autogen.orchestration import (
    create_citation,
    create_focused_research_team,
    create_gps_research_team,
    evaluate_fact_gps,
    run_research_session,
    synthesize_proof,
    translate_record,
)
from gps_agents.autogen.wiki_publishing import (
    create_wiki_publishing_team,
    generate_wikidata_payload,
    grade_article_gps,
    publish_to_wikis,
)

__all__ = [
    # Agent classes
    "GPSAssistantAgent",
    # Agent factories
    "create_all_agents",
    "create_citation_agent",
    "create_data_quality_agent",
    "create_dna_agent",
    "create_gps_reasoning_critic",
    "create_gps_standards_critic",
    "create_research_agent",
    "create_synthesis_agent",
    "create_translation_agent",
    "create_workflow_agent",
    # Model client utilities
    "create_model_client",
    "get_available_providers",
    "validate_api_key",
    # Team orchestration
    "create_focused_research_team",
    "create_gps_research_team",
    # Research workflows
    "create_citation",
    "evaluate_fact_gps",
    "run_research_session",
    "synthesize_proof",
    "translate_record",
    # Wiki publishing
    "create_wiki_publishing_team",
    "generate_wikidata_payload",
    "grade_article_gps",
    "publish_to_wikis",
]
