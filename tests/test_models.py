"""Tests for Pydantic models."""

from datetime import datetime
from uuid import uuid4

import pytest

from gps_agents.models.confidence import ConfidenceDelta, calculate_confidence
from gps_agents.models.fact import Annotation, Fact, FactStatus
from gps_agents.models.gps import Conflict, GPSEvaluation, PillarStatus
from gps_agents.models.provenance import Provenance, ProvenanceSource
from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.models.source import EvidenceType, SourceCitation


class TestFact:
    """Tests for the Fact model."""

    def test_create_fact(self):
        """Test basic fact creation."""
        fact = Fact(
            statement="John Smith was born in 1842",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        assert fact.statement == "John Smith was born in 1842"
        assert fact.status == FactStatus.PROPOSED
        assert fact.version == 1
        assert fact.confidence_score == 0.5

    def test_fact_immutability(self):
        """Test that fact methods return new instances."""
        fact = Fact(
            statement="Test fact",
            provenance=Provenance(created_by=ProvenanceSource.USER_INPUT),
        )

        # Apply confidence delta
        delta = ConfidenceDelta(
            agent="test",
            delta=0.1,
            reason="Test adjustment",
            previous_score=0.5,
            new_score=0.6,
        )
        new_fact = fact.apply_confidence_delta(delta)

        assert new_fact is not fact
        assert new_fact.version == 2
        assert new_fact.confidence_score == 0.6
        assert fact.confidence_score == 0.5  # Original unchanged

    def test_fact_set_status(self):
        """Test status updates."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        accepted = fact.set_status(FactStatus.ACCEPTED)
        assert accepted.status == FactStatus.ACCEPTED
        assert accepted.version == 2
        assert fact.status == FactStatus.PROPOSED  # Original unchanged

    def test_add_source(self):
        """Test adding sources."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        source = SourceCitation(
            repository="FamilySearch",
            record_id="ABC123",
            evidence_type=EvidenceType.DIRECT,
        )

        with_source = fact.add_source(source)
        assert len(with_source.sources) == 1
        assert len(fact.sources) == 0

    def test_ledger_key(self):
        """Test ledger key generation."""
        fact = Fact(
            fact_id=uuid4(),
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.USER_INPUT),
        )

        key = fact.ledger_key()
        assert key == f"{fact.fact_id}:1"

    def test_can_accept(self):
        """Test acceptance criteria."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            confidence_score=0.8,
            gps_evaluation=GPSEvaluation(
                pillar_1=PillarStatus.SATISFIED,
                pillar_2=PillarStatus.SATISFIED,
                pillar_3=PillarStatus.SATISFIED,
                pillar_4=PillarStatus.SATISFIED,
                pillar_5=PillarStatus.SATISFIED,
            ),
        )

        assert fact.can_accept() is True

    def test_cannot_accept_low_confidence(self):
        """Test that low confidence prevents acceptance."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            confidence_score=0.5,  # Below 0.7 threshold
            gps_evaluation=GPSEvaluation(
                pillar_1=PillarStatus.SATISFIED,
                pillar_2=PillarStatus.SATISFIED,
                pillar_3=PillarStatus.SATISFIED,
                pillar_4=PillarStatus.SATISFIED,
                pillar_5=PillarStatus.SATISFIED,
            ),
        )

        assert fact.can_accept() is False


class TestSourceCitation:
    """Tests for SourceCitation model."""

    def test_create_citation(self):
        """Test citation creation."""
        citation = SourceCitation(
            repository="WikiTree",
            record_id="Smith-123",
            url="https://www.wikitree.com/wiki/Smith-123",
            evidence_type=EvidenceType.DIRECT,
        )

        assert citation.repository == "WikiTree"
        assert citation.evidence_type == EvidenceType.DIRECT

    def test_evidence_explained_format(self):
        """Test Evidence Explained formatting."""
        citation = SourceCitation(
            repository="FamilySearch",
            record_id="12345",
            url="https://familysearch.org/12345",
            record_type="Birth Certificate",
            evidence_type=EvidenceType.DIRECT,
        )

        formatted = citation.to_evidence_explained()
        assert "FamilySearch" in formatted
        assert "Birth Certificate" in formatted
        assert "12345" in formatted


class TestGPSEvaluation:
    """Tests for GPS evaluation models."""

    def test_all_satisfied(self):
        """Test all_satisfied check."""
        evaluation = GPSEvaluation(
            pillar_1=PillarStatus.SATISFIED,
            pillar_2=PillarStatus.SATISFIED,
            pillar_3=PillarStatus.SATISFIED,
            pillar_4=PillarStatus.SATISFIED,
            pillar_5=PillarStatus.SATISFIED,
        )

        assert evaluation.all_satisfied() is True

    def test_partial_not_satisfied(self):
        """Test that partial pillars aren't satisfied."""
        evaluation = GPSEvaluation(
            pillar_1=PillarStatus.SATISFIED,
            pillar_2=PillarStatus.PARTIAL,
            pillar_3=PillarStatus.SATISFIED,
            pillar_4=PillarStatus.SATISFIED,
            pillar_5=PillarStatus.SATISFIED,
        )

        assert evaluation.all_satisfied() is False

    def test_get_failed_pillars(self):
        """Test identifying failed pillars."""
        evaluation = GPSEvaluation(
            pillar_1=PillarStatus.FAILED,
            pillar_2=PillarStatus.SATISFIED,
            pillar_3=PillarStatus.FAILED,
            pillar_4=PillarStatus.SATISFIED,
            pillar_5=PillarStatus.PENDING,
        )

        failed = evaluation.get_failed_pillars()
        assert failed == [1, 3]

    def test_confidence_delta_suggestion(self):
        """Test confidence adjustment suggestions."""
        # All satisfied
        good_eval = GPSEvaluation(
            pillar_1=PillarStatus.SATISFIED,
            pillar_2=PillarStatus.SATISFIED,
            pillar_3=PillarStatus.SATISFIED,
            pillar_4=PillarStatus.SATISFIED,
            pillar_5=PillarStatus.SATISFIED,
        )
        assert good_eval.suggest_confidence_delta() > 0

        # One failed
        bad_eval = GPSEvaluation(
            pillar_1=PillarStatus.FAILED,
            pillar_2=PillarStatus.SATISFIED,
            pillar_3=PillarStatus.SATISFIED,
            pillar_4=PillarStatus.SATISFIED,
            pillar_5=PillarStatus.SATISFIED,
        )
        assert bad_eval.suggest_confidence_delta() < 0


class TestSearchQuery:
    """Tests for SearchQuery model."""

    def test_create_query(self):
        """Test query creation."""
        query = SearchQuery(
            given_name="John",
            surname="Smith",
            birth_year=1842,
            birth_place="Ireland",
        )

        assert query.given_name == "John"
        assert query.surname == "Smith"
        assert query.birth_year_range == 5  # Default

    def test_year_range(self):
        """Test year range calculation."""
        query = SearchQuery(birth_year=1850, birth_year_range=10)

        year_range = query.get_year_range(query.birth_year, query.birth_year_range)
        assert year_range == (1840, 1860)

    def test_year_range_none(self):
        """Test year range with no year."""
        query = SearchQuery()
        assert query.get_year_range(None, 5) is None


class TestConfidence:
    """Tests for confidence calculations."""

    def test_direct_evidence_high_confidence(self):
        """Test that direct evidence yields higher confidence."""
        score = calculate_confidence("direct", 2, False, "high")
        assert score > 0.7

    def test_indirect_evidence_lower_confidence(self):
        """Test that indirect evidence yields lower confidence."""
        direct = calculate_confidence("direct", 1, False)
        indirect = calculate_confidence("indirect", 1, False)
        assert direct > indirect

    def test_conflicts_reduce_confidence(self):
        """Test that conflicts reduce confidence."""
        no_conflict = calculate_confidence("direct", 2, False)
        with_conflict = calculate_confidence("direct", 2, True)
        assert no_conflict > with_conflict

    def test_multiple_sources_boost(self):
        """Test that multiple sources increase confidence."""
        one_source = calculate_confidence("direct", 1, False)
        three_sources = calculate_confidence("direct", 3, False)
        assert three_sources > one_source

    def test_confidence_bounds(self):
        """Test confidence stays in [0, 1]."""
        # Very good evidence
        high = calculate_confidence("direct", 10, False, "high")
        assert high <= 1.0

        # Very poor evidence
        low = calculate_confidence("negative", 1, True, "low")
        assert low >= 0.0
