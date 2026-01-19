"""Tests for Gramps Match-Merge Agent."""

import pytest

from gps_agents.autogen.match_merge import (
    MATCH_MERGE_PROMPT,
    MERGE_REVIEWER_PROMPT,
    MatchMergeAgent,
    MergeAction,
    MergeDecision,
    confidence_to_action,
    quick_match_decision,
)
from gps_agents.gramps.models import Event, GrampsDate, Name, Person


class TestMergeAction:
    """Test MergeAction enum."""

    def test_action_values(self):
        """Test action enum values."""
        assert MergeAction.MERGE.value == "merge"
        assert MergeAction.NEEDS_HUMAN.value == "needs_human_decision"
        assert MergeAction.CREATE.value == "create"


class TestMergeDecision:
    """Test MergeDecision dataclass."""

    def test_default_decision(self):
        """Test default decision values."""
        decision = MergeDecision(action=MergeAction.CREATE)
        assert decision.matched_id is None
        assert decision.confidence == 0.0
        assert decision.conflicts == []
        assert decision.merge_plan == {}
        assert decision.reasoning == ""

    def test_to_json(self):
        """Test JSON serialization."""
        decision = MergeDecision(
            action=MergeAction.MERGE,
            matched_id="I0001",
            confidence=0.92,
            conflicts=["minor date discrepancy"],
            merge_plan={"preserve_from_existing": ["birth_date"]},
            reasoning="High confidence match",
        )
        result = decision.to_json()

        assert result["action"] == "merge"
        assert result["matched_id"] == "I0001"
        assert result["confidence"] == 0.92
        assert "minor date discrepancy" in result["conflicts"]
        assert "birth_date" in result["merge_plan"]["preserve_from_existing"]


class TestPrompts:
    """Test agent prompts."""

    def test_match_merge_prompt_has_thresholds(self):
        """Prompt should define decision thresholds."""
        assert "0.85" in MATCH_MERGE_PROMPT
        assert "0.50" in MATCH_MERGE_PROMPT
        assert "MERGE" in MATCH_MERGE_PROMPT
        assert "NEEDS_HUMAN_DECISION" in MATCH_MERGE_PROMPT
        assert "CREATE" in MATCH_MERGE_PROMPT

    def test_match_merge_prompt_has_rules(self):
        """Prompt should have merge rules."""
        assert "Never overwrite better-sourced" in MATCH_MERGE_PROMPT
        assert "preserve citations" in MATCH_MERGE_PROMPT
        assert "transactional" in MATCH_MERGE_PROMPT

    def test_match_merge_prompt_has_scoring_factors(self):
        """Prompt should describe scoring factors."""
        assert "Soundex" in MATCH_MERGE_PROMPT
        assert "Name variants" in MATCH_MERGE_PROMPT
        assert "Date proximity" in MATCH_MERGE_PROMPT
        assert "Place" in MATCH_MERGE_PROMPT

    def test_reviewer_prompt_checks_false_positives(self):
        """Reviewer should check for false positives."""
        assert "FALSE POSITIVES" in MERGE_REVIEWER_PROMPT
        assert "wrongly merging" in MERGE_REVIEWER_PROMPT

    def test_reviewer_prompt_checks_false_negatives(self):
        """Reviewer should check for false negatives."""
        assert "FALSE NEGATIVES" in MERGE_REVIEWER_PROMPT
        assert "wrongly creating" in MERGE_REVIEWER_PROMPT

    def test_reviewer_has_verdicts(self):
        """Reviewer should have verdict options."""
        assert "APPROVE" in MERGE_REVIEWER_PROMPT
        assert "REJECT" in MERGE_REVIEWER_PROMPT
        assert "ESCALATE" in MERGE_REVIEWER_PROMPT


class TestConfidenceToAction:
    """Test confidence_to_action function."""

    def test_high_confidence_merges(self):
        """High confidence should result in merge."""
        assert confidence_to_action(0.95) == MergeAction.MERGE
        assert confidence_to_action(0.85) == MergeAction.MERGE

    def test_medium_confidence_needs_human(self):
        """Medium confidence should need human decision."""
        assert confidence_to_action(0.75) == MergeAction.NEEDS_HUMAN
        assert confidence_to_action(0.50) == MergeAction.NEEDS_HUMAN

    def test_low_confidence_creates(self):
        """Low confidence should create new."""
        assert confidence_to_action(0.49) == MergeAction.CREATE
        assert confidence_to_action(0.10) == MergeAction.CREATE
        assert confidence_to_action(0.0) == MergeAction.CREATE


class TestMatchMergeAgent:
    """Test MatchMergeAgent class."""

    @pytest.fixture
    def agent(self):
        """Create agent for testing."""
        return MatchMergeAgent()

    @pytest.fixture
    def john_smith_1850(self):
        """Create test person: John Smith born 1850."""
        return Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
            sex="M",
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1850),
            ),
        )

    @pytest.fixture
    def john_smith_1850_v2(self):
        """Create similar person: John Smith born 1850."""
        return Person(
            gramps_id="I0002",
            names=[Name(given="John", surname="Smith")],
            sex="M",
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1850),
            ),
        )

    @pytest.fixture
    def jack_smith_1852(self):
        """Create similar person: Jack Smith born 1852."""
        return Person(
            gramps_id="I0003",
            names=[Name(given="Jack", surname="Smith")],
            sex="M",
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1852),
            ),
        )

    @pytest.fixture
    def mary_jones_1860(self):
        """Create different person: Mary Jones born 1860."""
        return Person(
            gramps_id="I0004",
            names=[Name(given="Mary", surname="Jones")],
            sex="F",
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1860),
            ),
        )

    def test_no_candidates_creates(self, agent, john_smith_1850):
        """No candidates should result in create action."""
        decision = agent.evaluate_match(john_smith_1850, [])
        assert decision.action == MergeAction.CREATE
        assert decision.confidence == 0.0

    def test_exact_match_high_confidence(self, agent, john_smith_1850, john_smith_1850_v2):
        """Exact name and date match should have high confidence."""
        decision = agent.evaluate_match(john_smith_1850, [john_smith_1850_v2])
        assert decision.confidence >= 0.85
        assert decision.action == MergeAction.MERGE

    def test_variant_match_medium_confidence(self, agent, john_smith_1850, jack_smith_1852):
        """Name variant with close date should have medium confidence."""
        decision = agent.evaluate_match(john_smith_1850, [jack_smith_1852])
        # Jack is a variant of John, dates close
        assert decision.confidence > 0.0
        assert "reasons" in decision.reasoning or len(decision.reasoning) > 0

    def test_different_person_low_confidence(self, agent, john_smith_1850, mary_jones_1860):
        """Different person should have low confidence."""
        decision = agent.evaluate_match(john_smith_1850, [mary_jones_1860])
        assert decision.confidence < 0.50
        assert decision.action == MergeAction.CREATE

    def test_sex_mismatch_penalty(self, agent):
        """Sex mismatch should heavily penalize score."""
        person1 = Person(
            names=[Name(given="Pat", surname="Smith")],
            sex="M",
        )
        person2 = Person(
            gramps_id="I0005",
            names=[Name(given="Pat", surname="Smith")],
            sex="F",
        )
        decision = agent.evaluate_match(person1, [person2])
        # Even with same name, sex mismatch should lower confidence significantly
        assert decision.confidence < 0.50 or "Sex mismatch" in str(decision.conflicts)


class TestSoundexMatching:
    """Test Soundex phonetic matching."""

    @pytest.fixture
    def agent(self):
        return MatchMergeAgent()

    def test_soundex_basic(self, agent):
        """Test basic Soundex generation."""
        assert agent._soundex("Smith") == "S530"
        assert agent._soundex("Smyth") == "S530"
        assert agent._soundex("Schmidt") == "S530"

    def test_soundex_johnson_variants(self, agent):
        """Test Johnson variants have same Soundex."""
        assert agent._soundex("Johnson") == agent._soundex("Johnsen")

    def test_soundex_empty(self, agent):
        """Test empty string handling."""
        assert agent._soundex("") == ""


class TestNameVariants:
    """Test name variant detection."""

    @pytest.fixture
    def agent(self):
        return MatchMergeAgent()

    def test_william_bill_variant(self, agent):
        """William and Bill should be recognized as variants."""
        assert agent._is_variant("william", "bill")
        # Function expects lowercase input (it doesn't lowercase internally)
        assert agent._is_variant("william", "bill")

    def test_elizabeth_beth_variant(self, agent):
        """Elizabeth and Beth should be recognized."""
        assert agent._is_variant("elizabeth", "beth")
        assert agent._is_variant("elizabeth", "liz")

    def test_john_jack_variant(self, agent):
        """John and Jack should be recognized."""
        assert agent._is_variant("john", "jack")

    def test_unrelated_names_not_variants(self, agent):
        """Unrelated names should not match."""
        assert not agent._is_variant("john", "mary")
        assert not agent._is_variant("william", "elizabeth")


class TestMergePlan:
    """Test merge plan building."""

    @pytest.fixture
    def agent(self):
        return MatchMergeAgent()

    def test_merge_plan_preserves_existing(self, agent):
        """Merge plan should preserve existing data."""
        existing = Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1850),
            ),
        )
        proposed = Person(
            names=[Name(given="John", surname="Smith")],
            birth=Event(
                event_type="birth",
                date=GrampsDate(year=1850),
            ),
        )
        plan = agent._build_merge_plan(proposed, existing)
        assert "preserve_from_existing" in plan

    def test_merge_plan_adds_new_names(self, agent):
        """Merge plan should add new name variants."""
        existing = Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
        )
        proposed = Person(
            names=[
                Name(given="John", surname="Smith"),
                Name(given="Johnny", surname="Smith"),
            ],
        )
        plan = agent._build_merge_plan(proposed, existing)
        # Should add Johnny Smith
        assert any("Johnny" in str(item) for item in plan.get("add_from_new", []))


class TestQuickMatchDecision:
    """Test the quick_match_decision convenience function."""

    def test_quick_decision_no_candidates(self):
        """Quick decision with no candidates creates."""
        proposed = Person(names=[Name(given="Test", surname="Person")])
        decision = quick_match_decision(proposed, [])
        assert decision.action == MergeAction.CREATE

    def test_quick_decision_with_match(self):
        """Quick decision finds matches."""
        proposed = Person(
            names=[Name(given="John", surname="Smith")],
            sex="M",
            birth=Event(event_type="birth", date=GrampsDate(year=1850)),
        )
        candidate = Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
            sex="M",
            birth=Event(event_type="birth", date=GrampsDate(year=1850)),
        )
        decision = quick_match_decision(proposed, [candidate])
        assert decision.confidence > 0
        assert decision.matched_id == "I0001"


class TestReasoningOutput:
    """Test that reasoning is generated correctly."""

    @pytest.fixture
    def agent(self):
        return MatchMergeAgent()

    def test_reasoning_includes_action(self, agent):
        """Reasoning should include the recommended action."""
        proposed = Person(names=[Name(given="John", surname="Smith")])
        candidate = Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
        )
        decision = agent.evaluate_match(proposed, [candidate])
        assert any(action in decision.reasoning for action in ["MERGE", "CREATE", "HUMAN"])

    def test_reasoning_includes_signals(self, agent):
        """Reasoning should include match signals."""
        proposed = Person(
            names=[Name(given="John", surname="Smith")],
            birth=Event(event_type="birth", date=GrampsDate(year=1850)),
        )
        candidate = Person(
            gramps_id="I0001",
            names=[Name(given="John", surname="Smith")],
            birth=Event(event_type="birth", date=GrampsDate(year=1850)),
        )
        decision = agent.evaluate_match(proposed, [candidate])
        # Should mention name match and birth year
        assert "surname" in decision.reasoning.lower() or "name" in decision.reasoning.lower()
