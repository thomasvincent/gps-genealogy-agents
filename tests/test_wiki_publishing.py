"""Tests for Wiki Publishing Team."""

import pytest

from gps_agents.autogen.wiki_publishing import (
    DATA_ENGINEER_PROMPT,
    DEVOPS_PROMPT,
    LINGUIST_PROMPT,
    MANAGER_PROMPT,
    _extract_section,
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
