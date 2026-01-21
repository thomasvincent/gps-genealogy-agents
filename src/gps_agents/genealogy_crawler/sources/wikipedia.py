"""Wikipedia source plugin for the genealogy crawler.

Tier 0 source - no authentication required.
Uses Wikipedia's API for structured data extraction.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ..models import SourceTier
from .plugin import (
    ComplianceConfig,
    ExtractionRule,
    PaginationConfig,
    ReliabilityConfig,
    RegexExtractor,
    SearchConfig,
    SourcePlugin,
    SourcePluginConfig,
)

logger = logging.getLogger(__name__)


def create_wikipedia_config() -> SourcePluginConfig:
    """Create Wikipedia plugin configuration."""
    return SourcePluginConfig(
        plugin_id="wikipedia",
        display_name="Wikipedia",
        tier=0,
        base_url="https://en.wikipedia.org",
        compliance=ComplianceConfig(
            robots_txt=True,
            rate_limit_requests_per_minute=30,
            rate_limit_burst=5,
            cache_ttl_seconds=86400,
            requires_auth=False,
            tos_url="https://en.wikipedia.org/wiki/Wikipedia:Terms_of_Use",
        ),
        reliability=ReliabilityConfig(
            evidence_type="secondary",
            base_weight=0.6,
            user_contributed=True,
        ),
        extraction_rules={
            "person": {
                "name": ExtractionRule(
                    selector="h1#firstHeading",
                    type="text",
                    required=True,
                ),
                "birth_date": ExtractionRule(
                    regex=r"(?:born|b\.?)\s*([A-Za-z]+ \d{1,2},? \d{4}|\d{4})",
                    type="date",
                    format="fuzzy",
                ),
                "death_date": ExtractionRule(
                    regex=r"(?:died|d\.?)\s*([A-Za-z]+ \d{1,2},? \d{4}|\d{4})",
                    type="date",
                    format="fuzzy",
                ),
                "birth_place": ExtractionRule(
                    regex=r"born[^,]*,\s*([^,\)]+)",
                    type="text",
                ),
                "death_place": ExtractionRule(
                    regex=r"died[^,]*,\s*([^,\)]+)",
                    type="text",
                ),
            },
        },
        search=SearchConfig(
            endpoint="/w/api.php",
            method="GET",
            params={
                "action": "query",
                "list": "search",
                "srsearch": "{query}",
                "format": "json",
            },
            result_selector=".searchresult",
        ),
        pagination=PaginationConfig(
            type="offset",
            param="sroffset",
            max_pages=5,
            results_per_page=10,
        ),
        default_headers={
            "User-Agent": "GenealogyResearchBot/1.0 (Educational use)",
        },
    )


class WikipediaPlugin(SourcePlugin):
    """Wikipedia source plugin implementation."""

    def __init__(self, config: SourcePluginConfig | None = None):
        if config is None:
            config = create_wikipedia_config()
        super().__init__(config)
        self._extractor = RegexExtractor()
        self._client = httpx.AsyncClient(
            headers=config.default_headers,
            timeout=30.0,
        )

    async def fetch(self, url: str) -> tuple[str, dict[str, Any]]:
        """Fetch Wikipedia page content.

        Uses the Wikipedia API to get parsed content.
        """
        # Extract page title from URL
        title_match = re.search(r"/wiki/([^?#]+)", url)
        if not title_match:
            raise ValueError(f"Invalid Wikipedia URL: {url}")

        title = title_match.group(1)

        # Use API to get page content
        api_url = f"{self.config.base_url}/w/api.php"
        params = {
            "action": "parse",
            "page": title,
            "format": "json",
            "prop": "text|categories|links",
        }

        response = await self._client.get(api_url, params=params)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise ValueError(f"Wikipedia API error: {data['error'].get('info', 'Unknown')}")

        parse_data = data.get("parse", {})
        content = parse_data.get("text", {}).get("*", "")

        metadata = {
            "title": parse_data.get("title"),
            "pageid": parse_data.get("pageid"),
            "categories": [c["*"] for c in parse_data.get("categories", [])],
            "links": [l["*"] for l in parse_data.get("links", [])],
        }

        return content, metadata

    async def search(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search Wikipedia for articles."""
        if self.config.search is None:
            raise ValueError("Search not configured for this plugin")

        api_url = f"{self.config.base_url}{self.config.search.endpoint}"

        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": self.config.pagination.results_per_page if self.config.pagination else 10,
        }

        if params:
            search_params.update(params)

        results: list[dict[str, Any]] = []
        offset = 0
        max_pages = self.config.pagination.max_pages if self.config.pagination else 1

        for _ in range(max_pages):
            search_params["sroffset"] = offset

            response = await self._client.get(api_url, params=search_params)
            response.raise_for_status()
            data = response.json()

            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                break

            for result in search_results:
                results.append({
                    "title": result["title"],
                    "pageid": result["pageid"],
                    "snippet": result.get("snippet", ""),
                    "url": f"{self.config.base_url}/wiki/{result['title'].replace(' ', '_')}",
                })

            # Check for continuation
            if "continue" not in data:
                break

            offset = data["continue"].get("sroffset", offset + len(search_results))

        return results

    def extract(
        self,
        content: str,
        entity_type: str = "person",
    ) -> dict[str, Any]:
        """Extract person data from Wikipedia HTML content."""
        extracted: dict[str, Any] = {}

        # Strip HTML tags for text extraction
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text)

        # Get extraction rules for entity type
        rules = self.config.extraction_rules.get(entity_type, {})

        for field_name, rule in rules.items():
            if isinstance(rule, ExtractionRule):
                value, citation = self._extractor.extract_field(text, rule)
                if value:
                    extracted[field_name] = {
                        "value": value,
                        "citation": citation,
                    }

        # Also try general date extraction
        dates = self._extractor.extract_dates(text)
        if dates["birth_date"][0] and "birth_date" not in extracted:
            extracted["birth_date"] = {
                "value": dates["birth_date"][0],
                "citation": dates["birth_date"][1],
            }
        if dates["death_date"][0] and "death_date" not in extracted:
            extracted["death_date"] = {
                "value": dates["death_date"][0],
                "citation": dates["death_date"][1],
            }

        return extracted

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
