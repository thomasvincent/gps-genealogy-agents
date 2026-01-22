"""LLM-Native Extraction models for structured genealogical data.

Pydantic models designed for LLM-native extraction with ScrapeGraphAI/Firecrawl.
These replace raw dict-based extraction with typed, validated schemas.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, computed_field, model_validator


# =============================================================================
# Enums
# =============================================================================


class CensusMemberRole(str, Enum):
    """Role of a person within a census household."""

    HEAD = "head"
    WIFE = "wife"
    HUSBAND = "husband"
    SON = "son"
    DAUGHTER = "daughter"
    FATHER = "father"
    MOTHER = "mother"
    FATHER_IN_LAW = "father_in_law"
    MOTHER_IN_LAW = "mother_in_law"
    BROTHER = "brother"
    SISTER = "sister"
    GRANDSON = "grandson"
    GRANDDAUGHTER = "granddaughter"
    NEPHEW = "nephew"
    NIECE = "niece"
    BOARDER = "boarder"
    LODGER = "lodger"
    SERVANT = "servant"
    OTHER_RELATIVE = "other_relative"
    OTHER = "other"


class ExtractionConfidence(str, Enum):
    """Confidence level for extracted values."""

    HIGH = "high"  # Clear, unambiguous extraction
    MEDIUM = "medium"  # Some ambiguity or OCR uncertainty
    LOW = "low"  # Significant uncertainty
    INFERRED = "inferred"  # Value inferred from context


class ExtractorType(str, Enum):
    """Type of extractor that produced the data."""

    SCRAPEGRAPHAI = "scrapegraphai"  # ScrapeGraphAI LLM extraction
    FIRECRAWL = "firecrawl"  # Firecrawl markdown + LLM
    CRAWL4AI = "crawl4ai"  # Crawl4AI extraction
    DETERMINISTIC = "deterministic"  # Rule-based DOM extraction
    LLM_STRUCTURED = "llm_structured"  # Direct structured output
    HYBRID = "hybrid"  # Combination of methods


# =============================================================================
# Census Person (Enhanced from census_tree.py)
# =============================================================================


class StructuredCensusPerson(BaseModel):
    """A person extracted from a census record with full provenance.

    Enhanced from CensusPerson dataclass to support:
    - LLM-native extraction with confidence scores
    - Name variant tracking for entity resolution
    - Direct citation snippets for GPS compliance
    """

    # Identity
    id: UUID = Field(default_factory=uuid4)
    given_name: str = Field(description="First/given name as it appears in the record")
    surname: str = Field(description="Family name/surname")
    middle_name: str | None = Field(default=None, description="Middle name or initial")

    # Name variants (for entity resolution)
    name_as_recorded: str = Field(
        description="Exact name transcription from the original record"
    )
    name_variants: list[str] = Field(
        default_factory=list,
        description="Alternative spellings found in the record",
    )

    # Demographics
    birth_year: int | None = Field(default=None, ge=1500, le=2100)
    birth_year_confidence: ExtractionConfidence = Field(
        default=ExtractionConfidence.MEDIUM
    )
    age_at_census: int | None = Field(default=None, ge=0, le=150)
    birth_place: str | None = Field(default=None)
    birth_place_normalized: str | None = Field(default=None)

    # Census-specific
    relation_to_head: CensusMemberRole = Field(default=CensusMemberRole.OTHER)
    relation_as_recorded: str | None = Field(
        default=None,
        description="Exact relation text from record (e.g., 'Dau' for daughter)",
    )
    occupation: str | None = Field(default=None)
    marital_status: str | None = Field(default=None)
    sex: str | None = Field(default=None, description="M/F as recorded")
    race: str | None = Field(default=None, description="As recorded in census")

    # Additional census fields (varies by year)
    can_read: bool | None = Field(default=None)
    can_write: bool | None = Field(default=None)
    school_attendance: str | None = Field(default=None)
    citizenship: str | None = Field(default=None)
    immigration_year: int | None = Field(default=None)

    # Extraction metadata
    line_number: int | None = Field(
        default=None,
        description="Line number on census page",
    )
    extraction_confidence: ExtractionConfidence = Field(
        default=ExtractionConfidence.MEDIUM
    )
    citation_snippet: str | None = Field(
        default=None,
        description="Direct quote from record for GPS citation",
    )

    @computed_field
    @property
    def full_name(self) -> str:
        """Canonical full name."""
        parts = [self.given_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.surname)
        return " ".join(parts)

    @computed_field
    @property
    def search_key(self) -> str:
        """Unique key for deduplication and entity resolution."""
        return f"{self.given_name}|{self.surname}|{self.birth_year or ''}|{self.birth_place or ''}"

    def estimated_birth_year_from_age(self, census_year: int) -> int | None:
        """Calculate birth year from age at census."""
        if self.age_at_census is not None:
            return census_year - self.age_at_census
        return None


# =============================================================================
# Census Household (Enhanced for LLM-Native Extraction)
# =============================================================================


class StructuredCensusHousehold(BaseModel):
    """A complete household extracted from a census record.

    This is the primary extraction target for LLM-native web scraping.
    Designed to be returned directly from ScrapeGraphAI/Firecrawl.
    """

    # Identification
    id: UUID = Field(default_factory=uuid4)
    census_year: int = Field(ge=1790, le=2030, description="Year of the census")
    census_type: str = Field(
        default="federal",
        description="federal, state, territorial, etc.",
    )

    # Location hierarchy
    country: str = Field(default="United States")
    state: str = Field(description="State or territory")
    county: str = Field(description="County name")
    city_or_township: str | None = Field(default=None)
    enumeration_district: str | None = Field(
        default=None,
        description="E.D. number for census",
    )
    ward: str | None = Field(default=None)
    street_address: str | None = Field(default=None)
    dwelling_number: int | None = Field(default=None)
    family_number: int | None = Field(default=None)

    # Census page reference
    sheet_number: str | None = Field(default=None)
    page_number: str | None = Field(default=None)
    microfilm_roll: str | None = Field(default=None)

    # Household members
    head: StructuredCensusPerson | None = Field(
        default=None,
        description="Head of household",
    )
    members: list[StructuredCensusPerson] = Field(
        default_factory=list,
        description="All household members including head",
    )

    # Source provenance
    source_url: str | None = Field(default=None)
    source_repository: str | None = Field(
        default=None,
        description="FamilySearch, Ancestry, NARA, etc.",
    )
    source_collection: str | None = Field(default=None)
    image_url: str | None = Field(default=None)
    ark_id: str | None = Field(
        default=None,
        description="FamilySearch ARK identifier",
    )

    # Extraction metadata
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extractor_type: ExtractorType = Field(default=ExtractorType.LLM_STRUCTURED)
    extraction_confidence: ExtractionConfidence = Field(
        default=ExtractionConfidence.MEDIUM
    )
    raw_text_snippet: str | None = Field(
        default=None,
        description="Raw text used for extraction (for debugging)",
    )

    @computed_field
    @property
    def location_display(self) -> str:
        """Formatted location string."""
        parts = []
        if self.street_address:
            parts.append(self.street_address)
        if self.city_or_township:
            parts.append(self.city_or_township)
        parts.append(self.county)
        parts.append(self.state)
        return ", ".join(parts)

    @computed_field
    @property
    def citation_reference(self) -> str:
        """GPS-compliant citation reference."""
        ref = f"{self.census_year} U.S. Census, {self.county}, {self.state}"
        if self.enumeration_district:
            ref += f", ED {self.enumeration_district}"
        if self.sheet_number:
            ref += f", sheet {self.sheet_number}"
        if self.dwelling_number:
            ref += f", dwelling {self.dwelling_number}"
        if self.family_number:
            ref += f", family {self.family_number}"
        return ref

    @model_validator(mode="after")
    def set_head_from_members(self) -> "StructuredCensusHousehold":
        """Auto-detect head if not explicitly set."""
        if self.head is None and self.members:
            for member in self.members:
                if member.relation_to_head == CensusMemberRole.HEAD:
                    self.head = member
                    break
        return self

    def get_parents_of(self, person_name: str) -> list[StructuredCensusPerson]:
        """Find likely parents of a person in this household."""
        parents = []
        target_found = False

        # First, check if person is a child in this household
        for member in self.members:
            if person_name.lower() in member.full_name.lower():
                if member.relation_to_head in (
                    CensusMemberRole.SON,
                    CensusMemberRole.DAUGHTER,
                ):
                    target_found = True
                    break

        if target_found:
            for member in self.members:
                if member.relation_to_head in (
                    CensusMemberRole.HEAD,
                    CensusMemberRole.WIFE,
                    CensusMemberRole.HUSBAND,
                    CensusMemberRole.FATHER,
                    CensusMemberRole.MOTHER,
                ):
                    parents.append(member)

        return parents

    def get_siblings_of(self, person_name: str) -> list[StructuredCensusPerson]:
        """Find siblings of a person in this household."""
        siblings = []
        for member in self.members:
            if member.relation_to_head in (
                CensusMemberRole.SON,
                CensusMemberRole.DAUGHTER,
            ):
                if person_name.lower() not in member.full_name.lower():
                    siblings.append(member)
        return siblings

    def get_spouse_of_head(self) -> StructuredCensusPerson | None:
        """Get the spouse of the household head."""
        for member in self.members:
            if member.relation_to_head in (
                CensusMemberRole.WIFE,
                CensusMemberRole.HUSBAND,
            ):
                return member
        return None


# =============================================================================
# Extraction Result Wrapper
# =============================================================================

T = TypeVar("T", bound=BaseModel)


class ExtractionProvenance(BaseModel):
    """Provenance tracking for an extraction operation."""

    extraction_id: UUID = Field(default_factory=uuid4)
    source_url: str
    extractor_type: ExtractorType
    extractor_version: str = Field(default="1.0.0")

    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int | None = None

    # Token usage (for cost tracking)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None

    # Intermediate artifacts
    markdown_content: str | None = Field(
        default=None,
        description="Firecrawl markdown output before LLM extraction",
    )
    html_size_bytes: int | None = None
    markdown_size_bytes: int | None = None

    @computed_field
    @property
    def compression_ratio(self) -> float | None:
        """Calculate HTML→Markdown compression ratio."""
        if self.html_size_bytes and self.markdown_size_bytes:
            return 1 - (self.markdown_size_bytes / self.html_size_bytes)
        return None


class ExtractionResult(BaseModel, Generic[T]):
    """Generic wrapper for extraction results with full provenance.

    Example:
        result: ExtractionResult[StructuredCensusHousehold]
        if result.success:
            household = result.data
            print(f"Extracted {len(household.members)} people")
    """

    success: bool = Field(description="Whether extraction succeeded")
    data: T | None = Field(default=None, description="Extracted data if successful")
    error: str | None = Field(default=None, description="Error message if failed")
    error_type: str | None = Field(
        default=None,
        description="Exception class name",
    )

    provenance: ExtractionProvenance
    confidence: ExtractionConfidence = Field(default=ExtractionConfidence.MEDIUM)

    # GPS compliance hints
    citation_ready: bool = Field(
        default=False,
        description="Whether data includes citation snippets",
    )
    needs_verification: bool = Field(
        default=True,
        description="Whether LLM verification is recommended",
    )

    # Warnings (non-fatal issues)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def success_result(
        cls,
        data: T,
        provenance: ExtractionProvenance,
        confidence: ExtractionConfidence = ExtractionConfidence.MEDIUM,
        citation_ready: bool = False,
        warnings: list[str] | None = None,
    ) -> "ExtractionResult[T]":
        """Create a successful extraction result."""
        provenance.completed_at = datetime.now(UTC)
        if provenance.started_at:
            delta = provenance.completed_at - provenance.started_at
            provenance.duration_ms = int(delta.total_seconds() * 1000)

        return cls(
            success=True,
            data=data,
            provenance=provenance,
            confidence=confidence,
            citation_ready=citation_ready,
            needs_verification=confidence in (
                ExtractionConfidence.LOW,
                ExtractionConfidence.INFERRED,
            ),
            warnings=warnings or [],
        )

    @classmethod
    def failure_result(
        cls,
        error: str,
        provenance: ExtractionProvenance,
        error_type: str | None = None,
    ) -> "ExtractionResult[T]":
        """Create a failed extraction result."""
        provenance.completed_at = datetime.now(UTC)
        return cls(
            success=False,
            error=error,
            error_type=error_type,
            provenance=provenance,
            confidence=ExtractionConfidence.LOW,
        )


# =============================================================================
# LLM Extraction Schemas (for structured output)
# =============================================================================


class CensusExtractionPrompt(BaseModel):
    """Input schema for LLM census extraction."""

    html_or_markdown: str = Field(description="Page content to extract from")
    hint_name: str | None = Field(
        default=None,
        description="Name of person to focus on (if known)",
    )
    hint_year: int | None = Field(
        default=None,
        description="Expected census year",
    )
    hint_location: str | None = Field(
        default=None,
        description="Expected location",
    )
    extract_all_members: bool = Field(
        default=True,
        description="Whether to extract all household members",
    )


class BatchExtractionResult(BaseModel):
    """Result of extracting multiple households from a search results page."""

    households: list[StructuredCensusHousehold] = Field(default_factory=list)
    total_found: int = Field(default=0)
    has_more: bool = Field(default=False)
    next_page_url: str | None = None
    provenance: ExtractionProvenance
