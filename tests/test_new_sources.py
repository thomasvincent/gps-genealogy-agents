"""Tests for new genealogy sources: USGenWeb, Fold3, RootsWeb, and AccessGenealogy cemetery extension."""
from __future__ import annotations

import pytest

from gps_agents.models.search import SearchQuery
from gps_agents.sources import (
    AccessGenealogySource,
    Fold3Source,
    RootsWebSource,
    USGenWebSource,
)


class TestAccessGenealogyCemetery:
    """Tests for AccessGenealogy cemetery records extension."""

    def test_normalize_state_abbreviation(self):
        """State abbreviations should normalize to URL slugs."""
        source = AccessGenealogySource()
        assert source._normalize_state("CA") == "california"
        assert source._normalize_state("NY") == "new-york"
        assert source._normalize_state("TX") == "texas"

    def test_normalize_state_full_name(self):
        """Full state names should normalize to URL slugs."""
        source = AccessGenealogySource()
        assert source._normalize_state("California") == "california"
        assert source._normalize_state("New York") == "new-york"
        assert source._normalize_state("TEXAS") == "texas"

    def test_normalize_state_invalid(self):
        """Invalid states should return None."""
        source = AccessGenealogySource()
        assert source._normalize_state("Invalid") is None
        assert source._normalize_state("") is None
        assert source._normalize_state(None) is None

    def test_extract_location(self):
        """Location extraction from cemetery titles."""
        source = AccessGenealogySource()
        assert "Los Angeles County" in source._extract_location("Los Angeles County Cemetery Records")
        assert "San Diego County" in source._extract_location("San Diego County Burial Index")
        assert source._extract_location("Some Cemetery") == ""

    def test_requires_no_auth(self):
        """AccessGenealogy should not require authentication."""
        source = AccessGenealogySource()
        assert source.requires_auth() is False


class TestUSGenWebSource:
    """Tests for USGenWeb source."""

    def test_normalize_state(self):
        """State normalization for USGenWeb URLs."""
        source = USGenWebSource()
        assert source._normalize_state("CA") == "california"
        assert source._normalize_state("california") == "california"
        assert source._normalize_state("New York") == "newyork"  # Spaces removed
        assert source._normalize_state("InvalidState") is None

    def test_classify_record_type(self):
        """Record type classification from text/URL."""
        source = USGenWebSource()
        assert source._classify_record_type("cemetery records", "") == "cemetery"
        assert source._classify_record_type("1850 census", "") == "census"
        assert source._classify_record_type("birth records", "") == "vital"
        assert source._classify_record_type("military roster", "") == "military"
        assert source._classify_record_type("land grants", "") == "land"

    def test_extract_state_from_url(self):
        """State extraction from USGenWeb URLs."""
        source = USGenWebSource()
        assert source._extract_state("https://california.usgenweb.org/") == "CA"
        assert source._extract_state("https://texas.usgenweb.org/harris/") == "TX"
        assert source._extract_state("https://usgenweb.org/") == ""

    def test_requires_no_auth(self):
        """USGenWeb should not require authentication."""
        source = USGenWebSource()
        assert source.requires_auth() is False


class TestFold3Source:
    """Tests for Fold3 source."""

    def test_requires_no_auth(self):
        """Fold3 works without auth (limited)."""
        source = Fold3Source()
        assert source.requires_auth() is False

    def test_is_configured_without_credentials(self):
        """Without credentials, is_configured returns False."""
        source = Fold3Source()
        assert source.is_configured() is False

    def test_is_configured_with_api_key(self):
        """With API key, is_configured returns True."""
        source = Fold3Source(api_key="test-key")
        assert source.is_configured() is True

    def test_classify_record_type(self):
        """Record type classification for military records."""
        source = Fold3Source()
        assert source._classify_record_type("draft registration", "") == "draft"
        assert source._classify_record_type("pension file", "") == "pension"
        assert source._classify_record_type("army enlistment", "") == "military"
        assert source._classify_record_type("naturalization", "") == "naturalization"

    def test_extract_name_from_title(self):
        """Name extraction from record titles."""
        source = Fold3Source()
        assert source._extract_name("John Smith - Draft Card") == "John Smith"
        assert source._extract_name("Jane Doe | Military Record") == "Jane Doe"
        assert source._extract_name("Robert Johnson") == "Robert Johnson"


class TestRootsWebSource:
    """Tests for RootsWeb source."""

    def test_requires_no_auth(self):
        """RootsWeb should not require authentication."""
        source = RootsWebSource()
        assert source.requires_auth() is False

    def test_base_urls(self):
        """RootsWeb should have correct base URLs."""
        source = RootsWebSource()
        assert "rootsweb.com" in source.base_url
        assert "boards.rootsweb.com" in source.boards_url
        assert "lists.rootsweb.com" in source.lists_url


class TestSearchQueryLocationFields:
    """Tests for SearchQuery state/county fields."""

    def test_state_field(self):
        """SearchQuery should accept state field."""
        query = SearchQuery(surname="Smith", state="CA")
        assert query.state == "CA"

    def test_county_field(self):
        """SearchQuery should accept county field."""
        query = SearchQuery(surname="Smith", county="Los Angeles")
        assert query.county == "Los Angeles"

    def test_state_and_county(self):
        """SearchQuery should accept both state and county."""
        query = SearchQuery(
            surname="Smith",
            given_name="John",
            state="California",
            county="Los Angeles County",
        )
        assert query.state == "California"
        assert query.county == "Los Angeles County"


@pytest.mark.asyncio
async def test_accessgenealogy_search_empty_query():
    """Empty query should return no results."""
    source = AccessGenealogySource()
    query = SearchQuery()
    results = await source.search(query)
    assert results == []


@pytest.mark.asyncio
async def test_usgenweb_search_empty_query():
    """Empty query should return no results."""
    source = USGenWebSource()
    query = SearchQuery()
    results = await source.search(query)
    assert results == []


@pytest.mark.asyncio
async def test_rootsweb_search_no_surname():
    """RootsWeb requires surname, empty should return no results."""
    source = RootsWebSource()
    query = SearchQuery(given_name="John")
    results = await source.search(query)
    assert results == []


@pytest.mark.asyncio
async def test_fold3_search_empty_query():
    """Empty query should return no results."""
    source = Fold3Source()
    query = SearchQuery()
    results = await source.search(query)
    assert results == []
