"""Tests for Wiki Publishing Team."""

import tempfile
from pathlib import Path

import pytest

from gps_agents.autogen.wiki_publishing import (
    DATA_ENGINEER_PROMPT,
    DEVOPS_PROMPT,
    LINGUIST_PROMPT,
    LOGIC_REVIEWER_PROMPT,
    MANAGER_PROMPT,
    Platform,
    PublishDecision,
    QuorumResult,
    REVIEWER_PROMPT,
    ReviewerMemory,
    ReviewIssue,
    SOURCE_REVIEWER_PROMPT,
    Severity,
    _extract_section,
    _is_approved,
    check_quorum,
)


class TestPrompts:
    """Test agent prompts are properly defined."""

    def test_manager_prompt_contains_gps(self):
        """Manager prompt should mention GPS grading."""
        assert "GPS" in MANAGER_PROMPT
        assert "Genealogical Proof Standard" in MANAGER_PROMPT
        assert "Pillars 1-5" in MANAGER_PROMPT

    def test_manager_prompt_has_workflow_steps(self):
        """Manager prompt should define workflow steps."""
        assert "Step 1" in MANAGER_PROMPT
        assert "Step 2" in MANAGER_PROMPT
        assert "Step 3" in MANAGER_PROMPT

    def test_manager_prompt_has_output_formats(self):
        """Manager prompt should specify output format headers."""
        assert "WIKIDATA_PAYLOAD" in MANAGER_PROMPT
        assert "WIKITREE_BIO" in MANAGER_PROMPT
        assert "WIKIPEDIA_DRAFT" in MANAGER_PROMPT
        assert "GIT_COMMIT_MSG" in MANAGER_PROMPT

    def test_linguist_prompt_has_platforms(self):
        """Linguist prompt should cover Wikipedia and WikiTree."""
        assert "Wikipedia" in LINGUIST_PROMPT
        assert "WikiTree" in LINGUIST_PROMPT
        assert "NPOV" in LINGUIST_PROMPT

    def test_data_engineer_prompt_has_properties(self):
        """Data engineer prompt should list Wikidata properties."""
        assert "P569" in DATA_ENGINEER_PROMPT  # birth date
        assert "P19" in DATA_ENGINEER_PROMPT   # birth place
        assert "P570" in DATA_ENGINEER_PROMPT  # death date
        assert "P20" in DATA_ENGINEER_PROMPT   # death place

    def test_devops_prompt_has_commit_format(self):
        """DevOps prompt should specify commit format."""
        assert "conventional commit" in DEVOPS_PROMPT.lower()
        assert "feat" in DEVOPS_PROMPT
        assert "fix" in DEVOPS_PROMPT
        assert "docs" in DEVOPS_PROMPT


class TestExtractSection:
    """Test section extraction from messages."""

    def test_extract_existing_section(self):
        """Test extracting an existing section."""
        messages = [
            {
                "source": "DataEngineer",
                "content": """Here's the payload:

### WIKIDATA_PAYLOAD
```json
{"claims": []}
```

### OTHER_SECTION
More content here.
""",
            }
        ]

        result = _extract_section(messages, "WIKIDATA_PAYLOAD")
        assert result is not None
        assert "claims" in result

    def test_extract_nonexistent_section(self):
        """Test extracting a section that doesn't exist."""
        messages = [
            {"source": "Agent", "content": "No sections here."}
        ]

        result = _extract_section(messages, "MISSING_SECTION")
        assert result is None

    def test_extract_from_multiple_messages(self):
        """Test extraction prefers later messages."""
        messages = [
            {"source": "Agent1", "content": "### SECTION\nOld content"},
            {"source": "Agent2", "content": "### SECTION\nNew content"},
        ]

        result = _extract_section(messages, "SECTION")
        assert "New content" in result

    def test_extract_gps_grade_card(self):
        """Test extracting GPS Grade Card section."""
        messages = [
            {
                "source": "Manager",
                "content": """Analysis complete.

### 📊 GPS Grade Card
Overall: 7/10
- Evidence Quality: 8/10
- Citations: 6/10
- Narrative: 7/10

### 📝 Suggested Improvements
Add more sources.
""",
            }
        ]

        result = _extract_section(messages, "GPS Grade Card")
        assert result is not None
        assert "7/10" in result
        assert "Evidence Quality" in result


class TestPromptRules:
    """Test that prompts contain critical rules."""

    def test_manager_no_invented_sources(self):
        """Manager should prohibit inventing sources."""
        assert "Never invent sources" in MANAGER_PROMPT

    def test_linguist_evidence_driven(self):
        """Linguist should emphasize evidence-driven content."""
        assert "evidence" in LINGUIST_PROMPT.lower()

    def test_data_engineer_references(self):
        """Data engineer should require references."""
        assert "references" in DATA_ENGINEER_PROMPT.lower()
        assert "do not invent" in DATA_ENGINEER_PROMPT.lower()

    def test_devops_atomic_commits(self):
        """DevOps should prefer small commits."""
        assert "small" in DEVOPS_PROMPT.lower() or "atomic" in DEVOPS_PROMPT.lower()


class TestWikidataProperties:
    """Test Wikidata property coverage in prompts."""

    def test_vital_record_properties(self):
        """Ensure vital record properties are documented."""
        properties = ["P569", "P570", "P19", "P20"]  # birth/death dates/places
        for prop in properties:
            assert prop in DATA_ENGINEER_PROMPT, f"Missing property {prop}"

    def test_relationship_properties(self):
        """Ensure relationship properties are documented."""
        properties = ["P22", "P25", "P26", "P40"]  # father, mother, spouse, child
        for prop in properties:
            assert prop in DATA_ENGINEER_PROMPT, f"Missing property {prop}"


class TestOutputFormats:
    """Test expected output format specifications."""

    def test_manager_format_headers(self):
        """Manager output should use standard headers."""
        headers = [
            "### 📊 GPS Grade Card",
            "### 🧬 Extracted Entities",
            "### 📝 Suggested Improvements",
            "### 🚀 Sync Commands",
        ]
        for header in headers:
            assert header in MANAGER_PROMPT

    def test_linguist_format_headers(self):
        """Linguist should have platform-specific sections."""
        assert "### WIKIPEDIA_DRAFT" in LINGUIST_PROMPT
        assert "### WIKITREE_BIO" in LINGUIST_PROMPT
        assert "### DIFF" in LINGUIST_PROMPT

    def test_devops_format_headers(self):
        """DevOps should have commit and command sections."""
        assert "### GIT_COMMIT_MSG" in DEVOPS_PROMPT
        assert "### GIT_COMMANDS" in DEVOPS_PROMPT


class TestDelegationRules:
    """Test that Manager prompt specifies proper delegation."""

    def test_linguist_delegation(self):
        """Manager should delegate to Linguist for content."""
        assert "Linguist" in MANAGER_PROMPT
        assert "tone" in MANAGER_PROMPT.lower() or "DIFF" in MANAGER_PROMPT

    def test_data_engineer_delegation(self):
        """Manager should delegate to Data Engineer for Wikidata."""
        assert "Data Engineer" in MANAGER_PROMPT
        assert "Wikidata" in MANAGER_PROMPT

    def test_devops_delegation(self):
        """Manager should delegate to DevOps for git workflow."""
        assert "DevOps" in MANAGER_PROMPT
        assert "commit" in MANAGER_PROMPT.lower()

    def test_reviewer_delegation(self):
        """Manager should delegate to Reviewer before finalizing."""
        assert "Reviewer" in MANAGER_PROMPT
        assert "fact-check" in MANAGER_PROMPT.lower() or "FINAL" in MANAGER_PROMPT


class TestReviewerPrompt:
    """Test Reviewer agent prompt."""

    def test_reviewer_is_adversarial(self):
        """Reviewer should be explicitly adversarial."""
        assert "ADVERSARIAL" in REVIEWER_PROMPT
        assert "find problems" in REVIEWER_PROMPT.lower()

    def test_reviewer_severity_levels(self):
        """Reviewer should define severity levels."""
        assert "CRITICAL" in REVIEWER_PROMPT
        assert "HIGH" in REVIEWER_PROMPT
        assert "MEDIUM" in REVIEWER_PROMPT
        assert "LOW" in REVIEWER_PROMPT

    def test_reviewer_checks_fabrications(self):
        """Reviewer should check for fabrications."""
        assert "FABRICATIONS" in REVIEWER_PROMPT
        assert "invented" in REVIEWER_PROMPT.lower() or "Invented" in REVIEWER_PROMPT

    def test_reviewer_checks_logic(self):
        """Reviewer should check for logical errors."""
        assert "LOGICAL ERRORS" in REVIEWER_PROMPT
        assert "death before birth" in REVIEWER_PROMPT.lower()

    def test_reviewer_checks_sources(self):
        """Reviewer should verify source matching."""
        assert "SOURCE MISMATCHES" in REVIEWER_PROMPT
        assert "cited source" in REVIEWER_PROMPT.lower()

    def test_reviewer_output_format(self):
        """Reviewer should have defined output sections."""
        assert "REVIEW REPORT" in REVIEWER_PROMPT
        assert "INTEGRITY SCORE" in REVIEWER_PROMPT
        assert "BLOCKING ISSUES" in REVIEWER_PROMPT

    def test_reviewer_blocks_critical(self):
        """Reviewer should block publication on critical issues."""
        assert "block" in REVIEWER_PROMPT.lower()
        assert "CRITICAL" in REVIEWER_PROMPT


class TestApprovalLogic:
    """Test the _is_approved helper function."""

    def test_approved_with_none(self):
        """Test approval when blocking issues is 'None'."""
        messages = [
            {"source": "Reviewer", "content": "### ⚠️ BLOCKING ISSUES\nNone - clear to publish"}
        ]
        assert _is_approved(messages) is True

    def test_approved_clear_to_publish(self):
        """Test approval with 'clear to publish' message."""
        messages = [
            {"source": "Reviewer", "content": "### ⚠️ BLOCKING ISSUES\nNo blocking issues. Clear to publish."}
        ]
        assert _is_approved(messages) is True

    def test_not_approved_with_issues(self):
        """Test rejection when blocking issues exist."""
        messages = [
            {"source": "Reviewer", "content": "### ⚠️ BLOCKING ISSUES\n1. Birth date unsourced\n2. Death date conflicts"}
        ]
        assert _is_approved(messages) is False

    def test_not_approved_no_review(self):
        """Test rejection when no review found."""
        messages = [
            {"source": "Manager", "content": "All done!"}
        ]
        assert _is_approved(messages) is False


class TestReviewerExtraction:
    """Test extraction of Reviewer output sections."""

    def test_extract_integrity_score(self):
        """Test extracting integrity score."""
        messages = [
            {
                "source": "Reviewer",
                "content": """### 🔍 REVIEW REPORT
Some review content.

### 📊 INTEGRITY SCORE
85/100
- Fabrication Check: 100%
- Logic Check: 90%
- Source Verification: 70%

### ⚠️ BLOCKING ISSUES
None - clear to publish
""",
            }
        ]

        score = _extract_section(messages, "INTEGRITY SCORE")
        assert score is not None
        assert "85/100" in score

    def test_extract_blocking_issues(self):
        """Test extracting blocking issues."""
        messages = [
            {
                "source": "Reviewer",
                "content": """### 📊 INTEGRITY SCORE
50/100

### ⚠️ BLOCKING ISSUES
1. CRITICAL: Birth date (1931) not supported by any source
2. HIGH: Father's name appears to be fabricated

Must fix before publishing.
""",
            }
        ]

        blocking = _extract_section(messages, "BLOCKING ISSUES")
        assert blocking is not None
        assert "CRITICAL" in blocking
        assert "Birth date" in blocking


class TestDualReviewerPrompts:
    """Test dual reviewer prompts are properly defined."""

    def test_logic_reviewer_has_timeline_focus(self):
        """LogicReviewer should focus on timeline errors."""
        assert "TIMELINE" in LOGIC_REVIEWER_PROMPT
        assert "Death before birth" in LOGIC_REVIEWER_PROMPT
        assert "LOGIC_VERDICT" in LOGIC_REVIEWER_PROMPT

    def test_logic_reviewer_has_relationship_checks(self):
        """LogicReviewer should check relationships."""
        assert "RELATIONSHIP" in LOGIC_REVIEWER_PROMPT
        assert "Circular" in LOGIC_REVIEWER_PROMPT

    def test_logic_reviewer_requires_quorum(self):
        """LogicReviewer should require agreement with SourceReviewer."""
        assert "SourceReviewer" in LOGIC_REVIEWER_PROMPT
        assert "AGREE" in LOGIC_REVIEWER_PROMPT

    def test_source_reviewer_has_fabrication_focus(self):
        """SourceReviewer should focus on fabrications."""
        assert "FABRICATION" in SOURCE_REVIEWER_PROMPT
        assert "Hallucinated" in SOURCE_REVIEWER_PROMPT
        assert "SOURCE_VERDICT" in SOURCE_REVIEWER_PROMPT

    def test_source_reviewer_has_citation_checks(self):
        """SourceReviewer should check citations."""
        assert "CITATION" in SOURCE_REVIEWER_PROMPT
        assert "Incomplete" in SOURCE_REVIEWER_PROMPT

    def test_source_reviewer_requires_quorum(self):
        """SourceReviewer should require agreement with LogicReviewer."""
        assert "LogicReviewer" in SOURCE_REVIEWER_PROMPT
        assert "AGREE" in SOURCE_REVIEWER_PROMPT


class TestQuorumResult:
    """Test QuorumResult dataclass."""

    def test_both_pass(self):
        """Test quorum when both reviewers pass."""
        result = QuorumResult(
            logic_verdict="PASS",
            source_verdict="PASS",
            quorum_reached=True,
            approved=True,
        )
        assert result.approved is True
        assert "Both reviewers approved" in result.status

    def test_logic_fails(self):
        """Test quorum when LogicReviewer fails."""
        result = QuorumResult(
            logic_verdict="FAIL",
            source_verdict="PASS",
            quorum_reached=True,
            approved=False,
        )
        assert result.approved is False
        assert "LogicReviewer" in result.status

    def test_source_fails(self):
        """Test quorum when SourceReviewer fails."""
        result = QuorumResult(
            logic_verdict="PASS",
            source_verdict="FAIL",
            quorum_reached=True,
            approved=False,
        )
        assert result.approved is False
        assert "SourceReviewer" in result.status

    def test_both_fail(self):
        """Test quorum when both fail."""
        result = QuorumResult(
            logic_verdict="FAIL",
            source_verdict="FAIL",
            quorum_reached=True,
            approved=False,
        )
        assert "Both reviewers found issues" in result.status

    def test_awaiting_logic(self):
        """Test status when awaiting LogicReviewer."""
        result = QuorumResult(
            source_verdict="PASS",
        )
        assert "Awaiting LogicReviewer" in result.status

    def test_awaiting_source(self):
        """Test status when awaiting SourceReviewer."""
        result = QuorumResult(
            logic_verdict="PASS",
        )
        assert "Awaiting SourceReviewer" in result.status


class TestCheckQuorum:
    """Test check_quorum function."""

    def test_quorum_both_pass(self):
        """Test quorum detection when both pass."""
        messages = [
            {
                "source": "LogicReviewer",
                "content": """### 🧮 LOGIC REVIEW
All timeline checks passed.

### LOGIC_VERDICT
PASS - No logical errors found.
""",
            },
            {
                "source": "SourceReviewer",
                "content": """### 📚 SOURCE REVIEW
All sources verified.

### SOURCE_VERDICT
PASS - Sources are accurate.
""",
            },
        ]

        result = check_quorum(messages)
        assert result.quorum_reached is True
        assert result.approved is True
        assert result.logic_verdict == "PASS"
        assert result.source_verdict == "PASS"

    def test_quorum_logic_fails(self):
        """Test quorum when logic fails."""
        messages = [
            {
                "source": "LogicReviewer",
                "content": """### 🧮 LOGIC REVIEW
- CRITICAL: Death before birth

### LOGIC_VERDICT
FAIL - Timeline impossibility found.
""",
            },
            {
                "source": "SourceReviewer",
                "content": """### SOURCE_VERDICT
PASS - Sources are accurate.
""",
            },
        ]

        result = check_quorum(messages)
        assert result.quorum_reached is True
        assert result.approved is False
        assert result.logic_verdict == "FAIL"

    def test_quorum_not_reached(self):
        """Test when only one reviewer has responded."""
        messages = [
            {
                "source": "LogicReviewer",
                "content": """### LOGIC_VERDICT
PASS
""",
            },
        ]

        result = check_quorum(messages)
        assert result.quorum_reached is False
        assert result.approved is False


class TestPublishDecision:
    """Test auto-downgrade publishing logic."""

    def test_no_issues_all_approved(self):
        """Test all platforms approved with no issues."""
        decision = PublishDecision.from_issues([])
        assert decision.wikipedia is True
        assert decision.wikidata is True
        assert decision.wikitree is True
        assert decision.github is True
        assert decision.integrity_score == 100

    def test_critical_blocks_all(self):
        """Test CRITICAL issue blocks all platforms."""
        issues = [
            ReviewIssue(
                severity=Severity.CRITICAL,
                category="fabrication",
                description="Birth date invented",
            )
        ]
        decision = PublishDecision.from_issues(issues)
        assert decision.wikipedia is False
        assert decision.wikidata is False
        assert decision.wikitree is False
        assert decision.github is False
        assert decision.integrity_score == 60  # 100 - 40

    def test_high_blocks_wikipedia_wikidata(self):
        """Test HIGH issue blocks Wikipedia and Wikidata."""
        issues = [
            ReviewIssue(
                severity=Severity.HIGH,
                category="logic",
                description="Timeline impossible",
            )
        ]
        decision = PublishDecision.from_issues(issues)
        assert decision.wikipedia is False
        assert decision.wikidata is False
        assert decision.wikitree is True
        assert decision.wikitree is True
        assert decision.github is True
        assert decision.integrity_score == 80  # 100 - 20

    def test_medium_blocks_wikipedia_only(self):
        """Test MEDIUM issue blocks only Wikipedia."""
        issues = [
            ReviewIssue(
                severity=Severity.MEDIUM,
                category="quality",
                description="Missing uncertainty marker",
            )
        ]
        decision = PublishDecision.from_issues(issues)
        assert decision.wikipedia is False
        assert decision.wikidata is True
        assert decision.wikitree is True
        assert decision.github is True
        assert decision.integrity_score == 90  # 100 - 10

    def test_low_blocks_nothing(self):
        """Test LOW issue blocks nothing."""
        issues = [
            ReviewIssue(
                severity=Severity.LOW,
                category="style",
                description="Template format issue",
            )
        ]
        decision = PublishDecision.from_issues(issues)
        assert decision.wikipedia is True
        assert decision.wikidata is True
        assert decision.wikitree is True
        assert decision.github is True
        assert decision.integrity_score == 95  # 100 - 5

    def test_get_allowed_platforms(self):
        """Test getting allowed platforms."""
        issues = [
            ReviewIssue(severity=Severity.MEDIUM, category="quality", description="Test")
        ]
        decision = PublishDecision.from_issues(issues)
        allowed = decision.get_allowed_platforms()
        assert Platform.WIKIPEDIA not in allowed
        assert Platform.WIKIDATA in allowed
        assert Platform.WIKITREE in allowed
        assert Platform.GITHUB in allowed

    def test_summary_all_approved(self):
        """Test summary when all approved."""
        decision = PublishDecision.from_issues([])
        assert "APPROVED" in decision.summary()

    def test_summary_downgraded(self):
        """Test summary when downgraded."""
        issues = [
            ReviewIssue(severity=Severity.MEDIUM, category="quality", description="Test")
        ]
        decision = PublishDecision.from_issues(issues)
        assert "DOWNGRADED" in decision.summary()
        assert "Wikipedia" in decision.summary()

    def test_summary_blocked(self):
        """Test summary when all blocked."""
        issues = [
            ReviewIssue(severity=Severity.CRITICAL, category="fabrication", description="Test")
        ]
        decision = PublishDecision.from_issues(issues)
        assert "BLOCKED" in decision.summary()


class TestReviewerMemory:
    """Test ReviewerMemory tracking."""

    def test_record_mistake(self):
        """Test recording a single mistake."""
        memory = ReviewerMemory()
        memory.record_mistake(
            agent_name="DataEngineer",
            category="fabrication",
            severity=Severity.CRITICAL,
            description="Hallucinated QID",
        )
        assert len(memory.mistakes) == 1
        assert memory.mistakes[0].agent_name == "DataEngineer"

    def test_agent_stats(self):
        """Test getting agent statistics."""
        memory = ReviewerMemory()
        memory.record_mistake("DataEngineer", "fabrication", Severity.CRITICAL, "Issue 1")
        memory.record_mistake("DataEngineer", "fabrication", Severity.HIGH, "Issue 2")
        memory.record_mistake("DataEngineer", "logic", Severity.MEDIUM, "Issue 3")

        stats = memory.get_agent_stats("DataEngineer")
        assert stats["total"] == 3
        assert stats["by_category"]["fabrication"] == 2
        assert stats["by_category"]["logic"] == 1
        assert stats["most_common"] == "fabrication"

    def test_agent_stats_empty(self):
        """Test stats for agent with no mistakes."""
        memory = ReviewerMemory()
        stats = memory.get_agent_stats("UnknownAgent")
        assert stats["total"] == 0

    def test_problem_agents(self):
        """Test identifying problem agents."""
        memory = ReviewerMemory()
        # DataEngineer has 4 mistakes
        for i in range(4):
            memory.record_mistake("DataEngineer", "fabrication", Severity.HIGH, f"Issue {i}")
        # Linguist has 2 mistakes
        for i in range(2):
            memory.record_mistake("Linguist", "style", Severity.LOW, f"Issue {i}")

        problems = memory.get_problem_agents(min_mistakes=3)
        assert len(problems) == 1
        assert problems[0][0] == "DataEngineer"

    def test_generate_report(self):
        """Test report generation."""
        memory = ReviewerMemory()
        memory.record_mistake("DataEngineer", "fabrication", Severity.CRITICAL, "Test issue")

        report = memory.generate_report()
        assert "DataEngineer" in report
        assert "fabrication" in report

    def test_empty_report(self):
        """Test report with no mistakes."""
        memory = ReviewerMemory()
        report = memory.generate_report()
        assert "No mistakes" in report

    def test_persistence(self):
        """Test saving and loading memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memory.json"

            # Create and save
            memory1 = ReviewerMemory(persist_path=path)
            memory1.record_mistake("DataEngineer", "fabrication", Severity.CRITICAL, "Test")

            assert path.exists()

            # Load in new instance
            memory2 = ReviewerMemory(persist_path=path)
            assert len(memory2.mistakes) == 1
            assert memory2.mistakes[0].agent_name == "DataEngineer"

    def test_record_issues(self):
        """Test recording issues from review."""
        memory = ReviewerMemory()
        issues = [
            ReviewIssue(
                severity=Severity.CRITICAL,
                category="fabrication",
                description="Made up date",
                agent_responsible="DataEngineer",
            ),
            ReviewIssue(
                severity=Severity.HIGH,
                category="logic",
                description="Timeline error",
                agent_responsible="Linguist",
            ),
        ]
        memory.record_issues(issues)

        assert len(memory.mistakes) == 2
        assert memory.get_agent_stats("DataEngineer")["total"] == 1
        assert memory.get_agent_stats("Linguist")["total"] == 1
