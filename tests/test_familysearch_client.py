"""Tests for FamilySearch API client."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gps_agents.sources.familysearch_client import (
    Authenticator,
    ClientConfig,
    DateInfo,
    Environment,
    Fact,
    FamilySearchClient,
    FileTokenStorage,
    Gender,
    Name,
    NameForm,
    NamePart,
    Person,
    PlaceInfo,
    RateLimiter,
    RecordCollection,
    ResponseCache,
    SearchEntry,
    SearchParams,
    SearchResponse,
    TokenResponse,
)
from gps_agents.sources.familysearch_browser_auth import (
    BrowserCredentials,
    FamilySearchBrowserAuth,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestTokenResponse:
    """Tests for TokenResponse model."""

    def test_create_token(self):
        """Test basic token creation."""
        token = TokenResponse(
            access_token="test_token",
            token_type="Bearer",
            expires_in=3600,
        )
        assert token.access_token == "test_token"
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert not token.is_expired

    def test_expired_token(self):
        """Test token expiration detection."""
        # Create token that was issued 2 hours ago with 1 hour expiry
        token = TokenResponse(
            access_token="test_token",
            expires_in=3600,
            issued_at=datetime.now(UTC) - timedelta(hours=2),
        )
        assert token.is_expired

    def test_token_not_expired(self):
        """Test token that is still valid."""
        token = TokenResponse(
            access_token="test_token",
            expires_in=3600,
            issued_at=datetime.now(UTC),
        )
        assert not token.is_expired

    def test_token_without_expiry(self):
        """Test token without expiry is never expired."""
        token = TokenResponse(
            access_token="test_token",
            expires_in=None,
        )
        assert not token.is_expired

    def test_token_serialization(self):
        """Test token to_dict and from_dict."""
        original = TokenResponse(
            access_token="test_token",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="refresh_token",
        )
        data = original.to_dict()
        restored = TokenResponse.from_dict(data)

        assert restored.access_token == original.access_token
        assert restored.token_type == original.token_type
        assert restored.expires_in == original.expires_in
        assert restored.refresh_token == original.refresh_token


class TestSearchParams:
    """Tests for SearchParams model."""

    def test_basic_search_params(self):
        """Test basic search parameter conversion."""
        params = SearchParams(surname="Durham", given_name="Archer")
        api_params = params.to_api_params()

        assert api_params["q.surname"] == "Durham"
        assert api_params["q.givenName"] == "Archer"
        assert "q.surname.exact" not in api_params

    def test_exact_matching(self):
        """Test exact matching flags."""
        params = SearchParams(
            surname="Durham",
            surname_exact=True,
            given_name="Archer",
            given_name_exact=True,
        )
        api_params = params.to_api_params()

        assert api_params["q.surname.exact"] == "on"
        assert api_params["q.givenName.exact"] == "on"

    def test_date_range_params(self):
        """Test birth/death year range calculation."""
        params = SearchParams(
            surname="Durham",
            birth_year=1900,
            birth_year_range=5,
            death_year=1980,
            death_year_range=3,
        )
        api_params = params.to_api_params()

        assert api_params["q.birthLikeDate.from"] == "1895"
        assert api_params["q.birthLikeDate.to"] == "1905"
        assert api_params["q.deathLikeDate.from"] == "1977"
        assert api_params["q.deathLikeDate.to"] == "1983"

    def test_place_params(self):
        """Test place parameters."""
        params = SearchParams(
            surname="Durham",
            birth_place="North Carolina",
            death_place="California",
            any_place="United States",
        )
        api_params = params.to_api_params()

        assert api_params["q.birthLikePlace"] == "North Carolina"
        assert api_params["q.deathLikePlace"] == "California"
        assert api_params["q.anyPlace"] == "United States"

    def test_relative_params(self):
        """Test relative (family) parameters."""
        params = SearchParams(
            surname="Durham",
            father_given_name="Barney",
            father_surname="Durham",
            mother_given_name="Ruby",
            mother_surname="Smith",
            spouse_given_name="Colleen",
        )
        api_params = params.to_api_params()

        assert api_params["q.fatherGivenName"] == "Barney"
        assert api_params["q.fatherSurname"] == "Durham"
        assert api_params["q.motherGivenName"] == "Ruby"
        assert api_params["q.motherSurname"] == "Smith"
        assert api_params["q.spouseGivenName"] == "Colleen"

    def test_collection_filter(self):
        """Test collection ID filter."""
        params = SearchParams(
            surname="Durham",
            collection_id="1325221",
        )
        api_params = params.to_api_params()

        assert api_params["f.collectionId"] == "1325221"

    def test_pagination(self):
        """Test pagination parameters."""
        params = SearchParams(surname="Durham", count=50, start=100)
        api_params = params.to_api_params()

        assert api_params["count"] == "50"
        assert api_params["start"] == "100"


class TestPerson:
    """Tests for Person model."""

    def test_person_display_name(self):
        """Test person display name extraction."""
        person = Person(
            id="ABCD-123",
            names=[
                Name(
                    name_forms=[
                        NameForm(
                            full_text="Archer Durham",
                            parts=[
                                NamePart(type="http://gedcomx.org/Given", value="Archer"),
                                NamePart(type="http://gedcomx.org/Surname", value="Durham"),
                            ],
                        )
                    ],
                    preferred=True,
                )
            ],
        )
        assert person.display_name == "Archer Durham"
        assert person.given_name == "Archer"
        assert person.surname == "Durham"

    def test_person_facts(self):
        """Test person fact extraction."""
        person = Person(
            id="ABCD-123",
            facts=[
                Fact(
                    type="http://gedcomx.org/Birth",
                    date=DateInfo(original="15 Mar 1900", formal="+1900-03-15"),
                    place=PlaceInfo(original="Raleigh, North Carolina"),
                ),
                Fact(
                    type="http://gedcomx.org/Death",
                    date=DateInfo(original="22 Dec 1980", formal="+1980-12-22"),
                    place=PlaceInfo(original="Pasadena, California"),
                ),
            ],
        )

        assert person.birth_date is not None
        assert person.birth_date.original == "15 Mar 1900"
        assert person.birth_date.year == 1900

        assert person.death_date is not None
        assert person.death_date.original == "22 Dec 1980"
        assert person.death_date.year == 1980

        assert person.birth_place is not None
        assert person.birth_place.original == "Raleigh, North Carolina"

    def test_person_gender(self):
        """Test person gender extraction."""
        person = Person(
            id="ABCD-123",
            gender=Gender(type="http://gedcomx.org/Male"),
        )
        assert person.gender is not None
        assert person.gender.value == "male"

    def test_get_fact(self):
        """Test getting specific facts."""
        person = Person(
            id="ABCD-123",
            facts=[
                Fact(
                    type="http://gedcomx.org/Occupation",
                    value="Farmer",
                ),
                Fact(
                    type="http://gedcomx.org/Residence",
                    place=PlaceInfo(original="Pasadena, CA"),
                ),
            ],
        )

        occupation = person.get_fact("occupation")
        assert occupation is not None
        assert occupation.value == "Farmer"

        residence = person.get_fact("Residence")
        assert residence is not None
        assert residence.place.original == "Pasadena, CA"


class TestSearchResponse:
    """Tests for SearchResponse model."""

    def test_search_response(self):
        """Test search response parsing."""
        response = SearchResponse(
            results=100,
            entries=[
                SearchEntry(
                    id="entry1",
                    score=0.95,
                    content={
                        "gedcomx": {
                            "persons": [
                                {
                                    "id": "PERSON-1",
                                    "names": [
                                        {
                                            "nameForms": [{"fullText": "Archer Durham"}],
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                )
            ],
        )

        assert response.total_results == 100
        assert len(response.entries) == 1
        persons = response.all_persons
        assert len(persons) == 1
        assert persons[0].display_name == "Archer Durham"


class TestDateInfo:
    """Tests for DateInfo model."""

    def test_year_extraction_formal(self):
        """Test year extraction from formal date."""
        date = DateInfo(formal="+1900-03-15")
        assert date.year == 1900

    def test_year_extraction_original(self):
        """Test year extraction from original date."""
        date = DateInfo(original="about 1905")
        assert date.year == 1905

    def test_year_extraction_none(self):
        """Test year extraction when no year present."""
        date = DateInfo(original="unknown")
        assert date.year is None


# =============================================================================
# Storage Tests
# =============================================================================


class TestFileTokenStorage:
    """Tests for FileTokenStorage."""

    def test_save_and_load(self, tmp_path: Path):
        """Test saving and loading tokens."""
        storage = FileTokenStorage(tmp_path / "token.json")
        token = TokenResponse(
            access_token="test_token",
            refresh_token="refresh_token",
            expires_in=3600,
        )

        storage.save(token)
        loaded = storage.load()

        assert loaded is not None
        assert loaded.access_token == "test_token"
        assert loaded.refresh_token == "refresh_token"

    def test_load_nonexistent(self, tmp_path: Path):
        """Test loading from nonexistent file."""
        storage = FileTokenStorage(tmp_path / "nonexistent.json")
        assert storage.load() is None

    def test_clear(self, tmp_path: Path):
        """Test clearing stored token."""
        path = tmp_path / "token.json"
        storage = FileTokenStorage(path)
        token = TokenResponse(access_token="test_token")

        storage.save(token)
        assert path.exists()

        storage.clear()
        assert not path.exists()


# =============================================================================
# Rate Limiter Tests
# =============================================================================


class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiter enforces delays."""
        limiter = RateLimiter(requests_per_second=10.0)

        start = datetime.now()
        for _ in range(3):
            await limiter.acquire()
        elapsed = (datetime.now() - start).total_seconds()

        # Should take at least 0.2 seconds for 3 requests at 10/sec
        assert elapsed >= 0.1


# =============================================================================
# Response Cache Tests
# =============================================================================


class TestResponseCache:
    """Tests for ResponseCache."""

    def test_cache_set_get(self, tmp_path: Path):
        """Test caching responses."""
        cache = ResponseCache(tmp_path, ttl_seconds=3600)
        cache.set("test_key", {"data": "value"})

        result = cache.get("test_key")
        assert result == {"data": "value"}

    def test_cache_miss(self, tmp_path: Path):
        """Test cache miss."""
        cache = ResponseCache(tmp_path, ttl_seconds=3600)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self, tmp_path: Path):
        """Test cache TTL expiry."""
        cache = ResponseCache(tmp_path, ttl_seconds=0)  # Immediate expiry
        cache.set("test_key", {"data": "value"})

        # Should be expired
        assert cache.get("test_key") is None

    def test_cache_clear(self, tmp_path: Path):
        """Test clearing cache."""
        cache = ResponseCache(tmp_path, ttl_seconds=3600)
        cache.set("key1", {"data": "1"})
        cache.set("key2", {"data": "2"})

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None


# =============================================================================
# Configuration Tests
# =============================================================================


class TestClientConfig:
    """Tests for ClientConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ClientConfig(client_id="test_client")

        assert config.client_id == "test_client"
        assert config.environment == Environment.PRODUCTION
        assert config.timeout == 30.0
        assert config.max_retries == 3

    def test_environment_urls(self):
        """Test environment-specific URLs."""
        prod_config = ClientConfig(
            client_id="test",
            environment=Environment.PRODUCTION,
        )
        assert "api.familysearch.org" in prod_config.base_url

        sandbox_config = ClientConfig(
            client_id="test",
            environment=Environment.SANDBOX,
        )
        assert "sandbox.familysearch.org" in sandbox_config.base_url


class TestRecordCollection:
    """Tests for RecordCollection enum."""

    def test_census_collections(self):
        """Test US Census collection IDs."""
        assert RecordCollection.US_CENSUS_1900.value == "1325221"
        assert RecordCollection.US_CENSUS_1940.value == "2000219"
        assert RecordCollection.US_CENSUS_1950.value == "4179881"

    def test_vital_records_collections(self):
        """Test vital records collection IDs."""
        assert RecordCollection.CALIFORNIA_DEATH_INDEX.value == "1932433"
        assert RecordCollection.SSDI.value == "1202535"

    def test_african_american_collections(self):
        """Test African American research collection IDs."""
        assert RecordCollection.FREEDMENS_BUREAU.value == "1989155"


# =============================================================================
# Client Integration Tests (Mocked)
# =============================================================================


class TestFamilySearchClient:
    """Tests for FamilySearchClient with mocked HTTP."""

    @pytest.fixture
    def config(self, tmp_path: Path):
        """Create test configuration."""
        return ClientConfig(
            client_id="test_client",
            client_secret="test_secret",
            token_file=tmp_path / "token.json",
            cache_dir=tmp_path / "cache",
        )

    @pytest.fixture
    def mock_token(self, tmp_path: Path):
        """Create mock token file."""
        token_path = tmp_path / "token.json"
        token_data = {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "issued_at": datetime.now(UTC).isoformat(),
        }
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(token_data))
        return token_path

    @pytest.mark.asyncio
    async def test_client_initialization(self, config: ClientConfig):
        """Test client initialization."""
        async with FamilySearchClient(config) as client:
            assert client.config == config
            assert not client.is_authenticated

    @pytest.mark.asyncio
    async def test_client_with_token(self, config: ClientConfig, mock_token: Path):
        """Test client with pre-existing token."""
        config.token_file = mock_token
        async with FamilySearchClient(config) as client:
            assert client.is_authenticated

    @pytest.mark.asyncio
    async def test_search_persons_mock(self, config: ClientConfig, mock_token: Path):
        """Test person search with mocked response."""
        config.token_file = mock_token

        mock_response = {
            "results": 1,
            "entries": [
                {
                    "id": "entry1",
                    "content": {
                        "gedcomx": {
                            "persons": [
                                {
                                    "id": "PERSON-1",
                                    "names": [
                                        {
                                            "nameForms": [
                                                {
                                                    "fullText": "Archer Durham",
                                                    "parts": [
                                                        {"type": "http://gedcomx.org/Given", "value": "Archer"},
                                                        {"type": "http://gedcomx.org/Surname", "value": "Durham"},
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                    "facts": [
                                        {
                                            "type": "http://gedcomx.org/Birth",
                                            "date": {"original": "1900"},
                                            "place": {"original": "North Carolina"},
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                }
            ],
        }

        async with FamilySearchClient(config) as client:
            with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response

                params = SearchParams(surname="Durham", given_name="Archer")
                response = await client.search_persons(params)

                assert response.total_results == 1
                persons = response.all_persons
                assert len(persons) == 1
                assert persons[0].display_name == "Archer Durham"
                assert persons[0].given_name == "Archer"
                assert persons[0].surname == "Durham"

    @pytest.mark.asyncio
    async def test_get_person_mock(self, config: ClientConfig, mock_token: Path):
        """Test getting a specific person."""
        config.token_file = mock_token

        mock_response = {
            "persons": [
                {
                    "id": "PERSON-1",
                    "names": [{"nameForms": [{"fullText": "Archer Durham"}]}],
                    "gender": {"type": "http://gedcomx.org/Male"},
                }
            ]
        }

        async with FamilySearchClient(config) as client:
            with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response

                person = await client.get_person("PERSON-1")

                assert person is not None
                assert person.id == "PERSON-1"
                assert person.display_name == "Archer Durham"
                assert person.gender.value == "male"

    @pytest.mark.asyncio
    async def test_search_collection_mock(self, config: ClientConfig, mock_token: Path):
        """Test searching within a specific collection."""
        config.token_file = mock_token

        mock_response = {"results": 0, "entries": []}

        async with FamilySearchClient(config) as client:
            with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
                mock_req.return_value = mock_response

                params = SearchParams(surname="Durham")
                response = await client.search_collection(
                    RecordCollection.US_CENSUS_1900,
                    params,
                )

                # Verify collection ID was passed
                mock_req.assert_called_once()
                call_args = mock_req.call_args
                assert call_args[1]["params"]["f.collectionId"] == "1325221"


# =============================================================================
# Authenticator Tests
# =============================================================================


class TestAuthenticator:
    """Tests for Authenticator."""

    @pytest.fixture
    def config(self, tmp_path: Path):
        return ClientConfig(
            client_id="test_client",
            client_secret="test_secret",
            token_file=tmp_path / "token.json",
        )

    def test_authorization_url(self, config: ClientConfig):
        """Test authorization URL generation."""
        auth = Authenticator(config)
        url = auth.get_authorization_url(state="test_state")

        assert "response_type=code" in url
        assert f"client_id={config.client_id}" in url
        assert "state=test_state" in url

    @pytest.mark.asyncio
    async def test_load_token(self, config: ClientConfig, tmp_path: Path):
        """Test loading existing token."""
        # Create token file
        token_data = {
            "access_token": "existing_token",
            "expires_in": 3600,
            "issued_at": datetime.now(UTC).isoformat(),
        }
        config.token_file.write_text(json.dumps(token_data))

        auth = Authenticator(config)
        result = await auth.load_token()

        assert result is True
        assert auth.is_authenticated
        assert auth.access_token == "existing_token"

        await auth.close()

    @pytest.mark.asyncio
    async def test_logout(self, config: ClientConfig, tmp_path: Path):
        """Test logout clears credentials."""
        # Create token file
        token_data = {
            "access_token": "existing_token",
            "expires_in": 3600,
            "issued_at": datetime.now(UTC).isoformat(),
        }
        config.token_file.write_text(json.dumps(token_data))

        auth = Authenticator(config)
        await auth.load_token()
        assert auth.is_authenticated

        auth.logout()
        assert not auth.is_authenticated
        assert not config.token_file.exists()

        await auth.close()


# =============================================================================
# Browser Authentication Tests
# =============================================================================


class TestBrowserCredentials:
    """Tests for BrowserCredentials."""

    def test_from_params(self):
        """Test loading from parameters (highest priority)."""
        creds = BrowserCredentials.from_sources(
            username="param_user", password="param_pass"
        )
        assert creds is not None
        assert creds.username == "param_user"
        assert creds.password == "param_pass"

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "env_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "env_pass")

        creds = BrowserCredentials.from_sources()
        assert creds is not None
        assert creds.username == "env_user"
        assert creds.password == "env_pass"

    def test_from_config_file(self, tmp_path: Path):
        """Test loading from config file."""
        config_file = tmp_path / "creds.json"
        config_file.write_text(
            json.dumps(
                {"familysearch_username": "file_user", "familysearch_password": "file_pass"}
            )
        )

        creds = BrowserCredentials.from_sources(config_file=config_file)
        assert creds is not None
        assert creds.username == "file_user"
        assert creds.password == "file_pass"

    def test_priority_params_over_env(self, monkeypatch):
        """Test that params take priority over env."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "env_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "env_pass")

        creds = BrowserCredentials.from_sources(
            username="param_user", password="param_pass"
        )
        assert creds.username == "param_user"
        assert creds.password == "param_pass"

    def test_priority_env_over_config(self, monkeypatch, tmp_path: Path):
        """Test that env takes priority over config file."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "env_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "env_pass")

        config_file = tmp_path / "creds.json"
        config_file.write_text(
            json.dumps(
                {"familysearch_username": "file_user", "familysearch_password": "file_pass"}
            )
        )

        creds = BrowserCredentials.from_sources(config_file=config_file)
        assert creds.username == "env_user"
        assert creds.password == "env_pass"

    def test_no_credentials_found(self):
        """Test when no credentials are available."""
        creds = BrowserCredentials.from_sources()
        assert creds is None


class TestFamilySearchBrowserAuth:
    """Tests for FamilySearchBrowserAuth."""

    @pytest.mark.asyncio
    async def test_playwright_login_mock(self, monkeypatch):
        """Test Playwright login with mocked browser."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "test_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "test_pass")

        auth = FamilySearchBrowserAuth(headless=True)

        # Mock the Playwright calls
        with patch(
            "gps_agents.sources.familysearch_browser_auth.async_playwright"
        ) as mock_playwright:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()

            mock_context.new_page.return_value = mock_page
            mock_browser.new_context.return_value = mock_context
            mock_playwright.return_value.__aenter__.return_value.chromium.launch.return_value = (
                mock_browser
            )

            # Mock page interactions
            mock_page.goto = AsyncMock()
            mock_page.fill = AsyncMock()
            mock_page.click = AsyncMock()
            mock_page.wait_for_load_state = AsyncMock()
            mock_page.query_selector = AsyncMock(return_value=None)
            mock_page.evaluate = AsyncMock(return_value="test_access_token_12345")

            token = await auth.login_with_playwright()

            assert token == "test_access_token_12345"
            assert mock_page.fill.call_count == 2  # username and password
            assert mock_page.click.call_count == 1  # login button

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self):
        """Test login fails without credentials."""
        auth = FamilySearchBrowserAuth()

        with pytest.raises(ValueError, match="No FamilySearch credentials found"):
            await auth.login_with_playwright()

    @pytest.mark.asyncio
    async def test_mcp_login_mock(self):
        """Test MCP browser login."""
        auth = FamilySearchBrowserAuth()

        mock_tools = {
            "browser_navigate": AsyncMock(),
            "browser_type": AsyncMock(),
            "browser_click": AsyncMock(),
            "browser_evaluate": AsyncMock(return_value="mcp_token_12345"),
        }

        token = await auth.login_with_mcp(
            username="test_user", password="test_pass", mcp_tools=mock_tools
        )

        assert token == "mcp_token_12345"
        assert mock_tools["browser_navigate"].call_count == 2  # login + tree
        assert mock_tools["browser_type"].call_count == 2  # username + password
        assert mock_tools["browser_click"].call_count == 1  # login button


class TestAuthenticatorBrowserLogin:
    """Tests for Authenticator browser login integration."""

    @pytest.fixture
    def config(self, tmp_path: Path):
        return ClientConfig(
            client_id="test_client",
            token_file=tmp_path / "token.json",
        )

    @pytest.mark.asyncio
    async def test_authenticator_browser_login(
        self, config: ClientConfig, monkeypatch
    ):
        """Test Authenticator.login_with_browser."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "test_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "test_pass")

        auth = Authenticator(config)

        # Mock the browser auth module (lazy import)
        with patch(
            "gps_agents.sources.familysearch_browser_auth.FamilySearchBrowserAuth"
        ) as MockBrowserAuth:
            mock_instance = MockBrowserAuth.return_value
            mock_instance.login_with_playwright = AsyncMock(
                return_value="browser_token_123"
            )

            token_response = await auth.login_with_browser()

            assert token_response.access_token == "browser_token_123"
            assert auth.is_authenticated
            mock_instance.login_with_playwright.assert_called_once()

        await auth.close()


class TestFamilySearchClientBrowserLogin:
    """Tests for FamilySearchClient browser login integration."""

    @pytest.fixture
    def config(self, tmp_path: Path):
        return ClientConfig(
            client_id="test_client",
            token_file=tmp_path / "token.json",
        )

    @pytest.mark.asyncio
    async def test_client_login_browser_method(
        self, config: ClientConfig, monkeypatch
    ):
        """Test client.login with method='browser'."""
        monkeypatch.setenv("FAMILYSEARCH_USERNAME", "test_user")
        monkeypatch.setenv("FAMILYSEARCH_PASSWORD", "test_pass")

        async with FamilySearchClient(config) as client:
            with patch.object(
                client.auth, "login_with_browser", new_callable=AsyncMock
            ) as mock_browser:
                mock_browser.return_value = TokenResponse(access_token="test_token")

                await client.login(method="browser")

                mock_browser.assert_called_once()

    @pytest.mark.asyncio
    async def test_client_login_with_credentials(self, config: ClientConfig):
        """Test client.login with explicit credentials."""
        async with FamilySearchClient(config) as client:
            with patch.object(
                client.auth, "login_with_browser", new_callable=AsyncMock
            ) as mock_browser:
                mock_browser.return_value = TokenResponse(access_token="test_token")

                await client.login(username="user@example.com", password="secret123")

                mock_browser.assert_called_once_with(
                    username="user@example.com", password="secret123"
                )

    @pytest.mark.asyncio
    async def test_client_login_token_method(self, config: ClientConfig):
        """Test client.login with method='token'."""
        async with FamilySearchClient(config) as client:
            await client.login(access_token="direct_token", method="token")

            assert client.is_authenticated
            assert client.auth.access_token == "direct_token"
