"""Tests for the GPS Search Orchestrator Agent."""

import pytest

from gps_agents.agents.search_orchestrator import (
    ConflictInfo,
    OrchestratorAction,
    OrchestratorResponse,
    OrchestratorResult,
    SearchOrchestratorAgent,
    SourceType,
)
from gps_agents.gramps.merge import MatchConfidence, MatchResult
from gps_agents.gramps.models import Name, Person
from gps_agents.models.search import RawRecord
from gps_agents.sources.router import Region


class TestSearchOrchestratorAgent:
    """Test SearchOrchestratorAgent functionality."""

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        agent = SearchOrchestratorAgent()
        assert agent.name == "search_orchestrator"
        assert agent.prompt_file == "search_orchestrator.txt"

    def test_generate_name_variants(self):
        """Test surname variant generation."""
        agent = SearchOrchestratorAgent()

        variants = agent._generate_name_variants("Johnson")
        assert "Johnson" in variants
        assert "Johnsen" in variants  # son -> sen

        variants = agent._generate_name_variants("Schmidt")
        assert "Schmidt" in variants
        # ck -> k transformation

    def test_determine_region_from_place(self):
        """Test region determination from place names."""
        agent = SearchOrchestratorAgent()

        assert agent._determine_region("County Cork, Ireland", None) == Region.IRELAND
        assert agent._determine_region("Brussels, Belgium", None) == Region.BELGIUM
        assert agent._determine_region("Jersey, Channel Islands", None) == Region.CHANNEL_ISLANDS
        assert agent._determine_region("Unknown", None) is None

    def test_determine_region_explicit(self):
        """Test explicit region override."""
        agent = SearchOrchestratorAgent()

        # Explicit region takes precedence
        assert agent._determine_region("New York", "ireland") == Region.IRELAND
        assert agent._determine_region("", "belgium") == Region.BELGIUM


class TestSourceClassification:
    """Test source type classification."""

    def test_classify_original_source(self):
        """Test classification of original sources."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="Parish Records Archive",
            record_id="123",
            record_type="original image",
            extracted_fields={},
        )
        result = agent._classify_source(record)
        assert result == SourceType.ORIGINAL

    def test_classify_derivative_source(self):
        """Test classification of derivative sources."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="FamilySearch Index",
            record_id="456",
            record_type="index",
            extracted_fields={},
        )
        result = agent._classify_source(record)
        assert result == SourceType.DERIVATIVE

    def test_classify_authored_source(self):
        """Test classification of authored sources."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="WikiTree",
            record_id="Smith-123",
            record_type="profile",
            extracted_fields={},
        )
        result = agent._classify_source(record)
        assert result == SourceType.AUTHORED


class TestEvidenceEvaluation:
    """Test evidence evaluation logic."""

    def test_evaluate_evidence_original(self):
        """Test evaluation boosts original sources."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="Parish Church Records",
            record_id="123",
            record_type="original",
            extracted_fields={"name": "John Smith"},
            confidence_hint=0.6,
        )
        result = agent._evaluate_evidence(record)

        # Original source gets +0.2 boost
        assert result.confidence == 0.8
        assert result.source_type == SourceType.ORIGINAL

    def test_evaluate_evidence_authored(self):
        """Test evaluation penalizes authored sources."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="WikiTree Tree",
            record_id="456",
            record_type="tree",
            extracted_fields={"name": "John Smith"},
            confidence_hint=0.6,
        )
        result = agent._evaluate_evidence(record)

        # Authored source gets -0.1 penalty
        assert result.confidence == 0.5
        assert result.source_type == SourceType.AUTHORED


class TestConflictDetection:
    """Test conflict detection logic."""

    def test_detect_no_conflicts(self):
        """Test detection with consistent data."""
        agent = SearchOrchestratorAgent()

        results = [
            OrchestratorResult(
                model="Person",
                data={"birth_year": 1850},
                source_citation="Source A",
                confidence=0.8,
            ),
            OrchestratorResult(
                model="Person",
                data={"birth_year": 1850},
                source_citation="Source B",
                confidence=0.7,
            ),
        ]

        conflicts = agent._detect_conflicts(results)
        assert len(conflicts) == 0

    def test_detect_birth_year_conflict(self):
        """Test detection of birth year conflicts."""
        agent = SearchOrchestratorAgent()

        results = [
            OrchestratorResult(
                model="Person",
                data={"birth_year": 1850},
                source_citation="Source A",
                confidence=0.8,
            ),
            OrchestratorResult(
                model="Person",
                data={"birth_year": 1852},
                source_citation="Source B",
                confidence=0.6,
            ),
        ]

        conflicts = agent._detect_conflicts(results)
        assert len(conflicts) == 1
        assert conflicts[0].field == "birth_year"
        assert conflicts[0].value_a == 1850
        assert conflicts[0].value_b == 1852


class TestConflictResolution:
    """Test conflict resolution logic."""

    def test_can_resolve_clear_winner(self):
        """Test resolution when one source is clearly better."""
        agent = SearchOrchestratorAgent()

        conflicts = [
            ConflictInfo(
                field="birth_year",
                value_a=1850,
                value_b=1852,
                source_a="Source A",
                source_b="Source B",
                confidence_a=0.9,  # Clear winner
                confidence_b=0.5,
            )
        ]

        assert agent._can_resolve_conflicts(conflicts) is True

    def test_cannot_resolve_close_confidence(self):
        """Test resolution fails when confidences are close."""
        agent = SearchOrchestratorAgent()

        conflicts = [
            ConflictInfo(
                field="birth_year",
                value_a=1850,
                value_b=1852,
                source_a="Source A",
                source_b="Source B",
                confidence_a=0.75,  # Too close
                confidence_b=0.70,
            )
        ]

        assert agent._can_resolve_conflicts(conflicts) is False


class TestOverallConfidence:
    """Test overall confidence calculation."""

    def test_weighted_confidence(self):
        """Test confidence weighting by source type."""
        agent = SearchOrchestratorAgent()

        results = [
            OrchestratorResult(
                model="Person",
                data={},
                source_citation="A",
                confidence=0.9,
                source_type=SourceType.ORIGINAL,  # weight 3
            ),
            OrchestratorResult(
                model="Person",
                data={},
                source_citation="B",
                confidence=0.6,
                source_type=SourceType.AUTHORED,  # weight 1
            ),
        ]

        overall = agent._calculate_overall_confidence(results)
        # (0.9 * 3 + 0.6 * 1) / (3 + 1) = 3.3 / 4 = 0.825
        assert abs(overall - 0.825) < 0.001

    def test_empty_results_confidence(self):
        """Test confidence with no results."""
        agent = SearchOrchestratorAgent()
        overall = agent._calculate_overall_confidence([])
        assert overall == 0.0


class TestNextStepRecommendation:
    """Test next step recommendation logic."""

    def test_low_confidence_expands(self):
        """Test low confidence recommends expansion."""
        agent = SearchOrchestratorAgent()

        recommendation = agent._recommend_next_step(
            confidence=0.5,
            sources_searched=["familysearch"],
        )

        assert "Expand search" in recommendation
        assert "name variants" in recommendation.lower()

    def test_high_confidence_sufficient(self):
        """Test high confidence indicates sufficiency."""
        agent = SearchOrchestratorAgent()

        recommendation = agent._recommend_next_step(
            confidence=0.85,
            sources_searched=["familysearch", "wikitree", "findmypast"],
        )

        assert "GPS compliance" in recommendation


class TestOrchestratorResponse:
    """Test OrchestratorResponse model."""

    def test_response_serialization(self):
        """Test response serializes to JSON."""
        response = OrchestratorResponse(
            action=OrchestratorAction.SEARCH,
            parameters={"surname": "Smith"},
            results=[
                OrchestratorResult(
                    model="Person",
                    data={"name": "John Smith"},
                    source_citation="FamilySearch, record 123",
                    confidence=0.8,
                    source_type=SourceType.DERIVATIVE,
                )
            ],
            justification="Found 1 record",
            next_step="Verify with additional sources",
        )

        json_str = response.model_dump_json()
        assert "search" in json_str.lower()
        assert "Smith" in json_str
        assert "0.8" in json_str

    def test_response_with_match(self):
        """Test response with Gramps match."""
        match_result = MatchResult(
            matched=True,
            confidence=MatchConfidence.PROBABLE,
            match_score=75.0,
            matched_person=Person(
                gramps_id="I001",
                names=[Name(given="John", surname="Smith")],
            ),
            matched_handle="I001",
            match_reasons=["Exact surname match"],
        )

        response = OrchestratorResponse(
            action=OrchestratorAction.MATCH,
            parameters={},
            results=[],
            justification="Match found in Gramps",
            next_step="Review existing record",
            gramps_match=match_result,
        )

        assert response.action == OrchestratorAction.MATCH
        assert response.gramps_match is not None
        assert response.gramps_match.confidence == MatchConfidence.PROBABLE


class TestCitationFormatting:
    """Test GPS-compliant citation formatting."""

    def test_format_citation_complete(self):
        """Test full citation formatting."""
        agent = SearchOrchestratorAgent()

        from datetime import datetime

        record = RawRecord(
            source="FamilySearch",
            record_id="ABCD-1234",
            record_type="Birth Certificate",
            url="https://familysearch.org/ark:/12345",
            extracted_fields={},
            accessed_at=datetime(2024, 1, 15),
        )

        citation = agent._format_citation(record)

        assert "FamilySearch" in citation
        assert "ABCD-1234" in citation
        assert "Birth Certificate" in citation
        assert "familysearch.org" in citation
        assert "15 Jan 2024" in citation

    def test_format_citation_minimal(self):
        """Test citation with minimal info."""
        agent = SearchOrchestratorAgent()

        record = RawRecord(
            source="Unknown Archive",
            record_id="123",
            record_type="document",
            extracted_fields={},
        )

        citation = agent._format_citation(record)
        assert "Unknown Archive" in citation
        assert "123" in citation


class TestSearchQueryBuilding:
    """Test exhaustive query building."""

    def test_build_exhaustive_query(self):
        """Test GPS Pillar 1 compliant query building."""
        agent = SearchOrchestratorAgent()

        query = agent._build_exhaustive_query(
            surname="Johnson",
            given_name="John",
            birth_year=1850,
            birth_place="Cork, Ireland",
        )

        assert query.surname == "Johnson"
        assert query.given_name == "John"
        assert query.birth_year == 1850
        assert query.birth_year_range == 5  # GPS standard
        assert "birth" in query.record_types
        assert "death" in query.record_types
        assert len(query.surname_variants) > 1  # Has variants
