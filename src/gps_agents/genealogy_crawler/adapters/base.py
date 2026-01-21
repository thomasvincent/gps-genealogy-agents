"""Base classes for the Source Adapter Framework.

Implements the micro-kernel adapter pattern where the core handles
state and provenance while adapters handle source-specific crawling.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import httpx
import yaml
from pydantic import BaseModel, Field

from ..models_v2 import (
    EvidenceClass,
    EvidenceClaim,
    FuzzyDate,
    GeoCodedPlace,
    SourceDescription,
    SourceTier,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Models
# =============================================================================


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    requests_per_second: float = 0.2  # 1 request per 5 seconds default
    burst: int = 3
    retry_after_429: int = 60  # seconds


class ComplianceConfig(BaseModel):
    """Compliance settings for a source adapter."""
    robots_txt: bool = True
    respect_nofollow: bool = True
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    user_agent: str = "GenealogyResearchBot/2.0 (+https://example.com/bot)"
    cache_ttl_seconds: int = 86400  # 24 hours
    tos_url: str | None = None
    tos_accepted: bool = False


class ExtractionRule(BaseModel):
    """Rule for extracting a field from content."""
    selector: str | None = None  # CSS selector
    xpath: str | None = None
    regex: str | None = None
    parser: Literal["text", "fuzzy_date", "geocode", "number"] = "text"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    required: bool = False


class ExtractionConfig(BaseModel):
    """Extraction configuration for an entity type."""
    rules: dict[str, ExtractionRule] = Field(default_factory=dict)


class SearchEndpointConfig(BaseModel):
    """Search endpoint configuration."""
    endpoint: str
    method: Literal["GET", "POST"] = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)


class PaginationConfig(BaseModel):
    """Pagination configuration."""
    type: Literal["page_number", "offset", "cursor"] = "page_number"
    param: str = "page"
    max_pages: int = 5
    results_per_page: int = 20


class AdapterConfig(BaseModel):
    """Complete configuration for a source adapter."""
    adapter_id: str
    display_name: str
    tier: int = Field(ge=0, le=2)
    domain: str
    base_url: str

    # Evidence classification
    evidence_class: str = "secondary_published"
    prior_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    # Compliance
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)

    # Extraction rules by entity type
    extraction: dict[str, ExtractionConfig] = Field(default_factory=dict)

    # Search configuration
    search: SearchEndpointConfig | None = None
    pagination: PaginationConfig | None = None

    @property
    def source_tier(self) -> SourceTier:
        """Get source tier as enum."""
        return SourceTier(self.tier)

    @property
    def evidence_class_enum(self) -> EvidenceClass:
        """Get evidence class as enum."""
        return EvidenceClass(self.evidence_class)


# =============================================================================
# Data Transfer Objects
# =============================================================================


@dataclass
class SearchQuery:
    """A search query to execute."""
    query_string: str
    given_name: str | None = None
    surname: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    location: str | None = None
    additional_params: dict[str, Any] = field(default_factory=dict)

    def format_param(self, template: str) -> str:
        """Format a parameter template with query values."""
        result = template
        if self.given_name:
            result = result.replace("{given_name}", self.given_name)
        if self.surname:
            result = result.replace("{surname}", self.surname)
        if self.birth_year:
            result = result.replace("{birth_year}", str(self.birth_year))
        if self.death_year:
            result = result.replace("{death_year}", str(self.death_year))
        if self.location:
            result = result.replace("{location}", self.location)
        result = result.replace("{query}", self.query_string)
        return result


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    snippet: str | None = None
    relevance_score: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    """Result of fetching a resource."""
    url: str
    content: str
    content_type: str = "text/html"
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    from_cache: bool = False

    @property
    def content_hash(self) -> str:
        """Compute content hash for deduplication."""
        return hashlib.sha256(self.content.encode()).hexdigest()


# =============================================================================
# Rate Limiter
# =============================================================================


class RateLimiter:
    """Token bucket rate limiter for compliant crawling."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.burst
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate limit token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            # Add tokens based on elapsed time
            self.tokens = min(
                self.config.burst,
                self.tokens + elapsed * self.config.requests_per_second,
            )

            if self.tokens < 1:
                # Wait for a token
                wait_time = (1 - self.tokens) / self.config.requests_per_second
                logger.debug(f"Rate limited, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self.tokens = 1

            self.tokens -= 1


# =============================================================================
# Abstract Source Adapter
# =============================================================================


class SourceAdapter(ABC):
    """Abstract base class for source adapters.

    Implements the plugin interface for the micro-kernel architecture.
    Each adapter handles source-specific crawling, extraction, and compliance.
    """

    def __init__(self, config: AdapterConfig):
        self.config = config
        self._rate_limiter = RateLimiter(config.compliance.rate_limit)
        self._client: httpx.AsyncClient | None = None
        self._robots_rules: dict[str, bool] = {}
        self._cache: dict[str, FetchResult] = {}

    @property
    def adapter_id(self) -> str:
        """Unique identifier for this adapter."""
        return self.config.adapter_id

    @property
    def tier(self) -> SourceTier:
        """Source tier for this adapter."""
        return self.config.source_tier

    @property
    def domain(self) -> str:
        """Primary domain for this adapter."""
        return self.config.domain

    @property
    def evidence_class(self) -> EvidenceClass:
        """Evidence classification for Bayesian weighting."""
        return self.config.evidence_class_enum

    @property
    def prior_weight(self) -> float:
        """Bayesian prior weight for this source."""
        return self.config.prior_weight

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.config.compliance.user_agent},
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _check_robots(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        if not self.config.compliance.robots_txt:
            return True

        # Parse URL to get path
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or "/"

        # Check cache
        if path in self._robots_rules:
            return self._robots_rules[path]

        # Fetch robots.txt if not cached
        try:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            client = await self._get_client()
            response = await client.get(robots_url)

            if response.status_code == 200:
                # Simple robots.txt parsing (production should use robotparser)
                disallowed = []
                for line in response.text.split("\n"):
                    line = line.strip().lower()
                    if line.startswith("disallow:"):
                        disallowed.append(line.split(":", 1)[1].strip())

                # Check if path is disallowed
                allowed = True
                for rule in disallowed:
                    if path.startswith(rule):
                        allowed = False
                        break

                self._robots_rules[path] = allowed
                return allowed

        except Exception as e:
            logger.warning(f"Failed to fetch robots.txt: {e}")

        return True  # Allow if can't fetch robots.txt

    async def _fetch_with_compliance(self, url: str) -> FetchResult:
        """Fetch a URL with compliance checks."""
        # Check robots.txt
        if not await self._check_robots(url):
            raise PermissionError(f"URL disallowed by robots.txt: {url}")

        # Check cache
        cache_key = hashlib.md5(url.encode()).hexdigest()
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            cache_age = (datetime.now(UTC) - cached.fetched_at).total_seconds()
            if cache_age < self.config.compliance.cache_ttl_seconds:
                return FetchResult(
                    url=cached.url,
                    content=cached.content,
                    content_type=cached.content_type,
                    status_code=cached.status_code,
                    headers=cached.headers,
                    fetched_at=cached.fetched_at,
                    from_cache=True,
                )

        # Rate limit
        await self._rate_limiter.acquire()

        # Fetch
        client = await self._get_client()
        response = await client.get(url)

        result = FetchResult(
            url=str(response.url),
            content=response.text,
            content_type=response.headers.get("content-type", "text/html"),
            status_code=response.status_code,
            headers=dict(response.headers),
        )

        # Cache
        self._cache[cache_key] = result

        return result

    @abstractmethod
    async def search(
        self,
        query: SearchQuery,
    ) -> AsyncIterator[SearchResult]:
        """Execute a search query and yield results.

        Args:
            query: The search query to execute

        Yields:
            SearchResult objects
        """
        ...

    @abstractmethod
    async def fetch(self, url: str) -> FetchResult:
        """Fetch a specific resource.

        Args:
            url: The URL to fetch

        Returns:
            FetchResult with content and metadata
        """
        ...

    @abstractmethod
    def extract(
        self,
        content: FetchResult,
        entity_type: str = "person",
    ) -> list[EvidenceClaim]:
        """Extract evidence claims from fetched content.

        Args:
            content: The fetched content
            entity_type: Type of entity to extract

        Returns:
            List of EvidenceClaim objects
        """
        ...

    def create_source_description(
        self,
        url: str,
        content: FetchResult,
    ) -> SourceDescription:
        """Create a SourceDescription for fetched content."""
        return SourceDescription(
            resource_type="DigitalArtifact",
            titles=[f"{self.config.display_name}: {url}"],
            evidence_class=self.evidence_class,
            tier=self.tier,
            url=url,
            accessed_at=content.fetched_at,
            content_hash=content.content_hash,
            raw_content=content.content,
            robots_respected=self.config.compliance.robots_txt,
            tos_compliant=self.config.compliance.tos_accepted,
        )


# =============================================================================
# Adapter Registry
# =============================================================================


class AdapterRegistry:
    """Registry for managing source adapters."""

    def __init__(self):
        self._adapters: dict[str, SourceAdapter] = {}
        self._configs: dict[str, AdapterConfig] = {}

    def register(self, adapter: SourceAdapter) -> None:
        """Register an adapter instance."""
        self._adapters[adapter.adapter_id] = adapter
        self._configs[adapter.adapter_id] = adapter.config

    def get(self, adapter_id: str) -> SourceAdapter | None:
        """Get an adapter by ID."""
        return self._adapters.get(adapter_id)

    def get_by_tier(self, tier: SourceTier) -> list[SourceAdapter]:
        """Get all adapters for a given tier."""
        return [a for a in self._adapters.values() if a.tier == tier]

    def list_adapters(self) -> list[str]:
        """List all registered adapter IDs."""
        return list(self._adapters.keys())

    def load_config(self, path: Path | str) -> AdapterConfig:
        """Load an adapter configuration from YAML."""
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse nested configs
        if "compliance" in data and isinstance(data["compliance"], dict):
            if "rate_limit" in data["compliance"]:
                data["compliance"]["rate_limit"] = RateLimitConfig(
                    **data["compliance"]["rate_limit"]
                )
            data["compliance"] = ComplianceConfig(**data["compliance"])

        if "extraction" in data:
            for entity_type, rules in data["extraction"].items():
                if isinstance(rules, dict):
                    parsed_rules = {}
                    for field_name, rule_data in rules.items():
                        if isinstance(rule_data, dict):
                            parsed_rules[field_name] = ExtractionRule(**rule_data)
                    data["extraction"][entity_type] = ExtractionConfig(rules=parsed_rules)

        if "search" in data and isinstance(data["search"], dict):
            data["search"] = SearchEndpointConfig(**data["search"])

        if "pagination" in data and isinstance(data["pagination"], dict):
            data["pagination"] = PaginationConfig(**data["pagination"])

        config = AdapterConfig(**data)
        self._configs[config.adapter_id] = config
        return config

    async def close_all(self) -> None:
        """Close all adapter connections."""
        for adapter in self._adapters.values():
            await adapter.close()
