"""Source plugin system for the genealogy crawler.

Defines the plugin schema and base classes for source-specific
extraction and compliance configuration.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

from ..models import EvidenceType, SourceRecord, SourceTier


# =============================================================================
# Plugin Configuration Schema
# =============================================================================


class ComplianceConfig(BaseModel):
    """Compliance configuration for a source."""
    robots_txt: bool = True
    rate_limit_requests_per_minute: int = 10
    rate_limit_burst: int = 3
    cache_ttl_seconds: int = 86400  # 24 hours
    requires_auth: bool = False
    tos_url: str | None = None


class ReliabilityConfig(BaseModel):
    """Reliability scoring configuration."""
    evidence_type: str = "secondary"  # primary, secondary, authored
    base_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    user_contributed: bool = False

    @property
    def evidence_type_enum(self) -> EvidenceType:
        """Get evidence type as enum."""
        return EvidenceType(self.evidence_type)


class ExtractionRule(BaseModel):
    """Rule for extracting a field from HTML/text."""
    selector: str | None = None  # CSS selector
    xpath: str | None = None  # XPath expression
    regex: str | None = None  # Regex pattern
    type: str = "text"  # text, date, number
    format: str | None = None  # Date format or number format
    required: bool = False
    default: Any = None

    @model_validator(mode="after")
    def validate_has_selector(self) -> "ExtractionRule":
        """Ensure at least one selector type is specified."""
        if not self.selector and not self.xpath and not self.regex:
            raise ValueError("At least one of selector, xpath, or regex must be specified")
        return self


class SearchConfig(BaseModel):
    """Search endpoint configuration."""
    endpoint: str
    method: str = "GET"
    params: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    result_selector: str | None = None
    result_xpath: str | None = None


class PaginationConfig(BaseModel):
    """Pagination handling configuration."""
    type: str = "page_number"  # page_number, offset, cursor
    param: str = "page"
    max_pages: int = 10
    results_per_page: int = 20


class SourcePluginConfig(BaseModel):
    """Complete source plugin configuration."""
    plugin_id: str
    display_name: str
    tier: int = Field(ge=0, le=2)
    base_url: str

    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    reliability: ReliabilityConfig = Field(default_factory=ReliabilityConfig)
    extraction_rules: dict[str, dict[str, ExtractionRule]] = Field(default_factory=dict)
    search: SearchConfig | None = None
    pagination: PaginationConfig | None = None

    # Optional custom headers for all requests
    default_headers: dict[str, str] = Field(default_factory=dict)

    @property
    def source_tier(self) -> SourceTier:
        """Get tier as enum."""
        return SourceTier(self.tier)


# =============================================================================
# Plugin Registry
# =============================================================================


@dataclass
class PluginRegistry:
    """Registry of loaded source plugins."""
    plugins: dict[str, SourcePluginConfig] = field(default_factory=dict)

    def register(self, config: SourcePluginConfig) -> None:
        """Register a plugin configuration."""
        self.plugins[config.plugin_id] = config

    def get(self, plugin_id: str) -> SourcePluginConfig | None:
        """Get a plugin by ID."""
        return self.plugins.get(plugin_id)

    def get_by_tier(self, tier: SourceTier) -> list[SourcePluginConfig]:
        """Get all plugins for a given tier."""
        return [p for p in self.plugins.values() if p.source_tier == tier]

    def load_from_yaml(self, path: Path | str) -> SourcePluginConfig:
        """Load a plugin configuration from YAML file."""
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse extraction rules specially
        if "extraction_rules" in data:
            for entity_type, rules in data["extraction_rules"].items():
                for field_name, rule_data in rules.items():
                    if isinstance(rule_data, dict):
                        rules[field_name] = ExtractionRule(**rule_data)

        config = SourcePluginConfig(**data)
        self.register(config)
        return config

    def load_registry_file(self, path: Path | str) -> None:
        """Load multiple plugins from a registry YAML file."""
        path = Path(path)
        base_dir = path.parent

        with open(path) as f:
            registry_data = yaml.safe_load(f)

        for source in registry_data.get("sources", []):
            config_path = base_dir / source["config"]
            self.load_from_yaml(config_path)


# =============================================================================
# Abstract Source Plugin
# =============================================================================


class SourcePlugin(ABC):
    """Base class for source plugins.

    Subclasses implement source-specific fetching and parsing logic.
    """

    def __init__(self, config: SourcePluginConfig):
        self.config = config
        self._request_count = 0
        self._last_request_time: float = 0.0

    @property
    def plugin_id(self) -> str:
        return self.config.plugin_id

    @property
    def tier(self) -> SourceTier:
        return self.config.source_tier

    @abstractmethod
    async def fetch(self, url: str) -> tuple[str, dict[str, Any]]:
        """Fetch content from a URL.

        Args:
            url: The URL to fetch

        Returns:
            Tuple of (content, metadata)
        """
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search the source.

        Args:
            query: Search query string
            params: Additional search parameters

        Returns:
            List of search results
        """
        ...

    @abstractmethod
    def extract(
        self,
        content: str,
        entity_type: str = "person",
    ) -> dict[str, Any]:
        """Extract fields from content.

        Args:
            content: Raw HTML or text content
            entity_type: Type of entity to extract (person, event, etc.)

        Returns:
            Dictionary of extracted fields
        """
        ...

    def create_source_record(
        self,
        url: str,
        content: str,
        extracted: dict[str, Any],
    ) -> SourceRecord:
        """Create a SourceRecord from fetched content."""
        record = SourceRecord(
            url=url,
            source_name=self.config.display_name,
            source_tier=self.tier,
            raw_text=content,
            raw_extracted=extracted,
            metadata={
                "plugin_id": self.plugin_id,
                "evidence_type": self.config.reliability.evidence_type,
            },
        )
        record.compute_content_hash(content)
        return record


# =============================================================================
# Simple Regex Extractor
# =============================================================================


class RegexExtractor:
    """Simple regex-based field extractor."""

    # Common date patterns
    DATE_PATTERNS = [
        r"(?:born|b\.?)\s*([A-Za-z]+ \d{1,2},? \d{4})",
        r"(?:born|b\.?)\s*(\d{1,2} [A-Za-z]+ \d{4})",
        r"(?:born|b\.?)\s*(\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ]

    DEATH_PATTERNS = [
        r"(?:died|d\.?)\s*([A-Za-z]+ \d{1,2},? \d{4})",
        r"(?:died|d\.?)\s*(\d{1,2} [A-Za-z]+ \d{4})",
        r"(?:died|d\.?)\s*(\d{4})",
    ]

    def extract_field(
        self,
        content: str,
        rule: ExtractionRule,
    ) -> tuple[Any, str | None]:
        """Extract a field using the rule.

        Returns:
            Tuple of (value, citation_snippet)
        """
        if rule.regex:
            match = re.search(rule.regex, content, re.IGNORECASE)
            if match:
                # Get surrounding context for citation
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                citation = content[start:end].strip()
                return match.group(1) if match.groups() else match.group(0), citation

        return rule.default, None

    def extract_dates(
        self,
        content: str,
    ) -> dict[str, tuple[str | None, str | None]]:
        """Extract birth and death dates from content.

        Returns:
            Dict with 'birth_date' and 'death_date' keys,
            values are (date_str, citation_snippet) tuples
        """
        results: dict[str, tuple[str | None, str | None]] = {
            "birth_date": (None, None),
            "death_date": (None, None),
        }

        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match and not results["birth_date"][0]:
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                results["birth_date"] = (match.group(1), content[start:end].strip())
                break

        for pattern in self.DEATH_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match and not results["death_date"][0]:
                start = max(0, match.start() - 20)
                end = min(len(content), match.end() + 20)
                results["death_date"] = (match.group(1), content[start:end].strip())
                break

        return results
