"""Gramps Match-Merge Agent for preventing duplicate records.

LLM-powered duplicate detection and merge decision making that wraps
the deterministic PersonMatcher/GrampsMerger with intelligent reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import MaxMessageTermination
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import RoundRobinGroupChat

from gps_agents.autogen.agents import create_model_client
from gps_agents.gramps.merge import (
    GrampsMerger,
    MatchConfidence,
    MatchResult,
    MergeResult,
    MergeStrategy,
    PersonMatcher,
)
from gps_agents.gramps.models import Event, Name, Person


# =============================================================================
# Action Types
# =============================================================================

class MergeAction(str, Enum):
    """Decision for how to handle a potential match."""
    MERGE = "merge"                    # Confidence >= 0.85 → auto-merge
    NEEDS_HUMAN = "needs_human_decision"  # 0.50-0.84 → ask user
    CREATE = "create"                  # < 0.50 → create new record


@dataclass
class MergeDecision:
    """Result of the LLM-enhanced merge decision process."""
    action: MergeAction
    matched_id: str | None = None
    confidence: float = 0.0
    conflicts: list[str] = field(default_factory=list)
    merge_plan: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "action": self.action.value,
            "matched_id": self.matched_id,
            "confidence": self.confidence,
            "conflicts": self.conflicts,
            "merge_plan": self.merge_plan,
            "reasoning": self.reasoning,
        }


# =============================================================================
# Agent Prompts
# =============================================================================

MATCH_MERGE_PROMPT = r"""You are the Gramps Match-Merge Agent. Your job is to prevent duplicates.

For any proposed Person/Event:
1) Search existing Gramps entities for candidates.
2) Score candidates using: name similarity, date proximity, place similarity, relationships.
3) Decide:
   - confidence >= 0.85 → MERGE into existing
   - 0.50–0.84 → NEEDS_HUMAN_DECISION
   - < 0.50 → CREATE new

Merge rules:
- Never overwrite better-sourced data with weaker data.
- Always preserve citations; attach new sources as additional evidence.
- Writes must be transactional.
- Prefer Original sources over Derivative over Authored when resolving conflicts.

When analyzing matches, consider:
- Soundex phonetic similarity for names
- Name variants (William = Bill, Elizabeth = Beth, etc.)
- Date proximity (exact, close within 2 years, far apart 10+ years)
- Place name matches (normalize capitalization, handle abbreviations)
- Sex matching (conflicts are heavily penalized)
- Family relationship verification if available

Output format (JSON only):
{
  "action": "merge|create|needs_human_decision",
  "matched_id": "...|null",
  "confidence": 0.0-1.0,
  "conflicts": [...],
  "merge_plan": {
    "preserve_from_existing": [...],
    "add_from_new": [...],
    "sources_to_attach": [...]
  },
  "reasoning": "..."
}

CRITICAL RULES:
- NEVER invent identifiers, dates, or relationships
- If data conflicts, document the conflict in your output
- If unsure, recommend NEEDS_HUMAN_DECISION
- Explain your reasoning clearly for human review
"""

MERGE_REVIEWER_PROMPT = r"""You are the Merge Reviewer. You verify match-merge decisions.

Your job is to CATCH MISTAKES in merge decisions:

1. FALSE POSITIVES (wrongly merging different people)
   - Same name but different birth years (10+ years apart)
   - Same name but different places (different countries)
   - Sex mismatches
   - Family relationship conflicts (different parents)

2. FALSE NEGATIVES (wrongly creating duplicates)
   - Obvious name variants not recognized
   - Minor date discrepancies (within 2 years)
   - Same person with maiden vs married name

3. DATA INTEGRITY ISSUES
   - Would merge overwrite better-sourced data?
   - Are citations properly preserved?
   - Is confidence score reasonable?

For each decision reviewed:
- APPROVE: Decision is correct
- REJECT: Decision is wrong, explain why
- ESCALATE: Too close to call, needs human

Output format:
{
  "verdict": "approve|reject|escalate",
  "issues": [...],
  "recommendation": "...",
  "confidence_adjustment": 0.0 (optional delta to apply)
}
"""


# =============================================================================
# Match-Merge Agent
# =============================================================================

class MatchMergeAgent:
    """
    LLM-powered match-merge agent for Gramps duplicate prevention.

    Combines deterministic PersonMatcher scoring with LLM reasoning
    to make intelligent merge decisions.
    """

    # Threshold constants
    MERGE_THRESHOLD = 0.85
    REVIEW_THRESHOLD = 0.50

    def __init__(
        self,
        matcher: PersonMatcher | None = None,
        model: str = "gpt-4o-mini",
    ):
        """Initialize the match-merge agent.

        Args:
            matcher: PersonMatcher instance (for deterministic scoring)
            model: LLM model name for reasoning
        """
        self.matcher = matcher
        self.model = model
        self._client = None

    @property
    def client(self):
        """Lazy-load model client."""
        if self._client is None:
            self._client = create_model_client("openai", model=self.model, temperature=0.1)
        return self._client

    def evaluate_match(
        self,
        proposed_person: Person,
        candidates: list[Person],
    ) -> MergeDecision:
        """
        Evaluate a proposed person against existing candidates.

        Uses deterministic scoring from PersonMatcher if available,
        enhanced with LLM reasoning.

        Args:
            proposed_person: New person to evaluate
            candidates: Existing persons to compare against

        Returns:
            MergeDecision with action and reasoning
        """
        if not candidates:
            return MergeDecision(
                action=MergeAction.CREATE,
                confidence=0.0,
                reasoning="No existing candidates found. Safe to create new record.",
            )

        # Score candidates
        scored = self._score_candidates(proposed_person, candidates)

        if not scored:
            return MergeDecision(
                action=MergeAction.CREATE,
                confidence=0.0,
                reasoning="No candidates passed minimum threshold.",
            )

        best = scored[0]

        # Determine action based on confidence
        if best["score"] >= self.MERGE_THRESHOLD:
            action = MergeAction.MERGE
        elif best["score"] >= self.REVIEW_THRESHOLD:
            action = MergeAction.NEEDS_HUMAN
        else:
            action = MergeAction.CREATE

        # Build merge plan if merging
        merge_plan = {}
        if action == MergeAction.MERGE:
            merge_plan = self._build_merge_plan(proposed_person, best["person"])

        return MergeDecision(
            action=action,
            matched_id=best["person"].gramps_id,
            confidence=best["score"],
            conflicts=best.get("conflicts", []),
            merge_plan=merge_plan,
            reasoning=self._build_reasoning(proposed_person, best, action),
        )

    def _score_candidates(
        self,
        proposed: Person,
        candidates: list[Person],
    ) -> list[dict[str, Any]]:
        """Score all candidates against the proposed person."""
        scored = []

        for candidate in candidates:
            score_result = self._score_single(proposed, candidate)
            if score_result["score"] > 0:
                scored.append(score_result)

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _score_single(
        self,
        proposed: Person,
        candidate: Person,
    ) -> dict[str, Any]:
        """Score a single candidate match."""
        score = 0.0
        reasons = []
        conflicts = []

        # Name matching
        if proposed.primary_name and candidate.primary_name:
            name_score, name_reasons, name_conflicts = self._compare_names(
                proposed.primary_name,
                candidate.primary_name,
            )
            score += name_score
            reasons.extend(name_reasons)
            conflicts.extend(name_conflicts)

        # Sex matching
        if proposed.sex and candidate.sex:
            if proposed.sex == candidate.sex:
                score += 0.05
                reasons.append(f"Sex match: {proposed.sex}")
            elif proposed.sex != "U" and candidate.sex != "U":
                score -= 0.50  # Heavy penalty
                conflicts.append(f"Sex mismatch: {proposed.sex} vs {candidate.sex}")

        # Birth date matching
        if proposed.birth and candidate.birth:
            birth_score, birth_reasons, birth_conflicts = self._compare_dates(
                proposed.birth.date.year if proposed.birth.date else None,
                candidate.birth.date.year if candidate.birth.date else None,
                "birth",
            )
            score += birth_score
            reasons.extend(birth_reasons)
            conflicts.extend(birth_conflicts)

        # Death date matching
        if proposed.death and candidate.death:
            death_score, death_reasons, death_conflicts = self._compare_dates(
                proposed.death.date.year if proposed.death.date else None,
                candidate.death.date.year if candidate.death.date else None,
                "death",
            )
            score += death_score
            reasons.extend(death_reasons)
            conflicts.extend(death_conflicts)

        # Normalize to 0-1
        score = max(0.0, min(1.0, score))

        return {
            "person": candidate,
            "score": score,
            "reasons": reasons,
            "conflicts": conflicts,
        }

    def _compare_names(
        self,
        name1: Name,
        name2: Name,
    ) -> tuple[float, list[str], list[str]]:
        """Compare two names and return score, reasons, conflicts."""
        score = 0.0
        reasons = []
        conflicts = []

        # Surname comparison
        s1 = name1.surname.lower().strip()
        s2 = name2.surname.lower().strip()

        if s1 == s2:
            score += 0.40
            reasons.append(f"Exact surname: {name1.surname}")
        elif self._soundex(s1) == self._soundex(s2):
            score += 0.25
            reasons.append(f"Soundex surname: {name1.surname} ~ {name2.surname}")

        # Given name comparison
        g1 = name1.given.lower().strip()
        g2 = name2.given.lower().strip()

        if g1 == g2:
            score += 0.25
            reasons.append(f"Exact given name: {name1.given}")
        elif self._soundex(g1) == self._soundex(g2):
            score += 0.15
            reasons.append(f"Soundex given: {name1.given} ~ {name2.given}")
        elif self._is_variant(g1, g2):
            score += 0.15
            reasons.append(f"Name variant: {name1.given} ~ {name2.given}")

        return score, reasons, conflicts

    def _compare_dates(
        self,
        year1: int | None,
        year2: int | None,
        event_type: str,
    ) -> tuple[float, list[str], list[str]]:
        """Compare two dates and return score, reasons, conflicts."""
        if year1 is None or year2 is None:
            return 0.0, [], []

        diff = abs(year1 - year2)

        if diff == 0:
            return 0.20, [f"{event_type.title()} year exact: {year1}"], []
        elif diff <= 2:
            return 0.10, [f"{event_type.title()} year close: {year1} vs {year2}"], []
        elif diff > 10:
            return -0.30, [], [f"{event_type.title()} years far apart: {year1} vs {year2}"]
        else:
            return 0.0, [], []

    def _soundex(self, name: str) -> str:
        """Generate Soundex code."""
        if not name:
            return ""

        name = name.upper()
        soundex = name[0]

        mapping = {
            'B': '1', 'F': '1', 'P': '1', 'V': '1',
            'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
            'D': '3', 'T': '3',
            'L': '4',
            'M': '5', 'N': '5',
            'R': '6',
        }

        prev_code = mapping.get(name[0], '0')

        for char in name[1:]:
            code = mapping.get(char, '0')
            if code != '0' and code != prev_code:
                soundex += code
                prev_code = code
            if len(soundex) == 4:
                break

        return soundex.ljust(4, '0')

    def _is_variant(self, name1: str, name2: str) -> bool:
        """Check if names are common variants."""
        variants = {
            "william": ["bill", "will", "willy", "billy", "liam"],
            "elizabeth": ["beth", "liz", "lizzy", "betty", "eliza", "bessie"],
            "robert": ["bob", "rob", "robbie", "bobby", "bert"],
            "james": ["jim", "jimmy", "jamie"],
            "john": ["jack", "johnny", "jon"],
            "margaret": ["peggy", "maggie", "meg", "marge"],
            "catherine": ["kate", "katie", "cathy", "kitty"],
            "thomas": ["tom", "tommy", "thom"],
            "richard": ["rick", "dick", "rich"],
            "joseph": ["joe", "joey"],
            "mary": ["marie", "maria", "molly", "polly"],
        }

        for base, var_list in variants.items():
            all_names = [base] + var_list
            if name1 in all_names and name2 in all_names:
                return True
        return False

    def _build_merge_plan(
        self,
        proposed: Person,
        existing: Person,
    ) -> dict[str, Any]:
        """Build a plan for merging two person records."""
        plan = {
            "preserve_from_existing": [],
            "add_from_new": [],
            "sources_to_attach": [],
        }

        # Determine what to preserve vs add
        if existing.birth and proposed.birth:
            if existing.birth.date and proposed.birth.date:
                plan["preserve_from_existing"].append("birth_date")
            elif proposed.birth.date:
                plan["add_from_new"].append("birth_date")

        if existing.death and proposed.death:
            if existing.death.date and proposed.death.date:
                plan["preserve_from_existing"].append("death_date")
            elif proposed.death.date:
                plan["add_from_new"].append("death_date")

        # Add any names not in existing
        for name in proposed.names:
            if not any(
                n.given.lower() == name.given.lower() and
                n.surname.lower() == name.surname.lower()
                for n in existing.names
            ):
                plan["add_from_new"].append(f"name:{name.given} {name.surname}")

        return plan

    def _build_reasoning(
        self,
        proposed: Person,
        best_match: dict[str, Any],
        action: MergeAction,
    ) -> str:
        """Build human-readable reasoning for the decision."""
        lines = []

        if action == MergeAction.MERGE:
            lines.append(f"Recommend MERGE with confidence {best_match['score']:.2f}")
        elif action == MergeAction.NEEDS_HUMAN:
            lines.append(f"Recommend HUMAN REVIEW - confidence {best_match['score']:.2f} in uncertain range")
        else:
            lines.append(f"Recommend CREATE NEW - confidence {best_match['score']:.2f} below threshold")

        if best_match.get("reasons"):
            lines.append("Match signals:")
            for r in best_match["reasons"]:
                lines.append(f"  + {r}")

        if best_match.get("conflicts"):
            lines.append("Conflicts:")
            for c in best_match["conflicts"]:
                lines.append(f"  - {c}")

        return "\n".join(lines)


# =============================================================================
# Team Factory
# =============================================================================

def create_match_merge_team(
    model: str = "gpt-4o-mini",
    max_messages: int = 10,
) -> tuple[RoundRobinGroupChat, dict[str, AssistantAgent]]:
    """Create the Match-Merge team with agent and reviewer.

    Args:
        model: Model name for agents
        max_messages: Maximum messages before termination

    Returns:
        Tuple of (team, agents dict)
    """
    client = create_model_client("openai", model=model, temperature=0.1)

    matcher = AssistantAgent(
        name="MatchMergeAgent",
        model_client=client,
        system_message=MATCH_MERGE_PROMPT,
        description="Duplicate detection and merge decision maker",
    )

    reviewer = AssistantAgent(
        name="MergeReviewer",
        model_client=client,
        system_message=MERGE_REVIEWER_PROMPT,
        description="Verifies match-merge decisions for correctness",
    )

    agents = {
        "matcher": matcher,
        "reviewer": reviewer,
    }

    team = RoundRobinGroupChat(
        participants=[matcher, reviewer],
        termination_condition=MaxMessageTermination(max_messages),
    )

    return team, agents


async def evaluate_match_with_review(
    proposed: dict[str, Any],
    candidates: list[dict[str, Any]],
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Evaluate a match with LLM reasoning and review.

    Args:
        proposed: Proposed person data as dict
        candidates: List of candidate person dicts
        model: Model to use

    Returns:
        Decision with verdict and reasoning
    """
    team, agents = create_match_merge_team(model=model)

    task = f"""Evaluate this proposed person against existing candidates:

PROPOSED PERSON:
{json.dumps(proposed, indent=2, default=str)}

EXISTING CANDIDATES:
{json.dumps(candidates, indent=2, default=str)}

MatchMergeAgent: Analyze and decide: merge, create, or needs_human_decision.
MergeReviewer: Verify the decision is correct.
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
        "proposed": proposed,
        "candidates": candidates,
    }


# =============================================================================
# Convenience Functions
# =============================================================================

def quick_match_decision(
    proposed: Person,
    candidates: list[Person],
) -> MergeDecision:
    """Make a quick match decision without LLM (deterministic only).

    Args:
        proposed: Proposed person
        candidates: Existing candidates

    Returns:
        MergeDecision based on scoring
    """
    agent = MatchMergeAgent()
    return agent.evaluate_match(proposed, candidates)


def confidence_to_action(confidence: float) -> MergeAction:
    """Convert confidence score to action.

    Args:
        confidence: Score 0.0-1.0

    Returns:
        Appropriate MergeAction
    """
    if confidence >= 0.85:
        return MergeAction.MERGE
    elif confidence >= 0.50:
        return MergeAction.NEEDS_HUMAN
    else:
        return MergeAction.CREATE
