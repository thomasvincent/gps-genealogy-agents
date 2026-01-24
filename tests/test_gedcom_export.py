"""Tests for GEDCOM export functionality."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from gps_agents.export.gedcom import (
    GedcomEvent,
    GedcomFamily,
    GedcomIndividual,
    _name_from_person_key,
    _parse_event_from_fact,
    export_gedcom,
)
from gps_agents.models.fact import Fact, FactStatus
from gps_agents.models.provenance import Provenance, ProvenanceSource


# =============================================================================
# Unit Tests for Helper Functions
# =============================================================================


class TestNameFromPersonKey:
    """Tests for _name_from_person_key function."""

    def test_full_name(self) -> None:
        """Test extraction of full name with given and surname."""
        result = _name_from_person_key("John Smith|1900|New York")
        assert result == "John /Smith/"

    def test_multiple_given_names(self) -> None:
        """Test extraction with multiple given names."""
        result = _name_from_person_key("Mary Jane Watson|1985|Los Angeles")
        assert result == "Mary Jane /Watson/"

    def test_single_name(self) -> None:
        """Test extraction with only one name part."""
        result = _name_from_person_key("Madonna|1958|Michigan")
        assert result == "Madonna /Unknown/"

    def test_empty_name(self) -> None:
        """Test extraction with empty name."""
        result = _name_from_person_key("|1900|Unknown")
        assert result == "Unknown /Unknown/"

    def test_whitespace_handling(self) -> None:
        """Test that whitespace is handled correctly."""
        result = _name_from_person_key("  John   Doe  |1900|City")
        assert result == "John /Doe/"

    def test_no_delimiter(self) -> None:
        """Test name without pipe delimiter."""
        result = _name_from_person_key("John Smith")
        assert result == "John /Smith/"


class TestParseEventFromFact:
    """Tests for _parse_event_from_fact function."""

    def test_birth_with_date(self) -> None:
        """Test parsing birth fact with date."""
        fact = Fact(
            statement="Birth on 12 Jan 1900",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        date, place = _parse_event_from_fact(fact)
        assert date == "12 Jan 1900"
        assert place is None

    def test_no_date(self) -> None:
        """Test parsing fact without date."""
        fact = Fact(
            statement="Born in New York",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        date, place = _parse_event_from_fact(fact)
        assert date is None
        assert place is None

    def test_complex_date(self) -> None:
        """Test parsing fact with complex date."""
        fact = Fact(
            statement="Death on about 1950 in California",
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        date, place = _parse_event_from_fact(fact)
        assert date == "about 1950 in California"


# =============================================================================
# Unit Tests for Data Classes
# =============================================================================


class TestGedcomEvent:
    """Tests for GedcomEvent dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating event with minimal data."""
        event = GedcomEvent(tag="BIRT")
        assert event.tag == "BIRT"
        assert event.date is None
        assert event.place is None

    def test_creation_full(self) -> None:
        """Test creating event with all data."""
        event = GedcomEvent(tag="DEAT", date="15 Mar 1980", place="Los Angeles, CA")
        assert event.tag == "DEAT"
        assert event.date == "15 Mar 1980"
        assert event.place == "Los Angeles, CA"


class TestGedcomIndividual:
    """Tests for GedcomIndividual dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating individual with minimal data."""
        indi = GedcomIndividual(indi_id="@I1@", name="John /Smith/")
        assert indi.indi_id == "@I1@"
        assert indi.name == "John /Smith/"
        assert indi.events == []
        assert indi.fams_ids == set()
        assert indi.famc_ids == set()

    def test_add_events(self) -> None:
        """Test adding events to individual."""
        indi = GedcomIndividual(indi_id="@I1@", name="John /Smith/")
        indi.events.append(GedcomEvent(tag="BIRT", date="1900"))
        indi.events.append(GedcomEvent(tag="DEAT", date="1980"))
        assert len(indi.events) == 2


class TestGedcomFamily:
    """Tests for GedcomFamily dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating family with minimal data."""
        fam = GedcomFamily(fam_id="@F1@")
        assert fam.fam_id == "@F1@"
        assert fam.husb_id is None
        assert fam.wife_id is None
        assert fam.child_ids == set()

    def test_creation_full(self) -> None:
        """Test creating family with all data."""
        fam = GedcomFamily(
            fam_id="@F1@",
            husb_id="@I1@",
            wife_id="@I2@",
            child_ids={"@I3@", "@I4@"},
        )
        assert fam.husb_id == "@I1@"
        assert fam.wife_id == "@I2@"
        assert len(fam.child_ids) == 2


# =============================================================================
# Integration Tests for GEDCOM Export
# =============================================================================


class TestExportGedcomMinimal:
    """Tests for export_gedcom with minimal/empty data."""

    def test_empty_ledger(self, tmp_path: Path) -> None:
        """Test export with empty ledger produces valid GEDCOM skeleton."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)

        assert result.exists()
        content = result.read_text()
        lines = content.splitlines()

        # Check header
        assert lines[0] == "0 HEAD"
        assert any("1 SOUR gps-genealogy-agents" in line for line in lines)
        assert any("1 GEDC" in line for line in lines)
        assert any("2 VERS 5.5" in line for line in lines)
        assert any("1 CHAR UTF-8" in line for line in lines)

        # Check trailer
        assert lines[-1] == "0 TRLR"

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test that export creates parent directories if needed."""
        out = tmp_path / "nested" / "path" / "out.ged"
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)

        assert result.exists()
        assert result.parent.exists()


class TestExportGedcomWithFacts:
    """Tests for export_gedcom with actual facts."""

    def _create_ledger_with_facts(self, ledger_dir: Path, facts: list[Fact]) -> None:
        """Helper to create a ledger directory with facts using proper FactLedger format."""
        from gps_agents.ledger.fact_ledger import FactLedger

        ledger_dir.mkdir(parents=True, exist_ok=True)

        # Use FactLedger to properly append facts
        ledger = FactLedger(str(ledger_dir), enforce_privacy=False)
        for fact in facts:
            ledger.append(fact, skip_privacy_check=True)

    def test_single_person_birth(self, tmp_path: Path) -> None:
        """Test export with a single person birth fact."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        fact = Fact(
            statement="Birth on 9 June 1932",
            person_id="John Smith|1932|California",
            fact_type="birth",
            status=FactStatus.ACCEPTED,
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        self._create_ledger_with_facts(ledger_dir, [fact])

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Should contain INDI record
        assert "@I1@ INDI" in content
        assert "1 NAME John /Smith/" in content
        # Should contain BIRT event
        assert "1 BIRT" in content
        assert "2 DATE 9 June 1932" in content

    def test_relationship_spouse(self, tmp_path: Path) -> None:
        """Test export with spouse relationship."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        fact = Fact(
            statement="John Smith married Jane Doe",
            fact_type="relationship",
            relation_kind="spouse_of",
            relation_subject="John /Smith/",
            relation_object="Jane /Doe/",
            status=FactStatus.ACCEPTED,
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        self._create_ledger_with_facts(ledger_dir, [fact])

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Should contain both individuals
        assert "John /Smith/" in content
        assert "Jane /Doe/" in content
        # Should contain FAM record
        assert "FAM" in content
        assert "HUSB" in content
        assert "WIFE" in content

    def test_relationship_parent_child(self, tmp_path: Path) -> None:
        """Test export with parent-child relationship."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        fact = Fact(
            statement="John Smith is parent of Mary Smith",
            fact_type="relationship",
            relation_kind="parent_of",
            relation_subject="John /Smith/",
            relation_object="Mary /Smith/",
            status=FactStatus.ACCEPTED,
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )
        self._create_ledger_with_facts(ledger_dir, [fact])

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Should contain both individuals
        assert "John /Smith/" in content
        assert "Mary /Smith/" in content
        # Should contain FAM with CHIL
        assert "FAM" in content
        assert "CHIL" in content

    def test_multiple_events_same_person(self, tmp_path: Path) -> None:
        """Test export with multiple events for same person."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        facts = [
            Fact(
                statement="Birth on 1 Jan 1900",
                person_id="John Smith|1900|NY",
                fact_type="birth",
                status=FactStatus.ACCEPTED,
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            ),
            Fact(
                statement="Death on 15 Dec 1980",
                person_id="John Smith|1900|NY",
                fact_type="death",
                status=FactStatus.ACCEPTED,
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            ),
        ]
        self._create_ledger_with_facts(ledger_dir, facts)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Should have only one INDI record
        assert content.count("@I1@ INDI") == 1
        # Should have both events
        assert "1 BIRT" in content
        assert "1 DEAT" in content

    def test_only_accepted_facts(self, tmp_path: Path) -> None:
        """Test that only ACCEPTED facts are exported."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        facts = [
            Fact(
                statement="Birth on 1900",
                person_id="Accepted Person|1900|NY",
                fact_type="birth",
                status=FactStatus.ACCEPTED,
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            ),
            Fact(
                statement="Birth on 1901",
                person_id="Rejected Person|1901|CA",
                fact_type="birth",
                status=FactStatus.REJECTED,
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            ),
            Fact(
                statement="Birth on 1902",
                person_id="Proposed Person|1902|TX",
                fact_type="birth",
                status=FactStatus.PROPOSED,
                provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
            ),
        ]
        self._create_ledger_with_facts(ledger_dir, facts)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Should only contain accepted person
        assert "Accepted /Person/" in content
        assert "Rejected /Person/" not in content
        assert "Proposed /Person/" not in content


class TestGedcomValidity:
    """Tests for GEDCOM format validity."""

    def test_level_structure(self, tmp_path: Path) -> None:
        """Test that GEDCOM levels are correct."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        for line in content.splitlines():
            # Every line should start with a level number
            parts = line.split(" ", 1)
            assert parts[0].isdigit(), f"Line doesn't start with level: {line}"
            level = int(parts[0])
            # Levels should be 0-2 in this implementation
            assert 0 <= level <= 2, f"Invalid level {level} in line: {line}"

    def test_no_duplicate_records(self, tmp_path: Path) -> None:
        """Test that there are no duplicate FAM or INDI records."""
        from gps_agents.ledger.fact_ledger import FactLedger

        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"

        # Create facts that could potentially cause duplicates
        fact = Fact(
            statement="Spouse relationship",
            fact_type="relationship",
            relation_kind="spouse_of",
            relation_subject="Person A",
            relation_object="Person B",
            status=FactStatus.ACCEPTED,
            provenance=Provenance(created_by=ProvenanceSource.RESEARCH_AGENT),
        )

        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger = FactLedger(str(ledger_dir), enforce_privacy=False)
        ledger.append(fact, skip_privacy_check=True)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)
        content = result.read_text()

        # Count FAM records - should only be one
        fam_count = content.count("0 @F1@ FAM")
        assert fam_count == 1, f"Found {fam_count} duplicate FAM records"

    def test_utf8_encoding(self, tmp_path: Path) -> None:
        """Test that output is valid UTF-8."""
        out = tmp_path / "out.ged"
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)

        result = export_gedcom(ledger_dir=ledger_dir, out_file=out)

        # Should be able to read as UTF-8 without errors
        content = result.read_text(encoding="utf-8")
        assert "CHAR UTF-8" in content
