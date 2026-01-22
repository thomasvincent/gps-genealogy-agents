"""LLM-Native Extractors for structured genealogical data.

Implements extraction patterns using:
- ScrapeGraphAI: Direct LLM extraction from HTML
- Firecrawl: HTML→Markdown→LLM pipeline (67% token reduction)
- Crawl4AI: Chunked extraction for large pages

Integration with existing source adapters is via the `extract_household()` method.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

from .models import (
    CensusMemberRole,
    ExtractionConfidence,
    ExtractionProvenance,
    ExtractionResult,
    ExtractorType,
    StructuredCensusHousehold,
    StructuredCensusPerson,
)

if TYPE_CHECKING:
    from anthropic import Anthropic
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# Base Extractor Protocol
# =============================================================================


class StructuredExtractor(ABC, Generic[T]):
    """Abstract base for LLM-native structured extractors.

    Subclasses implement domain-specific extraction patterns.
    The extraction flow is:
    1. Fetch content (HTML or pre-converted Markdown)
    2. Apply LLM extraction with structured output
    3. Validate and return typed result
    """

    extractor_type: ExtractorType = ExtractorType.LLM_STRUCTURED

    @abstractmethod
    async def extract_from_url(
        self,
        url: str,
        **hints: Any,
    ) -> ExtractionResult[T]:
        """Extract structured data from a URL.

        Args:
            url: The URL to extract from
            **hints: Domain-specific hints (e.g., hint_name, hint_year)

        Returns:
            ExtractionResult with typed data or error
        """
        ...

    @abstractmethod
    async def extract_from_content(
        self,
        content: str,
        source_url: str,
        **hints: Any,
    ) -> ExtractionResult[T]:
        """Extract structured data from pre-fetched content.

        Args:
            content: HTML or Markdown content
            source_url: Original URL for provenance
            **hints: Domain-specific hints

        Returns:
            ExtractionResult with typed data or error
        """
        ...


# =============================================================================
# Census Household Extractor
# =============================================================================


# System prompt for census extraction
CENSUS_EXTRACTION_SYSTEM_PROMPT = """You are a genealogical data extraction specialist.
Your task is to extract structured census household data from the provided content.

CRITICAL RULES:
1. Extract EXACTLY what appears in the record - do not infer or guess
2. Preserve original spellings of names and places
3. Note the exact "relation to head" text (e.g., "Dau" for daughter)
4. Include line numbers if visible
5. Calculate birth year from age only if census year is known

For each person, extract:
- Name (given, middle, surname) exactly as written
- Age at census
- Birth year (calculated if age present)
- Birth place
- Relation to head of household
- Occupation, marital status if present

For the household, extract:
- Location hierarchy (state, county, city/township)
- Enumeration district, sheet, dwelling, family numbers
- Street address if present

Output must be valid JSON matching the StructuredCensusHousehold schema."""


class CensusHouseholdExtractor(StructuredExtractor[StructuredCensusHousehold]):
    """Extracts structured household data from census record pages.

    Supports multiple extraction backends:
    - Anthropic Claude with structured output
    - OpenAI GPT-4 with JSON mode
    - ScrapeGraphAI (when available)
    - Firecrawl markdown preprocessing

    Example:
        >>> extractor = CensusHouseholdExtractor(anthropic_client=client)
        >>> result = await extractor.extract_from_url(
        ...     "https://www.familysearch.org/ark:/...",
        ...     hint_name="Archer Durham",
        ...     hint_year=1950,
        ... )
        >>> if result.success:
        ...     print(f"Found: {result.data.head.full_name}")
    """

    extractor_type = ExtractorType.LLM_STRUCTURED

    def __init__(
        self,
        anthropic_client: "Anthropic | None" = None,
        openai_client: "AsyncOpenAI | None" = None,
        firecrawl_api_key: str | None = None,
        scrapegraph_config: dict[str, Any] | None = None,
        default_model: str = "claude-sonnet-4-20250514",
    ) -> None:
        """Initialize the census extractor.

        Args:
            anthropic_client: Anthropic client for Claude extraction
            openai_client: OpenAI client for GPT extraction
            firecrawl_api_key: API key for Firecrawl markdown conversion
            scrapegraph_config: Config dict for ScrapeGraphAI
            default_model: Default model to use
        """
        self.anthropic_client = anthropic_client
        self.openai_client = openai_client
        self.firecrawl_api_key = firecrawl_api_key
        self.scrapegraph_config = scrapegraph_config or {}
        self.default_model = default_model

    async def extract_from_url(
        self,
        url: str,
        **hints: Any,
    ) -> ExtractionResult[StructuredCensusHousehold]:
        """Extract household data from a census record URL.

        Args:
            url: URL of the census record page
            hint_name: Name of person to focus on
            hint_year: Expected census year
            hint_location: Expected location

        Returns:
            ExtractionResult with StructuredCensusHousehold
        """
        provenance = ExtractionProvenance(
            source_url=url,
            extractor_type=self.extractor_type,
            started_at=datetime.now(UTC),
        )

        try:
            # Step 1: Fetch and convert to Markdown (if Firecrawl available)
            content = await self._fetch_content(url, provenance)

            # Step 2: Extract structured data
            return await self.extract_from_content(content, url, **hints)

        except Exception as e:
            logger.exception("Extraction failed for %s", url)
            return ExtractionResult.failure_result(
                error=str(e),
                provenance=provenance,
                error_type=type(e).__name__,
            )

    async def extract_from_content(
        self,
        content: str,
        source_url: str,
        **hints: Any,
    ) -> ExtractionResult[StructuredCensusHousehold]:
        """Extract household data from pre-fetched content.

        Args:
            content: HTML or Markdown content
            source_url: Original URL for provenance
            hint_name: Name of person to focus on
            hint_year: Expected census year
            hint_location: Expected location

        Returns:
            ExtractionResult with StructuredCensusHousehold
        """
        provenance = ExtractionProvenance(
            source_url=source_url,
            extractor_type=self.extractor_type,
            started_at=datetime.now(UTC),
        )

        try:
            # Build extraction prompt
            user_prompt = self._build_extraction_prompt(content, **hints)

            # Call LLM with structured output
            if self.anthropic_client:
                household = await self._extract_with_anthropic(user_prompt, provenance)
            elif self.openai_client:
                household = await self._extract_with_openai(user_prompt, provenance)
            else:
                raise ValueError("No LLM client configured")

            # Post-process and validate
            household = self._post_process(household, source_url, hints)

            # Determine confidence based on extraction quality
            confidence = self._assess_confidence(household)

            return ExtractionResult.success_result(
                data=household,
                provenance=provenance,
                confidence=confidence,
                citation_ready=bool(household.citation_reference),
            )

        except Exception as e:
            logger.exception("Extraction failed for content from %s", source_url)
            return ExtractionResult.failure_result(
                error=str(e),
                provenance=provenance,
                error_type=type(e).__name__,
            )

    def _build_extraction_prompt(
        self,
        content: str,
        **hints: Any,
    ) -> str:
        """Build the extraction prompt with hints."""
        prompt_parts = [
            "Extract the census household data from the following content.",
            "",
        ]

        # Add hints
        if hints.get("hint_name"):
            prompt_parts.append(f"Focus on finding: {hints['hint_name']}")
        if hints.get("hint_year"):
            prompt_parts.append(f"Expected census year: {hints['hint_year']}")
        if hints.get("hint_location"):
            prompt_parts.append(f"Expected location: {hints['hint_location']}")

        prompt_parts.extend([
            "",
            "Content:",
            "---",
            content[:50000],  # Truncate to avoid token limits
            "---",
            "",
            "Extract the household data as a JSON object matching the StructuredCensusHousehold schema.",
        ])

        return "\n".join(prompt_parts)

    async def _extract_with_anthropic(
        self,
        user_prompt: str,
        provenance: ExtractionProvenance,
    ) -> StructuredCensusHousehold:
        """Extract using Anthropic Claude with structured output."""
        import json

        provenance.model_used = self.default_model

        response = self.anthropic_client.messages.create(
            model=self.default_model,
            max_tokens=4096,
            system=CENSUS_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Track token usage
        provenance.input_tokens = response.usage.input_tokens
        provenance.output_tokens = response.usage.output_tokens

        # Parse response
        content = response.content[0].text

        # Extract JSON from response
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(content[json_start:json_end])
            return StructuredCensusHousehold(**data)

        raise ValueError("No valid JSON found in response")

    async def _extract_with_openai(
        self,
        user_prompt: str,
        provenance: ExtractionProvenance,
    ) -> StructuredCensusHousehold:
        """Extract using OpenAI GPT-4 with JSON mode."""
        import json

        model = "gpt-4o"
        provenance.model_used = model

        response = await self.openai_client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CENSUS_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        # Track token usage
        if response.usage:
            provenance.input_tokens = response.usage.prompt_tokens
            provenance.output_tokens = response.usage.completion_tokens

        # Parse response
        content = response.choices[0].message.content
        data = json.loads(content)
        return StructuredCensusHousehold(**data)

    async def _fetch_content(
        self,
        url: str,
        provenance: ExtractionProvenance,
    ) -> str:
        """Fetch URL content, optionally converting to Markdown.

        Uses Firecrawl if available for 67% token reduction.
        Falls back to direct HTML fetch otherwise.
        """
        if self.firecrawl_api_key:
            return await self._fetch_with_firecrawl(url, provenance)

        # Fallback to direct HTTP fetch
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            provenance.html_size_bytes = len(html.encode())
            return html

    async def _fetch_with_firecrawl(
        self,
        url: str,
        provenance: ExtractionProvenance,
    ) -> str:
        """Fetch URL using Firecrawl API for Markdown conversion."""
        import httpx

        provenance.extractor_type = ExtractorType.FIRECRAWL

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v0/scrape",
                headers={"Authorization": f"Bearer {self.firecrawl_api_key}"},
                json={
                    "url": url,
                    "pageOptions": {
                        "onlyMainContent": True,
                        "includeHtml": False,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            markdown = data.get("data", {}).get("markdown", "")
            provenance.markdown_content = markdown
            provenance.markdown_size_bytes = len(markdown.encode())

            # Get HTML size if available
            if "html" in data.get("data", {}):
                provenance.html_size_bytes = len(data["data"]["html"].encode())

            return markdown

    def _post_process(
        self,
        household: StructuredCensusHousehold,
        source_url: str,
        hints: dict[str, Any],
    ) -> StructuredCensusHousehold:
        """Post-process extracted household data."""
        # Set source URL if not present
        if not household.source_url:
            household.source_url = source_url

        # Calculate birth years from ages if not set
        for member in household.members:
            if member.birth_year is None and member.age_at_census is not None:
                member.birth_year = household.census_year - member.age_at_census
                member.birth_year_confidence = ExtractionConfidence.INFERRED

        # Normalize relation to head
        for member in household.members:
            if member.relation_to_head == CensusMemberRole.OTHER and member.relation_as_recorded:
                member.relation_to_head = self._normalize_relation(
                    member.relation_as_recorded
                )

        return household

    def _normalize_relation(self, relation_text: str) -> CensusMemberRole:
        """Normalize relation text to enum value."""
        relation_map = {
            "head": CensusMemberRole.HEAD,
            "h": CensusMemberRole.HEAD,
            "wife": CensusMemberRole.WIFE,
            "w": CensusMemberRole.WIFE,
            "husband": CensusMemberRole.HUSBAND,
            "son": CensusMemberRole.SON,
            "s": CensusMemberRole.SON,
            "daughter": CensusMemberRole.DAUGHTER,
            "dau": CensusMemberRole.DAUGHTER,
            "d": CensusMemberRole.DAUGHTER,
            "father": CensusMemberRole.FATHER,
            "fa": CensusMemberRole.FATHER,
            "mother": CensusMemberRole.MOTHER,
            "mo": CensusMemberRole.MOTHER,
            "brother": CensusMemberRole.BROTHER,
            "bro": CensusMemberRole.BROTHER,
            "sister": CensusMemberRole.SISTER,
            "sis": CensusMemberRole.SISTER,
            "grandson": CensusMemberRole.GRANDSON,
            "gs": CensusMemberRole.GRANDSON,
            "granddaughter": CensusMemberRole.GRANDDAUGHTER,
            "gd": CensusMemberRole.GRANDDAUGHTER,
            "boarder": CensusMemberRole.BOARDER,
            "lodger": CensusMemberRole.LODGER,
            "servant": CensusMemberRole.SERVANT,
            "father-in-law": CensusMemberRole.FATHER_IN_LAW,
            "mother-in-law": CensusMemberRole.MOTHER_IN_LAW,
        }

        normalized = relation_text.lower().strip()
        return relation_map.get(normalized, CensusMemberRole.OTHER)

    def _assess_confidence(
        self,
        household: StructuredCensusHousehold,
    ) -> ExtractionConfidence:
        """Assess overall extraction confidence."""
        # High confidence if we have good structural data
        has_location = bool(household.state and household.county)
        has_head = household.head is not None
        has_members = len(household.members) > 0
        has_census_ref = bool(
            household.enumeration_district or household.sheet_number
        )

        if has_location and has_head and has_members and has_census_ref:
            return ExtractionConfidence.HIGH
        elif has_location and (has_head or has_members):
            return ExtractionConfidence.MEDIUM
        else:
            return ExtractionConfidence.LOW


# =============================================================================
# ScrapeGraphAI Integration (Optional Dependency)
# =============================================================================


class ScrapeGraphAIExtractor(StructuredExtractor[StructuredCensusHousehold]):
    """Extractor using ScrapeGraphAI for direct LLM scraping.

    ScrapeGraphAI provides native structured output extraction
    without intermediate Markdown conversion.

    Requires: pip install scrapegraphai
    """

    extractor_type = ExtractorType.SCRAPEGRAPHAI

    def __init__(
        self,
        llm_config: dict[str, Any],
        graph_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ScrapeGraphAI extractor.

        Args:
            llm_config: LLM configuration for ScrapeGraphAI
            graph_config: Optional graph execution config
        """
        self.llm_config = llm_config
        self.graph_config = graph_config or {
            "headless": True,
            "verbose": False,
        }

    async def extract_from_url(
        self,
        url: str,
        **hints: Any,
    ) -> ExtractionResult[StructuredCensusHousehold]:
        """Extract using ScrapeGraphAI SmartScraperGraph."""
        provenance = ExtractionProvenance(
            source_url=url,
            extractor_type=self.extractor_type,
            started_at=datetime.now(UTC),
        )

        try:
            # Import here to make dependency optional
            from scrapegraphai.graphs import SmartScraperGraph

            # Build prompt
            prompt = self._build_prompt(**hints)

            # Create and run graph
            graph = SmartScraperGraph(
                prompt=prompt,
                source=url,
                config=self.graph_config,
                schema=StructuredCensusHousehold,
            )

            result = graph.run()

            # Convert to our model
            if isinstance(result, dict):
                household = StructuredCensusHousehold(**result)
            elif isinstance(result, StructuredCensusHousehold):
                household = result
            else:
                raise ValueError(f"Unexpected result type: {type(result)}")

            household.source_url = url
            household.extractor_type = ExtractorType.SCRAPEGRAPHAI

            return ExtractionResult.success_result(
                data=household,
                provenance=provenance,
                confidence=ExtractionConfidence.MEDIUM,
            )

        except ImportError:
            return ExtractionResult.failure_result(
                error="scrapegraphai not installed. Run: pip install scrapegraphai",
                provenance=provenance,
                error_type="ImportError",
            )
        except Exception as e:
            logger.exception("ScrapeGraphAI extraction failed")
            return ExtractionResult.failure_result(
                error=str(e),
                provenance=provenance,
                error_type=type(e).__name__,
            )

    async def extract_from_content(
        self,
        content: str,
        source_url: str,
        **hints: Any,
    ) -> ExtractionResult[StructuredCensusHousehold]:
        """Extract from content using ScrapeGraphAI."""
        provenance = ExtractionProvenance(
            source_url=source_url,
            extractor_type=self.extractor_type,
            started_at=datetime.now(UTC),
        )

        try:
            from scrapegraphai.graphs import SmartScraperGraph

            prompt = self._build_prompt(**hints)

            graph = SmartScraperGraph(
                prompt=prompt,
                source=content,  # Can accept HTML/text directly
                config=self.graph_config,
                schema=StructuredCensusHousehold,
            )

            result = graph.run()

            if isinstance(result, dict):
                household = StructuredCensusHousehold(**result)
            else:
                household = result

            household.source_url = source_url

            return ExtractionResult.success_result(
                data=household,
                provenance=provenance,
                confidence=ExtractionConfidence.MEDIUM,
            )

        except ImportError:
            return ExtractionResult.failure_result(
                error="scrapegraphai not installed",
                provenance=provenance,
                error_type="ImportError",
            )
        except Exception as e:
            return ExtractionResult.failure_result(
                error=str(e),
                provenance=provenance,
                error_type=type(e).__name__,
            )

    def _build_prompt(self, **hints: Any) -> str:
        """Build ScrapeGraphAI prompt."""
        parts = [
            "Extract the complete census household information from this page.",
            "Include all household members with their names, ages, relations, and occupations.",
        ]

        if hints.get("hint_name"):
            parts.append(f"Focus on the household containing: {hints['hint_name']}")
        if hints.get("hint_year"):
            parts.append(f"This is a {hints['hint_year']} census record.")

        return " ".join(parts)
