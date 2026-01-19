"""Base interface for genealogy data sources."""
from __future__ import annotations

import logging
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
        """Make an HTTP request to the source API.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            JSON response as dict
        """
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

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
