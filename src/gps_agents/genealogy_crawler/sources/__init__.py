"""Source plugins for the genealogy crawler.

Provides a plugin system for different genealogical data sources
with standardized extraction, compliance, and reliability configuration.
"""
from .plugin import (
    ComplianceConfig,
    ExtractionRule,
    PaginationConfig,
    PluginRegistry,
    RegexExtractor,
    ReliabilityConfig,
    SearchConfig,
    SourcePlugin,
    SourcePluginConfig,
)
from .wikipedia import WikipediaPlugin, create_wikipedia_config

__all__ = [
    # Plugin System
    "SourcePlugin",
    "SourcePluginConfig",
    "PluginRegistry",
    # Config Types
    "ComplianceConfig",
    "ReliabilityConfig",
    "ExtractionRule",
    "SearchConfig",
    "PaginationConfig",
    # Utilities
    "RegexExtractor",
    # Implementations
    "WikipediaPlugin",
    "create_wikipedia_config",
]
