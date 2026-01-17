"""Tests for the fact ledger."""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus
from gps_agents.models.provenance import Provenance, ProvenanceSource


class TestFactLedger:
    """Tests for FactLedger."""

    @pytest.fixture
    def temp_ledger(self):
        """Create a temporary ledger for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = FactLedger(tmpdir)
            yield ledger
            ledger.close()

    def test_append_and_get(self, temp_ledger):
        """Test appending and retrieving facts."""
        fact = Fact(
            statement="John Smith born 1842",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        key = temp_ledger.append(fact)
        assert key == f"{fact.fact_id}:1"

        retrieved = temp_ledger.get(fact.fact_id)
        assert retrieved is not None
        assert retrieved.statement == fact.statement

    def test_versioning(self, temp_ledger):
        """Test that new versions are stored correctly."""
        fact = Fact(
            fact_id=uuid4(),
            statement="Original statement",
            provenance=Provenance(created_by=ProvenanceSource.USER_INPUT),
        )

        temp_ledger.append(fact)

        # Create version 2
        fact_v2 = fact.set_status(FactStatus.ACCEPTED)
        temp_ledger.append(fact_v2)

        # Get latest should return v2
        latest = temp_ledger.get(fact.fact_id)
        assert latest.version == 2
        assert latest.status == FactStatus.ACCEPTED

        # Can still get v1
        v1 = temp_ledger.get(fact.fact_id, version=1)
        assert v1.version == 1
        assert v1.status == FactStatus.PROPOSED

    def test_get_all_versions(self, temp_ledger):
        """Test retrieving all versions of a fact."""
        fact_id = uuid4()
        fact = Fact(
            fact_id=fact_id,
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        # Add multiple versions
        temp_ledger.append(fact)
        temp_ledger.append(fact.set_status(FactStatus.INCOMPLETE))
        temp_ledger.append(
            fact.model_copy(update={"version": 3, "status": FactStatus.ACCEPTED})
        )

        versions = temp_ledger.get_all_versions(fact_id)
        assert len(versions) == 3
        assert versions[0].version == 1
        assert versions[2].version == 3

    def test_get_latest_version(self, temp_ledger):
        """Test getting the latest version number."""
        fact_id = uuid4()
        fact = Fact(
            fact_id=fact_id,
            statement="Test",
            provenance=Provenance(created_by=ProvenanceSource.USER_INPUT),
        )

        temp_ledger.append(fact)
        temp_ledger.append(fact.model_copy(update={"version": 2}))
        temp_ledger.append(fact.model_copy(update={"version": 3}))

        latest = temp_ledger.get_latest_version(fact_id)
        assert latest == 3

    def test_iter_all_facts(self, temp_ledger):
        """Test iterating over all facts."""
        # Add several facts
        for i in range(5):
            fact = Fact(
                statement=f"Fact {i}",
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
                status=FactStatus.ACCEPTED if i % 2 == 0 else FactStatus.PROPOSED,
            )
            temp_ledger.append(fact)

        all_facts = list(temp_ledger.iter_all_facts())
        assert len(all_facts) == 5

        accepted = list(temp_ledger.iter_all_facts(FactStatus.ACCEPTED))
        assert len(accepted) == 3  # 0, 2, 4

    def test_count(self, temp_ledger):
        """Test counting facts."""
        for i in range(3):
            fact = Fact(
                statement=f"Fact {i}",
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            )
            temp_ledger.append(fact)

        assert temp_ledger.count() == 3

    def test_get_nonexistent(self, temp_ledger):
        """Test getting a fact that doesn't exist."""
        result = temp_ledger.get(uuid4())
        assert result is None
