"""Tests for Wiki Publishing Team."""

import pytest

from gps_agents.autogen.wiki_publishing import (
    DATA_ENGINEER_PROMPT,
    DEVOPS_PROMPT,
    LINGUIST_PROMPT,
    MANAGER_PROMPT,
    REVIEWER_PROMPT,
    _extract_section,
    _is_approved,
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
