"""Find A Grave source adapter.

Tier 0 source - no authentication required.
Secondary/memorial evidence class.
"""
from __future__ import annotations

import re
from typing import AsyncIterator
from uuid import uuid4

from ..models_v2 import (
    EvidenceClaim,
    EvidenceClass,
    FuzzyDate,
    DatePrecision,
    GeoCodedPlace,
)
from .base import (
    AdapterConfig,
    ComplianceConfig,
    ExtractionConfig,
    ExtractionRule,
    FetchResult,
    PaginationConfig,
    RateLimitConfig,
    SearchEndpointConfig,
    SearchQuery,
    SearchResult,
    SourceAdapter,
)


def create_find_a_grave_config() -> AdapterConfig:
    """Create Find A Grave adapter configuration."""
    return AdapterConfig(
        adapter_id="find_a_grave",
        display_name="Find A Grave",
        tier=0,
        domain="findagrave.com",
        base_url="https://www.findagrave.com",
        evidence_class="secondary_memorial",
        prior_weight=0.65,
        compliance=ComplianceConfig(
            robots_txt=True,
            respect_nofollow=True,
            rate_limit=RateLimitConfig(
                requests_per_second=0.2,  # 1 req per 5 seconds
                burst=3,
                retry_after_429=120,
            ),
            user_agent="GenealogyResearchBot/2.0 (+https://example.com/bot)",
            cache_ttl_seconds=86400,
            tos_url="https://www.findagrave.com/terms",
            tos_accepted=True,
        ),
        extraction={
            "person": ExtractionConfig(
                rules={
                    "name": ExtractionRule(
                        selector="h1#bio-name",
                        parser="text",
                        confidence=0.9,
                        required=True,
                    ),
                    "birth_date": ExtractionRule(
                        selector="#birthDateLabel",
                        parser="fuzzy_date",
                        confidence=0.7,
                    ),
                    "death_date": ExtractionRule(
                        selector="#deathDateLabel",
                        parser="fuzzy_date",
                        confidence=0.8,
                    ),
                    "burial_place": ExtractionRule(
                        selector="#cemeteryNameLabel",
                        parser="geocode",
                        confidence=0.9,
                    ),
                    "birth_place": ExtractionRule(
                        regex=r"Born[^,]*(?:in|at)\s+([^,\n]+)",
                        parser="geocode",
                        confidence=0.6,
                    ),
                    "death_place": ExtractionRule(
                        regex=r"Died[^,]*(?:in|at)\s+([^,\n]+)",
                        parser="geocode",
                        confidence=0.6,
                    ),
                }
            ),
        },
        search=SearchEndpointConfig(
            endpoint="/memorial/search",
            method="GET",
            params={
                "firstname": "{given_name}",
                "lastname": "{surname}",
                "birthyear": "{birth_year}",
                "deathyear": "{death_year}",
            },
        ),
        pagination=PaginationConfig(
            type="page_number",
            param="page",
            max_pages=5,
            results_per_page=20,
        ),
    )


class FindAGraveAdapter(SourceAdapter):
    """Find A Grave source adapter implementation."""

    def __init__(self, config: AdapterConfig | None = None):
        if config is None:
            config = create_find_a_grave_config()
        super().__init__(config)

    async def search(
        self,
        query: SearchQuery,
    ) -> AsyncIterator[SearchResult]:
        """Search Find A Grave for memorials."""
        if self.config.search is None:
            return

        # Build search URL
        base_url = f"{self.config.base_url}{self.config.search.endpoint}"
        params = {}
        for key, template in self.config.search.params.items():
            value = query.format_param(template)
            if value and value != template:  # Only include if substituted
                params[key] = value

        if not params:
            params["q"] = query.query_string

        # Paginate through results
        max_pages = self.config.pagination.max_pages if self.config.pagination else 1
        page = 1

        while page <= max_pages:
            if self.config.pagination:
                params[self.config.pagination.param] = str(page)

            # Fetch search results page
            try:
                url = base_url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
                result = await self._fetch_with_compliance(url)

                # Parse results (simplified - real impl would use BeautifulSoup)
                results_found = self._parse_search_results(result.content)

                if not results_found:
                    break

                for search_result in results_found:
                    yield search_result

                page += 1

            except Exception as e:
                # Log and stop pagination on error
                break

    async def fetch(self, url: str) -> FetchResult:
        """Fetch a Find A Grave memorial page."""
        return await self._fetch_with_compliance(url)

    def extract(
        self,
        content: FetchResult,
        entity_type: str = "person",
    ) -> list[EvidenceClaim]:
        """Extract evidence claims from a memorial page."""
        claims: list[EvidenceClaim] = []

        if entity_type not in self.config.extraction:
            return claims

        extraction_config = self.config.extraction[entity_type]
        text = self._strip_html(content.content)

        for field_name, rule in extraction_config.rules.items():
            value, snippet = self._extract_field(content.content, text, rule)
            if value is not None:
                claims.append(EvidenceClaim(
                    source_reference_id=uuid4(),  # Would be linked to actual source ref
                    claim_text=f"{field_name}: {value}",
                    claim_type=field_name,
                    claim_value=value,
                    citation_snippet=snippet or f"Extracted from {content.url}",
                    prior_weight=self.prior_weight * rule.confidence,
                    extraction_method="deterministic",
                    extractor_version="find_a_grave_adapter:1.0",
                ))

        return claims

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags from content."""
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_field(
        self,
        html: str,
        text: str,
        rule: ExtractionRule,
    ) -> tuple[str | None, str | None]:
        """Extract a field using the extraction rule."""
        value = None
        snippet = None

        # Try regex first
        if rule.regex:
            match = re.search(rule.regex, text, re.IGNORECASE)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                snippet = text[start:end].strip()

        # Try CSS selector (simplified - real impl would use BeautifulSoup)
        if value is None and rule.selector:
            # Very simplified selector matching
            id_match = re.search(r'id="([^"]+)"', rule.selector)
            if id_match:
                selector_id = id_match.group(1)
                pattern = rf'id="{selector_id}"[^>]*>([^<]+)'
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    snippet = match.group(0)

        # Parse value based on type
        if value and rule.parser == "fuzzy_date":
            # Return raw date string - would be parsed by FuzzyDate
            pass
        elif value and rule.parser == "geocode":
            # Return raw place string - would be geocoded
            pass

        return value, snippet

    def _parse_search_results(self, html: str) -> list[SearchResult]:
        """Parse search results from HTML (simplified)."""
        results: list[SearchResult] = []

        # Very simplified parsing - real impl would use BeautifulSoup
        # Look for memorial links
        pattern = r'href="(/memorial/\d+/[^"]+)"[^>]*>([^<]+)'
        for match in re.finditer(pattern, html):
            url = f"{self.config.base_url}{match.group(1)}"
            title = match.group(2).strip()
            results.append(SearchResult(
                title=title,
                url=url,
                relevance_score=0.5,
            ))

        return results[:20]  # Limit results
