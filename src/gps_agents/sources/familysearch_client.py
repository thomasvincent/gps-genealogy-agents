"""FamilySearch API Client - Clean Room Implementation.

A modern, type-safe client for the FamilySearch API built from official
API documentation. Features:

- OAuth2 authentication (authorization code and device flows)
- Async-first design with httpx
- Pydantic models for request/response validation
- Automatic token refresh
- Rate limiting and retry logic
- Caching support

Reference: https://developers.familysearch.org/

Note: This is a clean room implementation based on public API documentation,
not derived from any existing SDK code.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import webbrowser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import wraps
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Callable, TypeVar
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Configuration & Constants
# =============================================================================


class Environment(str, Enum):
    """FamilySearch API environments."""

    PRODUCTION = "https://api.familysearch.org"
    BETA = "https://apibeta.familysearch.org"
    INTEGRATION = "https://api-integ.familysearch.org"
    SANDBOX = "https://sandbox.familysearch.org"


class RecordCollection(str, Enum):
    """Common FamilySearch collection IDs."""

    # US Census
    US_CENSUS_1790 = "1803959"
    US_CENSUS_1800 = "1804228"
    US_CENSUS_1810 = "1803765"
    US_CENSUS_1820 = "1803955"
    US_CENSUS_1830 = "1803958"
    US_CENSUS_1840 = "1786457"
    US_CENSUS_1850 = "1401638"
    US_CENSUS_1860 = "1473181"
    US_CENSUS_1870 = "1438024"
    US_CENSUS_1880 = "1417683"
    US_CENSUS_1900 = "1325221"
    US_CENSUS_1910 = "1727033"
    US_CENSUS_1920 = "1488411"
    US_CENSUS_1930 = "1810731"
    US_CENSUS_1940 = "2000219"
    US_CENSUS_1950 = "4179881"

    # Vital Records
    CALIFORNIA_DEATH_INDEX = "1932433"
    CALIFORNIA_BIRTH_INDEX = "1932380"
    SSDI = "1202535"

    # African American Records
    FREEDMENS_BUREAU = "1989155"
    SLAVE_SCHEDULES_1850 = "1420440"
    SLAVE_SCHEDULES_1860 = "1473181"

    # Military
    WWI_DRAFT_CARDS = "1968530"
    WWII_DRAFT_CARDS = "2513478"

    # Immigration
    ELLIS_ISLAND = "1368704"
    CASTLE_GARDEN = "1849782"


@dataclass
class ClientConfig:
    """Configuration for FamilySearch API client."""

    client_id: str
    client_secret: str | None = None
    environment: Environment = Environment.PRODUCTION
    redirect_uri: str = "http://localhost:8765/callback"
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    token_file: Path = field(default_factory=lambda: Path("data/fs_token.json"))
    cache_dir: Path = field(default_factory=lambda: Path("data/fs_cache"))
    user_agent: str = "GPSGenealogyAgents/1.0"

    @property
    def base_url(self) -> str:
        return self.environment.value

    @property
    def auth_url(self) -> str:
        """OAuth authorization URL."""
        if self.environment == Environment.PRODUCTION:
            return "https://ident.familysearch.org/cis-web/oauth2/v3/authorization"
        return f"{self.base_url}/cis-web/oauth2/v3/authorization"

    @property
    def token_url(self) -> str:
        """OAuth token endpoint."""
        if self.environment == Environment.PRODUCTION:
            return "https://ident.familysearch.org/cis-web/oauth2/v3/token"
        return f"{self.base_url}/cis-web/oauth2/v3/token"


# =============================================================================
# Pydantic Models - Authentication
# =============================================================================


class TokenResponse(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None

    # Computed fields
    issued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_expired(self) -> bool:
        if self.expires_in is None:
            return False
        expiry = self.issued_at + timedelta(seconds=self.expires_in - 60)
        return datetime.now(UTC) > expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "issued_at": self.issued_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenResponse:
        issued_at = data.get("issued_at")
        if isinstance(issued_at, str):
            data["issued_at"] = datetime.fromisoformat(issued_at)
        return cls(**data)


# =============================================================================
# Pydantic Models - Search
# =============================================================================


class SearchParams(BaseModel):
    """Parameters for FamilySearch searches."""

    model_config = {"populate_by_name": True}

    # Name parameters
    given_name: str | None = None
    surname: str | None = None
    given_name_exact: bool = False
    surname_exact: bool = False

    # Date parameters
    birth_year: int | None = None
    birth_year_range: int = 2
    death_year: int | None = None
    death_year_range: int = 2

    # Place parameters
    birth_place: str | None = None
    death_place: str | None = None
    any_place: str | None = None

    # Relationship parameters
    father_given_name: str | None = None
    father_surname: str | None = None
    mother_given_name: str | None = None
    mother_surname: str | None = None
    spouse_given_name: str | None = None
    spouse_surname: str | None = None

    # Collection filter
    collection_id: str | None = None

    # Pagination
    count: int = 20
    start: int = 0

    def to_api_params(self) -> dict[str, str]:
        """Convert to FamilySearch API query parameters."""
        params: dict[str, str] = {}

        if self.given_name:
            params["q.givenName"] = self.given_name
            if self.given_name_exact:
                params["q.givenName.exact"] = "on"

        if self.surname:
            params["q.surname"] = self.surname
            if self.surname_exact:
                params["q.surname.exact"] = "on"

        if self.birth_year:
            params["q.birthLikeDate.from"] = str(self.birth_year - self.birth_year_range)
            params["q.birthLikeDate.to"] = str(self.birth_year + self.birth_year_range)

        if self.death_year:
            params["q.deathLikeDate.from"] = str(self.death_year - self.death_year_range)
            params["q.deathLikeDate.to"] = str(self.death_year + self.death_year_range)

        if self.birth_place:
            params["q.birthLikePlace"] = self.birth_place

        if self.death_place:
            params["q.deathLikePlace"] = self.death_place

        if self.any_place:
            params["q.anyPlace"] = self.any_place

        if self.father_given_name:
            params["q.fatherGivenName"] = self.father_given_name
        if self.father_surname:
            params["q.fatherSurname"] = self.father_surname

        if self.mother_given_name:
            params["q.motherGivenName"] = self.mother_given_name
        if self.mother_surname:
            params["q.motherSurname"] = self.mother_surname

        if self.spouse_given_name:
            params["q.spouseGivenName"] = self.spouse_given_name
        if self.spouse_surname:
            params["q.spouseSurname"] = self.spouse_surname

        if self.collection_id:
            params["f.collectionId"] = self.collection_id

        params["count"] = str(self.count)
        params["start"] = str(self.start)

        return params


class NamePart(BaseModel):
    """A part of a person's name (given, surname, etc.)."""

    type: str
    value: str

    @property
    def part_type(self) -> str:
        """Get simplified type name."""
        return self.type.split("/")[-1].lower()


class NameForm(BaseModel):
    """A form of a person's name."""

    model_config = {"populate_by_name": True}

    full_text: str | None = Field(None, alias="fullText")
    parts: list[NamePart] = []


class Name(BaseModel):
    """A person's name."""

    model_config = {"populate_by_name": True}

    name_forms: list[NameForm] = Field(default_factory=list, alias="nameForms")
    preferred: bool = False

    @property
    def full_name(self) -> str | None:
        if self.name_forms and self.name_forms[0].full_text:
            return self.name_forms[0].full_text
        return None

    @property
    def given_name(self) -> str | None:
        if not self.name_forms:
            return None
        for part in self.name_forms[0].parts:
            if part.part_type == "given":
                return part.value
        return None

    @property
    def surname(self) -> str | None:
        if not self.name_forms:
            return None
        for part in self.name_forms[0].parts:
            if part.part_type == "surname":
                return part.value
        return None


class DateInfo(BaseModel):
    """Date information."""

    original: str | None = None
    formal: str | None = None
    normalized: list[dict[str, str]] = []

    @property
    def year(self) -> int | None:
        """Extract year from date."""
        import re

        if self.formal:
            match = re.search(r"(\d{4})", self.formal)
            if match:
                return int(match.group(1))
        if self.original:
            match = re.search(r"(\d{4})", self.original)
            if match:
                return int(match.group(1))
        return None


class PlaceInfo(BaseModel):
    """Place information."""

    original: str | None = None
    normalized: list[dict[str, str]] = []


class Fact(BaseModel):
    """A fact about a person (birth, death, occupation, etc.)."""

    type: str
    date: DateInfo | None = None
    place: PlaceInfo | None = None
    value: str | None = None

    @property
    def fact_type(self) -> str:
        """Get simplified fact type."""
        return self.type.split("/")[-1].lower()


class Gender(BaseModel):
    """Gender information."""

    type: str

    @property
    def value(self) -> str:
        return self.type.split("/")[-1].lower()


class Person(BaseModel):
    """A person from FamilySearch."""

    id: str
    names: list[Name] = []
    gender: Gender | None = None
    facts: list[Fact] = []
    links: dict[str, Any] = {}

    @property
    def display_name(self) -> str:
        for name in self.names:
            if name.preferred and name.full_name:
                return name.full_name
        if self.names and self.names[0].full_name:
            return self.names[0].full_name
        return "Unknown"

    @property
    def given_name(self) -> str | None:
        for name in self.names:
            if name.given_name:
                return name.given_name
        return None

    @property
    def surname(self) -> str | None:
        for name in self.names:
            if name.surname:
                return name.surname
        return None

    @property
    def birth_date(self) -> DateInfo | None:
        for fact in self.facts:
            if fact.fact_type == "birth":
                return fact.date
        return None

    @property
    def birth_place(self) -> PlaceInfo | None:
        for fact in self.facts:
            if fact.fact_type == "birth":
                return fact.place
        return None

    @property
    def death_date(self) -> DateInfo | None:
        for fact in self.facts:
            if fact.fact_type == "death":
                return fact.date
        return None

    @property
    def death_place(self) -> PlaceInfo | None:
        for fact in self.facts:
            if fact.fact_type == "death":
                return fact.place
        return None

    def get_fact(self, fact_type: str) -> Fact | None:
        """Get a specific fact by type."""
        for fact in self.facts:
            if fact.fact_type == fact_type.lower():
                return fact
        return None


class SearchEntry(BaseModel):
    """A single search result entry."""

    id: str | None = None
    score: float | None = None
    content: dict[str, Any] = {}
    links: dict[str, Any] = {}

    @property
    def persons(self) -> list[Person]:
        """Extract persons from GEDCOM-X content."""
        gedcomx = self.content.get("gedcomx", {})
        persons_data = gedcomx.get("persons", [])
        return [Person.model_validate(p) for p in persons_data]


class SearchResponse(BaseModel):
    """Response from a FamilySearch search."""

    results: int = 0
    entries: list[SearchEntry] = []
    links: dict[str, Any] = {}

    @property
    def total_results(self) -> int:
        return self.results

    @property
    def all_persons(self) -> list[Person]:
        """Get all persons from all entries."""
        persons = []
        for entry in self.entries:
            persons.extend(entry.persons)
        return persons


# =============================================================================
# Token Storage
# =============================================================================


class TokenStorage(ABC):
    """Abstract base for token storage."""

    @abstractmethod
    def load(self) -> TokenResponse | None:
        """Load stored token."""
        ...

    @abstractmethod
    def save(self, token: TokenResponse) -> None:
        """Save token."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear stored token."""
        ...


class FileTokenStorage(TokenStorage):
    """File-based token storage."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TokenResponse | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text())
            return TokenResponse.from_dict(data)
        except Exception as e:
            logger.debug(f"Failed to load token: {e}")
            return None

    def save(self, token: TokenResponse) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(token.to_dict(), indent=2))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class EnvTokenStorage(TokenStorage):
    """Environment variable token storage (read-only)."""

    def __init__(self, env_var: str = "FAMILYSEARCH_ACCESS_TOKEN") -> None:
        self.env_var = env_var

    def load(self) -> TokenResponse | None:
        token = os.getenv(self.env_var)
        if token:
            return TokenResponse(access_token=token.strip())
        return None

    def save(self, token: TokenResponse) -> None:
        logger.warning("Cannot save to environment variable")

    def clear(self) -> None:
        logger.warning("Cannot clear environment variable")


# =============================================================================
# OAuth2 Authentication
# =============================================================================


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth callback."""

    auth_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body>
                <h1>Authorization Successful!</h1>
                <p>You can close this window and return to the application.</p>
                </body></html>
            """)
        elif "error" in params:
            OAuthCallbackHandler.error = params.get("error_description", params["error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html><body>
                <h1>Authorization Failed</h1>
                <p>Error: {OAuthCallbackHandler.error}</p>
                </body></html>
            """.encode())
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress logging


class Authenticator:
    """OAuth2 authenticator for FamilySearch."""

    def __init__(
        self,
        config: ClientConfig,
        token_storage: TokenStorage | None = None,
    ) -> None:
        self.config = config
        self.storage = token_storage or FileTokenStorage(config.token_file)
        self._token: TokenResponse | None = None
        self._http = httpx.AsyncClient(timeout=config.timeout)
        self._browser_auth = None  # Lazy load to avoid import if not needed

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def token(self) -> TokenResponse | None:
        return self._token

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None and not self._token.is_expired

    @property
    def access_token(self) -> str | None:
        return self._token.access_token if self._token else None

    async def load_token(self) -> bool:
        """Load token from storage."""
        self._token = self.storage.load()
        if self._token and self._token.is_expired:
            if self._token.refresh_token:
                try:
                    await self.refresh_token()
                    return True
                except Exception:
                    self._token = None
                    return False
            self._token = None
            return False
        return self._token is not None

    async def refresh_token(self) -> None:
        """Refresh the access token."""
        if not self._token or not self._token.refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._token.refresh_token,
            "client_id": self.config.client_id,
        }

        response = await self._http.post(
            self.config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        self._token = TokenResponse.model_validate(response.json())
        self.storage.save(self._token)

    def get_authorization_url(self, state: str | None = None) -> str:
        """Get URL for OAuth authorization."""
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
        }
        if state:
            params["state"] = state

        return f"{self.config.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> TokenResponse:
        """Exchange authorization code for tokens."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
        }

        response = await self._http.post(
            self.config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        self._token = TokenResponse.model_validate(response.json())
        self.storage.save(self._token)
        return self._token

    async def login_interactive(self) -> TokenResponse:
        """Interactive OAuth login flow.

        Opens browser for user authorization and captures callback.
        """
        # Reset handler state
        OAuthCallbackHandler.auth_code = None
        OAuthCallbackHandler.error = None

        # Parse redirect URI
        parsed = urlparse(self.config.redirect_uri)
        port = parsed.port or 8765

        # Start local server
        server = HTTPServer(("localhost", port), OAuthCallbackHandler)
        server_thread = Thread(target=server.handle_request)
        server_thread.start()

        # Open browser
        auth_url = self.get_authorization_url()
        logger.info(f"Opening browser for authorization: {auth_url}")
        webbrowser.open(auth_url)

        # Wait for callback
        server_thread.join(timeout=120)
        server.server_close()

        if OAuthCallbackHandler.error:
            raise RuntimeError(f"Authorization failed: {OAuthCallbackHandler.error}")

        if not OAuthCallbackHandler.auth_code:
            raise RuntimeError("Authorization timed out")

        return await self.exchange_code(OAuthCallbackHandler.auth_code)

    async def login_with_token(self, access_token: str) -> None:
        """Login with an existing access token."""
        self._token = TokenResponse(access_token=access_token)
        self.storage.save(self._token)

    async def login_with_browser(
        self,
        username: str | None = None,
        password: str | None = None,
        headless: bool = True,
        use_mcp: bool = False,
        mcp_tools: dict[str, Any] | None = None,
    ) -> TokenResponse:
        """Login using browser automation with username/password.

        Credentials are loaded with priority: params > env > config file

        Args:
            username: FamilySearch username (optional, loads from env/config)
            password: FamilySearch password (optional, loads from env/config)
            headless: Run browser in headless mode
            use_mcp: Use MCP browser server instead of Playwright
            mcp_tools: MCP tool functions (required if use_mcp=True)

        Returns:
            TokenResponse with access token

        Raises:
            ValueError: If credentials not found or login failed
        """
        # Lazy import to avoid dependency if not using browser auth
        from .familysearch_browser_auth import FamilySearchBrowserAuth

        if self._browser_auth is None:
            self._browser_auth = FamilySearchBrowserAuth(
                headless=headless,
                timeout=int(self.config.timeout * 1000),  # Convert to ms
            )

        # Perform login
        if use_mcp:
            access_token = await self._browser_auth.login_with_mcp(
                username, password, mcp_tools
            )
        else:
            access_token = await self._browser_auth.login_with_playwright(
                username, password
            )

        # Store token
        self._token = TokenResponse(access_token=access_token)
        self.storage.save(self._token)
        return self._token

    def logout(self) -> None:
        """Clear stored credentials."""
        self._token = None
        self.storage.clear()


# =============================================================================
# Rate Limiting & Caching
# =============================================================================


@dataclass
class RateLimiter:
    """Simple rate limiter."""

    requests_per_second: float = 5.0
    _last_request: float = 0.0

    async def acquire(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        min_interval = 1.0 / self.requests_per_second
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request = time.monotonic()


class ResponseCache:
    """Simple disk-based response cache."""

    def __init__(self, cache_dir: Path, ttl_seconds: int = 3600) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        hash_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{hash_key}.json"

    def get(self, key: str) -> dict | None:
        path = self._key_to_path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now(UTC) - cached_at > timedelta(seconds=self.ttl):
                path.unlink()
                return None
            return data["response"]
        except Exception:
            return None

    def set(self, key: str, value: dict) -> None:
        path = self._key_to_path(key)
        data = {
            "cached_at": datetime.now(UTC).isoformat(),
            "response": value,
        }
        path.write_text(json.dumps(data))

    def clear(self) -> None:
        for path in self.cache_dir.glob("*.json"):
            path.unlink()


# =============================================================================
# FamilySearch API Client
# =============================================================================


class FamilySearchAPIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class FamilySearchClient:
    """Modern FamilySearch API client.

    Example:
        config = ClientConfig(client_id="your-client-id")
        async with FamilySearchClient(config) as client:
            # Interactive login
            await client.login()

            # Search for records
            results = await client.search_persons(
                SearchParams(surname="Durham", birth_place="North Carolina")
            )
            for person in results.all_persons:
                print(f"{person.display_name} ({person.birth_date})")
    """

    def __init__(
        self,
        config: ClientConfig | None = None,
        token_storage: TokenStorage | None = None,
    ) -> None:
        """Initialize client.

        Args:
            config: Client configuration. If None, will attempt to load from environment.
            token_storage: Custom token storage. Defaults to file-based storage.
        """
        if config is None:
            client_id = os.getenv("FAMILYSEARCH_CLIENT_ID")
            if not client_id:
                raise ValueError("FAMILYSEARCH_CLIENT_ID not set and no config provided")
            config = ClientConfig(
                client_id=client_id,
                client_secret=os.getenv("FAMILYSEARCH_CLIENT_SECRET"),
            )

        self.config = config
        self.auth = Authenticator(config, token_storage)
        self.rate_limiter = RateLimiter()
        self.cache = ResponseCache(config.cache_dir)

        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FamilySearchClient:
        self._http = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "application/x-gedcomx-v1+json, application/json",
            },
        )
        await self.auth.load_token()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._http:
            await self._http.aclose()
        await self.auth.close()

    @property
    def is_authenticated(self) -> bool:
        return self.auth.is_authenticated

    async def login(
        self,
        access_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        method: str = "oauth",
    ) -> None:
        """Authenticate with FamilySearch.

        Args:
            access_token: Optional token to use directly
            username: Username for browser login (requires password)
            password: Password for browser login (requires username)
            method: Authentication method - "oauth", "browser", or "token"
                   - "oauth": Interactive OAuth flow (default)
                   - "browser": Automated browser login with username/password
                   - "token": Use provided access_token directly

        Examples:
            # OAuth flow (opens browser)
            await client.login()

            # Direct token
            await client.login(access_token="your_token")

            # Browser automation with credentials from env
            await client.login(method="browser")

            # Browser automation with explicit credentials
            await client.login(
                username="user@example.com",
                password="secret",
                method="browser"
            )
        """
        if access_token or method == "token":
            if not access_token:
                raise ValueError("access_token required when method='token'")
            await self.auth.login_with_token(access_token)
        elif method == "browser" or (username and password):
            await self.auth.login_with_browser(username=username, password=password)
        elif not self.is_authenticated:
            await self.auth.login_interactive()

    def logout(self) -> None:
        """Clear authentication."""
        self.auth.logout()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        data: dict | None = None,
        use_cache: bool = True,
    ) -> dict:
        """Make authenticated API request."""
        if not self._http:
            raise RuntimeError("Client not initialized. Use 'async with' context.")

        if not self.is_authenticated:
            raise FamilySearchAPIError("Not authenticated")

        # Check cache for GET requests
        cache_key = f"{method}:{path}:{json.dumps(params or {}, sort_keys=True)}"
        if method == "GET" and use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

        # Apply rate limiting
        await self.rate_limiter.acquire()

        url = f"{self.config.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.auth.access_token}"}

        for attempt in range(self.config.max_retries):
            try:
                response = await self._http.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=headers,
                )

                if response.status_code == 401:
                    # Token expired, try refresh
                    if self.auth.token and self.auth.token.refresh_token:
                        await self.auth.refresh_token()
                        headers["Authorization"] = f"Bearer {self.auth.access_token}"
                        continue
                    raise FamilySearchAPIError("Unauthorized", 401)

                if response.status_code == 429:
                    # Rate limited
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                result = response.json()

                # Cache successful GET responses
                if method == "GET" and use_cache:
                    self.cache.set(cache_key, result)

                return result

            except httpx.HTTPStatusError as e:
                if attempt == self.config.max_retries - 1:
                    raise FamilySearchAPIError(
                        f"API request failed: {e}",
                        e.response.status_code,
                        e.response.json() if e.response.content else None,
                    ) from e
                await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        raise FamilySearchAPIError("Max retries exceeded")

    # =========================================================================
    # Search Methods
    # =========================================================================

    async def search_persons(
        self,
        params: SearchParams,
        use_cache: bool = True,
    ) -> SearchResponse:
        """Search for persons in the FamilySearch tree.

        Args:
            params: Search parameters
            use_cache: Whether to use cached results

        Returns:
            SearchResponse with matching persons
        """
        api_params = params.to_api_params()
        data = await self._request(
            "GET",
            "/platform/tree/search",
            params=api_params,
            use_cache=use_cache,
        )
        return SearchResponse.model_validate(data)

    async def search_records(
        self,
        params: SearchParams,
        collection_id: str | None = None,
        use_cache: bool = True,
    ) -> SearchResponse:
        """Search historical records.

        Args:
            params: Search parameters
            collection_id: Optional collection to search within
            use_cache: Whether to use cached results

        Returns:
            SearchResponse with matching records
        """
        api_params = params.to_api_params()
        if collection_id:
            api_params["f.collectionId"] = collection_id

        data = await self._request(
            "GET",
            "/platform/tree/search",
            params=api_params,
            use_cache=use_cache,
        )
        return SearchResponse.model_validate(data)

    async def search_collection(
        self,
        collection: RecordCollection | str,
        params: SearchParams,
        use_cache: bool = True,
    ) -> SearchResponse:
        """Search within a specific collection.

        Args:
            collection: Collection ID or RecordCollection enum
            params: Search parameters
            use_cache: Whether to use cached results

        Returns:
            SearchResponse with matching records
        """
        collection_id = collection.value if isinstance(collection, RecordCollection) else collection
        return await self.search_records(params, collection_id, use_cache)

    # =========================================================================
    # Person Methods
    # =========================================================================

    async def get_person(self, person_id: str, use_cache: bool = True) -> Person | None:
        """Get a specific person by ID.

        Args:
            person_id: FamilySearch person ID
            use_cache: Whether to use cached results

        Returns:
            Person or None if not found
        """
        try:
            data = await self._request(
                "GET",
                f"/platform/tree/persons/{person_id}",
                use_cache=use_cache,
            )
            persons = data.get("persons", [])
            if persons:
                return Person.model_validate(persons[0])
            return None
        except FamilySearchAPIError as e:
            if e.status_code == 404:
                return None
            raise

    async def get_person_ancestors(
        self,
        person_id: str,
        generations: int = 4,
        use_cache: bool = True,
    ) -> list[Person]:
        """Get ancestors of a person.

        Args:
            person_id: FamilySearch person ID
            generations: Number of generations to retrieve (1-8)
            use_cache: Whether to use cached results

        Returns:
            List of ancestor persons
        """
        data = await self._request(
            "GET",
            f"/platform/tree/ancestry",
            params={"person": person_id, "generations": str(min(generations, 8))},
            use_cache=use_cache,
        )
        persons_data = data.get("persons", [])
        return [Person.model_validate(p) for p in persons_data]

    async def get_person_descendants(
        self,
        person_id: str,
        generations: int = 2,
        use_cache: bool = True,
    ) -> list[Person]:
        """Get descendants of a person.

        Args:
            person_id: FamilySearch person ID
            generations: Number of generations to retrieve (1-2)
            use_cache: Whether to use cached results

        Returns:
            List of descendant persons
        """
        data = await self._request(
            "GET",
            f"/platform/tree/descendancy",
            params={"person": person_id, "generations": str(min(generations, 2))},
            use_cache=use_cache,
        )
        persons_data = data.get("persons", [])
        return [Person.model_validate(p) for p in persons_data]

    # =========================================================================
    # Collection Methods
    # =========================================================================

    async def list_collections(self, use_cache: bool = True) -> dict:
        """List available record collections.

        Returns:
            Collection metadata
        """
        return await self._request(
            "GET",
            "/platform/collections",
            use_cache=use_cache,
        )

    async def get_collection(self, collection_id: str, use_cache: bool = True) -> dict:
        """Get information about a specific collection.

        Args:
            collection_id: Collection ID

        Returns:
            Collection metadata
        """
        return await self._request(
            "GET",
            f"/platform/collections/{collection_id}",
            use_cache=use_cache,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


async def quick_search(
    surname: str,
    given_name: str | None = None,
    birth_year: int | None = None,
    birth_place: str | None = None,
    access_token: str | None = None,
) -> list[Person]:
    """Quick search without full client setup.

    Args:
        surname: Last name to search
        given_name: Optional first name
        birth_year: Optional birth year
        birth_place: Optional birth place
        access_token: Optional access token (uses env var if not provided)

    Returns:
        List of matching persons
    """
    token = access_token or os.getenv("FAMILYSEARCH_ACCESS_TOKEN")
    if not token:
        raise ValueError("No access token provided")

    client_id = os.getenv("FAMILYSEARCH_CLIENT_ID", "default")
    config = ClientConfig(client_id=client_id)

    async with FamilySearchClient(config, EnvTokenStorage()) as client:
        await client.login(token)
        params = SearchParams(
            surname=surname,
            given_name=given_name,
            birth_year=birth_year,
            birth_place=birth_place,
        )
        results = await client.search_persons(params)
        return results.all_persons
