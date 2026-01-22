"""LLM-Native Web Extraction module for GPS-compliant genealogical research.

This module provides structured extraction using LLM-native web scraping patterns
with ScrapeGraphAI/Firecrawl integration for 67% token reduction vs raw HTML.

Key Components:
- CensusHouseholdExtractor: Extracts structured household data from census pages
- StructuredExtractor: Base class for domain-specific extraction patterns
- ExtractionResult: Typed wrapper for extraction outputs with provenance

Example:
    >>> from gps_agents.genealogy_crawler.extraction import (
    ...     CensusHouseholdExtractor,
    ...     StructuredCensusHousehold,
    ... )
    >>>
    >>> extractor = CensusHouseholdExtractor(llm_client)
    >>> result = await extractor.extract_from_url(
    ...     "https://www.familysearch.org/ark:/...",
    ...     hint_name="Archer Durham",
    ...     hint_year=1950,
    ... )
    >>>
    >>> household = result.data
    >>> print(f"Head: {household.head.full_name}, {len(household.members)} members")
"""
from .models import (
    CensusMemberRole,
    ExtractionConfidence,
    ExtractionProvenance,
    ExtractionResult,
    ExtractorType,
    StructuredCensusHousehold,
    StructuredCensusPerson,
)
from .extractors import (
    CensusHouseholdExtractor,
    StructuredExtractor,
)

__all__ = [
    # Models - Enums
    "CensusMemberRole",
    "ExtractionConfidence",
    "ExtractorType",
    # Models - Data
    "StructuredCensusPerson",
    "StructuredCensusHousehold",
    "ExtractionProvenance",
    "ExtractionResult",
    # Extractors
    "StructuredExtractor",
    "CensusHouseholdExtractor",
]
