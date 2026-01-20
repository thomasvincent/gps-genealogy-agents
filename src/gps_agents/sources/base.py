"""Base interface for genealogy data sources."""
from __future__ import annotations

import asyncio
import logging
import os
import random
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models.search import RawRecord, SearchQuery


@runtime_checkable
class GenealogySource(Protocol):
    """Protocol defining the interface all data sources must implement."""

    name: str

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search for records matching the query.

        Args:
            query: Search parameters

        Returns:
            List of raw records found
        """
        ...

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific record by ID.

        Args:
            record_id: The record's unique identifier

        Returns:
            The record or None if not found
        """
        ...

    def requires_auth(self) -> bool:
        """Check if this source requires authentication.

        Returns:
            True if authentication is needed
        """
        ...


class BaseSource(ABC):
    """Abstract base class for genealogy data sources."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the source.

        Args:
            api_key: Optional API key for authenticated sources
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search for records matching the query."""

    @abstractmethod
    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific record by ID."""

    @abstractmethod
    def requires_auth(self) -> bool:
        """Check if this source requires authentication."""

    def is_configured(self) -> bool:
        """Check if this source is properly configured."""
        if self.requires_auth():
            return self.api_key is not None
        return True

    def _build_name_variants(self, surname: str) -> list[str]:
        """Build common surname variants for searching.

        Args:
            surname: The base surname

        Returns:
            List of variant spellings
        """
        variants = [surname]

        # Common substitutions
        substitutions = [
            ("son", "sen"),  # Johnson/Johnsen
            ("ck", "k"),  # Black/Blak
            ("k", "ck"),
            ("Mac", "Mc"),  # MacDonald/McDonald
            ("Mc", "Mac"),
            ("O'", "O"),  # O'Brien/OBrien
        ]

        for old, new in substitutions:
            if old in surname:
                variants.append(surname.replace(old, new))

        return list(set(variants))

    async def _make_request(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a polite HTTP request to the source API with rate limiting and circuit breaking."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        # Resolve per-source guard configs (env overrides or safe defaults)
        from gps_agents.net import GUARDS, RateLimitConfig

        key = getattr(self, "name", "source").lower()
        # Defaults: 1 req / 1.5s; window 5s
        rl_default = RateLimitConfig(
            max_calls=int(os.getenv(f"RATE_{key.upper()}_MAX", os.getenv("RATE_DEFAULT_MAX", "1"))),
            window_seconds=float(os.getenv(f"RATE_{key.upper()}_WINDOW", os.getenv("RATE_DEFAULT_WINDOW", "5"))),
            min_interval=float(os.getenv(f"RATE_{key.upper()}_MIN_INTERVAL", os.getenv("RATE_DEFAULT_MIN_INTERVAL", "1.5"))),
        )
        limiter = GUARDS.get_limiter(key, rl_default)
        breaker = GUARDS.get_breaker(
            key,
            max_failures=int(os.getenv(f"CB_{key.upper()}_THRESHOLD", os.getenv("CB_DEFAULT_THRESHOLD", "5"))),
            window_seconds=float(os.getenv(f"CB_{key.upper()}_WINDOW", os.getenv("CB_DEFAULT_WINDOW", "60"))),
            cooldown_seconds=float(os.getenv(f"CB_{key.upper()}_COOLDOWN", os.getenv("CB_DEFAULT_COOLDOWN", "300"))),
        )

        if not breaker.allow_call():
            raise httpx.HTTPError(f"circuit_open:{key}")

        await limiter.acquire()

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4.0),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError)),
        )
        async def _do() -> dict[str, Any]:
            # Small jitter to avoid herding
            await asyncio.sleep(random.uniform(0.05, 0.2))
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

        try:
            result = await _do()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise

    async def close(self) -> None:
        """Close HTTP client connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> BaseSource:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Async context manager exit - ensures connection cleanup."""
        await self.close()
        return False
