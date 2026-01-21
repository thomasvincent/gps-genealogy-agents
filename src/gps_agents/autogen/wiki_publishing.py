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
- LogicReviewer: Timeline and relationship validation
- SourceReviewer: Source verification and citation checking
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import SelectorGroupChat

from gps_agents.autogen.agents import create_model_client

if TYPE_CHECKING:
    from pathlib import Path

    from autogen_agentchat.base import TaskResult

# =============================================================================
# Publishing Decision Models
# =============================================================================

class Platform(str, Enum):
    """Publishing platforms with different quality thresholds."""
    WIKIPEDIA = "wikipedia"    # Highest bar: encyclopedic, fully sourced
    WIKIDATA = "wikidata"      # High bar: structured claims with references
    WIKITREE = "wikitree"      # Medium bar: collaborative, allows uncertainty
    GITHUB = "github"          # Low bar: version-controlled drafts


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"  # Fabrications - blocks all platforms
    HIGH = "high"          # Logic/source errors - blocks Wikipedia/Wikidata
    MEDIUM = "medium"      # Quality issues - blocks Wikipedia only
    LOW = "low"            # Style issues - warning only


@dataclass
class ReviewIssue:
    """A single issue found by a reviewer."""
    severity: Severity
    category: str  # fabrication, logic, source, quality, style
    description: str
    agent_responsible: str | None = None  # Which agent caused this?
    confidence: float = 1.0  # 0-1


@dataclass
class PublishDecision:
    """Decision about what can be published where."""
    wikipedia: bool = True
    wikidata: bool = True
    wikitree: bool = True
    github: bool = True

    issues: list[ReviewIssue] = field(default_factory=list)
    integrity_score: int = 100

    @classmethod
    def from_issues(cls, issues: list[ReviewIssue]) -> PublishDecision:
        """Create a publish decision based on found issues."""
        decision = cls(issues=issues)

        for issue in issues:
            if issue.severity == Severity.CRITICAL:
                # Block everything
                decision.wikipedia = False
                decision.wikidata = False
                decision.wikitree = False
                decision.github = False
            elif issue.severity == Severity.HIGH:
                # Block high-quality platforms
                decision.wikipedia = False
                decision.wikidata = False
            elif issue.severity == Severity.MEDIUM:
                # Block only Wikipedia (strictest platform)
                decision.wikipedia = False

        # Calculate integrity score
        severity_penalties = {
            Severity.CRITICAL: 40,
            Severity.HIGH: 20,
            Severity.MEDIUM: 10,
            Severity.LOW: 5,
        }
        total_penalty = sum(severity_penalties[i.severity] for i in issues)
        decision.integrity_score = max(0, 100 - total_penalty)

        return decision

    def get_allowed_platforms(self) -> list[Platform]:
        """Get list of platforms where publishing is allowed."""
        allowed = []
        if self.wikipedia:
            allowed.append(Platform.WIKIPEDIA)
        if self.wikidata:
            allowed.append(Platform.WIKIDATA)
        if self.wikitree:
            allowed.append(Platform.WIKITREE)
        if self.github:
            allowed.append(Platform.GITHUB)
        return allowed

    def summary(self) -> str:
        """Human-readable summary of the decision."""
        allowed = self.get_allowed_platforms()
        if not allowed:
            return "❌ BLOCKED: No platforms approved for publishing"

        platform_names = [p.value.title() for p in allowed]
        blocked = []
        if not self.wikipedia:
            blocked.append("Wikipedia")
        if not self.wikidata:
            blocked.append("Wikidata")
        if not self.wikitree:
            blocked.append("WikiTree")

        if blocked:
            return f"⚠️ DOWNGRADED: Approved for {', '.join(platform_names)} only (blocked: {', '.join(blocked)})"
        return f"✅ APPROVED: All platforms ({', '.join(platform_names)})"


# =============================================================================
# Reviewer Memory - Track Agent Mistake Patterns
# =============================================================================

@dataclass
class AgentMistake:
    """Record of a mistake made by an agent."""
    agent_name: str
    category: str
    severity: Severity
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class ReviewerMemory:
    """
    Tracks recurring mistake patterns per agent.

    Identifies which agents are problematic and what kinds of mistakes
    they tend to make (e.g., "DataEngineer keeps hallucinating QIDs").
    """

    def __init__(self, persist_path: Path | None = None) -> None:
        """Initialize reviewer memory.

        Args:
            persist_path: Optional path to persist memory to disk
        """
        self.mistakes: list[AgentMistake] = []
        self.persist_path = persist_path

        if persist_path and persist_path.exists():
            self._load()

    def record_mistake(
        self,
        agent_name: str,
        category: str,
        severity: Severity,
        description: str,
    ) -> None:
        """Record a mistake made by an agent."""
        mistake = AgentMistake(
            agent_name=agent_name,
            category=category,
            severity=severity,
            description=description,
        )
        self.mistakes.append(mistake)

        if self.persist_path:
            self._save()

    def record_issues(self, issues: list[ReviewIssue]) -> None:
        """Record all issues from a review."""
        for issue in issues:
            if issue.agent_responsible:
                self.record_mistake(
                    agent_name=issue.agent_responsible,
                    category=issue.category,
                    severity=issue.severity,
                    description=issue.description,
                )

    def get_agent_stats(self, agent_name: str) -> dict[str, Any]:
        """Get mistake statistics for an agent."""
        agent_mistakes = [m for m in self.mistakes if m.agent_name == agent_name]

        if not agent_mistakes:
            return {"total": 0, "by_category": {}, "by_severity": {}}

        by_category: dict[str, int] = defaultdict(int)
        by_severity: dict[str, int] = defaultdict(int)

        for m in agent_mistakes:
            by_category[m.category] += 1
            by_severity[m.severity.value] += 1

        return {
            "total": len(agent_mistakes),
            "by_category": dict(by_category),
            "by_severity": dict(by_severity),
            "most_common": max(by_category.items(), key=lambda x: x[1])[0] if by_category else None,
        }

    def get_problem_agents(self, min_mistakes: int = 3) -> list[tuple[str, dict]]:
        """Get agents with recurring mistake patterns.

        Args:
            min_mistakes: Minimum mistakes to be considered problematic

        Returns:
            List of (agent_name, stats) tuples sorted by mistake count
        """
        agent_names = {m.agent_name for m in self.mistakes}

        problem_agents = []
        for name in agent_names:
            stats = self.get_agent_stats(name)
            if stats["total"] >= min_mistakes:
                problem_agents.append((name, stats))

        return sorted(problem_agents, key=lambda x: x[1]["total"], reverse=True)

    def generate_report(self) -> str:
        """Generate a human-readable report of mistake patterns."""
        if not self.mistakes:
            return "No mistakes recorded yet."

        lines = ["# Reviewer Memory Report", ""]

        # Overall stats
        lines.append(f"**Total Mistakes Recorded:** {len(self.mistakes)}")
        lines.append("")

        # Problem agents
        problem_agents = self.get_problem_agents(min_mistakes=1)
        if problem_agents:
            lines.append("## Agent Mistake Patterns")
            lines.append("")
            for agent, stats in problem_agents:
                lines.append(f"### {agent}")
                lines.append(f"- Total mistakes: {stats['total']}")
                if stats["most_common"]:
                    lines.append(f"- Most common issue: {stats['most_common']}")
                lines.append(f"- By severity: {stats['by_severity']}")
                lines.append("")

        return "\n".join(lines)

    def _save(self) -> None:
        """Persist memory to disk."""
        if not self.persist_path:
            return

        data = [
            {
                "agent_name": m.agent_name,
                "category": m.category,
                "severity": m.severity.value,
                "description": m.description,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in self.mistakes
        ]

        self.persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        """Load memory from disk."""
        if not self.persist_path or not self.persist_path.exists():
            return

        try:
            data = json.loads(self.persist_path.read_text())
            self.mistakes = [
                AgentMistake(
                    agent_name=d["agent_name"],
                    category=d["category"],
                    severity=Severity(d["severity"]),
                    description=d["description"],
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                )
                for d in data
            ]
        except (json.JSONDecodeError, KeyError):
            self.mistakes = []


# Global reviewer memory instance
_reviewer_memory: ReviewerMemory | None = None


def get_reviewer_memory(persist_path: Path | None = None) -> ReviewerMemory:
    """Get or create the global reviewer memory instance."""
    global _reviewer_memory
    if _reviewer_memory is None:
        _reviewer_memory = ReviewerMemory(persist_path)
    return _reviewer_memory


# =============================================================================
# Agent Prompts
# =============================================================================

MANAGER_PROMPT = r"""You are the Lead Genealogy Integration Architect. Your mission is to maintain a
"Single Source of Truth" for genealogical research, starting from local
Markdown/Gramps data and synchronizing it across Wikipedia, Wikidata, WikiTree,
and GitHub.

CORE RESPONSIBILITIES:
1. Entity Extraction: Parse local research to identify Persons, Places, and Events.
2. Platform Mapping: Prepare data payloads for Wikitext (Wikipedia), Bio-profiles (WikiTree), and Claims (Wikidata).
3. GPS Grading: Audit articles against the 5 Pillars of the Genealogical Proof Standard.
4. Integrity Review: Ensure no fabrications or logical errors exist.

WORKFLOW DELEGATION (execute in order):

Step 1 - EXTRACTION:
Ask the Data Engineer to:
- Extract entities (Persons, Places, Events)
- Map facts to Wikidata properties (P569, P19, P570, P20, etc.)
- Identify existing QIDs or flag as NEW_ITEM
- Produce WIKIDATA_PAYLOAD JSON block

Step 2 - CONTENT:
Ask the Linguist to:
- Draft Wikipedia lead section (NPOV, encyclopedic tone)
- Generate WikiTree biography with templates
- Provide GPS Grade Card (1-10 scale)
- Suggest DIFF improvements for local Markdown

Step 3 - REVIEW:
Ask the Reviewer to:
- Fact-check ALL outputs against original sources
- Find fabrications, logic errors, source mismatches
- Produce REVIEW REPORT with INTEGRITY SCORE
- List BLOCKING ISSUES (CRITICAL/HIGH severity)

Step 4 - DEVOPS:
Ask the DevOps Specialist to:
- Generate conventional commit message
- Provide exact git commands
- Suggest file organization

REQUIRED OUTPUT HEADERS (for automation parsing):
### 📊 GPS Grade Card
### 🧬 Extracted Entities
### 🔍 REVIEW REPORT
### 🧭 Research Notes
### 🚀 Sync Commands

HARD RULES:
- Never invent sources or fabricate data.
- If evidence conflicts or is insufficient, ask for specific records needed.
- NEVER say "FINAL" until Reviewer has cleared ALL "CRITICAL" and "HIGH" issues.
- If Reviewer finds blocking issues, coordinate fixes before proceeding.
- When finished AND Reviewer reports "Clear to publish", include "FINAL" to terminate.
"""

LINGUIST_PROMPT = r"""You are the Linguist Agent. You specialize in the distinct writing styles of
Wikipedia (encyclopedic NPOV) and WikiTree (collaborative narrative).

CRITICAL CONSTRAINT: You ONLY consume ACCEPTED facts with confidence >= 0.9.
Any facts below this threshold must be noted as uncertainties, not stated as fact.

TASKS:
1. Draft a Wikipedia lead section with neutral tone and infobox data (target "Grade A": comprehensive, neutral, well-sourced; if not at 9/10, list exact improvements)
2. Generate a WikiTree biography using community templates (e.g., {{Birth Date and Age}})
3. Provide a DIFF block suggesting specific improvements for the user's local Markdown article
4. Grade the article on a scale of 1-10 based on GPS Pillar 5 (Written Conclusion)

WIKIPEDIA STYLE:
- Encyclopedic, neutral point of view (NPOV)
- Third person, past tense for deceased
- Cite sources inline with {{cite web}} or {{cite book}}
- Lead should summarize: who, what, when, where, significance

WIKIPEDIA INFOBOX TEMPLATE (use for all person profiles):
```wikitext
{{Infobox person
| name             = {full_name}
| image            = <!-- filename only, no File: prefix -->
| image_size       =
| alt              =
| caption          =
| birth_name       = {birth_name_if_different}
| birth_date       = {{{{birth date|{birth_year}|{birth_month}|{birth_day}|df=yes}}}}
| birth_place      = [[{birth_city}]], [[{birth_region}]], [[{birth_country}]]
| death_date       = {{{{death date and age|{death_year}|{death_month}|{death_day}|{birth_year}|{birth_month}|{birth_day}|df=yes}}}}
| death_place      = [[{death_city}]], [[{death_region}]], [[{death_country}]]
| death_cause      = <!-- only if notable and sourced -->
| resting_place    = [[{cemetery_name}]], [[{cemetery_location}]]
| resting_place_coordinates = <!-- {{{{coord|LAT|LONG|type:landmark|display=inline}}}} -->
| nationality      = {nationality}
| citizenship      =
| occupation       = {occupation}
| years_active     =
| known_for        =
| spouse           = {{{{marriage|{spouse_name}|{marriage_year}|{end_year_or_blank}}}}}
| children         = {number_of_children}
| parents          = {father_name}<br>{mother_name}
| relatives        =
| signature        =
| website          =
| footnotes        =
}}
```

INFOBOX RULES:
- Only include fields with ACCEPTED facts (confidence >= 0.9)
- Use [[wikilinks]] for places that have Wikipedia articles
- Birth/death dates: Use templates, not raw text
- For uncertain dates: Use {{circa}} or note in footnotes
- For living persons: OMIT death fields entirely
- For unknown parents: Leave blank, don't speculate

WIKITREE STYLE:
- Collaborative narrative voice ("Our research shows...")
- Personal but evidence-driven
- Use community templates: {{Birth Date and Age}}, {{Death Date and Age}}
- Include research notes and DNA connections if available

WIKITREE BIOGRAPHY TEMPLATE:
```
== Biography ==
'''[Given Name] [Surname]''' was born [date] in [[Place]].

=== Family ===
[He/She] was the [son/daughter] of [[Father Name]] and [[Mother Name]].

[Marriage and children details with {{Marriage}} and {{Child}} templates]

=== Life ===
[Narrative of significant life events, evidence-driven]

=== Death ===
[Death details if known]

== Research Notes ==
=== Uncertainties ===
* [List facts with confidence < 0.9]

=== Sources Needed ===
* [List records to search next]

== Sources ==
<references />
```

UNCERTAINTY HANDLING:
- Facts with confidence < 0.9: Label as "possibly" or "research suggests"
- Unresolved conflicts: Present both views with sources
- Missing data: Note what records could fill gaps
- Never assert uncertain facts as definitive

GPS GRADE CARD (1-10 scale):
Rate each of the 5 GPS Pillars:
1. Reasonably Exhaustive Search
2. Complete, Accurate Citations
3. Analysis and Correlation
4. Resolution of Conflicts
5. Sound Written Conclusion

OUTPUT FORMAT:
### 📊 GPS Grade Card
[Scores and overall grade]

### RESEARCH_NOTES
[List unknowns/uncertainties, conflicts, and next actions with specific sources to consult]

### WIKIPEDIA_DRAFT
[Lead paragraph + infobox wikitext using template above]

### WIKITREE_BIO
[WikiTree-formatted biography with templates]

### DIFF
[Unified diff showing exact changes for local Markdown]

RULES:
- Follow Wikipedia NPOV strictly; avoid unsourced claims
- Keep WikiTree personal but evidence-driven
- When conflicts exist, draft a proof-style paragraph or flag for Reviewer
- Output must be concise and directly usable by automation
- ONLY use ACCEPTED facts for definitive statements
"""

DATA_ENGINEER_PROMPT = r"""You are the Data Engineer Agent. Your specialty is converting unstructured
narrative into structured claims for Wikidata and Gramps.

TASKS:
1. Map facts to Wikidata Property IDs
2. Generate a WIKIDATA_PAYLOAD JSON block for automation tools (pywikibot)
3. Identify if an entity is NEW_ITEM or provide existing QID
4. Include source references for every claim; do not invent data

WIKIDATA PROPERTIES (commonly used for genealogy):
- P31: instance of (use Q5 for humans)
- P569: date of birth
- P570: date of death
- P19: place of birth
- P20: place of death
- P21: sex or gender (Q6581097=male, Q6581072=female)
- P22: father
- P25: mother
- P26: spouse
- P40: child
- P106: occupation
- P27: country of citizenship
- P735: given name
- P734: family name
- P1412: languages spoken

MULTILINGUAL REQUIREMENTS:
- Provide labels, descriptions, and aliases for at least: en, es, fr, de, it, nl
- If native or regional languages are inferable from sources, include them as well

PAYLOAD STRUCTURE:
Each claim must include:
- property: Pxxx identifier
- value: the data value
- qualifiers: date precision, sourcing circumstances
- references: cite provided sources only; NEVER invent

ENTITY IDENTIFICATION:
- If QID is known: use it
- If QID is unknown: search Wikidata first
- If no match found: flag as "NEW_ITEM" with creation guidance

OUTPUT FORMAT:
### 🧬 Extracted Entities
[List of persons/places/events with identifiers]

### WIKIDATA_PAYLOAD
```json
{
  "entity": "NEW_ITEM" | "Qxxxxxxx",
  "labels": {"en": "Person Name"},
  "claims": [
    {
      "property": "P569",
      "value": {"time": "+1850-03-15T00:00:00Z", "precision": 11},
      "references": [{"P248": "Qxxxxx", "P854": "https://..."}]
    }
  ]
}
```

HARD RULES:
- Include source references for EVERY claim
- Do not invent QIDs, dates, or relationships
- If data is uncertain, use appropriate precision (year=9, month=10, day=11)
- Flag conflicting data for Reviewer attention
"""

DEVOPS_PROMPT = r"""You are the DevOps Specialist. You manage the local repository and deployment workflow.

TASKS:
1. Generate a Conventional Commit message
2. Provide exact git commands for the user to add and commit files
3. Suggest file organization for media and research exports

CONVENTIONAL COMMIT FORMAT:
- feat(genealogy): add P569 to Q1234
- feat(genealogy): create profile for [name]
- docs(genealogy): update research notes for [name]
- fix(genealogy): correct birth date for [name]
- chore(genealogy): reorganize media files
- data(genealogy): add Wikidata claims for [name]

COMMIT MESSAGE STRUCTURE:
```
type(scope): short description (max 72 chars)

- Bullet points explaining what changed
- Reference to source records used
- Note any pending items

Co-Authored-By: AI Assistant <noreply@anthropic.com>
```

FILE ORGANIZATION:
```
research/
├── persons/
│   └── surname-firstname-birthyear/
│       ├── profile.md
│       ├── sources/
│       └── media/
├── exports/
│   ├── wikidata/
│   └── wikitree/
└── gedcom/
```

OUTPUT FORMAT:
### 🚀 Sync Commands

#### GIT_COMMIT_MSG
```
[type](scope): [description]

[body]

Co-Authored-By: AI Assistant <noreply@anthropic.com>
```

#### GIT_COMMANDS
```bash
git add [files]
git commit -m "$(cat <<'EOF'
[commit message here]
EOF
)"
```

RULES:
- Keep outputs deterministic and copy/paste ready
- Prefer small, atomic commits over large changes
- Always include Co-Authored-By for AI assistance
- Validate file paths exist before suggesting git add
"""

REVIEWER_PROMPT = r"""You are the Reviewer Agent. You are the adversarial skeptic whose job is to
find errors in the other agents' work.

TASK: Review ALL outputs from other agents and produce a REVIEW REPORT.

CHECKS TO PERFORM:

1. FABRICATION CHECK (Severity: CRITICAL)
   - Claims not supported by the original sources
   - Invented dates, places, relationships
   - Hallucinated Wikidata QIDs (verify they exist)
   - Made-up citations or references

2. LOGIC CHECK (Severity: HIGH)
   - Timeline impossibilities:
     * Death before birth
     * Child born before parent was ~12 years old
     * Parent died before child was born
   - Geographic impossibilities (born in two places)
   - Relationship contradictions (same person as both father and son)
   - Mathematical errors in age/date calculations

3. SOURCE MISMATCH CHECK (Severity: HIGH)
   - Claims that misinterpret the provided text
   - Over-interpretation of evidence (source says "about 1850", claim says "1850")
   - Treating derivative sources as primary
   - Missing uncertainty qualifiers

4. QUALITY CHECK (Severity: MEDIUM)
   - Incomplete citations
   - Ambiguous statements
   - Missing precision indicators

5. STYLE CHECK (Severity: LOW)
   - Wikipedia NPOV violations
   - WikiTree template errors
   - Commit message format issues

OUTPUT FORMAT:
### 🔍 REVIEW REPORT

#### Fabrication Check
[List issues or "✓ No fabrications detected"]

#### Logic Check
[List issues or "✓ No logical errors detected"]

#### Source Verification
[List issues or "✓ Sources verified"]

#### Quality Issues
[List issues or "✓ Quality acceptable"]

### 📊 INTEGRITY SCORE
[0-100 score]
- Fabrication: [0-40 points deducted per issue]
- Logic: [0-20 points deducted per issue]
- Sources: [0-15 points deducted per issue]
- Quality: [0-10 points deducted per issue]

### ⚠️ BLOCKING ISSUES
[List CRITICAL and HIGH severity issues that MUST be fixed]
[If none: "Clear to publish."]

CRITICAL RULES:
- You are ADVERSARIAL - your job is to find problems, not approve work
- If ANY CRITICAL or HIGH severity issues exist, do NOT say "Clear to publish"
- Never approve work you haven't thoroughly checked
- When in doubt, flag it - false positives are better than errors going live
- Demand evidence from other agents if they dispute your findings
"""

# Dual Reviewer System - Two perspectives for quorum
LOGIC_REVIEWER_PROMPT = r"""You are the Logic Reviewer - you focus on TIMELINE and RELATIONSHIP consistency.

Your specialty is detecting LOGICAL IMPOSSIBILITIES in genealogical data:

1. TIMELINE ERRORS (Your primary focus)
   - Death before birth
   - Child born before parent was 12 or after parent was 60
   - Marriage before age 14
   - Events after death
   - Lifespan > 120 years
   - Birth/death dates that don't match era (e.g., exact dates for 1500s)

2. RELATIONSHIP CONTRADICTIONS
   - Same person listed as both parent and child
   - Circular relationships
   - Conflicting parent assignments
   - Age gaps that make relationships impossible

3. GEOGRAPHIC IMPOSSIBILITIES
   - Born in two different places
   - Events in different continents on same day
   - Place names that didn't exist at claimed date

4. MATHEMATICAL ERRORS
   - Ages don't match birth/death dates
   - Generation gaps too short (<15 years) or too long (>50 years)

For each issue, identify:
- AGENT: Which agent produced the problematic data
- ISSUE: What's logically wrong
- SEVERITY: CRITICAL (impossible) / HIGH (very unlikely) / MEDIUM (suspicious)
- EVIDENCE: The specific dates/facts that conflict

Format your output as:
### 🧮 LOGIC REVIEW

#### Timeline Analysis
[Check all date calculations]

#### Relationship Verification
[Check all family connections]

#### Geographic Consistency
[Check all place claims]

### LOGIC_VERDICT
[PASS / FAIL with specific issues]

You must AGREE with SourceReviewer for publication to proceed.
If you disagree with SourceReviewer, explain why and demand resolution.
"""

SOURCE_REVIEWER_PROMPT = r"""You are the Source Reviewer - you focus on EVIDENCE and CITATION accuracy.

Your specialty is detecting SOURCE PROBLEMS in genealogical claims:

1. FABRICATIONS (Your primary focus)
   - Claims with no source cited
   - Made-up citations that don't exist
   - Hallucinated Wikidata QIDs (e.g., Q numbers that don't exist)
   - Invented repository names or record types

2. SOURCE MISMATCHES
   - Claims that don't match what the source says
   - Over-interpretation (source says "John" but claim says "John William")
   - Missing uncertainty (source says "about 1850" but claim says "1850")
   - Treating derivative sources as original

3. CITATION PROBLEMS
   - Incomplete citations (missing repository, date accessed, etc.)
   - Wrong citation format for source type
   - URLs that are malformed or likely broken
   - References to sources not actually consulted

4. EVIDENCE CLASSIFICATION
   - Direct evidence treated as proof (it still needs correlation)
   - Indirect evidence treated as direct
   - Negative evidence not acknowledged

For each issue, identify:
- AGENT: Which agent produced the problematic claim
- CLAIM: The specific claim that's problematic
- SOURCE: What the source actually says (if available)
- SEVERITY: CRITICAL (fabrication) / HIGH (mismatch) / MEDIUM (incomplete)

Format your output as:
### 📚 SOURCE REVIEW

#### Fabrication Check
[Verify each claim has legitimate source support]

#### Source-Claim Matching
[Compare claims to cited sources]

#### Citation Quality
[Check citation completeness and format]

### SOURCE_VERDICT
[PASS / FAIL with specific issues]

You must AGREE with LogicReviewer for publication to proceed.
If you disagree with LogicReviewer, explain why and demand resolution.
"""


# =============================================================================
# Team Builder
# =============================================================================

def create_wiki_publishing_team(
    model: str = "gpt-4o-mini",
    max_messages: int = 30,
    use_dual_reviewers: bool = True,
) -> tuple[SelectorGroupChat, dict[str, AssistantAgent]]:
    """Create the Wiki Publishing team with specialized agents.

    Args:
        model: Model name for all agents
        max_messages: Maximum messages before termination
        use_dual_reviewers: If True, use LogicReviewer + SourceReviewer quorum
                           If False, use single Reviewer (legacy mode)

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

    if use_dual_reviewers:
        # Dual reviewer quorum system
        logic_reviewer = AssistantAgent(
            name="LogicReviewer",
            model_client=client,
            system_message=LOGIC_REVIEWER_PROMPT,
            description="Timeline and relationship consistency checker",
        )

        source_reviewer = AssistantAgent(
            name="SourceReviewer",
            model_client=client,
            system_message=SOURCE_REVIEWER_PROMPT,
            description="Source verification and citation accuracy checker",
        )

        agents["logic_reviewer"] = logic_reviewer
        agents["source_reviewer"] = source_reviewer
        participants = [manager, linguist, data_engineer, devops, logic_reviewer, source_reviewer]

        selector_prompt = (
            "Based on the conversation, select the next agent to speak:\n"
            "- Manager: Overall coordination and GPS grading\n"
            "- Linguist: Wikipedia/WikiTree content generation\n"
            "- DataEngineer: Wikidata JSON payloads\n"
            "- DevOps: Git commands and commit messages\n"
            "- LogicReviewer: Timeline/relationship validation (must check BEFORE publication)\n"
            "- SourceReviewer: Source/citation verification (must check BEFORE publication)\n\n"
            "QUORUM REQUIREMENT: BOTH LogicReviewer AND SourceReviewer MUST review\n"
            "and BOTH must say PASS before Manager can say FINAL.\n"
            "If either reviewer says FAIL, issues must be addressed first.\n"
            "Select the single most appropriate next speaker."
        )
    else:
        # Legacy single reviewer mode
        reviewer = AssistantAgent(
            name="Reviewer",
            model_client=client,
            system_message=REVIEWER_PROMPT,
            description="Skeptical fact-checker who finds errors and blocks bad data",
        )
        agents["reviewer"] = reviewer
        participants = [manager, linguist, data_engineer, devops, reviewer]

        selector_prompt = (
            "Based on the conversation, select the next agent to speak:\n"
            "- Manager: Overall coordination and GPS grading\n"
            "- Linguist: Wikipedia/WikiTree content generation\n"
            "- DataEngineer: Wikidata JSON payloads\n"
            "- DevOps: Git commands and commit messages\n"
            "- Reviewer: Fact-checking, error detection, blocking bad data\n\n"
            "IMPORTANT: Before Manager says FINAL, Reviewer MUST review all outputs.\n"
            "Select the single most appropriate next speaker."
        )

    # Termination when Manager says "FINAL"
    termination = (
        MaxMessageTermination(max_messages)
        | TextMentionTermination("FINAL")
    )

    # Manager selects which agent speaks next
    team = SelectorGroupChat(
        participants=participants,
        model_client=client,
        selector_prompt=selector_prompt,
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
    team, _agents = create_wiki_publishing_team(model=model)

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
    return {
        "subject": subject_name,
        "messages": messages,
        "wikidata_payload": _extract_section(messages, "WIKIDATA_PAYLOAD"),
        "wikipedia_draft": _extract_section(messages, "WIKIPEDIA_DRAFT"),
        "wikitree_bio": _extract_section(messages, "WIKITREE_BIO"),
        "git_commit": _extract_section(messages, "GIT_COMMIT_MSG"),
        "gps_grade": _extract_section(messages, "GPS Grade Card"),
        "review_report": _extract_section(messages, "REVIEW REPORT"),
        "integrity_score": _extract_section(messages, "INTEGRITY SCORE"),
        "blocking_issues": _extract_section(messages, "BLOCKING ISSUES"),
    }



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
    team, _agents = create_wiki_publishing_team(model=model, max_messages=15)

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
    team, _agents = create_wiki_publishing_team(model=model, max_messages=10)

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
                if in_section:
                    if line.startswith(("###", "## ")):
                        break
                    section_lines.append(line)

            if section_lines:
                return "\n".join(section_lines).strip()

    return None


async def review_outputs(
    outputs: dict[str, Any],
    original_sources: str,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Have the Reviewer agent fact-check existing outputs.

    Use this for a second-pass review of previously generated content.

    Args:
        outputs: Dictionary of outputs to review (wikidata_payload, wikipedia_draft, etc.)
        original_sources: The original source material to verify against
        model: Model to use

    Returns:
        Review report with integrity score and blocking issues
    """
    team, _agents = create_wiki_publishing_team(model=model, max_messages=10)

    outputs_text = "\n\n".join(
        f"### {key}\n{value}" for key, value in outputs.items() if value
    )

    task = f"""REVIEWER: Fact-check the following outputs against the original sources.

Original Sources:
---
{original_sources}
---

Outputs to Review:
---
{outputs_text}
---

Check for:
1. FABRICATIONS - Any claims not supported by sources
2. LOGICAL ERRORS - Timeline or relationship impossibilities
3. SOURCE MISMATCHES - Claims that don't match cited sources
4. QUALITY ISSUES - Missing citations, ambiguous statements

Provide your REVIEW REPORT with INTEGRITY SCORE and BLOCKING ISSUES.
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
        "messages": messages,
        "review_report": _extract_section(messages, "REVIEW REPORT"),
        "integrity_score": _extract_section(messages, "INTEGRITY SCORE"),
        "blocking_issues": _extract_section(messages, "BLOCKING ISSUES"),
        "approved": _is_approved(messages),
    }


def _is_approved(messages: list[dict]) -> bool:
    """Check if the Reviewer approved the outputs.

    Args:
        messages: List of message dicts

    Returns:
        True if no blocking issues found
    """
    blocking = _extract_section(messages, "BLOCKING ISSUES")
    if not blocking:
        return False  # No review found

    blocking_lower = blocking.lower()
    return (
        "none" in blocking_lower
        or "clear to publish" in blocking_lower
        or "no blocking" in blocking_lower
    )


def _extract_verdict(messages: list[dict], verdict_section: str) -> str | None:
    """Extract a reviewer verdict (PASS/FAIL) from messages.

    Args:
        messages: List of message dicts
        verdict_section: Section name (e.g., "LOGIC_VERDICT" or "SOURCE_VERDICT")

    Returns:
        "PASS", "FAIL", or None if not found
    """
    verdict = _extract_section(messages, verdict_section)
    if not verdict:
        return None

    verdict_upper = verdict.upper()
    if "PASS" in verdict_upper:
        return "PASS"
    if "FAIL" in verdict_upper:
        return "FAIL"
    return None


@dataclass
class QuorumResult:
    """Result of quorum check between dual reviewers."""
    logic_verdict: str | None = None  # PASS, FAIL, or None
    source_verdict: str | None = None  # PASS, FAIL, or None
    quorum_reached: bool = False  # Both reviewed and agreed
    approved: bool = False  # Both passed
    logic_issues: list[str] = field(default_factory=list)
    source_issues: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Human-readable status."""
        if not self.logic_verdict:
            return "⏳ Awaiting LogicReviewer"
        if not self.source_verdict:
            return "⏳ Awaiting SourceReviewer"
        if self.approved:
            return "✅ QUORUM: Both reviewers approved"
        if self.logic_verdict == "FAIL" and self.source_verdict == "FAIL":
            return "❌ BLOCKED: Both reviewers found issues"
        if self.logic_verdict == "FAIL":
            return "❌ BLOCKED: LogicReviewer found issues"
        if self.source_verdict == "FAIL":
            return "❌ BLOCKED: SourceReviewer found issues"
        return "⚠️ Unknown quorum state"


def check_quorum(messages: list[dict]) -> QuorumResult:
    """Check if dual reviewers have reached quorum.

    Quorum requires:
    - Both LogicReviewer and SourceReviewer must have submitted verdicts
    - Both must have said PASS for publication to proceed

    Args:
        messages: List of message dicts from the team

    Returns:
        QuorumResult with verdict details
    """
    result = QuorumResult()

    # Find LogicReviewer's verdict
    result.logic_verdict = _extract_verdict(messages, "LOGIC_VERDICT")

    # Find SourceReviewer's verdict
    result.source_verdict = _extract_verdict(messages, "SOURCE_VERDICT")

    # Extract any issues mentioned
    logic_review = _extract_section(messages, "LOGIC REVIEW")
    if logic_review:
        # Parse out specific issues (lines starting with "- ")
        for line in logic_review.split("\n"):
            line = line.strip()
            if line.startswith("- ") and any(sev in line.upper() for sev in ["CRITICAL", "HIGH", "MEDIUM"]):
                result.logic_issues.append(line[2:])

    source_review = _extract_section(messages, "SOURCE REVIEW")
    if source_review:
        for line in source_review.split("\n"):
            line = line.strip()
            if line.startswith("- ") and any(sev in line.upper() for sev in ["CRITICAL", "HIGH", "MEDIUM"]):
                result.source_issues.append(line[2:])

    # Check quorum
    result.quorum_reached = (
        result.logic_verdict is not None
        and result.source_verdict is not None
    )

    result.approved = (
        result.quorum_reached
        and result.logic_verdict == "PASS"
        and result.source_verdict == "PASS"
    )

    return result


def parse_review_issues(messages: list[dict]) -> list[ReviewIssue]:
    """Parse review issues from reviewer messages for auto-downgrade.

    Args:
        messages: List of message dicts from reviewers

    Returns:
        List of ReviewIssue objects for PublishDecision
    """
    issues: list[ReviewIssue] = []

    # Map keywords to severity
    severity_keywords = {
        Severity.CRITICAL: ["fabrication", "invented", "hallucinated", "made-up", "no source"],
        Severity.HIGH: ["logical error", "timeline", "impossible", "mismatch", "contradiction"],
        Severity.MEDIUM: ["incomplete", "ambiguous", "missing qualifier", "uncertain"],
        Severity.LOW: ["style", "format", "npov", "template"],
    }

    # Map keywords to categories
    category_keywords = {
        "fabrication": ["fabrication", "invented", "hallucinated", "made-up", "no source"],
        "logic": ["timeline", "impossible", "before birth", "after death", "contradiction"],
        "source": ["mismatch", "cited source", "reference", "citation"],
        "quality": ["incomplete", "ambiguous", "missing", "uncertain"],
        "style": ["style", "format", "template", "npov"],
    }

    # Check both reviewer types
    for section_name in ["LOGIC REVIEW", "SOURCE REVIEW", "REVIEW REPORT"]:
        content = _extract_section(messages, section_name)
        if not content:
            continue

        # Determine responsible agent
        agent = None
        if "LOGIC" in section_name:
            agent = "LogicReviewer"
        elif "SOURCE" in section_name:
            agent = "SourceReviewer"
        else:
            agent = "Reviewer"

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("✓"):  # Skip empty and check marks
                continue

            line_lower = line.lower()

            # Determine severity
            severity = Severity.LOW
            for sev, keywords in severity_keywords.items():
                if any(kw in line_lower for kw in keywords):
                    severity = sev
                    break

            # Determine category
            category = "quality"
            for cat, keywords in category_keywords.items():
                if any(kw in line_lower for kw in keywords):
                    category = cat
                    break

            # Only add if it looks like an issue (contains severity indicator or dash)
            if any(sev.upper() in line.upper() for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]) or line.startswith("-"):
                issues.append(ReviewIssue(
                    severity=severity,
                    category=category,
                    description=line.lstrip("- "),
                    agent_responsible=agent,
                ))

    return issues


# =============================================================================
# CLI Entry Point
# =============================================================================

async def publish_with_accepted_facts(
    facts: list[dict[str, Any]],
    subject_name: str,
    subject_id: str | None = None,
    uncertainties: list[dict[str, Any]] | None = None,
    unresolved_conflicts: list[dict[str, Any]] | None = None,
    wikidata_qid: str | None = None,
    wikitree_id: str | None = None,
    gramps_id: str | None = None,
    min_confidence: float = 0.9,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Publish genealogical research using only ACCEPTED facts.

    This function integrates with the PublishingManager's fact filtering
    to ensure only verified facts with confidence >= min_confidence are
    used for public wiki content.

    Args:
        facts: List of fact dictionaries with keys:
            - field: Field name (e.g., "birth_date", "death_place")
            - value: The verified value
            - status: Must be "ACCEPTED" to be included
            - confidence: Float 0-1 (must be >= min_confidence)
            - source_refs: List of source references
        subject_name: Full name of the subject
        subject_id: Optional unique identifier
        uncertainties: List of documented uncertainties (field, description, confidence_level)
        unresolved_conflicts: List of unresolved conflicts (field, competing_claims)
        wikidata_qid: Existing Wikidata QID if known
        wikitree_id: Existing WikiTree ID if known
        gramps_id: Existing Gramps ID if known
        min_confidence: Minimum confidence threshold (default 0.9)
        model: Model to use

    Returns:
        Publishing outputs with fact filtering applied
    """
    # Filter to only ACCEPTED facts meeting confidence threshold
    accepted_facts = [
        f for f in facts
        if f.get("status") == "ACCEPTED" and f.get("confidence", 0.0) >= min_confidence
    ]

    # Separate uncertain facts for documentation
    uncertain_facts = [
        f for f in facts
        if f.get("status") == "ACCEPTED" and f.get("confidence", 0.0) < min_confidence
    ]

    # Build structured article from accepted facts
    fact_lines = []
    for fact in accepted_facts:
        field = fact.get("field", "unknown")
        value = fact.get("value", "")
        sources = fact.get("source_refs", [])
        source_str = f" (Sources: {', '.join(sources)})" if sources else ""
        fact_lines.append(f"- **{field}**: {value}{source_str}")

    # Build uncertainty documentation
    uncertainty_lines = []
    if uncertainties:
        for u in uncertainties:
            uncertainty_lines.append(
                f"- {u.get('field', 'unknown')}: {u.get('description', '')} "
                f"(confidence: {u.get('confidence_level', 'N/A')})"
            )
    for fact in uncertain_facts:
        uncertainty_lines.append(
            f"- {fact.get('field', 'unknown')}: {fact.get('value', '')} "
            f"(confidence: {fact.get('confidence', 0.0):.2f} - below threshold)"
        )

    # Build conflict documentation
    conflict_lines = []
    if unresolved_conflicts:
        for c in unresolved_conflicts:
            claims = c.get("competing_claims", [])
            claims_str = " vs ".join(
                f"{claim.get('value', '?')} ({claim.get('source', '?')})"
                for claim in claims
            )
            conflict_lines.append(f"- {c.get('field', 'unknown')}: {claims_str}")

    # Build the article text
    article_text = f"""# {subject_name}

## Verified Facts (ACCEPTED, confidence >= {min_confidence})

{chr(10).join(fact_lines) if fact_lines else "No facts meet the acceptance threshold."}

## Uncertainties

{chr(10).join(uncertainty_lines) if uncertainty_lines else "No documented uncertainties."}

## Unresolved Conflicts

{chr(10).join(conflict_lines) if conflict_lines else "No unresolved conflicts."}

## Metadata
- Subject ID: {subject_id or "Not assigned"}
- Total facts provided: {len(facts)}
- ACCEPTED facts (>= {min_confidence}): {len(accepted_facts)}
- Uncertain facts (< {min_confidence}): {len(uncertain_facts)}
"""

    # Run through the publishing team
    result = await publish_to_wikis(
        article_text=article_text,
        subject_name=subject_name,
        gramps_id=gramps_id,
        wikidata_qid=wikidata_qid,
        wikitree_id=wikitree_id,
        model=model,
    )

    # Add fact filtering metadata to result
    result["fact_filtering"] = {
        "total_facts": len(facts),
        "accepted_facts": len(accepted_facts),
        "uncertain_facts": len(uncertain_facts),
        "min_confidence": min_confidence,
        "accepted_fields": [f.get("field") for f in accepted_facts],
        "uncertain_fields": [f.get("field") for f in uncertain_facts],
    }

    return result


@dataclass
class WikiPublishingResult:
    """Structured result from wiki publishing workflow.

    Combines outputs from all agents with publish decision.
    """
    subject_name: str
    subject_id: str | None = None

    # GPS Grading
    gps_grade_card: str | None = None
    gps_overall_score: float | None = None

    # Platform-specific outputs
    wikipedia_draft: str | None = None
    wikitree_bio: str | None = None
    wikidata_payload: str | None = None
    git_commit_msg: str | None = None

    # Review results
    review_report: str | None = None
    integrity_score: int | None = None
    blocking_issues: list[str] = field(default_factory=list)
    quorum_result: QuorumResult | None = None

    # Publish decision
    publish_decision: PublishDecision | None = None

    # Fact filtering (if using publish_with_accepted_facts)
    fact_filtering: dict[str, Any] | None = None

    @property
    def can_publish_wikipedia(self) -> bool:
        """Whether Wikipedia publishing is allowed."""
        if self.publish_decision:
            return self.publish_decision.wikipedia
        return not self.blocking_issues

    @property
    def can_publish_wikitree(self) -> bool:
        """Whether WikiTree publishing is allowed."""
        if self.publish_decision:
            return self.publish_decision.wikitree
        return not self.blocking_issues

    def summary(self) -> str:
        """Human-readable summary of the result."""
        lines = [
            f"# Wiki Publishing Result: {self.subject_name}",
            "",
        ]

        if self.gps_overall_score:
            lines.append(f"**GPS Score:** {self.gps_overall_score}/10")

        if self.integrity_score:
            lines.append(f"**Integrity Score:** {self.integrity_score}/100")

        if self.quorum_result:
            lines.append(f"**Quorum Status:** {self.quorum_result.status}")

        if self.publish_decision:
            lines.append(f"**Publish Decision:** {self.publish_decision.summary()}")

        if self.fact_filtering:
            lines.append(
                f"**Facts:** {self.fact_filtering['accepted_facts']} accepted / "
                f"{self.fact_filtering['total_facts']} total"
            )

        return "\n".join(lines)


def create_wiki_publishing_result(
    result_dict: dict[str, Any],
    subject_name: str,
    subject_id: str | None = None,
) -> WikiPublishingResult:
    """Convert raw result dict to structured WikiPublishingResult.

    Args:
        result_dict: Raw result from publish_to_wikis or publish_with_accepted_facts
        subject_name: Name of the subject
        subject_id: Optional subject ID

    Returns:
        Structured WikiPublishingResult
    """
    # Parse messages for quorum
    messages = result_dict.get("messages", [])
    quorum = check_quorum(messages) if messages else None

    # Parse review issues for publish decision
    issues = parse_review_issues(messages) if messages else []
    decision = PublishDecision.from_issues(issues) if issues else None

    # Parse integrity score
    integrity_str = result_dict.get("integrity_score", "")
    integrity_score = None
    if integrity_str:
        try:
            # Extract number from string like "85/100" or just "85"
            import re
            match = re.search(r"(\d+)", integrity_str)
            if match:
                integrity_score = int(match.group(1))
        except (ValueError, TypeError):
            pass

    # Parse blocking issues
    blocking_str = result_dict.get("blocking_issues", "")
    blocking_issues = []
    if blocking_str and "clear" not in blocking_str.lower() and "none" not in blocking_str.lower():
        blocking_issues = [
            line.strip()
            for line in blocking_str.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

    return WikiPublishingResult(
        subject_name=subject_name,
        subject_id=subject_id,
        gps_grade_card=result_dict.get("gps_grade"),
        wikipedia_draft=result_dict.get("wikipedia_draft"),
        wikitree_bio=result_dict.get("wikitree_bio"),
        wikidata_payload=result_dict.get("wikidata_payload"),
        git_commit_msg=result_dict.get("git_commit"),
        review_report=result_dict.get("review_report"),
        integrity_score=integrity_score,
        blocking_issues=blocking_issues,
        quorum_result=quorum,
        publish_decision=decision,
        fact_filtering=result_dict.get("fact_filtering"),
    )


async def main() -> None:
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
    print("\n=== Review Report ===")
    print(f"\nIntegrity Score:\n{result.get('integrity_score', 'Not found')}")
    print(f"\nBlocking Issues:\n{result.get('blocking_issues', 'Not found')}")

    # Example with accepted facts
    print("\n\n=== Example with Accepted Facts ===")
    facts = [
        {
            "field": "birth_date",
            "value": "1931-03-15",
            "status": "ACCEPTED",
            "confidence": 0.95,
            "source_refs": ["Birth Certificate, States of Jersey, 1931"],
        },
        {
            "field": "birth_place",
            "value": "St. Helier, Jersey",
            "status": "ACCEPTED",
            "confidence": 0.95,
            "source_refs": ["Birth Certificate, States of Jersey, 1931"],
        },
        {
            "field": "death_date",
            "value": "2023",
            "status": "ACCEPTED",
            "confidence": 0.85,  # Below threshold - will be flagged
            "source_refs": ["Death notice, Jersey Evening Post, 2023"],
        },
    ]

    result_with_facts = await publish_with_accepted_facts(
        facts=facts,
        subject_name="Paul Janvrin Vincent",
        subject_id="I0001",
        min_confidence=0.9,
    )

    structured_result = create_wiki_publishing_result(
        result_with_facts,
        subject_name="Paul Janvrin Vincent",
        subject_id="I0001",
    )

    print(structured_result.summary())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
