"""LLM wrappers for publishing review roles.

Provides GPS Grader, Logic Reviewer, and Source Reviewer LLM wrappers
for the publishing quorum system.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, Field

from ..llm.wrapper import LLMClient, StructuredLLMWrapper

from .models import (
    GPSGradeCard,
    GPSPillar,
    GPSPillarScore,
    ReviewerType,
    ReviewIssue,
    ReviewVerdict,
    Severity,
    Verdict,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# GPS Grader Schemas
# =============================================================================


class GPSGraderInput(BaseModel):
    """Input for GPS Grader LLM."""

    subject_id: str = Field(description="ID of the person being graded")
    subject_name: str = Field(description="Name of the person")

    # Evidence summary
    source_count: int = Field(description="Total number of sources consulted")
    source_tiers: dict[str, int] = Field(
        description="Count of sources by tier (tier_0, tier_1, tier_2)",
    )
    citation_count: int = Field(description="Number of properly cited claims")
    total_claims: int = Field(description="Total number of claims")

    # Research quality indicators
    conflicts_found: int = Field(description="Number of conflicts identified")
    conflicts_resolved: int = Field(description="Number of conflicts resolved")
    uncertainties_documented: int = Field(
        description="Number of uncertainties in Paper Trail of Doubt",
    )

    # Conclusion status
    has_written_conclusion: bool = Field(
        description="Whether a written proof argument exists",
    )
    conclusion_summary: str = Field(
        default="",
        description="Brief summary of the conclusion (if exists)",
    )

    # Additional context
    research_notes_count: int = Field(
        default=0,
        description="Number of research notes documenting methodology",
    )
    years_covered: str = Field(
        default="",
        description="Date range of research (e.g., '1850-1920')",
    )


class GPSGraderOutput(BaseModel):
    """Output from GPS Grader LLM."""

    pillar_scores: list[GPSPillarScore] = Field(
        min_length=5,
        max_length=5,
        description="Scores for all 5 GPS pillars",
    )
    reasoning: str = Field(description="Overall grading rationale")


# =============================================================================
# Logic Reviewer Schemas
# =============================================================================


class LogicReviewerInput(BaseModel):
    """Input for Logic Reviewer LLM."""

    subject_id: str = Field(description="ID of the person being reviewed")
    subject_name: str = Field(description="Name of the person")

    # Timeline data
    events: list[dict] = Field(
        description="List of events with dates and types",
    )
    birth_date: str | None = Field(default=None)
    death_date: str | None = Field(default=None)

    # Relationship data
    relationships: list[dict] = Field(
        default_factory=list,
        description="List of relationships with types and dates",
    )

    # Claims to review
    claims: list[dict] = Field(
        description="List of claims with source refs and values",
    )


class LogicReviewerOutput(BaseModel):
    """Output from Logic Reviewer LLM."""

    verdict: Verdict
    issues: list[ReviewIssue] = Field(default_factory=list)
    rationale: str = Field(description="Explanation for the verdict")

    # Specific checks
    timeline_consistent: bool = Field(
        description="Whether all events are chronologically possible",
    )
    relationships_valid: bool = Field(
        description="Whether relationships are logically consistent",
    )
    no_impossible_claims: bool = Field(
        description="Whether all claims are physically possible",
    )


# =============================================================================
# Source Reviewer Schemas
# =============================================================================


class SourceReviewerInput(BaseModel):
    """Input for Source Reviewer LLM."""

    subject_id: str = Field(description="ID of the person being reviewed")
    subject_name: str = Field(description="Name of the person")

    # Citation data
    claims_with_citations: list[dict] = Field(
        description="Claims paired with their citations",
    )

    # Source quality data
    source_summaries: list[dict] = Field(
        description="Summary of each source (tier, type, reliability)",
    )

    # Evidence support
    key_facts: list[dict] = Field(
        description="Key biographical facts to verify",
    )


class SourceReviewerOutput(BaseModel):
    """Output from Source Reviewer LLM."""

    verdict: Verdict
    issues: list[ReviewIssue] = Field(default_factory=list)
    rationale: str = Field(description="Explanation for the verdict")

    # Specific checks
    citations_valid: bool = Field(
        description="Whether all citations point to real sources",
    )
    evidence_sufficient: bool = Field(
        description="Whether evidence adequately supports claims",
    )
    no_fabricated_sources: bool = Field(
        description="Whether all sources appear legitimate",
    )


# =============================================================================
# LLM Wrapper Classes
# =============================================================================


class GPSGraderLLM:
    """LLM wrapper for GPS pillar grading."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="gps_grader",
            input_schema=GPSGraderInput,
            output_schema=GPSGraderOutput,
            temperature=0.1,  # Slight creativity for nuanced grading
        )

    def grade(self, input_data: GPSGraderInput) -> GPSGradeCard:
        """Grade research against GPS pillars.

        Args:
            input_data: GPS grader input with evidence summary

        Returns:
            Complete GPS Grade Card with computed properties
        """
        output = self._wrapper.invoke(input_data)

        return GPSGradeCard(
            subject_id=input_data.subject_id,
            pillar_scores=output.pillar_scores,
            grader_model="gps_grader_llm",
        )


class PublishingLogicReviewerLLM:
    """LLM wrapper for logic/consistency review in publishing quorum."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="publishing_logic_reviewer",
            input_schema=LogicReviewerInput,
            output_schema=LogicReviewerOutput,
            temperature=0.0,  # Deterministic for verification
        )

    def review(self, input_data: LogicReviewerInput, model: str = "") -> ReviewVerdict:
        """Review research for logical consistency.

        Args:
            input_data: Logic reviewer input with timeline/relationships
            model: Model identifier for audit trail

        Returns:
            Review verdict with issues and rationale
        """
        output = self._wrapper.invoke(input_data)

        return ReviewVerdict(
            reviewer_type=ReviewerType.LOGIC_REVIEWER,
            verdict=output.verdict,
            issues=output.issues,
            rationale=output.rationale,
            reviewer_model=model or "publishing_logic_reviewer_llm",
        )


class PublishingSourceReviewerLLM:
    """LLM wrapper for source/citation review in publishing quorum."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="publishing_source_reviewer",
            input_schema=SourceReviewerInput,
            output_schema=SourceReviewerOutput,
            temperature=0.0,  # Deterministic for verification
        )

    def review(self, input_data: SourceReviewerInput, model: str = "") -> ReviewVerdict:
        """Review research for source/citation validity.

        Args:
            input_data: Source reviewer input with citations/sources
            model: Model identifier for audit trail

        Returns:
            Review verdict with issues and rationale
        """
        output = self._wrapper.invoke(input_data)

        return ReviewVerdict(
            reviewer_type=ReviewerType.SOURCE_REVIEWER,
            verdict=output.verdict,
            issues=output.issues,
            rationale=output.rationale,
            reviewer_model=model or "publishing_source_reviewer_llm",
        )


# =============================================================================
# Linguist Agent Schemas
# =============================================================================


class AcceptedFact(BaseModel):
    """A verified fact that has been accepted for publishing.

    Only facts with status="ACCEPTED" and confidence >= 0.9 should be used.
    """

    field: str = Field(description="The field name (e.g., 'birth_date', 'death_place')")
    value: str = Field(description="The verified value")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (must be >= 0.9 for publishing)",
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="References to supporting sources",
    )
    source_tier: str = Field(
        default="tier_1",
        description="Source tier (tier_0=primary official, tier_1=primary, tier_2=secondary)",
    )


class LinguistInput(BaseModel):
    """Input for Linguist Agent LLM."""

    subject_id: str = Field(description="ID of the person")
    subject_name: str = Field(description="Full name of the person")

    # Only ACCEPTED facts with confidence >= 0.9
    accepted_facts: list[AcceptedFact] = Field(
        description="Verified facts to include in content (status=ACCEPTED, confidence>=0.9)",
    )

    # Uncertainties to document
    uncertainties: list[dict] = Field(
        default_factory=list,
        description="Documented uncertainties (field, description, confidence_level)",
    )

    # Unresolved conflicts to note
    unresolved_conflicts: list[dict] = Field(
        default_factory=list,
        description="Unresolved conflicts (field, competing_claims, remaining_doubt)",
    )

    # Existing identifiers
    wikidata_qid: str | None = Field(
        default=None,
        description="Existing Wikidata QID if known",
    )
    wikitree_id: str | None = Field(
        default=None,
        description="Existing WikiTree ID if known",
    )

    # Output targets
    generate_wikipedia: bool = Field(
        default=True,
        description="Whether to generate Wikipedia draft",
    )
    generate_wikitree: bool = Field(
        default=True,
        description="Whether to generate WikiTree biography",
    )
    generate_diff: bool = Field(
        default=True,
        description="Whether to generate DIFF for local Markdown",
    )


class WikipediaDraft(BaseModel):
    """Wikipedia article draft."""

    lead_paragraph: str = Field(description="Encyclopedic lead paragraph (NPOV)")
    infobox_wikitext: str = Field(description="Infobox wikitext for the person")
    categories: list[str] = Field(
        default_factory=list,
        description="Suggested Wikipedia categories",
    )


class WikiTreeBio(BaseModel):
    """WikiTree biography draft."""

    narrative: str = Field(description="Collaborative narrative biography")
    research_notes: str = Field(description="Notes for other genealogists")
    templates_used: list[str] = Field(
        default_factory=list,
        description="WikiTree templates used (e.g., {{Birth Date and Age}})",
    )


class GPSPillar5Grade(BaseModel):
    """GPS Pillar 5 (Written Conclusion) grading."""

    score: float = Field(ge=1.0, le=10.0, description="Score from 1-10")
    rationale: str = Field(description="Explanation for the score")
    improvements_needed: list[str] = Field(
        default_factory=list,
        description="Specific improvements to reach 10/10",
    )


class LinguistOutput(BaseModel):
    """Output from Linguist Agent LLM."""

    # GPS Grade Card for Pillar 5
    gps_pillar_5_grade: GPSPillar5Grade = Field(
        description="Grade for GPS Pillar 5 (Written Conclusion)",
    )

    # Wikipedia output (if requested)
    wikipedia_draft: WikipediaDraft | None = Field(
        default=None,
        description="Wikipedia article draft",
    )

    # WikiTree output (if requested)
    wikitree_bio: WikiTreeBio | None = Field(
        default=None,
        description="WikiTree biography draft",
    )

    # DIFF for local Markdown (if requested)
    markdown_diff: str | None = Field(
        default=None,
        description="Unified diff for local Markdown file improvements",
    )

    # Research notes section
    research_notes: str = Field(
        description="RESEARCH_NOTES section documenting uncertainties and next actions",
    )

    # Overall assessment
    is_publication_ready: bool = Field(
        description="Whether content meets minimum publication standards",
    )
    blocking_issues: list[str] = Field(
        default_factory=list,
        description="Issues that block publication",
    )


# =============================================================================
# Linguist Agent LLM Wrapper
# =============================================================================


class LinguistLLM:
    """LLM wrapper for content generation in Wikipedia and WikiTree styles.

    The Linguist Agent specializes in:
    - Wikipedia: Encyclopedic NPOV (Neutral Point of View)
    - WikiTree: Collaborative narrative voice

    CONSTRAINT: Only consumes ACCEPTED facts with confidence >= 0.9.
    """

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="linguist",
            input_schema=LinguistInput,
            output_schema=LinguistOutput,
            temperature=0.3,  # Some creativity for narrative generation
        )

    @staticmethod
    def filter_accepted_facts(
        facts: list[dict],
        min_confidence: float = 0.9,
    ) -> list[AcceptedFact]:
        """Filter facts to only include ACCEPTED with confidence >= threshold.

        Args:
            facts: Raw facts with status and confidence fields
            min_confidence: Minimum confidence threshold (default 0.9)

        Returns:
            List of AcceptedFact objects meeting the criteria
        """
        accepted = []
        for fact in facts:
            if fact.get("status") != "ACCEPTED":
                continue
            if fact.get("confidence", 0.0) < min_confidence:
                continue

            accepted.append(
                AcceptedFact(
                    field=fact.get("field", ""),
                    value=fact.get("value", ""),
                    confidence=fact.get("confidence", 0.9),
                    source_refs=fact.get("source_refs", []),
                    source_tier=fact.get("source_tier", "tier_1"),
                )
            )
        return accepted

    def generate(self, input_data: LinguistInput, model: str = "") -> LinguistOutput:
        """Generate wiki content from accepted facts.

        Args:
            input_data: Linguist input with accepted facts and options
            model: Model identifier for audit trail

        Returns:
            LinguistOutput with Wikipedia draft, WikiTree bio, DIFF, and GPS grade
        """
        return self._wrapper.invoke(input_data)


# =============================================================================
# Media & Photo Agent Schemas
# =============================================================================


from enum import Enum


class PhotoSource(str, Enum):
    """Supported photo sources for genealogical media."""

    FIND_A_GRAVE = "find_a_grave"
    WIKITREE = "wikitree"
    WIKIMEDIA_COMMONS = "wikimedia_commons"
    FAMILYSEARCH = "familysearch"
    ANCESTRY = "ancestry"
    OTHER = "other"


class MediaLicense(str, Enum):
    """Supported licenses for media publishing."""

    CC0 = "CC0"
    CC_BY = "CC-BY"
    CC_BY_SA = "CC-BY-SA"
    PUBLIC_DOMAIN = "Public Domain"
    FAIR_USE = "Fair Use"
    ALL_RIGHTS_RESERVED = "All Rights Reserved"
    UNKNOWN = "Unknown"


class MediaType(str, Enum):
    """Types of genealogical media."""

    HEADSTONE = "headstone"
    PORTRAIT = "portrait"
    CERTIFICATE = "certificate"
    DOCUMENT = "document"
    NEWSPAPER_CLIPPING = "newspaper_clipping"
    MAP = "map"
    OTHER = "other"


class SubjectConfidence(str, Enum):
    """Confidence level that photo depicts the claimed subject."""

    HIGH = "high"  # Explicit confirmation in record (name on headstone, caption)
    MEDIUM = "medium"  # Inferred from context (album, family collection)
    LOW = "low"  # Subject identity not confirmed by record
    UNKNOWN = "unknown"  # No information available


class PhotoTarget(BaseModel):
    """A discovered photo target from research sources."""

    url: str = Field(description="Full URL to the photo")
    source: PhotoSource = Field(description="Source platform")
    media_type: MediaType = Field(description="Type of media")
    subject_id: str = Field(description="ID of the person this photo relates to")
    subject_name: str = Field(description="Name of the person")
    caption: str = Field(default="", description="Discovered caption or description")
    license_detected: MediaLicense = Field(
        default=MediaLicense.UNKNOWN,
        description="Detected license from source",
    )
    source_page_url: str = Field(
        default="",
        description="URL of the page where photo was found",
    )
    date_photographed: str | None = Field(
        default=None,
        description="Date the photo was taken (if known)",
    )
    photographer: str | None = Field(
        default=None,
        description="Photographer or uploader name",
    )

    # New fields for compliance
    evidence_claim_id: str | None = Field(
        default=None,
        description="ID of the EvidenceClaim that links to this photo (required for download)",
    )
    subject_confidence: SubjectConfidence = Field(
        default=SubjectConfidence.UNKNOWN,
        description="Confidence that photo depicts claimed subject",
    )
    confidence_rationale: str = Field(
        default="",
        description="Reason for confidence level assignment",
    )


class MediaMetadata(BaseModel):
    """Sidecar JSON metadata for a downloaded media file.

    This follows DevOps standards for organizing genealogical attachments.
    Directory format: research/persons/{surname-firstname-birthyear}/media/
    """

    subject_id: str = Field(description="ID of the person")
    subject_name: str = Field(description="Name of the person")
    surname: str = Field(description="Surname for directory organization")
    caption: str = Field(description="Caption for the media")
    license: MediaLicense = Field(description="License for the media")
    repository_url: str = Field(description="Original source URL")
    source: PhotoSource = Field(description="Source platform")
    media_type: MediaType = Field(description="Type of media")

    # Additional metadata
    date_photographed: str | None = Field(default=None)
    photographer: str | None = Field(default=None)
    date_downloaded: str = Field(description="ISO timestamp when downloaded")
    local_filename: str = Field(description="Local filename after download")
    local_directory: str = Field(description="Local directory path")

    # UUID7 ledger tracking
    ledger_uuid: str = Field(
        description="UUID7 for ledger tracking (appended to filename)",
    )
    original_filename: str = Field(
        default="",
        description="Original filename before UUID7 was appended",
    )

    # Evidence linkage
    evidence_claim_id: str | None = Field(
        default=None,
        description="ID of the EvidenceClaim that authorized this download",
    )

    # Subject confidence
    subject_confidence: SubjectConfidence = Field(
        default=SubjectConfidence.UNKNOWN,
        description="Confidence that photo depicts claimed subject",
    )
    confidence_rationale: str = Field(
        default="",
        description="Reason for confidence level assignment",
    )

    # Verification
    license_verified: bool = Field(
        default=False,
        description="Whether license was manually verified",
    )
    sync_targets: list[str] = Field(
        default_factory=list,
        description="Allowed sync targets based on license (wikipedia, github, wikitree)",
    )


class DownloadQueueItem(BaseModel):
    """An item in the download queue.

    COMPLIANCE: Download is only allowed if evidence_claim_id is set.
    """

    photo_target: PhotoTarget = Field(description="The photo to download")
    priority: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Download priority (1=highest, 5=lowest)",
    )
    local_path: str = Field(description="Target local path for download")
    sidecar_path: str = Field(description="Path for sidecar JSON metadata")
    ledger_uuid: str = Field(description="UUID7 for ledger tracking")
    status: str = Field(
        default="pending",
        description="Download status (pending, downloading, completed, failed, blocked)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if download failed",
    )

    # Validation status
    is_valid_for_download: bool = Field(
        default=False,
        description="Whether download is allowed (requires valid EvidenceClaim)",
    )
    validation_errors: list[str] = Field(
        default_factory=list,
        description="List of validation errors blocking download",
    )

    def validate_for_download(self) -> bool:
        """Check if this item is valid for download.

        Returns:
            True if download is allowed, False otherwise
        """
        self.validation_errors = []

        # COMPLIANCE: Never download without valid EvidenceClaim link
        if not self.photo_target.evidence_claim_id:
            self.validation_errors.append(
                "No EvidenceClaim ID - download blocked per compliance rules"
            )

        # Check license
        if self.photo_target.license_detected == MediaLicense.UNKNOWN:
            self.validation_errors.append(
                "Unknown license - verify before download"
            )

        if self.photo_target.license_detected == MediaLicense.ALL_RIGHTS_RESERVED:
            self.validation_errors.append(
                "All Rights Reserved - cannot download"
            )

        self.is_valid_for_download = len(self.validation_errors) == 0
        if not self.is_valid_for_download:
            self.status = "blocked"

        return self.is_valid_for_download


class MediaPhotoAgentInput(BaseModel):
    """Input for Media & Photo Agent LLM.

    COMPLIANCE: Photos are only discovered through EvidenceClaims. Never download
    a file without a valid EvidenceClaim link.
    """

    subject_id: str = Field(description="ID of the person")
    subject_name: str = Field(description="Name of the person")
    surname: str = Field(description="Surname for directory organization")
    firstname: str = Field(default="", description="First name for directory path")
    birth_year: str | None = Field(
        default=None,
        description="Birth year for directory path (e.g., '1850')",
    )

    # EvidenceClaim references (primary source for photo discovery)
    evidence_claims: list[dict] = Field(
        default_factory=list,
        description="EvidenceClaims to scan for photo URLs (id, source_url, claim_text)",
    )

    # Research context (secondary - URLs must be linked to EvidenceClaims)
    research_sources: list[dict] = Field(
        default_factory=list,
        description="Sources from research with URLs to check for photos",
    )

    # Discovered photo URLs (from sources like Find A Grave, WikiTree, etc.)
    discovered_urls: list[str] = Field(
        default_factory=list,
        description="URLs discovered during research that may contain photos",
    )

    # Target platforms
    target_wikipedia: bool = Field(
        default=True,
        description="Whether photos are intended for Wikipedia",
    )
    target_github: bool = Field(
        default=True,
        description="Whether photos are intended for GitHub archive",
    )
    target_wikitree: bool = Field(
        default=True,
        description="Whether photos are intended for WikiTree",
    )

    # DevOps configuration
    base_output_directory: str = Field(
        default="research/persons",
        description="Base directory for DevOps standard: research/persons/{surname-firstname-birthyear}/media/",
    )


class MediaPhotoAgentOutput(BaseModel):
    """Output from Media & Photo Agent LLM.

    Returns a Download Queue of URLs with intended local paths and metadata schemas.
    """

    # Discovered photos
    photo_targets: list[PhotoTarget] = Field(
        default_factory=list,
        description="Identified photos with metadata",
    )

    # Download queue
    download_queue: list[DownloadQueueItem] = Field(
        default_factory=list,
        description="Prioritized download queue",
    )

    # Generated sidecar metadata
    sidecar_files: list[MediaMetadata] = Field(
        default_factory=list,
        description="Sidecar JSON metadata to write",
    )

    # License verification results
    license_issues: list[dict] = Field(
        default_factory=list,
        description="Photos with license issues blocking sync",
    )

    # Validation results
    compliance_blocked: list[dict] = Field(
        default_factory=list,
        description="Photos blocked due to compliance (no EvidenceClaim link)",
    )
    low_confidence_warnings: list[dict] = Field(
        default_factory=list,
        description="Photos flagged as Low Confidence (subject not confirmed)",
    )

    # Summary
    total_photos_found: int = Field(default=0)
    photos_valid_for_download: int = Field(default=0)
    photos_blocked_compliance: int = Field(default=0)
    photos_low_confidence: int = Field(default=0)
    photos_allowed_wikipedia: int = Field(default=0)
    photos_allowed_github: int = Field(default=0)
    photos_allowed_wikitree: int = Field(default=0)

    # Directory structure
    directory_structure: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Proposed directory structure (path -> files)",
    )


# =============================================================================
# Media & Photo Agent LLM Wrapper
# =============================================================================


class MediaPhotoAgentLLM:
    """LLM wrapper for media and photo management.

    The Media & Photo Agent manages:
    - EVIDENCE DISCOVERY: Scan EvidenceClaims for photo URLs from Find A Grave, WikiTree, Wikimedia Commons
    - METADATA WRITING: Generate sidecar JSON files with subject_id, caption, license, timestamp
    - SOURCE VERIFICATION: Ensure licenses allow intended sync (CC0, CC-BY, Public Domain)
    - ORGANIZATION: Organize into surname-centric directories per DevOps standards

    COMPLIANCE RULES:
    - Never download a file without a valid EvidenceClaim link
    - Preserve original filenames but append unique UUID7 for ledger tracking
    - Flag "Low Confidence" for photos where subject identity is not confirmed
    """

    # License compatibility mapping
    LICENSE_SYNC_TARGETS: dict[MediaLicense, list[str]] = {
        MediaLicense.CC0: ["wikipedia", "github", "wikitree"],
        MediaLicense.CC_BY: ["wikipedia", "github", "wikitree"],
        MediaLicense.CC_BY_SA: ["wikipedia", "github", "wikitree"],
        MediaLicense.PUBLIC_DOMAIN: ["wikipedia", "github", "wikitree"],
        MediaLicense.FAIR_USE: ["github"],  # Not suitable for Wikipedia
        MediaLicense.ALL_RIGHTS_RESERVED: [],  # Cannot sync anywhere
        MediaLicense.UNKNOWN: [],  # Must verify before sync
    }

    # Media type priority mapping (headstones highest priority)
    MEDIA_PRIORITY: dict[MediaType, int] = {
        MediaType.HEADSTONE: 1,
        MediaType.PORTRAIT: 2,
        MediaType.CERTIFICATE: 3,
        MediaType.DOCUMENT: 4,
        MediaType.NEWSPAPER_CLIPPING: 5,
        MediaType.MAP: 5,
        MediaType.OTHER: 5,
    }

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="media_photo_agent",
            input_schema=MediaPhotoAgentInput,
            output_schema=MediaPhotoAgentOutput,
            temperature=0.0,  # Deterministic for metadata generation
        )

    @staticmethod
    def generate_uuid7() -> str:
        """Generate a UUID7 for ledger tracking.

        UUID7 is time-ordered, making it suitable for chronological tracking.

        Returns:
            UUID7 string (e.g., "0190c8a2-7e3b-7000-8000-000000000001")
        """
        import time
        import uuid

        # UUID7: time-ordered UUID (timestamp + random)
        # Use UUID4 as fallback since uuid7 requires Python 3.12+ or uuid-utils
        try:
            # Try to use uuid7 if available
            from uuid import uuid7  # type: ignore[attr-defined]
            return str(uuid7())
        except (ImportError, AttributeError):
            # Fallback: Create a time-prefixed UUID4
            timestamp_ms = int(time.time() * 1000)
            random_uuid = uuid.uuid4()
            # Combine timestamp and random components
            return f"{timestamp_ms:013x}-{str(random_uuid)[14:]}"

    @staticmethod
    def get_allowed_sync_targets(license: MediaLicense) -> list[str]:
        """Get allowed sync targets for a given license.

        Args:
            license: The media license

        Returns:
            List of allowed targets (wikipedia, github, wikitree)
        """
        return MediaPhotoAgentLLM.LICENSE_SYNC_TARGETS.get(license, [])

    @staticmethod
    def get_media_priority(media_type: MediaType) -> int:
        """Get download priority for a media type.

        Args:
            media_type: The type of media

        Returns:
            Priority (1=highest, 5=lowest)
        """
        return MediaPhotoAgentLLM.MEDIA_PRIORITY.get(media_type, 5)

    @staticmethod
    def generate_directory_path(
        base_directory: str,
        surname: str,
        firstname: str = "",
        birth_year: str | None = None,
    ) -> str:
        """Generate directory path per DevOps standards.

        Format: research/persons/{surname-firstname-birthyear}/media/

        Args:
            base_directory: Base output directory (usually "research/persons")
            surname: Subject's surname
            firstname: Subject's first name
            birth_year: Subject's birth year (e.g., "1850")

        Returns:
            Directory path (e.g., "research/persons/smith-john-1850/media/")
        """
        # Normalize names
        surname_clean = surname.lower().replace(" ", "-")
        firstname_clean = firstname.lower().replace(" ", "-") if firstname else ""

        # Build directory name
        parts = [surname_clean]
        if firstname_clean:
            parts.append(firstname_clean)
        if birth_year:
            parts.append(birth_year)

        dir_name = "-".join(parts)
        return f"{base_directory}/{dir_name}/media/"

    @staticmethod
    def generate_filename_with_uuid7(
        original_filename: str,
        ledger_uuid: str,
    ) -> str:
        """Generate filename with UUID7 appended for ledger tracking.

        Args:
            original_filename: Original filename from source
            ledger_uuid: UUID7 for tracking

        Returns:
            Filename with UUID7 (e.g., "headstone.jpg" -> "headstone_0190c8a2.jpg")
        """
        import os

        base, ext = os.path.splitext(original_filename)
        # Use first 8 chars of UUID for brevity
        short_uuid = ledger_uuid.replace("-", "")[:8]
        return f"{base}_{short_uuid}{ext}"

    @staticmethod
    def generate_sidecar_filename(local_filename: str) -> str:
        """Generate sidecar JSON filename for a media file.

        Args:
            local_filename: The media filename

        Returns:
            Sidecar filename (e.g., "headstone_001.jpg" -> "headstone_001.json")
        """
        import os

        base, _ = os.path.splitext(local_filename)
        return f"{base}.json"

    def process(
        self,
        input_data: MediaPhotoAgentInput,
        model: str = "",
    ) -> MediaPhotoAgentOutput:
        """Process research sources to discover and catalog photos.

        Args:
            input_data: Media agent input with sources and URLs
            model: Model identifier for audit trail

        Returns:
            MediaPhotoAgentOutput with download queue and sidecar metadata
        """
        return self._wrapper.invoke(input_data)

    def create_sidecar_metadata(
        self,
        photo_target: PhotoTarget,
        original_filename: str,
        base_directory: str,
        firstname: str = "",
        birth_year: str | None = None,
        ledger_uuid: str | None = None,
        target_wikipedia: bool = True,
        target_github: bool = True,
        target_wikitree: bool = True,
    ) -> MediaMetadata:
        """Create sidecar metadata for a photo target.

        Args:
            photo_target: The photo target with source info
            original_filename: Original filename before UUID7 appending
            base_directory: Base output directory
            firstname: Subject's first name for directory path
            birth_year: Subject's birth year for directory path
            ledger_uuid: UUID7 for ledger tracking (generated if not provided)
            target_wikipedia: Whether Wikipedia sync is intended
            target_github: Whether GitHub sync is intended
            target_wikitree: Whether WikiTree sync is intended

        Returns:
            MediaMetadata sidecar data
        """
        from datetime import UTC, datetime

        # Extract surname from subject name
        surname = photo_target.subject_name.split()[-1] if photo_target.subject_name else "unknown"

        # Generate UUID7 for ledger tracking
        if ledger_uuid is None:
            ledger_uuid = self.generate_uuid7()

        # Generate filename with UUID7 appended
        local_filename = self.generate_filename_with_uuid7(original_filename, ledger_uuid)

        # Generate directory path per DevOps standard
        local_directory = self.generate_directory_path(
            base_directory,
            surname,
            firstname,
            birth_year,
        )

        # Determine allowed sync targets based on license
        allowed_targets = self.get_allowed_sync_targets(photo_target.license_detected)

        # Filter to requested targets
        sync_targets = []
        if target_wikipedia and "wikipedia" in allowed_targets:
            sync_targets.append("wikipedia")
        if target_github and "github" in allowed_targets:
            sync_targets.append("github")
        if target_wikitree and "wikitree" in allowed_targets:
            sync_targets.append("wikitree")

        return MediaMetadata(
            subject_id=photo_target.subject_id,
            subject_name=photo_target.subject_name,
            surname=surname,
            caption=photo_target.caption,
            license=photo_target.license_detected,
            repository_url=photo_target.url,
            source=photo_target.source,
            media_type=photo_target.media_type,
            date_photographed=photo_target.date_photographed,
            photographer=photo_target.photographer,
            date_downloaded=datetime.now(UTC).isoformat(),
            local_filename=local_filename,
            local_directory=local_directory,
            ledger_uuid=ledger_uuid,
            original_filename=original_filename,
            evidence_claim_id=photo_target.evidence_claim_id,
            subject_confidence=photo_target.subject_confidence,
            confidence_rationale=photo_target.confidence_rationale,
            license_verified=False,
            sync_targets=sync_targets,
        )

    def create_download_queue_item(
        self,
        photo_target: PhotoTarget,
        base_directory: str,
        firstname: str = "",
        birth_year: str | None = None,
        priority: int | None = None,
        validate: bool = True,
    ) -> DownloadQueueItem:
        """Create a download queue item for a photo target.

        COMPLIANCE: Validates that EvidenceClaim link exists before allowing download.

        Args:
            photo_target: The photo to download
            base_directory: Base output directory
            firstname: Subject's first name for directory path
            birth_year: Subject's birth year for directory path
            priority: Download priority (1=highest), auto-assigned from media type if not provided
            validate: Whether to run compliance validation

        Returns:
            DownloadQueueItem ready for processing (may be blocked if validation fails)
        """
        import os
        from urllib.parse import urlparse

        # Extract surname
        surname = photo_target.subject_name.split()[-1] if photo_target.subject_name else "unknown"

        # Generate UUID7 for ledger tracking
        ledger_uuid = self.generate_uuid7()

        # Auto-assign priority based on media type if not provided
        if priority is None:
            priority = self.get_media_priority(photo_target.media_type)

        # Generate directory path per DevOps standard
        local_directory = self.generate_directory_path(
            base_directory,
            surname,
            firstname,
            birth_year,
        )

        # Extract original filename from URL
        url_path = urlparse(photo_target.url).path
        original_filename = os.path.basename(url_path) if url_path else ""
        if not original_filename:
            extension = ".jpg"
            original_filename = f"{photo_target.media_type.value}_{photo_target.subject_id}{extension}"
        extension = os.path.splitext(original_filename)[1] or ".jpg"

        # Generate filename with UUID7 appended
        local_filename = self.generate_filename_with_uuid7(original_filename, ledger_uuid)

        local_path = f"{local_directory}{local_filename}"
        sidecar_path = f"{local_directory}{self.generate_sidecar_filename(local_filename)}"

        queue_item = DownloadQueueItem(
            photo_target=photo_target,
            priority=priority,
            local_path=local_path,
            sidecar_path=sidecar_path,
            ledger_uuid=ledger_uuid,
            status="pending",
        )

        # Run compliance validation
        if validate:
            queue_item.validate_for_download()

        return queue_item

    def scan_evidence_claims_for_photos(
        self,
        evidence_claims: list[dict],
        subject_id: str,
        subject_name: str,
    ) -> list[PhotoTarget]:
        """Scan EvidenceClaims for photo URLs.

        COMPLIANCE: This is the primary source for photo discovery.

        Args:
            evidence_claims: List of EvidenceClaim dicts with 'id', 'source_url', 'claim_text'
            subject_id: ID of the subject
            subject_name: Name of the subject

        Returns:
            List of PhotoTarget objects discovered from EvidenceClaims
        """
        import re

        photo_targets = []

        # Photo URL patterns for supported sources
        patterns = {
            PhotoSource.FIND_A_GRAVE: [
                r"findagrave\.com/.*\.jpe?g",
                r"findagrave\.com/.*photo",
            ],
            PhotoSource.WIKITREE: [
                r"wikitree\.com/photo\.php",
                r"wikitree\.com/.*\.jpe?g",
            ],
            PhotoSource.WIKIMEDIA_COMMONS: [
                r"commons\.wikimedia\.org/.*File:",
                r"upload\.wikimedia\.org/.*",
            ],
            PhotoSource.FAMILYSEARCH: [
                r"familysearch\.org/.*\.jpe?g",
                r"familysearch\.org/.*image",
            ],
        }

        for claim in evidence_claims:
            claim_id = claim.get("id", "")
            source_url = claim.get("source_url", "")
            claim_text = claim.get("claim_text", "")

            # Check URL and text for photo patterns
            text_to_search = f"{source_url} {claim_text}"

            for source, source_patterns in patterns.items():
                for pattern in source_patterns:
                    matches = re.findall(pattern, text_to_search, re.IGNORECASE)
                    for match in matches:
                        # Determine media type from URL
                        media_type = MediaType.OTHER
                        if "headstone" in match.lower() or "grave" in match.lower():
                            media_type = MediaType.HEADSTONE
                        elif "portrait" in match.lower() or "photo" in match.lower():
                            media_type = MediaType.PORTRAIT

                        # Determine confidence
                        confidence = SubjectConfidence.UNKNOWN
                        rationale = ""
                        if subject_name.lower() in claim_text.lower():
                            confidence = SubjectConfidence.HIGH
                            rationale = "Subject name found in claim text"
                        elif "headstone" in match.lower():
                            confidence = SubjectConfidence.MEDIUM
                            rationale = "Headstone photo from memorial"

                        photo_targets.append(PhotoTarget(
                            url=match if match.startswith("http") else f"https://{match}",
                            source=source,
                            media_type=media_type,
                            subject_id=subject_id,
                            subject_name=subject_name,
                            evidence_claim_id=claim_id,
                            subject_confidence=confidence,
                            confidence_rationale=rationale,
                            source_page_url=source_url,
                        ))

        return photo_targets


# =============================================================================
# Search Revision Agent - GPS Pillar 1 Tie-Breaker
# =============================================================================


class SearchStrategy(str, Enum):
    """Search revision strategies for GPS Pillar 1 remediation."""

    PHONETIC_EXPANSION = "phonetic_expansion"  # Soundex, historical spelling variants
    DATE_PAD = "date_pad"  # Expand date ranges by ±10 years
    REGIONAL_ROUTING = "regional_routing"  # Target specific regional archives
    NEGATIVE_SEARCH = "negative_search"  # Look for absence of expected records


class MissingSourceClass(BaseModel):
    """A category of sources that is missing from the research."""

    category: str = Field(description="Category of missing sources (e.g., 'vital_records', 'census')")
    description: str = Field(description="Description of what's missing")
    priority: Annotated[int, Field(ge=1, le=5)] = Field(
        default=3,
        description="Priority for filling this gap (1=highest)",
    )
    suggested_repositories: list[str] = Field(
        default_factory=list,
        description="Suggested archives/repositories to search",
    )


class NameVariant(BaseModel):
    """A name variant for phonetic expansion."""

    original: str = Field(description="Original name")
    variant: str = Field(description="Variant spelling")
    variant_type: str = Field(description="Type: soundex, historical, ethnic, abbreviation")
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.7,
        description="Confidence this variant is relevant",
    )


class DateRange(BaseModel):
    """An expanded date range for date padding strategy."""

    original_year: int | None = Field(default=None, description="Original year from research")
    expanded_start: int = Field(description="Start of expanded range")
    expanded_end: int = Field(description="End of expanded range")
    reason: str = Field(description="Reason for expansion (e.g., 'age misreporting common')")


class RegionalArchive(BaseModel):
    """A regional archive identified for targeted searching."""

    archive_name: str = Field(description="Name of the archive")
    location: str = Field(description="Location (country, state/province)")
    record_types: list[str] = Field(
        default_factory=list,
        description="Types of records held",
    )
    url: str | None = Field(default=None, description="Archive URL if known")
    access_tier: int = Field(default=0, description="Access tier (0=free, 1=API, 2=credential)")


class NegativeSearchTarget(BaseModel):
    """A target for negative evidence search."""

    expected_record_type: str = Field(description="Type of record expected")
    expected_location: str = Field(description="Where record should exist")
    time_period: str = Field(description="Time period to search")
    significance: str = Field(
        description="What absence would indicate (e.g., 'confirms emigration')"
    )


class TiebreakerSearchQuery(BaseModel):
    """A generated search query for the tie-breaker search plan."""

    query_string: str = Field(description="The search query string")
    given_name: str | None = Field(default=None, description="Given name to search")
    surname: str | None = Field(default=None, description="Surname to search")
    birth_year: int | None = Field(default=None, description="Birth year (may be padded)")
    death_year: int | None = Field(default=None, description="Death year (may be padded)")
    location: str | None = Field(default=None, description="Location to search")
    strategy: SearchStrategy = Field(description="Strategy that generated this query")
    target_repository: str | None = Field(default=None, description="Specific repository to target")
    priority: Annotated[int, Field(ge=1, le=5)] = Field(
        default=3,
        description="Priority (1=highest)",
    )
    rationale: str = Field(description="Why this query was generated")


class SearchRevisionInput(BaseModel):
    """Input schema for the Search Revision Agent."""

    subject_id: str = Field(description="UUID of the research subject")
    subject_name: str = Field(description="Display name of the subject")
    given_name: str = Field(description="Subject's given/first name")
    surname: str = Field(description="Subject's surname/family name")

    # Known dates (may be approximate)
    birth_year: int | None = Field(default=None, description="Known or estimated birth year")
    death_year: int | None = Field(default=None, description="Known or estimated death year")

    # Location context
    known_locations: list[str] = Field(
        default_factory=list,
        description="Known locations (residences, birth, death places)",
    )
    country_of_origin: str | None = Field(default=None, description="Country of origin if immigrant")

    # Current search state
    search_log: list[str] = Field(
        default_factory=list,
        description="Previous queries already executed",
    )
    sources_consulted: list[str] = Field(
        default_factory=list,
        description="Sources already consulted",
    )

    # GPS Critic feedback
    missing_source_classes: list[MissingSourceClass] = Field(
        default_factory=list,
        description="Source classes identified as missing by GPS Critic",
    )
    pillar1_score: float = Field(
        default=5.0,
        description="Current GPS Pillar 1 score (0-10)",
    )
    pillar1_issues: list[str] = Field(
        default_factory=list,
        description="Issues identified for Pillar 1",
    )


class SearchRevisionOutput(BaseModel):
    """Output schema for the Search Revision Agent."""

    analysis: str = Field(description="Analysis of search gaps and strategy")

    # Generated name variants
    name_variants: list[NameVariant] = Field(
        default_factory=list,
        description="Phonetic and historical name variants to try",
    )

    # Date range expansions
    date_expansions: list[DateRange] = Field(
        default_factory=list,
        description="Expanded date ranges for searching",
    )

    # Regional archives identified
    regional_archives: list[RegionalArchive] = Field(
        default_factory=list,
        description="Specific regional archives to target",
    )

    # Negative search targets
    negative_searches: list[NegativeSearchTarget] = Field(
        default_factory=list,
        description="Records to search for absence of",
    )

    # The generated search plan
    search_queries: list[TiebreakerSearchQuery] = Field(
        default_factory=list,
        description="High-priority search queries to execute",
    )

    # Summary
    total_queries_generated: int = Field(default=0, description="Total queries generated")
    estimated_pillar1_improvement: float = Field(
        default=0.0,
        description="Estimated Pillar 1 score improvement if queries succeed",
    )


class SearchRevisionAgentLLM:
    """Search Revision Agent for GPS Pillar 1 remediation.

    Activated when GPS Pillar 1 (Reasonably Exhaustive Search) fails validation.
    Generates tie-breaker search plans using:
    - PHONETIC EXPANSION: Soundex and historical spelling variants
    - DATE PAD: Expand date ranges by ±10 years
    - REGIONAL ROUTING: Target specific regional archives
    - NEGATIVE SEARCH: Look for absence of expected records

    Example:
        >>> agent = SearchRevisionAgentLLM(llm_client)
        >>> input_data = SearchRevisionInput(
        ...     subject_id="person_123",
        ...     subject_name="John Janvrin",
        ...     given_name="John",
        ...     surname="Janvrin",
        ...     birth_year=1850,
        ...     missing_source_classes=[
        ...         MissingSourceClass(category="vital_records", description="No birth certificate")
        ...     ],
        ... )
        >>> output = agent.generate_search_plan(input_data)
        >>> print(output.search_queries)
    """

    # Common historical spelling variations by ethnicity/region
    SPELLING_PATTERNS: dict[str, list[tuple[str, str]]] = {
        "french": [
            ("in", "en"),  # Janvrin -> Janvren
            ("ier", "er"),  # Janvier -> Janver
            ("eau", "o"),  # Moreau -> Moro
        ],
        "german": [
            ("sch", "sh"),  # Schmidt -> Shmidt
            ("tz", "ts"),  # Schultz -> Schults
            ("mann", "man"),  # Hoffman -> Hofman
        ],
        "irish": [
            ("O'", "O"),  # O'Brien -> OBrien
            ("Mc", "Mac"),  # McDonald -> MacDonald
        ],
        "italian": [
            ("i", "y"),  # Rossi -> Rossy
            ("cc", "c"),  # Ricci -> Rici
        ],
    }

    # Regional archive mappings
    REGIONAL_ARCHIVES: dict[str, list[dict[str, str]]] = {
        "belgium": [
            {"name": "Belgium State Archives", "url": "https://www.arch.be/", "types": "civil_registration,census"},
            {"name": "Rijksarchief", "url": "https://www.arch.be/", "types": "notarial,military"},
        ],
        "france": [
            {"name": "Archives Départementales", "url": "https://francearchives.fr/", "types": "civil,parish"},
            {"name": "Archives Nationales", "url": "https://www.archives-nationales.culture.gouv.fr/", "types": "military,notarial"},
        ],
        "germany": [
            {"name": "Bundesarchiv", "url": "https://www.bundesarchiv.de/", "types": "military,emigration"},
            {"name": "Standesamt", "url": "", "types": "civil_registration"},
        ],
        "ireland": [
            {"name": "General Register Office", "url": "https://www.gov.ie/gro", "types": "civil_registration"},
            {"name": "National Archives of Ireland", "url": "https://www.nationalarchives.ie/", "types": "census,wills"},
        ],
        "uk": [
            {"name": "General Register Office", "url": "https://www.gro.gov.uk/", "types": "civil_registration"},
            {"name": "The National Archives", "url": "https://www.nationalarchives.gov.uk/", "types": "census,military,wills"},
        ],
        "usa": [
            {"name": "NARA", "url": "https://www.archives.gov/", "types": "census,military,immigration"},
            {"name": "FamilySearch", "url": "https://www.familysearch.org/", "types": "vital,census,parish"},
        ],
    }

    def __init__(self, client: "LLMClient"):
        """Initialize the Search Revision Agent.

        Args:
            client: The LLM client to use
        """
        from ..llm import StructuredLLMWrapper

        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="search_revision_agent",
            input_schema=SearchRevisionInput,
            output_schema=SearchRevisionOutput,
            temperature=0.3,  # Some creativity for name variants
        )
        self._client = client

    def generate_search_plan(
        self,
        input_data: SearchRevisionInput,
    ) -> SearchRevisionOutput:
        """Generate a tie-breaker search plan.

        Args:
            input_data: Input with subject info and GPS Critic feedback

        Returns:
            SearchRevisionOutput with generated search queries
        """
        return self._wrapper.invoke(input_data)

    @staticmethod
    def generate_soundex(name: str) -> str:
        """Generate Soundex code for a name.

        Args:
            name: The name to encode

        Returns:
            4-character Soundex code
        """
        if not name:
            return ""

        name = name.upper()
        soundex = name[0]

        # Soundex encoding table
        codes = {
            "BFPV": "1",
            "CGJKQSXZ": "2",
            "DT": "3",
            "L": "4",
            "MN": "5",
            "R": "6",
        }

        prev_code = ""
        for char in name[1:]:
            for letters, code in codes.items():
                if char in letters:
                    if code != prev_code:
                        soundex += code
                        prev_code = code
                    break
            else:
                prev_code = ""

            if len(soundex) == 4:
                break

        return soundex.ljust(4, "0")

    def generate_name_variants(
        self,
        given_name: str,
        surname: str,
        ethnicity_hint: str | None = None,
    ) -> list[NameVariant]:
        """Generate phonetic and historical name variants.

        Args:
            given_name: Subject's given name
            surname: Subject's surname
            ethnicity_hint: Optional hint about ethnic origin

        Returns:
            List of name variants to search
        """
        variants = []

        # Soundex variants
        soundex = self.generate_soundex(surname)
        variants.append(NameVariant(
            original=surname,
            variant=f"[soundex:{soundex}]",
            variant_type="soundex",
            confidence=0.6,
        ))

        # Historical spelling patterns
        patterns_to_try = []
        if ethnicity_hint and ethnicity_hint.lower() in self.SPELLING_PATTERNS:
            patterns_to_try = self.SPELLING_PATTERNS[ethnicity_hint.lower()]
        else:
            # Try all patterns
            for patterns in self.SPELLING_PATTERNS.values():
                patterns_to_try.extend(patterns)

        for old, new in patterns_to_try:
            if old.lower() in surname.lower():
                variant = surname.lower().replace(old.lower(), new)
                variants.append(NameVariant(
                    original=surname,
                    variant=variant.title(),
                    variant_type="historical",
                    confidence=0.7,
                ))

        # Common abbreviations for given names
        abbreviations = {
            "william": ["wm", "will", "bill"],
            "elizabeth": ["eliz", "beth", "liz"],
            "thomas": ["thos", "tom"],
            "james": ["jas", "jim"],
            "margaret": ["marg", "maggie", "peggy"],
            "catherine": ["cath", "kate", "kitty"],
            "robert": ["robt", "rob", "bob"],
            "richard": ["richd", "rick", "dick"],
        }

        given_lower = given_name.lower()
        if given_lower in abbreviations:
            for abbrev in abbreviations[given_lower]:
                variants.append(NameVariant(
                    original=given_name,
                    variant=abbrev.title(),
                    variant_type="abbreviation",
                    confidence=0.8,
                ))

        return variants

    def generate_date_ranges(
        self,
        birth_year: int | None,
        death_year: int | None,
        padding_years: int = 10,
    ) -> list[DateRange]:
        """Generate expanded date ranges.

        Args:
            birth_year: Known/estimated birth year
            death_year: Known/estimated death year
            padding_years: Years to pad in each direction (default 10)

        Returns:
            List of expanded date ranges
        """
        ranges = []

        if birth_year:
            ranges.append(DateRange(
                original_year=birth_year,
                expanded_start=birth_year - padding_years,
                expanded_end=birth_year + padding_years,
                reason="Age misreporting common in historical records",
            ))

        if death_year:
            ranges.append(DateRange(
                original_year=death_year,
                expanded_start=death_year - padding_years,
                expanded_end=death_year + padding_years,
                reason="Death date may have been misremembered by family",
            ))

        return ranges

    def identify_regional_archives(
        self,
        locations: list[str],
        country_of_origin: str | None,
    ) -> list[RegionalArchive]:
        """Identify regional archives based on known locations.

        Args:
            locations: Known locations from research
            country_of_origin: Country of origin if immigrant

        Returns:
            List of relevant regional archives
        """
        archives = []
        countries_to_check = set()

        # Extract countries from locations
        for location in locations:
            loc_lower = location.lower()
            for country in self.REGIONAL_ARCHIVES.keys():
                if country in loc_lower:
                    countries_to_check.add(country)

        if country_of_origin:
            countries_to_check.add(country_of_origin.lower())

        # Build archive list
        for country in countries_to_check:
            if country in self.REGIONAL_ARCHIVES:
                for archive_info in self.REGIONAL_ARCHIVES[country]:
                    archives.append(RegionalArchive(
                        archive_name=archive_info["name"],
                        location=country.title(),
                        record_types=archive_info["types"].split(","),
                        url=archive_info["url"] if archive_info["url"] else None,
                        access_tier=0 if archive_info["url"] else 2,
                    ))

        return archives

    def generate_negative_searches(
        self,
        subject_name: str,
        known_locations: list[str],
        birth_year: int | None,
        death_year: int | None,
    ) -> list[NegativeSearchTarget]:
        """Generate negative search targets.

        Args:
            subject_name: Subject's name
            known_locations: Known locations
            birth_year: Birth year if known
            death_year: Death year if known

        Returns:
            List of negative search targets
        """
        targets = []

        # If we have birth info but no death, search for death records
        if birth_year and not death_year:
            for location in known_locations[:2]:  # Limit to first 2 locations
                targets.append(NegativeSearchTarget(
                    expected_record_type="death_certificate",
                    expected_location=location,
                    time_period=f"{birth_year + 20}-{birth_year + 100}",
                    significance="Absence may indicate emigration or death elsewhere",
                ))

        # Search for expected census records
        if birth_year:
            census_years = [y for y in range(1850, 1950, 10) if birth_year - 5 <= y <= (death_year or birth_year + 80)]
            for census_year in census_years[:3]:  # Limit to 3 census years
                for location in known_locations[:1]:
                    targets.append(NegativeSearchTarget(
                        expected_record_type=f"{census_year}_census",
                        expected_location=location,
                        time_period=str(census_year),
                        significance=f"Absence in {census_year} census confirms migration or temporary residence",
                    ))

        return targets

    def build_search_queries(
        self,
        input_data: SearchRevisionInput,
        name_variants: list[NameVariant],
        date_ranges: list[DateRange],
        archives: list[RegionalArchive],
        negative_targets: list[NegativeSearchTarget],
    ) -> list[TiebreakerSearchQuery]:
        """Build the final search query list.

        Args:
            input_data: Original input
            name_variants: Generated name variants
            date_ranges: Expanded date ranges
            archives: Regional archives to target
            negative_targets: Negative search targets

        Returns:
            List of prioritized search queries
        """
        queries = []

        # 1. Phonetic expansion queries (highest priority)
        for variant in name_variants[:5]:  # Limit to top 5 variants
            queries.append(TiebreakerSearchQuery(
                query_string=f"{input_data.given_name} {variant.variant}",
                given_name=input_data.given_name,
                surname=variant.variant,
                birth_year=input_data.birth_year,
                strategy=SearchStrategy.PHONETIC_EXPANSION,
                priority=1,
                rationale=f"Phonetic variant ({variant.variant_type}): {variant.original} -> {variant.variant}",
            ))

        # 2. Date padded queries
        for date_range in date_ranges:
            for year in [date_range.expanded_start, date_range.expanded_end]:
                queries.append(TiebreakerSearchQuery(
                    query_string=f"{input_data.given_name} {input_data.surname} {year}",
                    given_name=input_data.given_name,
                    surname=input_data.surname,
                    birth_year=year if "birth" in date_range.reason.lower() else input_data.birth_year,
                    death_year=year if "death" in date_range.reason.lower() else input_data.death_year,
                    strategy=SearchStrategy.DATE_PAD,
                    priority=2,
                    rationale=date_range.reason,
                ))

        # 3. Regional routing queries
        for archive in archives[:3]:  # Limit to 3 archives
            for record_type in archive.record_types[:2]:  # Top 2 record types
                queries.append(TiebreakerSearchQuery(
                    query_string=f"{input_data.given_name} {input_data.surname} {record_type}",
                    given_name=input_data.given_name,
                    surname=input_data.surname,
                    birth_year=input_data.birth_year,
                    location=archive.location,
                    strategy=SearchStrategy.REGIONAL_ROUTING,
                    target_repository=archive.archive_name,
                    priority=2,
                    rationale=f"Regional archive search: {archive.archive_name} for {record_type}",
                ))

        # 4. Negative searches (lowest priority but important)
        for target in negative_targets[:3]:  # Limit to 3
            queries.append(TiebreakerSearchQuery(
                query_string=f"{input_data.given_name} {input_data.surname} {target.expected_record_type}",
                given_name=input_data.given_name,
                surname=input_data.surname,
                location=target.expected_location,
                strategy=SearchStrategy.NEGATIVE_SEARCH,
                priority=3,
                rationale=f"Negative evidence: {target.significance}",
            ))

        # Sort by priority
        queries.sort(key=lambda q: q.priority)

        return queries


# =============================================================================
# DevOps Specialist - Git Workflow Generator
# =============================================================================


class CommitType(str, Enum):
    """Conventional commit types for genealogy data."""

    FEAT = "feat"  # New research/data
    FIX = "fix"  # Corrections to existing data
    DATA = "data"  # Pure data additions (no code)
    DOCS = "docs"  # Documentation updates
    REFACTOR = "refactor"  # Restructuring without data changes


class PublishingBundle(BaseModel):
    """A bundle of content ready for publishing."""

    bundle_id: str = Field(description="Unique ID for this bundle")
    subject_id: str = Field(description="ID of the research subject")
    subject_name: str = Field(description="Name of the research subject")
    surname: str = Field(description="Subject's surname")
    firstname: str = Field(description="Subject's first name")
    birth_year: str | None = Field(default=None, description="Subject's birth year")

    # Content files
    wikipedia_draft: str | None = Field(default=None, description="Wikipedia article draft markdown")
    wikidata_json: str | None = Field(default=None, description="Wikidata JSON-LD")
    wikitree_bio: str | None = Field(default=None, description="WikiTree biography text")
    research_notes: str | None = Field(default=None, description="Research notes markdown")

    # Media files
    media_files: list[dict] = Field(
        default_factory=list,
        description="List of media files with local_path and sidecar_path",
    )

    # Metadata
    gps_grade: str = Field(default="", description="GPS grade (A, B, C, D, F)")
    source_count: int = Field(default=0, description="Number of sources cited")


class GitFileOperation(BaseModel):
    """A single git file operation."""

    operation: str = Field(description="Operation: add, move, delete")
    source_path: str | None = Field(default=None, description="Source path for move operations")
    target_path: str = Field(description="Target path for the file")
    content: str | None = Field(default=None, description="File content if creating new")


class GitCommitSpec(BaseModel):
    """Specification for a git commit."""

    commit_type: CommitType = Field(description="Conventional commit type")
    scope: str = Field(default="genealogy", description="Commit scope")
    subject: str = Field(description="Commit subject line")
    body: str = Field(default="", description="Commit body with details")
    files: list[GitFileOperation] = Field(
        default_factory=list,
        description="Files to include in this commit",
    )
    co_authored_by: str = Field(
        default="Claude <noreply@anthropic.com>",
        description="Co-author attribution",
    )


class DevOpsWorkflowInput(BaseModel):
    """Input for DevOps Specialist to generate git workflow."""

    bundles: list[PublishingBundle] = Field(
        description="Approved publishing bundles to persist"
    )
    base_directory: str = Field(
        default="research/persons",
        description="Base directory for research files",
    )
    create_branch: bool = Field(
        default=True,
        description="Whether to create a feature branch",
    )
    branch_prefix: str = Field(
        default="data/genealogy",
        description="Prefix for feature branch names",
    )


class DevOpsWorkflowOutput(BaseModel):
    """Output from DevOps Specialist with git workflow."""

    analysis: str = Field(description="Analysis of the publishing bundles")

    # Branch info
    branch_name: str = Field(description="Name of the feature branch")
    base_branch: str = Field(default="main", description="Base branch to branch from")

    # Commits to create
    commits: list[GitCommitSpec] = Field(
        default_factory=list,
        description="Commits to create in order",
    )

    # Shell script
    shell_script: str = Field(description="Shell-ready script block")

    # Summary
    total_files: int = Field(default=0, description="Total files to commit")
    total_commits: int = Field(default=0, description="Total commits to create")


class DevOpsSpecialistLLM:
    """DevOps Specialist for generating git workflows.

    Given approved publishing bundles, generates precise git workflows
    to persist content to the local research repository following:
    - Conventional Commits with genealogy scope
    - DevOps standard file organization
    - AI Assistant co-author attribution

    Example:
        >>> specialist = DevOpsSpecialistLLM(llm_client)
        >>> input_data = DevOpsWorkflowInput(
        ...     bundles=[PublishingBundle(
        ...         bundle_id="bundle_001",
        ...         subject_id="person_123",
        ...         subject_name="John Smith",
        ...         surname="Smith",
        ...         firstname="John",
        ...         birth_year="1850",
        ...         wikipedia_draft="# John Smith\\n...",
        ...     )],
        ... )
        >>> output = specialist.generate_workflow(input_data)
        >>> print(output.shell_script)
    """

    def __init__(self, client: "LLMClient"):
        """Initialize the DevOps Specialist.

        Args:
            client: The LLM client to use
        """
        from ..llm import StructuredLLMWrapper

        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="devops_specialist",
            input_schema=DevOpsWorkflowInput,
            output_schema=DevOpsWorkflowOutput,
            temperature=0.0,  # Deterministic for scripts
        )
        self._client = client

    def generate_workflow(
        self,
        input_data: DevOpsWorkflowInput,
    ) -> DevOpsWorkflowOutput:
        """Generate git workflow for publishing bundles.

        Args:
            input_data: Input with bundles to persist

        Returns:
            DevOpsWorkflowOutput with shell script
        """
        return self._wrapper.invoke(input_data)

    @staticmethod
    def generate_person_directory(
        base_directory: str,
        surname: str,
        firstname: str,
        birth_year: str | None,
    ) -> str:
        """Generate the person directory path per DevOps standard.

        Args:
            base_directory: Base directory (e.g., "research/persons")
            surname: Subject's surname
            firstname: Subject's first name
            birth_year: Subject's birth year

        Returns:
            Directory path (e.g., "research/persons/smith-john-1850/")
        """
        surname_clean = surname.lower().replace(" ", "-")
        firstname_clean = firstname.lower().replace(" ", "-") if firstname else ""

        parts = [surname_clean]
        if firstname_clean:
            parts.append(firstname_clean)
        if birth_year:
            parts.append(birth_year)

        dir_name = "-".join(parts)
        return f"{base_directory}/{dir_name}/"

    @staticmethod
    def generate_branch_name(
        prefix: str,
        bundles: list[PublishingBundle],
    ) -> str:
        """Generate a branch name for the bundles.

        Args:
            prefix: Branch prefix (e.g., "data/genealogy")
            bundles: Bundles to include

        Returns:
            Branch name (e.g., "data/genealogy/smith-john")
        """
        import time

        if bundles:
            first = bundles[0]
            name_part = f"{first.surname.lower()}-{first.firstname.lower()}"
        else:
            name_part = "update"

        timestamp = int(time.time())
        return f"{prefix}/{name_part}-{timestamp}"

    def build_file_operations(
        self,
        bundle: PublishingBundle,
        base_directory: str,
    ) -> list[GitFileOperation]:
        """Build file operations for a bundle.

        Args:
            bundle: Publishing bundle
            base_directory: Base directory

        Returns:
            List of file operations
        """
        operations = []
        person_dir = self.generate_person_directory(
            base_directory,
            bundle.surname,
            bundle.firstname,
            bundle.birth_year,
        )

        # Wikipedia draft
        if bundle.wikipedia_draft:
            operations.append(GitFileOperation(
                operation="add",
                target_path=f"{person_dir}wikipedia-draft.md",
                content=bundle.wikipedia_draft,
            ))

        # Wikidata JSON
        if bundle.wikidata_json:
            operations.append(GitFileOperation(
                operation="add",
                target_path=f"{person_dir}wikidata.json",
                content=bundle.wikidata_json,
            ))

        # WikiTree bio
        if bundle.wikitree_bio:
            operations.append(GitFileOperation(
                operation="add",
                target_path=f"{person_dir}wikitree-bio.txt",
                content=bundle.wikitree_bio,
            ))

        # Research notes
        if bundle.research_notes:
            operations.append(GitFileOperation(
                operation="add",
                target_path=f"{person_dir}RESEARCH_NOTES.md",
                content=bundle.research_notes,
            ))

        # Media files
        media_dir = f"{person_dir}media/"
        for media in bundle.media_files:
            local_path = media.get("local_path", "")
            sidecar_path = media.get("sidecar_path", "")

            if local_path:
                # Move media file to correct location
                import os
                filename = os.path.basename(local_path)
                operations.append(GitFileOperation(
                    operation="move",
                    source_path=local_path,
                    target_path=f"{media_dir}{filename}",
                ))

            if sidecar_path:
                import os
                filename = os.path.basename(sidecar_path)
                operations.append(GitFileOperation(
                    operation="move",
                    source_path=sidecar_path,
                    target_path=f"{media_dir}{filename}",
                ))

        return operations

    def build_commit_spec(
        self,
        bundle: PublishingBundle,
        file_operations: list[GitFileOperation],
    ) -> GitCommitSpec:
        """Build a commit specification for a bundle.

        Args:
            bundle: Publishing bundle
            file_operations: File operations for this bundle

        Returns:
            GitCommitSpec for the commit
        """
        # Determine commit type based on content
        commit_type = CommitType.DATA
        if bundle.wikipedia_draft or bundle.wikitree_bio:
            commit_type = CommitType.FEAT

        subject = f"add research data for {bundle.subject_name}"
        if bundle.gps_grade:
            subject = f"add GPS Grade {bundle.gps_grade} research for {bundle.subject_name}"

        body_lines = [
            f"Subject: {bundle.subject_name}",
            f"GPS Grade: {bundle.gps_grade or 'N/A'}",
            f"Sources: {bundle.source_count}",
            "",
            "Files:",
        ]
        for op in file_operations:
            body_lines.append(f"  - {op.target_path}")

        return GitCommitSpec(
            commit_type=commit_type,
            scope="genealogy",
            subject=subject,
            body="\n".join(body_lines),
            files=file_operations,
            co_authored_by="Claude <noreply@anthropic.com>",
        )

    def generate_shell_script(
        self,
        branch_name: str,
        base_branch: str,
        commits: list[GitCommitSpec],
        create_branch: bool,
    ) -> str:
        """Generate the shell script for the git workflow.

        Args:
            branch_name: Feature branch name
            base_branch: Base branch to branch from
            commits: Commits to create
            create_branch: Whether to create a branch

        Returns:
            Shell script string
        """
        lines = [
            "#!/bin/bash",
            "set -e  # Exit on error",
            "",
            "# Git Workflow Generated by DevOps Specialist",
            f"# Branch: {branch_name}",
            f"# Commits: {len(commits)}",
            "",
        ]

        if create_branch:
            lines.extend([
                f"# Create feature branch from {base_branch}",
                f"git checkout {base_branch}",
                "git pull origin {base_branch}",
                f"git checkout -b {branch_name}",
                "",
            ])

        for i, commit in enumerate(commits, 1):
            lines.append(f"# Commit {i}: {commit.subject}")

            # Create directories and files
            dirs_created = set()
            for op in commit.files:
                import os
                dir_path = os.path.dirname(op.target_path)
                if dir_path and dir_path not in dirs_created:
                    lines.append(f"mkdir -p '{dir_path}'")
                    dirs_created.add(dir_path)

                if op.operation == "add" and op.content:
                    # Use heredoc for content
                    lines.append(f"cat > '{op.target_path}' << 'EOF'")
                    lines.append(op.content)
                    lines.append("EOF")
                elif op.operation == "move" and op.source_path:
                    lines.append(f"mv '{op.source_path}' '{op.target_path}'")

            # Stage files
            for op in commit.files:
                lines.append(f"git add '{op.target_path}'")

            # Create commit with conventional format
            commit_msg = f"{commit.commit_type.value}({commit.scope}): {commit.subject}"
            if commit.body:
                commit_msg += f"\n\n{commit.body}"
            commit_msg += f"\n\nCo-Authored-By: {commit.co_authored_by}"

            lines.append(f"git commit -m \"$(cat <<'COMMIT_EOF'")
            lines.append(commit_msg)
            lines.append("COMMIT_EOF")
            lines.append(")\"")
            lines.append("")

        lines.extend([
            "echo 'Git workflow complete!'",
            f"echo 'Branch: {branch_name}'",
            f"echo 'Commits: {len(commits)}'",
        ])

        return "\n".join(lines)

    def build_workflow(
        self,
        input_data: DevOpsWorkflowInput,
    ) -> DevOpsWorkflowOutput:
        """Build complete workflow without LLM call.

        This is a deterministic helper that can be used directly
        without calling the LLM for simple cases.

        Args:
            input_data: Workflow input

        Returns:
            Complete workflow output
        """
        commits = []
        total_files = 0

        for bundle in input_data.bundles:
            operations = self.build_file_operations(bundle, input_data.base_directory)
            commit = self.build_commit_spec(bundle, operations)
            commits.append(commit)
            total_files += len(operations)

        branch_name = self.generate_branch_name(
            input_data.branch_prefix,
            input_data.bundles,
        )

        script = self.generate_shell_script(
            branch_name=branch_name,
            base_branch="main",
            commits=commits,
            create_branch=input_data.create_branch,
        )

        analysis_lines = [
            f"Processing {len(input_data.bundles)} publishing bundle(s):",
        ]
        for bundle in input_data.bundles:
            analysis_lines.append(f"  - {bundle.subject_name} (Grade: {bundle.gps_grade or 'N/A'})")

        return DevOpsWorkflowOutput(
            analysis="\n".join(analysis_lines),
            branch_name=branch_name,
            base_branch="main",
            commits=commits,
            shell_script=script,
            total_files=total_files,
            total_commits=len(commits),
        )
