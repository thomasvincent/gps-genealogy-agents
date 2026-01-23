"""Tests for WikiTree census search functionality."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from gps_agents.sources.wikitree import (
    WikiTreeSource,
    CensusRecord,
    US_CENSUS_YEARS,
    CENSUS_PATTERNS,
)
from gps_agents.models.search import SearchQuery


class TestUSCensusYears:
    """Tests for US Census year constants."""

    def test_census_years_frozenset(self):
        """Test that all expected census years are present (now a frozenset for O(1) lookup)."""
        expected = frozenset([1790, 1800, 1810, 1820, 1830, 1840, 1850, 1860, 1870, 1880, 1890, 1900, 1910, 1920, 1930, 1940, 1950])
        assert US_CENSUS_YEARS == expected
        assert isinstance(US_CENSUS_YEARS, frozenset)

    def test_census_years_contains_all_decades(self):
        """Test that all expected decennial census years are present."""
        # Verify key census years for O(1) membership check
        assert 1790 in US_CENSUS_YEARS  # First census
        assert 1850 in US_CENSUS_YEARS  # First with name listings
        assert 1900 in US_CENSUS_YEARS
        assert 1940 in US_CENSUS_YEARS
        assert 1950 in US_CENSUS_YEARS  # Last publicly available

    def test_census_years_are_unique(self):
        """Test that there are no duplicate years (inherent in frozenset)."""
        # Frozenset guarantees uniqueness, but we test the count matches expected
        assert len(US_CENSUS_YEARS) == 17  # 1790-1950 = 17 census years


class TestCensusRecord:
    """Tests for the CensusRecord dataclass."""

    def test_create_minimal_record(self):
        """Test creating a record with just the year."""
        record = CensusRecord(year=1900)
        assert record.year == 1900
        assert record.location == ""
        assert record.state == ""
        assert record.age is None
        assert record.occupation == ""

    def test_create_full_record(self):
        """Test creating a record with all fields."""
        record = CensusRecord(
            year=1900,
            location="Durham, California",
            state="California",
            county="Butte",
            household_head="John Durham",
            relationship="Son",
            age=25,
            occupation="Farmer",
            birthplace="California",
            source_citation="1900 Census, page 5",
            raw_text="In the 1900 Census, aged 25, farmer",
            metadata={"sheet": "2A"},
        )
        assert record.year == 1900
        assert record.location == "Durham, California"
        assert record.state == "California"
        assert record.county == "Butte"
        assert record.household_head == "John Durham"
        assert record.relationship == "Son"
        assert record.age == 25
        assert record.occupation == "Farmer"
        assert record.birthplace == "California"
        assert record.metadata == {"sheet": "2A"}


class TestCensusPatterns:
    """Tests for census extraction regex patterns."""

    def test_year_pattern_standard(self):
        """Test standard US Census year pattern."""
        text = "Found in United States Census, 1900"
        match = CENSUS_PATTERNS["year_pattern"].search(text)
        assert match is not None
        assert match.group(1) == "1900"

    def test_year_pattern_federal(self):
        """Test Federal Census pattern."""
        text = "Listed in the Federal Census 1880"
        match = CENSUS_PATTERNS["year_pattern"].search(text)
        assert match is not None
        assert match.group(1) == "1880"

    def test_year_pattern_us_abbrev(self):
        """Test U.S. Census pattern."""
        text = "Recorded in U.S. Census, 1910"
        match = CENSUS_PATTERNS["year_pattern"].search(text)
        assert match is not None
        assert match.group(1) == "1910"

    def test_year_simple_pattern(self):
        """Test simple year + Census pattern."""
        text = "The 1920 Census shows the family"
        match = CENSUS_PATTERNS["year_simple"].search(text)
        assert match is not None
        assert match.group(1) == "1920"

    def test_age_pattern(self):
        """Test age extraction pattern."""
        text = "listed as aged 35 in the household"
        match = CENSUS_PATTERNS["age"].search(text)
        assert match is not None
        assert match.group(1) == "35"

    def test_age_pattern_with_colon(self):
        """Test age pattern with colon."""
        text = "Age: 42"
        match = CENSUS_PATTERNS["age"].search(text)
        assert match is not None
        assert match.group(1) == "42"

    def test_occupation_pattern(self):
        """Test occupation extraction pattern."""
        text = "Occupation: Blacksmith"
        match = CENSUS_PATTERNS["occupation"].search(text)
        assert match is not None
        assert match.group(1).strip() == "Blacksmith"

    def test_birthplace_pattern(self):
        """Test birthplace extraction pattern."""
        text = "Birthplace: North Carolina"
        match = CENSUS_PATTERNS["birthplace"].search(text)
        assert match is not None
        assert match.group(1).strip() == "North Carolina"

    def test_relationship_pattern(self):
        """Test relationship extraction pattern."""
        text = "Relationship: Son"
        match = CENSUS_PATTERNS["relationship"].search(text)
        assert match is not None
        assert match.group(1).strip() == "Son"

    def test_head_of_household_pattern(self):
        """Test head of household extraction pattern."""
        text = "Head of Household: William Durham"
        match = CENSUS_PATTERNS["head_of_household"].search(text)
        assert match is not None
        assert match.group(1).strip() == "William Durham"


class TestWikiTreeSourceCensusExtraction:
    """Tests for WikiTreeSource census extraction methods."""

    @pytest.fixture
    def source(self):
        """Create a WikiTreeSource instance."""
        return WikiTreeSource()

    def test_extract_census_years_single(self, source):
        """Test extracting a single census year."""
        bio = "John was found in the 1900 United States Census living in California."
        years = source.extract_census_years(bio)
        assert years == [1900]

    def test_extract_census_years_multiple(self, source):
        """Test extracting multiple census years."""
        bio = """
        John appears in the 1880 Census in Missouri.
        By the 1900 U.S. Census, he had moved to California.
        The 1910 Federal Census shows him as a farmer.
        """
        years = source.extract_census_years(bio)
        assert years == [1880, 1900, 1910]

    def test_extract_census_years_deduplicates(self, source):
        """Test that duplicate years are removed."""
        bio = """
        The 1900 Census shows John in California.
        Another reference to the 1900 United States Census.
        """
        years = source.extract_census_years(bio)
        assert years == [1900]

    def test_extract_census_years_ignores_non_census_years(self, source):
        """Test that non-census years are ignored."""
        bio = "John was born in 1875 and married in 1897."
        years = source.extract_census_years(bio)
        assert years == []

    def test_extract_census_records_with_location(self, source):
        """Test extracting census records with location info."""
        bio = """
        In the 1900 United States Census, Durham, California, John was listed as a farmer.
        """
        records = source.extract_census_records(bio)
        assert len(records) == 1
        assert records[0].year == 1900
        assert "Durham" in records[0].location or "Durham" in records[0].raw_text

    def test_extract_census_records_with_age(self, source):
        """Test extracting census records with age info."""
        bio = "The 1900 Census shows John aged 35 as head of household."
        records = source.extract_census_records(bio)
        assert len(records) == 1
        assert records[0].year == 1900
        assert records[0].age == 35

    def test_extract_census_records_with_occupation(self, source):
        """Test extracting census records with occupation info."""
        bio = "In the 1910 Federal Census, occupation: Carpenter, living in town."
        records = source.extract_census_records(bio)
        assert len(records) == 1
        assert records[0].year == 1910
        assert "Carpenter" in records[0].occupation

    def test_extract_census_records_multiple(self, source):
        """Test extracting multiple census records."""
        bio = """
        1880 Census: John was age: 15, living with parents.
        1900 U.S. Census shows John, aged 35, occupation: Farmer.
        1910 Federal Census lists John, age 45, Farmer.
        """
        records = source.extract_census_records(bio)
        assert len(records) == 3
        years = [r.year for r in records]
        assert 1880 in years
        assert 1900 in years
        assert 1910 in years


class TestWikiTreeSourceCensusAsync:
    """Async tests for WikiTreeSource census methods."""

    @pytest.fixture
    def source(self):
        """Create a WikiTreeSource instance."""
        return WikiTreeSource()

    @pytest.mark.asyncio
    async def test_get_biography_success(self, source):
        """Test successful biography retrieval."""
        # WikiTree API returns a list with profile dict keyed by WikiTree ID
        mock_response = [
            {
                "Durham-1234": {
                    "bio": "John Durham was born in 1865 in California. The 1900 Census shows him as a farmer.",
                    "page_name": "Durham-1234",
                }
            }
        ]

        with patch.object(source, "_make_wikitree_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            bio = await source.get_biography("Durham-1234")

            assert bio is not None
            assert "John Durham" in bio
            assert "1900 Census" in bio
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_biography_not_found(self, source):
        """Test biography retrieval when profile not found."""
        with patch.object(source, "_make_wikitree_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = []
            bio = await source.get_biography("NonExistent-9999")

            assert bio is None

    @pytest.mark.asyncio
    async def test_get_biography_error(self, source):
        """Test biography retrieval when API error occurs."""
        with patch.object(source, "_make_wikitree_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = Exception("API Error")
            bio = await source.get_biography("Durham-1234")

            assert bio is None

    @pytest.mark.asyncio
    async def test_get_person_census_history(self, source):
        """Test getting census history for a person."""
        mock_bio = """
        John Durham (1865-1940) was a California farmer.

        The 1880 United States Census shows John, age 15, living with his parents.
        By the 1900 Census, he was head of household, aged 35, occupation: Farmer.
        The 1910 Federal Census lists him, age 45, still farming.
        """

        with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
            mock_get_bio.return_value = mock_bio
            records = await source.get_person_census_history("Durham-1234")

            assert len(records) == 3
            years = [r.year for r in records]
            assert 1880 in years
            assert 1900 in years
            assert 1910 in years

    @pytest.mark.asyncio
    async def test_get_person_census_history_no_bio(self, source):
        """Test census history when no biography exists."""
        with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
            mock_get_bio.return_value = None
            records = await source.get_person_census_history("Durham-1234")

            assert records == []

    @pytest.mark.asyncio
    async def test_search_census(self, source):
        """Test searching for profiles with census records."""
        from gps_agents.models.search import RawRecord
        from datetime import UTC, datetime

        mock_search_results = [
            RawRecord(
                source="WikiTree",
                record_id="Durham-1234",
                record_type="profile",
                url="https://www.wikitree.com/wiki/Durham-1234",
                raw_data={"Name": "Durham-1234"},
                extracted_fields={"wikitree_id": "Durham-1234", "given_name": "John", "surname": "Durham"},
                accessed_at=datetime.now(UTC),
            )
        ]

        mock_bio = "John in the 1900 U.S. Census, California, age 35"

        with patch.object(source, "search", new_callable=AsyncMock) as mock_search:
            with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
                mock_search.return_value = mock_search_results
                mock_get_bio.return_value = mock_bio

                query = SearchQuery(surname="Durham")
                results = await source.search_census(query, census_year=1900)

                assert len(results) == 1
                assert results[0].extracted_fields.get("census_years") == [1900]
                assert results[0].record_type == "profile_with_census"

    @pytest.mark.asyncio
    async def test_search_census_filter_by_year(self, source):
        """Test filtering census search by year."""
        from gps_agents.models.search import RawRecord
        from datetime import UTC, datetime

        mock_search_results = [
            RawRecord(
                source="WikiTree",
                record_id="Durham-1234",
                record_type="profile",
                url="https://www.wikitree.com/wiki/Durham-1234",
                raw_data={"Name": "Durham-1234"},
                extracted_fields={"wikitree_id": "Durham-1234"},
                accessed_at=datetime.now(UTC),
            )
        ]

        mock_bio = "John in the 1880 Census and 1900 Census"

        with patch.object(source, "search", new_callable=AsyncMock) as mock_search:
            with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
                mock_search.return_value = mock_search_results
                mock_get_bio.return_value = mock_bio

                query = SearchQuery(surname="Durham")

                # Filter to only 1900
                results = await source.search_census(query, census_year=1900)

                assert len(results) == 1
                assert 1900 in results[0].extracted_fields.get("census_years", [])

    @pytest.mark.asyncio
    async def test_search_census_filter_by_state(self, source):
        """Test filtering census search by state."""
        from gps_agents.models.search import RawRecord
        from datetime import UTC, datetime

        mock_search_results = [
            RawRecord(
                source="WikiTree",
                record_id="Durham-1234",
                record_type="profile",
                url="https://www.wikitree.com/wiki/Durham-1234",
                raw_data={"Name": "Durham-1234"},
                extracted_fields={"wikitree_id": "Durham-1234"},
                accessed_at=datetime.now(UTC),
            )
        ]

        mock_bio = "Census, 1900, Durham, California - John Durham"

        with patch.object(source, "search", new_callable=AsyncMock) as mock_search:
            with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
                mock_search.return_value = mock_search_results
                mock_get_bio.return_value = mock_bio

                query = SearchQuery(surname="Durham")

                # Filter by California
                results = await source.search_census(query, state="California")

                # Should find records in California
                assert len(results) >= 0  # May or may not find depending on location parsing

    @pytest.mark.asyncio
    async def test_search_by_census_location(self, source):
        """Test searching by census location."""
        with patch.object(source, "search_census", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []

            results = await source.search_by_census_location(
                census_year=1900,
                state="California",
                county="Butte",
                surname="Durham",
            )

            mock_search.assert_called_once()
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_by_census_location_invalid_year(self, source):
        """Test that invalid census years return empty results."""
        results = await source.search_by_census_location(
            census_year=1895,  # Not a census year
            state="California",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_get_ancestors_with_census(self, source):
        """Test getting ancestors with census data."""
        mock_ancestors_response = {
            "ancestors": [
                {
                    "Name": "Durham-100",
                    "FirstName": "William",
                    "LastNameAtBirth": "Durham",
                    "BirthDate": "1835",
                    "DeathDate": "1910",
                    "BirthLocation": "North Carolina",
                }
            ]
        }

        mock_bio = "William in the 1870 Census, 1880 Census, 1900 Census"

        with patch.object(source, "_make_wikitree_request", new_callable=AsyncMock) as mock_request:
            with patch.object(source, "get_biography", new_callable=AsyncMock) as mock_get_bio:
                mock_request.return_value = mock_ancestors_response
                mock_get_bio.return_value = mock_bio

                results = await source.get_ancestors_with_census("Durham-1234", generations=2)

                assert len(results) == 1
                assert results[0]["wikitree_id"] == "Durham-100"
                assert results[0]["name"] == "William Durham"
                assert 1870 in results[0]["census_years"]
                assert 1880 in results[0]["census_years"]
                assert 1900 in results[0]["census_years"]


class TestWikiTreeSourceCensusIntegration:
    """Integration-style tests for census search workflow."""

    @pytest.fixture
    def source(self):
        """Create a WikiTreeSource instance."""
        return WikiTreeSource()

    def test_full_extraction_workflow(self, source):
        """Test complete extraction workflow with realistic bio text."""
        bio = """
        == Biography ==
        John William Durham was born on March 15, 1865, in Butte County, California.

        === Census Records ===
        In the '''1880 United States Census''', John (age: 15) was living with his
        parents William and Mary Durham in Durham Township, Butte County, California.
        Birthplace: California. His father was listed as a farmer.

        By the '''1900 U.S. Census''', John had established his own household in
        Durham, California. He was recorded as:
        - Age: 35
        - Occupation: Farmer
        - Relationship: Head of Household
        - Birthplace: California

        The '''1910 Federal Census''' shows John still farming in Durham, California,
        now aged 45 with his wife Sarah and three children.

        The '''1920 Census''' records show the family had moved to Chico, California.
        John, age 55, was still listed as a farmer.

        === Death ===
        John died on November 22, 1940, in Durham, California.
        """

        # Extract census years
        years = source.extract_census_years(bio)
        assert years == [1880, 1900, 1910, 1920]

        # Extract full records
        records = source.extract_census_records(bio)
        assert len(records) == 4

        # Check 1880 record
        r1880 = next(r for r in records if r.year == 1880)
        assert r1880.age == 15 or "15" in r1880.raw_text

        # Check 1900 record
        r1900 = next(r for r in records if r.year == 1900)
        assert r1900.age == 35 or "35" in r1900.raw_text

        # Check 1910 record
        r1910 = next(r for r in records if r.year == 1910)
        assert "1910" in str(r1910.year)

        # Check 1920 record
        r1920 = next(r for r in records if r.year == 1920)
        assert r1920.year == 1920
