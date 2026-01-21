"""Source Adapter Framework for the genealogy crawler.

Provides a plugin system for different genealogical data sources with:
- Abstract adapter interface
- Configuration-driven extraction rules
- Compliance enforcement (robots.txt, rate limits, ToS)
- Evidence classification for Bayesian weighting
"""
from .base import (
    AdapterConfig,
    AdapterRegistry,
    ComplianceConfig,
    ExtractionConfig,
    FetchResult,
    RateLimiter,
    SearchQuery,
    SearchResult,
    SourceAdapter,
)

__all__ = [
    "SourceAdapter",
    "AdapterConfig",
    "AdapterRegistry",
    "ComplianceConfig",
    "ExtractionConfig",
    "SearchQuery",
    "SearchResult",
    "FetchResult",
    "RateLimiter",
]
