"""Tests for Semantic Kernel plugins."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus
from gps_agents.models.gps import GPSEvaluation, PillarStatus
from gps_agents.models.provenance import Provenance, ProvenanceSource
from gps_agents.models.source import EvidenceType, SourceCitation
from gps_agents.projections.sqlite_projection import SQLiteProjection
from gps_agents.sk.plugins.citation import CitationPlugin
from gps_agents.sk.plugins.gps import GPSPlugin
from gps_agents.sk.plugins.ledger import LedgerPlugin
from gps_agents.sk.plugins.memory import MemoryPlugin


class TestLedgerPlugin:
    """Tests for LedgerPlugin."""

    @pytest.fixture
    def ledger_plugin(self):
        """Create a LedgerPlugin with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = FactLedger(str(Path(tmpdir) / "ledger"))
            projection = SQLiteProjection(str(Path(tmpdir) / "projection.db"))
            plugin = LedgerPlugin(ledger, projection)
            yield plugin
            ledger.close()

    def test_append_and_get_fact(self, ledger_plugin):
        """Test appending and retrieving a fact."""
        fact = Fact(
            statement="John Smith born 1842",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        result = ledger_plugin.append_fact(fact.model_dump_json())
        result_data = json.loads(result)

        assert result_data["success"] is True
        assert "key" in result_data

        # Retrieve
        retrieved = ledger_plugin.get_fact(str(fact.fact_id))
        retrieved_fact = Fact.model_validate_json(retrieved)
        assert retrieved_fact.statement == fact.statement

    def test_get_nonexistent_fact(self, ledger_plugin):
        """Test getting a fact that doesn't exist."""
        result = ledger_plugin.get_fact(str(uuid4()))
        result_data = json.loads(result)
        assert "error" in result_data

    def test_list_facts_by_status(self, ledger_plugin):
        """Test listing facts by status."""
        # Add some facts
        for i in range(3):
            fact = Fact(
                statement=f"Fact {i}",
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            )
            ledger_plugin.append_fact(fact.model_dump_json())

        result = ledger_plugin.list_facts_by_status("proposed")
        facts = json.loads(result)
        assert len(facts) == 3

    def test_update_fact_status(self, ledger_plugin):
        """Test updating fact status."""
        fact = Fact(
            statement="Test fact",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        ledger_plugin.append_fact(fact.model_dump_json())

        result = ledger_plugin.update_fact_status(str(fact.fact_id), "accepted")
        result_data = json.loads(result)

        assert result_data["success"] is True
        assert result_data["new_version"] == 2

    def test_get_ledger_stats(self, ledger_plugin):
        """Test getting ledger statistics."""
        for i in range(5):
            fact = Fact(
                statement=f"Fact {i}",
                provenance=Provenance(created_by=ProvenanceSource.USER_INPUT),
            )
            ledger_plugin.append_fact(fact.model_dump_json())

        result = ledger_plugin.get_ledger_stats()
        stats = json.loads(result)

        assert stats["total_facts"] == 5
        assert stats["by_status"]["proposed"] == 5


class TestGPSPlugin:
    """Tests for GPSPlugin."""

    @pytest.fixture
    def gps_plugin(self):
        """Create a GPSPlugin with temporary ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = FactLedger(str(Path(tmpdir) / "ledger"))
            plugin = GPSPlugin(ledger)
            yield plugin
            ledger.close()

    def test_evaluate_pillar_1_satisfied(self, gps_plugin):
        """Test Pillar 1 evaluation - satisfied."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            sources=[
                SourceCitation(
                    repository="FamilySearch",
                    record_id="123",
                    evidence_type=EvidenceType.DIRECT,
                ),
                SourceCitation(
                    repository="WikiTree",
                    record_id="456",
                    evidence_type=EvidenceType.DIRECT,
                ),
            ],
        )

        sources = ["FamilySearch", "WikiTree", "FindMyPast", "MyHeritage"]
        result = gps_plugin.evaluate_pillar_1(
            fact.model_dump_json(), json.dumps(sources)
        )
        result_data = json.loads(result)

        assert result_data["pillar"] == 1
        assert result_data["status"] == "satisfied"

    def test_evaluate_pillar_1_failed(self, gps_plugin):
        """Test Pillar 1 evaluation - failed."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        sources = ["SomeUnknownSource"]
        result = gps_plugin.evaluate_pillar_1(
            fact.model_dump_json(), json.dumps(sources)
        )
        result_data = json.loads(result)

        assert result_data["pillar"] == 1
        assert result_data["status"] == "failed"

    def test_evaluate_pillar_2_satisfied(self, gps_plugin):
        """Test Pillar 2 evaluation - complete citations."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            sources=[
                SourceCitation(
                    repository="FamilySearch",
                    record_id="ABC123",
                    evidence_type=EvidenceType.DIRECT,
                ),
            ],
        )

        result = gps_plugin.evaluate_pillar_2(fact.model_dump_json())
        result_data = json.loads(result)

        assert result_data["pillar"] == 2
        assert result_data["status"] == "satisfied"

    def test_evaluate_pillar_2_failed_no_sources(self, gps_plugin):
        """Test Pillar 2 evaluation - no sources."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        result = gps_plugin.evaluate_pillar_2(fact.model_dump_json())
        result_data = json.loads(result)

        assert result_data["pillar"] == 2
        assert result_data["status"] == "failed"

    def test_can_accept_fact_true(self, gps_plugin):
        """Test can_accept when all criteria met."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            confidence_score=0.85,
            gps_evaluation=GPSEvaluation(
                pillar_1=PillarStatus.SATISFIED,
                pillar_2=PillarStatus.SATISFIED,
                pillar_3=PillarStatus.SATISFIED,
                pillar_4=PillarStatus.SATISFIED,
                pillar_5=PillarStatus.SATISFIED,
            ),
        )

        gps_plugin.ledger.append(fact)

        result = gps_plugin.can_accept_fact(str(fact.fact_id))
        result_data = json.loads(result)

        assert result_data["can_accept"] is True

    def test_can_accept_fact_false_low_confidence(self, gps_plugin):
        """Test can_accept with low confidence."""
        fact = Fact(
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            confidence_score=0.5,
            gps_evaluation=GPSEvaluation(
                pillar_1=PillarStatus.SATISFIED,
                pillar_2=PillarStatus.SATISFIED,
                pillar_3=PillarStatus.SATISFIED,
                pillar_4=PillarStatus.SATISFIED,
                pillar_5=PillarStatus.SATISFIED,
            ),
        )

        gps_plugin.ledger.append(fact)

        result = gps_plugin.can_accept_fact(str(fact.fact_id))
        result_data = json.loads(result)

        assert result_data["can_accept"] is False


class TestCitationPlugin:
    """Tests for CitationPlugin."""

    @pytest.fixture
    def citation_plugin(self):
        """Create a CitationPlugin."""
        return CitationPlugin()

    def test_create_citation(self, citation_plugin):
        """Test creating a citation."""
        result = citation_plugin.create_citation(
            repository="FamilySearch",
            record_id="ABC123",
            evidence_type="direct",
            url="https://familysearch.org/ABC123",
            record_type="Birth Certificate",
        )

        citation = SourceCitation.model_validate_json(result)
        assert citation.repository == "FamilySearch"
        assert citation.evidence_type == EvidenceType.DIRECT

    def test_format_citation(self, citation_plugin):
        """Test formatting a citation."""
        citation = SourceCitation(
            repository="FamilySearch",
            record_id="ABC123",
            record_type="Birth Certificate",
            evidence_type=EvidenceType.DIRECT,
        )

        result = citation_plugin.format_citation(citation.model_dump_json())
        assert "FamilySearch" in result
        assert "Birth Certificate" in result

    def test_classify_evidence_direct(self, citation_plugin):
        """Test evidence classification - direct."""
        result = citation_plugin.classify_evidence(
            source_description="The birth certificate states that John Smith was born on January 5, 1842",
            claim="John Smith was born in 1842",
        )

        result_data = json.loads(result)
        assert result_data["evidence_type"] == "direct"

    def test_classify_evidence_indirect(self, citation_plugin):
        """Test evidence classification - indirect."""
        result = citation_plugin.classify_evidence(
            source_description="Based on age listed in the 1880 census, birth year estimated",
            claim="John Smith was born in 1842",
        )

        result_data = json.loads(result)
        assert result_data["evidence_type"] == "indirect"

    def test_validate_citation_valid(self, citation_plugin):
        """Test citation validation - valid."""
        citation = SourceCitation(
            repository="FamilySearch",
            record_id="ABC123",
            evidence_type=EvidenceType.DIRECT,
            url="https://familysearch.org/ABC123",
            record_type="Birth Certificate",
        )

        result = citation_plugin.validate_citation(citation.model_dump_json())
        result_data = json.loads(result)

        assert result_data["is_valid"] is True
        assert len(result_data["issues"]) == 0


class TestMemoryPlugin:
    """Tests for MemoryPlugin."""

    @pytest.fixture
    def memory_plugin(self):
        """Create a MemoryPlugin with temporary storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = MemoryPlugin(tmpdir)
            yield plugin

    def test_get_memory_stats(self, memory_plugin):
        """Test getting memory statistics."""
        result = memory_plugin.get_memory_stats()
        stats = json.loads(result)

        # ChromaDB may or may not be available
        if stats.get("available"):
            assert "collections" in stats
        else:
            assert "error" in stats or stats.get("available") is False

    def test_store_and_search_fact(self, memory_plugin):
        """Test storing and searching facts."""
        stats = json.loads(memory_plugin.get_memory_stats())
        if not stats.get("available"):
            pytest.skip("ChromaDB not available")

        # Store a fact
        fact_id = str(uuid4())
        memory_plugin.store_fact(
            fact_id=fact_id,
            statement="John Smith was born in Ireland in 1842",
            metadata_json=json.dumps({"status": "PROPOSED"}),
        )

        # Search for similar facts
        result = memory_plugin.search_similar_facts("Irish birth 1840s")
        results = json.loads(result)

        assert len(results) > 0
        assert results[0]["fact_id"] == fact_id
