"""Tests for LLM-Native Extraction module."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gps_agents.genealogy_crawler.extraction import (
    CensusMemberRole,
    ExtractionConfidence,
    ExtractionProvenance,
    ExtractionResult,
    ExtractorType,
    StructuredCensusHousehold,
    StructuredCensusPerson,
)


class TestStructuredCensusPerson:
    """Tests for StructuredCensusPerson model."""

    def test_create_person(self):
        """Test basic person creation."""
        person = StructuredCensusPerson(
            given_name="Archie",
            surname="Durham",
            middle_name="G",
            name_as_recorded="Archie G Durham",
            birth_year=1927,
            age_at_census=23,
            birth_place="North Carolina",
            relation_to_head=CensusMemberRole.HEAD,
        )

        assert person.given_name == "Archie"
        assert person.surname == "Durham"
        assert person.full_name == "Archie G Durham"
        assert person.birth_year == 1927

    def test_search_key(self):
        """Test search key generation for deduplication."""
        person = StructuredCensusPerson(
            given_name="Archie",
            surname="Durham",
            name_as_recorded="Archie Durham",
            birth_year=1927,
            birth_place="North Carolina",
        )

        assert person.search_key == "Archie|Durham|1927|North Carolina"

    def test_estimated_birth_year_from_age(self):
        """Test birth year calculation from age."""
        person = StructuredCensusPerson(
            given_name="Archie",
            surname="Durham",
            name_as_recorded="Archie Durham",
            age_at_census=23,
        )

        estimated = person.estimated_birth_year_from_age(1950)
        assert estimated == 1927

    def test_name_variants(self):
        """Test name variant tracking."""
        person = StructuredCensusPerson(
            given_name="Eafrom",
            surname="Durham",
            name_as_recorded="Eafrom B Durham",
            name_variants=["Eaf", "Eaf B", "E. B."],
        )

        assert len(person.name_variants) == 3
        assert "Eaf" in person.name_variants


class TestStructuredCensusHousehold:
    """Tests for StructuredCensusHousehold model."""

    @pytest.fixture
    def sample_household(self):
        """Create a sample household for testing."""
        head = StructuredCensusPerson(
            given_name="Archie",
            surname="Durham",
            middle_name="G",
            name_as_recorded="Archie G Durham",
            birth_year=1927,
            age_at_census=23,
            birth_place="North Carolina",
            relation_to_head=CensusMemberRole.HEAD,
            occupation="Laborer",
        )

        wife = StructuredCensusPerson(
            given_name="Ruth",
            surname="Durham",
            middle_name="L",
            name_as_recorded="Ruth L Durham",
            birth_year=1923,
            age_at_census=27,
            birth_place="California",
            relation_to_head=CensusMemberRole.WIFE,
        )

        son = StructuredCensusPerson(
            given_name="Archer",
            surname="Durham",
            middle_name="L",
            name_as_recorded="Archer L Durham",
            birth_year=1948,
            age_at_census=2,
            birth_place="California",
            relation_to_head=CensusMemberRole.SON,
        )

        return StructuredCensusHousehold(
            census_year=1950,
            state="California",
            county="Santa Clara",
            city_or_township="San Jose",
            enumeration_district="43-79",
            dwelling_number=125,
            family_number=126,
            head=head,
            members=[head, wife, son],
            source_url="https://www.familysearch.org/ark:/...",
            source_repository="FamilySearch",
        )

    def test_create_household(self, sample_household):
        """Test household creation."""
        assert sample_household.census_year == 1950
        assert sample_household.state == "California"
        assert sample_household.county == "Santa Clara"
        assert len(sample_household.members) == 3

    def test_location_display(self, sample_household):
        """Test formatted location string."""
        location = sample_household.location_display
        assert "San Jose" in location
        assert "Santa Clara" in location
        assert "California" in location

    def test_citation_reference(self, sample_household):
        """Test GPS citation reference generation."""
        citation = sample_household.citation_reference
        assert "1950 U.S. Census" in citation
        assert "Santa Clara" in citation
        assert "ED 43-79" in citation
        assert "dwelling 125" in citation

    def test_get_parents_of_child(self, sample_household):
        """Test finding parents of a child in household."""
        # Use full name including middle initial to match
        parents = sample_household.get_parents_of("Archer L Durham")
        assert len(parents) == 2
        parent_roles = {p.relation_to_head for p in parents}
        assert CensusMemberRole.HEAD in parent_roles
        assert CensusMemberRole.WIFE in parent_roles

    def test_get_siblings(self, sample_household):
        """Test finding siblings."""
        # Add another child
        daughter = StructuredCensusPerson(
            given_name="Mary",
            surname="Durham",
            name_as_recorded="Mary Durham",
            birth_year=1950,
            relation_to_head=CensusMemberRole.DAUGHTER,
        )
        sample_household.members.append(daughter)

        # Use full name to match - should find Mary as the only sibling
        siblings = sample_household.get_siblings_of("Archer L Durham")
        assert len(siblings) == 1
        assert siblings[0].given_name == "Mary"

    def test_get_spouse_of_head(self, sample_household):
        """Test finding spouse of head."""
        spouse = sample_household.get_spouse_of_head()
        assert spouse is not None
        assert spouse.given_name == "Ruth"

    def test_auto_detect_head(self):
        """Test auto-detection of head from members."""
        members = [
            StructuredCensusPerson(
                given_name="John",
                surname="Doe",
                name_as_recorded="John Doe",
                relation_to_head=CensusMemberRole.HEAD,
            ),
            StructuredCensusPerson(
                given_name="Jane",
                surname="Doe",
                name_as_recorded="Jane Doe",
                relation_to_head=CensusMemberRole.WIFE,
            ),
        ]

        household = StructuredCensusHousehold(
            census_year=1940,
            state="California",
            county="Los Angeles",
            members=members,
        )

        assert household.head is not None
        assert household.head.given_name == "John"


class TestExtractionProvenance:
    """Tests for ExtractionProvenance tracking."""

    def test_compression_ratio(self):
        """Test HTML to Markdown compression ratio calculation."""
        provenance = ExtractionProvenance(
            source_url="https://example.com",
            extractor_type=ExtractorType.FIRECRAWL,
            html_size_bytes=30000,
            markdown_size_bytes=10000,
        )

        assert provenance.compression_ratio == pytest.approx(0.667, rel=0.01)

    def test_token_tracking(self):
        """Test token usage tracking."""
        provenance = ExtractionProvenance(
            source_url="https://example.com",
            extractor_type=ExtractorType.LLM_STRUCTURED,
            input_tokens=1500,
            output_tokens=800,
            model_used="claude-sonnet-4-20250514",
        )

        assert provenance.input_tokens == 1500
        assert provenance.output_tokens == 800
        assert provenance.model_used == "claude-sonnet-4-20250514"


class TestExtractionResult:
    """Tests for ExtractionResult wrapper."""

    def test_success_result(self):
        """Test creating a successful result."""
        household = StructuredCensusHousehold(
            census_year=1950,
            state="California",
            county="Santa Clara",
            members=[],
        )

        provenance = ExtractionProvenance(
            source_url="https://example.com",
            extractor_type=ExtractorType.LLM_STRUCTURED,
        )

        result = ExtractionResult.success_result(
            data=household,
            provenance=provenance,
            confidence=ExtractionConfidence.HIGH,
            citation_ready=True,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data.census_year == 1950
        assert result.confidence == ExtractionConfidence.HIGH
        assert result.citation_ready is True

    def test_failure_result(self):
        """Test creating a failed result."""
        provenance = ExtractionProvenance(
            source_url="https://example.com",
            extractor_type=ExtractorType.LLM_STRUCTURED,
        )

        result = ExtractionResult.failure_result(
            error="Page not found",
            provenance=provenance,
            error_type="HTTPError",
        )

        assert result.success is False
        assert result.data is None
        assert result.error == "Page not found"
        assert result.error_type == "HTTPError"

    def test_needs_verification_for_low_confidence(self):
        """Test that low confidence triggers verification flag."""
        household = StructuredCensusHousehold(
            census_year=1950,
            state="California",
            county="Santa Clara",
            members=[],
        )

        provenance = ExtractionProvenance(
            source_url="https://example.com",
            extractor_type=ExtractorType.LLM_STRUCTURED,
        )

        result = ExtractionResult.success_result(
            data=household,
            provenance=provenance,
            confidence=ExtractionConfidence.LOW,
        )

        assert result.needs_verification is True


class TestCensusMemberRole:
    """Tests for CensusMemberRole enum."""

    def test_role_values(self):
        """Test that expected roles exist."""
        assert CensusMemberRole.HEAD.value == "head"
        assert CensusMemberRole.WIFE.value == "wife"
        assert CensusMemberRole.SON.value == "son"
        assert CensusMemberRole.DAUGHTER.value == "daughter"
        assert CensusMemberRole.BOARDER.value == "boarder"

    def test_role_from_string(self):
        """Test creating role from string value."""
        role = CensusMemberRole("head")
        assert role == CensusMemberRole.HEAD


class TestExtractorType:
    """Tests for ExtractorType enum."""

    def test_extractor_types(self):
        """Test that expected extractor types exist."""
        assert ExtractorType.SCRAPEGRAPHAI.value == "scrapegraphai"
        assert ExtractorType.FIRECRAWL.value == "firecrawl"
        assert ExtractorType.LLM_STRUCTURED.value == "llm_structured"
        assert ExtractorType.DETERMINISTIC.value == "deterministic"
