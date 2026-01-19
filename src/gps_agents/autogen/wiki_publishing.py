"""Wiki Publishing Team for gps-genealogy-agents.

SelectorGroupChat configuration for synchronized publishing across:
- Wikipedia (encyclopedic articles)
- Wikidata (structured claims/P-properties)
- WikiTree (collaborative genealogy profiles)
- GitHub (version-controlled research files)

Manager orchestrates specialized agents:
- Linguist: Wikipedia/WikiTree narrative tone
- DataEngineer: Wikidata JSON payloads
- DevOps: Git workflow and commits
"""

from __future__ import annotations

from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import SelectorGroupChat

from gps_agents.autogen.agents import create_model_client


# =============================================================================
# Agent Prompts
# =============================================================================

MANAGER_PROMPT = r"""You are the Lead Genealogy Integration Architect. Your mission is to maintain a
"Single Source of Truth" for genealogical research, starting from local
Markdown/Gramps data and synchronizing it across Wikipedia, Wikidata, WikiTree,
and GitHub.

Primary Objectives:
- Entity Extraction: Parse local research to identify Persons, Places, and Events.
- Platform Mapping: Prepare data payloads for Wikitext (Wikipedia), Bio-profiles (WikiTree), and Claims (Wikidata).
- GPS Grading: Audit articles against the Genealogical Proof Standard (Pillars 1-5).
- Version Control: Automate Git commit messages and file updates.

Workflow:
Step 1: Extraction & Mapping Logic
- Identify Subjects: Extract core biographical data (Names, Dates, Locations).
- Cross-Reference: Check if subject has existing gramps_id, wikidata_qid, or wikitree_id.
- Map Properties: Convert facts into Wikidata P-properties (P569 birth, P19 birth place, etc.) and WikiTree templates.

Step 2: Content Generation & Grading
- Produce a GPS Grade Card (1-10) with critiques:
  Evidence Quality, Proof Argument, Narrative Flow, Improvement Instructions.
- Include a DIFF block with exact additions/changes to reach 10/10.

Step 3: DevOps & Sync Workflow
- Output blocks:
  WIKIDATA_PAYLOAD (JSON for pywikibot)
  WIKITREE_BIO (WikiTree formatting)
  WIKIPEDIA_DRAFT (lead + infobox code)
  GIT_COMMIT_MSG (structured conventional commit)

Output format headers REQUIRED:
### 📊 GPS Grade Card
### 🧬 Extracted Entities
### 📝 Suggested Improvements
### 🚀 Sync Commands

Delegation:
- Ask Linguist for Wikipedia/WikiTree tone + DIFF suggestions.
- Ask Data Engineer for Wikidata JSON payload.
- Ask DevOps Specialist for commit message + suggested git commands.

Hard rules:
- Never invent sources.
- If evidence conflicts or is insufficient, ask for clarification or recommend specific additional sources.
- When finished, include "FINAL" to terminate the session.
"""

LINGUIST_PROMPT = r"""You are the Linguist Agent for genealogy publishing.

You produce:
- Wikipedia lead + neutral encyclopedic tone
- WikiTree biography with appropriate templates and narrative voice
- A precise unified DIFF against a local markdown article to improve clarity, sourcing, and GPS compliance.

Rules:
- Follow Wikipedia NPOV and avoid unsourced claims.
- Keep WikiTree personal but evidence-driven.
- When conflict exists, draft a short proof-style paragraph explaining resolution (or flag for reviewer).
- Output must be concise and directly usable.

Format your output as:
### WIKIPEDIA_DRAFT
[lead paragraph + infobox wikitext]

### WIKITREE_BIO
[WikiTree-formatted biography]

### DIFF
[unified diff for local article improvements]
"""

DATA_ENGINEER_PROMPT = r"""You are the Data Engineer Agent for genealogical knowledge graphs.

You produce:
- WIKIDATA_PAYLOAD JSON suitable for automation (e.g., pywikibot),
  mapping extracted facts to Wikidata properties (P569, P19, P570, P20, P106, P27, etc.)

Each statement should include:
- property (Pxxx)
- value
- qualifiers if relevant (dates with precision)
- references (cite the provided sources; do not invent)

Common properties:
- P569: date of birth
- P570: date of death
- P19: place of birth
- P20: place of death
- P106: occupation
- P27: country of citizenship
- P22: father
- P25: mother
- P26: spouse
- P40: child
- P21: sex or gender

If QID unknown, return a placeholder workflow: "search/create" guidance.

Format your output as:
### WIKIDATA_PAYLOAD
```json
{
  "claims": [...],
  "references": [...]
}
```
"""

DEVOPS_PROMPT = r"""You are the DevOps Specialist for the genealogy repo workflow.

You produce:
- A conventional commit message (feat/fix/chore/docs) with scope(genealogy)
- A short list of git commands the user can run
- Guidance for file organization (where to put markdown, media, exports)

Commit format:
- feat(genealogy): add new ancestor profile
- docs(genealogy): update research notes for [name]
- fix(genealogy): correct birth date for [name]
- chore(genealogy): reorganize media files

Rules:
- Keep outputs deterministic and copy/paste ready.
- Prefer small, atomic commits with clear message bodies.
- Always include Co-Authored-By for AI assistance.

Format your output as:
### GIT_COMMIT_MSG
```
[type](scope): [description]

[body]

Co-Authored-By: AI Assistant <noreply@example.com>
```

### GIT_COMMANDS
```bash
[commands]
```
"""


# =============================================================================
# Team Builder
# =============================================================================

def create_wiki_publishing_team(
    model: str = "gpt-4o-mini",
    max_messages: int = 30,
) -> tuple[SelectorGroupChat, dict[str, AssistantAgent]]:
    """Create the Wiki Publishing team with specialized agents.

    Args:
        model: Model name for all agents
        max_messages: Maximum messages before termination

    Returns:
        Tuple of (SelectorGroupChat team, dict of agents)
    """
    # Create model client
    client = create_model_client("openai", model=model, temperature=0.3)

    # Create agents
    manager = AssistantAgent(
        name="Manager",
        model_client=client,
        system_message=MANAGER_PROMPT,
        description="Lead architect coordinating wiki publishing workflow",
    )

    linguist = AssistantAgent(
        name="Linguist",
        model_client=client,
        system_message=LINGUIST_PROMPT,
        description="Wikipedia/WikiTree content writer with NPOV expertise",
    )

    data_engineer = AssistantAgent(
        name="DataEngineer",
        model_client=client,
        system_message=DATA_ENGINEER_PROMPT,
        description="Wikidata payload generator with P-property mapping",
    )

    devops = AssistantAgent(
        name="DevOps",
        model_client=client,
        system_message=DEVOPS_PROMPT,
        description="Git workflow specialist for version control",
    )

    agents = {
        "manager": manager,
        "linguist": linguist,
        "data_engineer": data_engineer,
        "devops": devops,
    }

    # Termination when Manager says "FINAL"
    termination = (
        MaxMessageTermination(max_messages)
        | TextMentionTermination("FINAL")
    )

    # Manager selects which agent speaks next
    team = SelectorGroupChat(
        participants=[manager, linguist, data_engineer, devops],
        model_client=client,
        selector_prompt=(
            "Based on the conversation, select the next agent to speak:\n"
            "- Manager: Overall coordination and GPS grading\n"
            "- Linguist: Wikipedia/WikiTree content generation\n"
            "- DataEngineer: Wikidata JSON payloads\n"
            "- DevOps: Git commands and commit messages\n\n"
            "Select the single most appropriate next speaker."
        ),
        termination_condition=termination,
    )

    return team, agents


async def publish_to_wikis(
    article_text: str,
    subject_name: str,
    gramps_id: str | None = None,
    wikidata_qid: str | None = None,
    wikitree_id: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Prepare genealogical research for wiki publishing.

    Args:
        article_text: Local research article/notes
        subject_name: Name of the subject
        gramps_id: Optional Gramps ID if known
        wikidata_qid: Optional Wikidata QID if known
        wikitree_id: Optional WikiTree ID if known
        model: Model to use

    Returns:
        Publishing outputs including payloads for each platform
    """
    team, agents = create_wiki_publishing_team(model=model)

    # Build context about existing IDs
    id_context = []
    if gramps_id:
        id_context.append(f"Gramps ID: {gramps_id}")
    if wikidata_qid:
        id_context.append(f"Wikidata QID: {wikidata_qid}")
    if wikitree_id:
        id_context.append(f"WikiTree ID: {wikitree_id}")

    id_str = "\n".join(id_context) if id_context else "No existing identifiers found."

    task = f"""Prepare wiki publishing outputs for the following genealogical research:

Subject: {subject_name}

Existing Identifiers:
{id_str}

Research Article:
---
{article_text}
---

Please:
1. Grade this against GPS standards (1-10 scale)
2. Extract entities for Wikidata (P-properties)
3. Draft Wikipedia lead and WikiTree bio
4. Prepare git commit for local changes
5. Provide improvement suggestions for 10/10 GPS compliance
"""

    result: TaskResult = await team.run(task=task)

    # Extract messages
    messages = []
    for msg in result.messages:
        if isinstance(msg, TextMessage):
            messages.append({
                "source": msg.source,
                "content": msg.content,
            })

    # Parse outputs from final messages
    outputs = {
        "subject": subject_name,
        "messages": messages,
        "wikidata_payload": _extract_section(messages, "WIKIDATA_PAYLOAD"),
        "wikipedia_draft": _extract_section(messages, "WIKIPEDIA_DRAFT"),
        "wikitree_bio": _extract_section(messages, "WIKITREE_BIO"),
        "git_commit": _extract_section(messages, "GIT_COMMIT_MSG"),
        "gps_grade": _extract_section(messages, "GPS Grade Card"),
    }

    return outputs


async def grade_article_gps(
    article_text: str,
    subject_name: str,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Grade a genealogical article against GPS standards.

    Args:
        article_text: The article to grade
        subject_name: Subject of the article
        model: Model to use

    Returns:
        GPS grading with improvement suggestions
    """
    team, agents = create_wiki_publishing_team(model=model, max_messages=15)

    task = f"""Grade the following genealogical article against GPS standards:

Subject: {subject_name}

Article:
---
{article_text}
---

Provide:
1. GPS Grade Card (1-10 scale) with scores for:
   - Evidence Quality
   - Source Citations
   - Proof Argument
   - Conflict Resolution
   - Narrative Flow

2. Specific improvements needed to reach 10/10

3. A DIFF showing exact changes to make

Manager should coordinate with Linguist for grading and improvements.
"""

    result: TaskResult = await team.run(task=task)

    messages = []
    for msg in result.messages:
        if isinstance(msg, TextMessage):
            messages.append({
                "source": msg.source,
                "content": msg.content,
            })

    return {
        "subject": subject_name,
        "messages": messages,
        "grade_card": _extract_section(messages, "GPS Grade Card"),
        "improvements": _extract_section(messages, "Suggested Improvements"),
        "diff": _extract_section(messages, "DIFF"),
    }


async def generate_wikidata_payload(
    facts: list[dict[str, Any]],
    subject_name: str,
    wikidata_qid: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Generate Wikidata claims from structured facts.

    Args:
        facts: List of fact dictionaries with keys like 'statement', 'sources'
        subject_name: Name of the subject
        wikidata_qid: Existing QID if known
        model: Model to use

    Returns:
        Wikidata payload ready for pywikibot
    """
    team, agents = create_wiki_publishing_team(model=model, max_messages=10)

    facts_text = "\n".join(
        f"- {f.get('statement', f)}" for f in facts
    )

    task = f"""Generate Wikidata claims for:

Subject: {subject_name}
{"Existing QID: " + wikidata_qid if wikidata_qid else "No existing QID - new item needed."}

Facts:
{facts_text}

DataEngineer: Create WIKIDATA_PAYLOAD with proper P-properties and references.
Map each fact to appropriate Wikidata properties.
"""

    result: TaskResult = await team.run(task=task)

    messages = []
    for msg in result.messages:
        if isinstance(msg, TextMessage):
            messages.append({
                "source": msg.source,
                "content": msg.content,
            })

    return {
        "subject": subject_name,
        "wikidata_qid": wikidata_qid,
        "payload": _extract_section(messages, "WIKIDATA_PAYLOAD"),
        "messages": messages,
    }


def _extract_section(messages: list[dict], section_name: str) -> str | None:
    """Extract a named section from agent messages.

    Args:
        messages: List of message dicts with 'content' key
        section_name: Section header to find (without ###)

    Returns:
        Section content or None if not found
    """
    for msg in reversed(messages):
        content = msg.get("content", "")
        if section_name in content:
            # Find the section
            lines = content.split("\n")
            in_section = False
            section_lines = []

            for line in lines:
                if section_name in line:
                    in_section = True
                    continue
                elif in_section:
                    if line.startswith("###") or line.startswith("## "):
                        break
                    section_lines.append(line)

            if section_lines:
                return "\n".join(section_lines).strip()

    return None


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    """Example usage of the wiki publishing team."""
    article = """
    # Paul Janvrin Vincent (1931-2023)

    Paul Janvrin Vincent was born on March 15, 1931 in St. Helier, Jersey.
    He was the son of Herbert Vincent and Marie Janvrin.

    ## Sources
    - Birth Certificate, States of Jersey, 1931
    - 1939 Register, Jersey
    - Death notice, Jersey Evening Post, 2023
    """

    result = await publish_to_wikis(
        article_text=article,
        subject_name="Paul Janvrin Vincent",
        gramps_id="I0001",
    )

    print("=== Wiki Publishing Results ===")
    print(f"\nGPS Grade:\n{result.get('gps_grade', 'Not found')}")
    print(f"\nWikidata Payload:\n{result.get('wikidata_payload', 'Not found')}")
    print(f"\nGit Commit:\n{result.get('git_commit', 'Not found')}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
