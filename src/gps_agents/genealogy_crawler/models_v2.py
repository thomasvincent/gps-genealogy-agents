"""Enhanced GEDCOM-X compatible data models for the genealogy crawler v2.

Features:
- Bayesian conflict resolution with evidence weighting
- GDPR/CCPA compliant living person protection
- Fuzzy date support with confidence intervals
- Geo-coded place support
- Full provenance chain
"""
from __future__ import annotations

import hashlib
import secrets
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator


# =============================================================================
# Enums
# =============================================================================


class SourceTier(int, Enum):
    """Source access tier classification."""
    TIER_0 = 0  # No login required
    TIER_1 = 1  # Open APIs
    TIER_2 = 2  # Credentialed


class EvidenceClass(str, Enum):
    """Evidence classification for Bayesian weighting."""
    PRIMARY_OFFICIAL = "primary_official"      # Birth/death certificates
    PRIMARY_GOVERNMENT = "primary_government"  # Census, military records
    PRIMARY_RELIGIOUS = "primary_religious"    # Church registers
    SECONDARY_PUBLISHED = "secondary_published"  # Newspapers, books
    SECONDARY_MEMORIAL = "secondary_memorial"  # Gravestones
    SECONDARY_PERSONAL = "secondary_personal"  # Family bibles
    AUTHORED_COMPILED = "authored_compiled"    # Published genealogies
    AUTHORED_UNVERIFIED = "authored_unverified"  # User trees
    DERIVED_AI = "derived_ai"                  # AI extractions


class NameType(str, Enum):
    """Type of name record."""
    BIRTH = "birth"
    MARRIED = "married"
    NICKNAME = "nickname"
    FORMAL = "formal"
    ALIAS = "alias"


class FactType(str, Enum):
    """Types of genealogical facts."""
    BIRTH = "birth"
    DEATH = "death"
    CHRISTENING = "christening"
    BURIAL = "burial"
    MARRIAGE = "marriage"
    DIVORCE = "divorce"
    CENSUS = "census"
    IMMIGRATION = "immigration"
    EMIGRATION = "emigration"
    NATURALIZATION = "naturalization"
    MILITARY_SERVICE = "military_service"
    OCCUPATION = "occupation"
    RESIDENCE = "residence"
    EDUCATION = "education"
    RELIGION = "religion"


class RelationshipType(str, Enum):
    """Types of relationships between persons."""
    PARENT_CHILD = "parent_child"
    COUPLE = "couple"
    SIBLING = "sibling"
    GODPARENT = "godparent"
    GUARDIAN = "guardian"
    ANCESTOR_DESCENDANT = "ancestor_descendant"


class Gender(str, Enum):
    """Gender classification."""
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


# =============================================================================
# Evidence Weight Matrix (Bayesian Priors)
# =============================================================================


EVIDENCE_PRIOR_WEIGHTS: dict[EvidenceClass, float] = {
    EvidenceClass.PRIMARY_OFFICIAL: 0.95,
    EvidenceClass.PRIMARY_GOVERNMENT: 0.80,
    EvidenceClass.PRIMARY_RELIGIOUS: 0.85,
    EvidenceClass.SECONDARY_PUBLISHED: 0.70,
    EvidenceClass.SECONDARY_MEMORIAL: 0.65,
    EvidenceClass.SECONDARY_PERSONAL: 0.60,
    EvidenceClass.AUTHORED_COMPILED: 0.50,
    EvidenceClass.AUTHORED_UNVERIFIED: 0.40,
    EvidenceClass.DERIVED_AI: 0.30,
}


def get_prior_weight(evidence_class: EvidenceClass) -> float:
    """Get the Bayesian prior weight for an evidence class."""
    return EVIDENCE_PRIOR_WEIGHTS.get(evidence_class, 0.30)


# =============================================================================
# Fuzzy Date Support
# =============================================================================


class DatePrecision(str, Enum):
    """Precision level of a date."""
    EXACT = "exact"        # Full date known
    YEAR_MONTH = "year_month"  # Day unknown
    YEAR = "year"          # Only year known
    DECADE = "decade"      # e.g., "1890s"
    APPROXIMATE = "approximate"  # "about 1890"
    RANGE = "range"        # "between 1888-1892"
    BEFORE = "before"      # "before 1890"
    AFTER = "after"        # "after 1890"


class FuzzyDate(BaseModel):
    """A date with uncertainty representation.

    Supports historical records where exact dates are often unknown.
    """
    # The primary date value
    date: datetime | None = None

    # For ranges
    date_start: datetime | None = None
    date_end: datetime | None = None

    # Precision
    precision: DatePrecision = DatePrecision.EXACT

    # Display string (as it appeared in source)
    original_text: str | None = None

    # Confidence in the date
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    @computed_field
    @property
    def year(self) -> int | None:
        """Extract year from date or range midpoint."""
        if self.date:
            return self.date.year
        if self.date_start and self.date_end:
            return (self.date_start.year + self.date_end.year) // 2
        if self.date_start:
            return self.date_start.year
        if self.date_end:
            return self.date_end.year
        return None

    @computed_field
    @property
    def display(self) -> str:
        """Human-readable date string."""
        if self.original_text:
            return self.original_text
        if self.precision == DatePrecision.EXACT and self.date:
            return self.date.strftime("%d %B %Y")
        if self.precision == DatePrecision.YEAR and self.date:
            return str(self.date.year)
        if self.precision == DatePrecision.RANGE and self.date_start and self.date_end:
            return f"{self.date_start.year}-{self.date_end.year}"
        if self.precision == DatePrecision.APPROXIMATE and self.date:
            return f"c. {self.date.year}"
        return "unknown"


# =============================================================================
# Geo-Coded Place
# =============================================================================


class GeoCodedPlace(BaseModel):
    """A place with geocoding and normalization."""
    # Original text as it appeared
    original_text: str

    # Normalized components
    city: str | None = None
    county: str | None = None
    state_province: str | None = None
    country: str | None = None

    # Geocoded coordinates
    latitude: float | None = None
    longitude: float | None = None

    # Standardized place ID (e.g., GeoNames ID)
    geonames_id: int | None = None

    # Historical jurisdiction (may differ from modern)
    historical_jurisdiction: str | None = None

    @computed_field
    @property
    def normalized(self) -> str:
        """Return normalized place string."""
        parts = [p for p in [self.city, self.county, self.state_province, self.country] if p]
        return ", ".join(parts) if parts else self.original_text


# =============================================================================
# Encryption for Living Persons (GDPR/CCPA)
# =============================================================================


class EncryptionContext:
    """Manages encryption for living person PII."""

    _instance: "EncryptionContext | None" = None
    _fernet: Fernet | None = None

    @classmethod
    def initialize(cls, master_key: bytes | None = None) -> None:
        """Initialize encryption with a master key.

        In production, the key should come from HashiCorp Vault.
        """
        if master_key is None:
            master_key = secrets.token_bytes(32)

        # Derive a Fernet key from the master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"genealogy_crawler_v2",  # In production, use unique salt per record
            iterations=480000,
        )
        key = b64encode(kdf.derive(master_key))
        cls._fernet = Fernet(key)
        cls._instance = cls()

    @classmethod
    def get_instance(cls) -> "EncryptionContext":
        """Get the singleton encryption context."""
        if cls._instance is None:
            cls.initialize()
        return cls._instance  # type: ignore

    @classmethod
    def encrypt(cls, data: str) -> str:
        """Encrypt a string value."""
        ctx = cls.get_instance()
        if ctx._fernet is None:
            raise RuntimeError("Encryption not initialized")
        return ctx._fernet.encrypt(data.encode()).decode()

    @classmethod
    def decrypt(cls, encrypted_data: str) -> str:
        """Decrypt a string value."""
        ctx = cls.get_instance()
        if ctx._fernet is None:
            raise RuntimeError("Encryption not initialized")
        return ctx._fernet.decrypt(encrypted_data.encode()).decode()


# =============================================================================
# GEDCOM-X Compatible Models
# =============================================================================


class PersonName(BaseModel):
    """A name associated with a person (GEDCOM-X NameForm)."""
    id: UUID = Field(default_factory=uuid4)
    name_type: NameType = NameType.BIRTH

    # Name components
    given_name: str | None = None
    surname: str | None = None
    prefix: str | None = None  # Dr., Mr., etc.
    suffix: str | None = None  # Jr., III, etc.

    # Full name as extracted
    full_text: str

    # Localized variants (key = language code)
    variants: dict[str, str] = Field(default_factory=dict)

    # Confidence
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    @computed_field
    @property
    def display_name(self) -> str:
        """Canonical display name."""
        parts = []
        if self.prefix:
            parts.append(self.prefix)
        if self.given_name:
            parts.append(self.given_name)
        if self.surname:
            parts.append(self.surname)
        if self.suffix:
            parts.append(self.suffix)
        return " ".join(parts) if parts else self.full_text


class Fact(BaseModel):
    """A fact about a person or relationship (GEDCOM-X Fact)."""
    id: UUID = Field(default_factory=uuid4)
    fact_type: FactType

    # When
    date: FuzzyDate | None = None

    # Where
    place: GeoCodedPlace | None = None

    # What (for facts like occupation, religion)
    value: str | None = None

    # Confidence
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    # Linked assertion (after conflict resolution)
    assertion_id: UUID | None = None


class SourceCitation(BaseModel):
    """Citation information for a source (GEDCOM-X SourceCitation)."""
    id: UUID = Field(default_factory=uuid4)

    # Citation text
    citation_text: str

    # Structured citation fields
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    publication_date: str | None = None
    page: str | None = None
    url: str | None = None

    # Repository information
    repository_name: str | None = None
    repository_ref: str | None = None


class SourceDescription(BaseModel):
    """Description of a source (GEDCOM-X SourceDescription)."""
    id: UUID = Field(default_factory=uuid4)

    # Source identification
    resource_type: Literal["PhysicalArtifact", "DigitalArtifact"] = "DigitalArtifact"

    # Titles
    titles: list[str] = Field(default_factory=list)

    # Citation
    citations: list[SourceCitation] = Field(default_factory=list)

    # Evidence classification for Bayesian weighting
    evidence_class: EvidenceClass = EvidenceClass.SECONDARY_PUBLISHED

    # Source tier
    tier: SourceTier = SourceTier.TIER_0

    # Access information
    url: str | None = None
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Content hash for deduplication
    content_hash: str | None = None

    # Raw content (for re-extraction)
    raw_content: str | None = None

    # Compliance
    robots_respected: bool = True
    tos_compliant: bool = True

    @computed_field
    @property
    def prior_weight(self) -> float:
        """Get Bayesian prior weight based on evidence class."""
        return get_prior_weight(self.evidence_class)


class SourceReference(BaseModel):
    """Reference to a source with qualifiers (GEDCOM-X SourceReference)."""
    id: UUID = Field(default_factory=uuid4)
    source_description_id: UUID

    # Qualifier information
    description_ref: str | None = None  # e.g., "page 42, line 3"

    # Attribution
    contributor: str | None = None
    modified: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceClaim(BaseModel):
    """A single claim extracted from a source (part of provenance chain)."""
    id: UUID = Field(default_factory=uuid4)
    source_reference_id: UUID

    # The claim
    claim_text: str
    claim_type: str  # e.g., "birth_date", "father_name"
    claim_value: Any

    # Citation snippet (exact quote from source)
    citation_snippet: str

    # Bayesian prior weight (inherited from source)
    prior_weight: Annotated[float, Field(ge=0.0, le=1.0)]

    # Extraction metadata
    extraction_method: Literal["deterministic", "llm", "manual"] = "deterministic"
    extractor_version: str | None = None
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # LLM verification (if applicable)
    llm_rationale: str | None = None
    llm_confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class Assertion(BaseModel):
    """A resolved assertion after Bayesian conflict resolution."""
    id: UUID = Field(default_factory=uuid4)

    # What this assertion is about
    subject_id: UUID  # Person or Relationship ID
    subject_type: Literal["person", "relationship", "event"]
    field_name: str  # e.g., "birth_date", "death_place"

    # The resolved value
    resolved_value: Any
    resolved_display: str | None = None

    # Bayesian posterior confidence
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    # Evidence claims that support this
    evidence_claim_ids: list[UUID] = Field(default_factory=list)

    # Conflict resolution details
    resolution_method: Literal["single_source", "consensus", "bayesian_weighted", "manual"]
    conflicting_values: list[dict[str, Any]] = Field(default_factory=list)

    # Resolution metadata
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_by: str = "conflict_engine"


class Person(BaseModel):
    """A person entity (GEDCOM-X Person)."""
    id: UUID = Field(default_factory=uuid4)

    # Privacy flag (CRITICAL for GDPR/CCPA)
    living: bool = False

    # Gender
    gender: Gender = Gender.UNKNOWN

    # Names
    names: list[PersonName] = Field(default_factory=list)

    # Facts (unresolved)
    facts: list[Fact] = Field(default_factory=list)

    # Source references
    source_references: list[SourceReference] = Field(default_factory=list)

    # Extracted raw data (for re-processing)
    extracted_data: dict[str, Any] = Field(default_factory=dict)

    # Encryption status
    _encrypted_fields: dict[str, str] = {}

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field
    @property
    def primary_name(self) -> PersonName | None:
        """Get the primary (birth) name."""
        for name in self.names:
            if name.name_type == NameType.BIRTH:
                return name
        return self.names[0] if self.names else None

    @computed_field
    @property
    def display_name(self) -> str:
        """Get display name for UI."""
        if self.living:
            return "[Living Person]"
        pn = self.primary_name
        return pn.display_name if pn else "Unknown"

    def encrypt_pii(self) -> None:
        """Encrypt PII fields if person is living."""
        if not self.living:
            return

        # Encrypt names
        for name in self.names:
            if name.given_name:
                self._encrypted_fields[f"name_{name.id}_given"] = EncryptionContext.encrypt(name.given_name)
                name.given_name = "[ENCRYPTED]"
            if name.surname:
                self._encrypted_fields[f"name_{name.id}_surname"] = EncryptionContext.encrypt(name.surname)
                name.surname = "[ENCRYPTED]"

        # Encrypt specific facts
        for fact in self.facts:
            if fact.place and fact.fact_type in (FactType.BIRTH, FactType.RESIDENCE):
                self._encrypted_fields[f"fact_{fact.id}_place"] = EncryptionContext.encrypt(
                    fact.place.model_dump_json()
                )
                fact.place = GeoCodedPlace(original_text="[ENCRYPTED]")

    def decrypt_pii(self) -> None:
        """Decrypt PII fields (requires authorization)."""
        for key, encrypted_value in self._encrypted_fields.items():
            decrypted = EncryptionContext.decrypt(encrypted_value)
            # Re-apply decrypted values based on key pattern
            # (Implementation depends on field structure)

    def to_jsonld(self, include_pii: bool = False) -> dict[str, Any]:
        """Export to schema.org/Person JSON-LD."""
        if self.living and not include_pii:
            return {
                "@context": "https://schema.org",
                "@type": "Person",
                "@id": f"urn:uuid:{self.id}",
                "name": "[Living Person - Data Protected]",
            }

        result: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "Person",
            "@id": f"urn:uuid:{self.id}",
        }

        if self.primary_name:
            result["name"] = self.primary_name.display_name
            if self.primary_name.given_name:
                result["givenName"] = self.primary_name.given_name
            if self.primary_name.surname:
                result["familyName"] = self.primary_name.surname

        # Add facts
        for fact in self.facts:
            if fact.fact_type == FactType.BIRTH:
                if fact.date:
                    result["birthDate"] = fact.date.display
                if fact.place:
                    result["birthPlace"] = {
                        "@type": "Place",
                        "name": fact.place.normalized,
                    }
            elif fact.fact_type == FactType.DEATH:
                if fact.date:
                    result["deathDate"] = fact.date.display
                if fact.place:
                    result["deathPlace"] = {
                        "@type": "Place",
                        "name": fact.place.normalized,
                    }

        return result


class Relationship(BaseModel):
    """A relationship between two persons (GEDCOM-X Relationship)."""
    id: UUID = Field(default_factory=uuid4)

    # Participants
    person1_id: UUID
    person2_id: UUID

    # Relationship type
    relationship_type: RelationshipType

    # Role clarification (for asymmetric relationships)
    person1_role: str | None = None  # e.g., "Parent"
    person2_role: str | None = None  # e.g., "Child"

    # Facts about the relationship
    facts: list[Fact] = Field(default_factory=list)

    # Source references
    source_references: list[SourceReference] = Field(default_factory=list)

    # Confidence
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_different_persons(self) -> "Relationship":
        """Ensure relationship is between different persons."""
        if self.person1_id == self.person2_id:
            raise ValueError("Relationship must be between different persons")
        return self


# =============================================================================
# Bayesian Conflict Resolution
# =============================================================================


class ConflictingEvidence(BaseModel):
    """A piece of conflicting evidence for Bayesian resolution."""
    claim_id: UUID
    value: Any
    prior_weight: float
    source_description: str
    citation_snippet: str


class BayesianResolution(BaseModel):
    """Result of Bayesian conflict resolution."""
    field_name: str
    subject_id: UUID

    # Competing evidence
    conflicting_evidence: list[ConflictingEvidence]

    # Resolution
    resolved_value: Any
    posterior_confidence: Annotated[float, Field(ge=0.0, le=1.0)]

    # Bayesian calculation details
    likelihood_ratios: dict[str, float] = Field(default_factory=dict)
    prior_weights: dict[str, float] = Field(default_factory=dict)
    posterior_weights: dict[str, float] = Field(default_factory=dict)

    # Resolution method
    method: Literal["weighted_average", "highest_posterior", "manual_override"]

    # Recommendations
    suggested_actions: list[str] = Field(default_factory=list)

    @classmethod
    def resolve(
        cls,
        field_name: str,
        subject_id: UUID,
        evidence: list[ConflictingEvidence],
    ) -> "BayesianResolution":
        """Perform Bayesian conflict resolution."""
        if not evidence:
            raise ValueError("No evidence to resolve")

        if len(evidence) == 1:
            # Single source - no conflict
            return cls(
                field_name=field_name,
                subject_id=subject_id,
                conflicting_evidence=evidence,
                resolved_value=evidence[0].value,
                posterior_confidence=evidence[0].prior_weight,
                method="weighted_average",
            )

        # Calculate posterior weights using Bayesian update
        # P(value|evidence) ∝ P(evidence|value) * P(value)
        # Simplified: use prior weights as proxy for full Bayesian calculation

        total_weight = sum(e.prior_weight for e in evidence)
        posterior_weights = {
            str(e.claim_id): e.prior_weight / total_weight
            for e in evidence
        }

        # Find consensus or highest-weighted value
        value_weights: dict[str, tuple[Any, float]] = {}
        for e in evidence:
            value_str = str(e.value)
            if value_str in value_weights:
                value_weights[value_str] = (
                    e.value,
                    value_weights[value_str][1] + e.prior_weight,
                )
            else:
                value_weights[value_str] = (e.value, e.prior_weight)

        # Select value with highest combined weight
        best_value, best_weight = max(value_weights.values(), key=lambda x: x[1])
        posterior_confidence = best_weight / total_weight

        # Generate suggestions
        suggestions = []
        if posterior_confidence < 0.7:
            suggestions.append("Seek additional primary sources to resolve conflict")
        if len(evidence) > 2:
            suggestions.append("Multiple conflicting sources - manual review recommended")

        return cls(
            field_name=field_name,
            subject_id=subject_id,
            conflicting_evidence=evidence,
            resolved_value=best_value,
            posterior_confidence=posterior_confidence,
            prior_weights={str(e.claim_id): e.prior_weight for e in evidence},
            posterior_weights=posterior_weights,
            method="weighted_average" if len(set(str(e.value) for e in evidence)) == 1 else "highest_posterior",
            suggested_actions=suggestions,
        )


# =============================================================================
# Living Person Detection
# =============================================================================


def is_living(person: Person) -> bool:
    """
    Conservative living status determination.
    GDPR/CCPA requires assuming living unless proven otherwise.
    """
    # Explicit living flag
    if person.living:
        return True

    # Check for death fact
    for fact in person.facts:
        if fact.fact_type == FactType.DEATH and fact.date:
            return False

    # Age-based heuristic (100-year rule)
    for fact in person.facts:
        if fact.fact_type == FactType.BIRTH and fact.date and fact.date.year:
            age = datetime.now(UTC).year - fact.date.year
            if age < 100:
                return True  # Assume living
            if age >= 120:
                return False  # Almost certainly deceased

    # Check for modern indicators in extracted data
    modern_indicators = ["email", "phone", "social_media", "linkedin", "facebook"]
    for indicator in modern_indicators:
        if indicator in person.extracted_data:
            return True

    # Default: Assume living (conservative for GDPR)
    return True


def apply_privacy_protection(person: Person) -> Person:
    """Apply privacy protection to a person based on living status."""
    if is_living(person):
        person.living = True
        person.encrypt_pii()
    return person


# =============================================================================
# Competing Assertions for Conflict Resolution
# =============================================================================


class ResolutionStatus(str, Enum):
    """Status of a competing assertion in the conflict resolution workflow."""
    PENDING_REVIEW = "pending_review"  # Awaiting analysis
    RESOLVED = "resolved"              # Winner selected via tie-breaker
    REJECTED = "rejected"              # Conflicted value rejected
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # Needs more sources
    HUMAN_REVIEW_REQUIRED = "human_review_required"  # Escalated to human


class ErrorPatternType(str, Enum):
    """Known genealogical error patterns for likelihood adjustment."""
    TOMBSTONE_ERROR = "tombstone_error"  # Death date rounded to Jan 1
    MILITARY_AGE_PADDING = "military_age_padding"  # Age inflated for enlistment
    IMMIGRATION_AGE_REDUCTION = "immigration_age_reduction"  # Age reduced at arrival
    CENSUS_APPROXIMATION = "census_approximation"  # Age approximated on census
    CLERICAL_TRANSCRIPTION = "clerical_transcription"  # Handwriting misread
    GENERATIONAL_CONFUSION = "generational_confusion"  # Father/son conflation


class CompetingAssertion(BaseModel):
    """A competing assertion stored inline in the knowledge graph.

    When multiple sources disagree about a fact (e.g., birth date), each
    conflicting value becomes a CompetingAssertion. This implements the
    "Paper Trail of Doubt" concept - no data is discarded, all competing
    claims are preserved for later analysis.

    The status field tracks the assertion through the resolution workflow:
    1. PENDING_REVIEW: Initial state when conflict detected
    2. Conflict Analyst tie-breaker runs vertical verification
    3. Resolution: RESOLVED (winner), REJECTED, INSUFFICIENT_EVIDENCE, or HUMAN_REVIEW_REQUIRED
    """
    id: UUID = Field(default_factory=uuid4)

    # What this assertion claims
    subject_id: UUID  # Person, Relationship, or Event ID
    subject_type: Literal["person", "relationship", "event"] = "person"
    fact_type: FactType
    proposed_value: Any

    # Resolution workflow status
    status: ResolutionStatus = ResolutionStatus.PENDING_REVIEW

    # Evidence supporting this assertion
    evidence_claim_ids: list[UUID] = Field(default_factory=list)

    # Bayesian weighting
    prior_weight: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    posterior_weight: Annotated[float, Field(ge=0.0, le=1.0)] | None = None

    # Temporal proximity bonus (+0.05 for sources closer to event)
    temporal_proximity_bonus: Annotated[float, Field(ge=-0.1, le=0.1)] = 0.0

    # Pattern-based adjustments
    detected_patterns: list[ErrorPatternType] = Field(default_factory=list)
    pattern_penalty: Annotated[float, Field(ge=-0.2, le=0.0)] = 0.0

    # Negative evidence (absence of expected records)
    negative_evidence_modifier: Annotated[float, Field(ge=-0.1, le=0.0)] = 0.0

    # Analysis from Conflict Analyst
    rationale: str = ""
    tie_breaker_queries: list[str] = Field(default_factory=list)

    # Conflict metadata
    conflict_group_id: UUID | None = None  # Links competing assertions together
    conflict_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    @computed_field
    @property
    def final_weight(self) -> float:
        """Calculate final Bayesian weight with all modifiers.

        Formula: base_weight + temporal_proximity_bonus + pattern_penalty + negative_evidence_modifier
        """
        base = self.posterior_weight if self.posterior_weight is not None else self.prior_weight
        return max(0.0, min(1.0,
            base
            + self.temporal_proximity_bonus
            + self.pattern_penalty
            + self.negative_evidence_modifier
        ))

    def mark_resolved(self, status: ResolutionStatus, rationale: str, resolved_by: str = "conflict_analyst") -> None:
        """Mark this assertion as resolved with a given status."""
        self.status = status
        self.rationale = rationale
        self.resolved_at = datetime.now(UTC)
        self.resolved_by = resolved_by


class NegativeEvidence(BaseModel):
    """Records the absence of an expected record as evidence.

    Example: If a death date is claimed as 1850, but the person appears
    in an 1860 census, the absence of the death record in the census
    jurisdiction's vital records is negative evidence against the 1850 date.
    """
    id: UUID = Field(default_factory=uuid4)

    # What record was expected but not found
    expected_record_type: str  # e.g., "death_certificate", "burial_record"
    expected_jurisdiction: str  # e.g., "Philadelphia County, PA"
    expected_date_range: tuple[datetime | None, datetime | None] | None = None

    # What assertion this evidence relates to
    related_assertion_id: UUID

    # How this affects confidence
    confidence_reduction: Annotated[float, Field(ge=0.0, le=0.2)] = 0.05

    # Rationale
    reasoning: str

    # Metadata
    searched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    search_thoroughness: Literal["cursory", "standard", "exhaustive"] = "standard"


# =============================================================================
# Date Normalization Utilities
# =============================================================================


import re
from calendar import monthrange


def normalize_date_to_iso8601(
    date_string: str,
    original_precision: DatePrecision | None = None,
) -> tuple[str, DatePrecision]:
    """Normalize a date string to ISO-8601 format.

    Handles various historical date formats:
    - "25 Dec 1900" -> "1900-12-25", EXACT
    - "December 1900" -> "1900-12", YEAR_MONTH
    - "1900" -> "1900", YEAR
    - "abt 1900" / "c. 1900" -> "1900", APPROXIMATE
    - "1890s" -> "1890/1899", DECADE
    - "bet 1888 and 1892" -> "1888/1892", RANGE
    - "bef 1890" -> "/1890", BEFORE
    - "aft 1890" -> "1890/", AFTER

    Args:
        date_string: The date string to normalize
        original_precision: Optional override for precision

    Returns:
        Tuple of (ISO-8601 string, inferred precision)
    """
    if not date_string:
        return "", DatePrecision.APPROXIMATE

    date_string = date_string.strip()
    date_lower = date_string.lower()

    # Month name to number mapping
    months = {
        "january": "01", "jan": "01",
        "february": "02", "feb": "02",
        "march": "03", "mar": "03",
        "april": "04", "apr": "04",
        "may": "05",
        "june": "06", "jun": "06",
        "july": "07", "jul": "07",
        "august": "08", "aug": "08",
        "september": "09", "sep": "09", "sept": "09",
        "october": "10", "oct": "10",
        "november": "11", "nov": "11",
        "december": "12", "dec": "12",
    }

    # Pattern: "bef" or "before" + year
    if date_lower.startswith(("bef ", "before ")):
        year_match = re.search(r"\d{4}", date_string)
        if year_match:
            return f"/{year_match.group()}", DatePrecision.BEFORE

    # Pattern: "aft" or "after" + year
    if date_lower.startswith(("aft ", "after ")):
        year_match = re.search(r"\d{4}", date_string)
        if year_match:
            return f"{year_match.group()}/", DatePrecision.AFTER

    # Pattern: "bet" or "between" + year "and" year
    range_match = re.search(r"(?:bet|between)\s+(\d{4})\s+(?:and|-)\s+(\d{4})", date_lower)
    if range_match:
        return f"{range_match.group(1)}/{range_match.group(2)}", DatePrecision.RANGE

    # Pattern: decade "1890s"
    decade_match = re.match(r"^(\d{3})0s$", date_lower)
    if decade_match:
        decade_start = f"{decade_match.group(1)}0"
        decade_end = f"{decade_match.group(1)}9"
        return f"{decade_start}/{decade_end}", DatePrecision.DECADE

    # Pattern: approximate "abt", "about", "c.", "circa"
    approx_match = re.match(r"^(?:abt\.?|about|c\.?|circa)\s*(\d{4})$", date_lower)
    if approx_match:
        return approx_match.group(1), DatePrecision.APPROXIMATE

    # Pattern: full date "DD Mon YYYY" or "Mon DD, YYYY"
    for pattern, fmt in [
        (r"(\d{1,2})\s+(\w+)\s+(\d{4})", "dmy"),
        (r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", "mdy"),
        (r"(\d{4})-(\d{2})-(\d{2})", "iso"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "mdy_slash"),
    ]:
        match = re.match(pattern, date_string, re.IGNORECASE)
        if match:
            if fmt == "dmy":
                day, month_str, year = match.groups()
                month = months.get(month_str.lower())
                if month:
                    return f"{year}-{month}-{int(day):02d}", DatePrecision.EXACT
            elif fmt == "mdy":
                month_str, day, year = match.groups()
                month = months.get(month_str.lower())
                if month:
                    return f"{year}-{month}-{int(day):02d}", DatePrecision.EXACT
            elif fmt == "iso":
                return date_string, DatePrecision.EXACT
            elif fmt == "mdy_slash":
                month, day, year = match.groups()
                return f"{year}-{int(month):02d}-{int(day):02d}", DatePrecision.EXACT

    # Pattern: month and year "December 1900"
    month_year_match = re.match(r"(\w+)\s+(\d{4})", date_string, re.IGNORECASE)
    if month_year_match:
        month_str, year = month_year_match.groups()
        month = months.get(month_str.lower())
        if month:
            return f"{year}-{month}", DatePrecision.YEAR_MONTH

    # Pattern: year only "1900"
    year_match = re.match(r"^(\d{4})$", date_string)
    if year_match:
        return year_match.group(1), DatePrecision.YEAR

    # Fallback: try to extract any 4-digit year
    any_year = re.search(r"\d{4}", date_string)
    if any_year:
        return any_year.group(), DatePrecision.APPROXIMATE

    return date_string, DatePrecision.APPROXIMATE


def calculate_temporal_proximity_bonus(
    source_date: datetime | None,
    event_date: datetime | None,
    source_type: EvidenceClass,
) -> float:
    """Calculate temporal proximity bonus for evidence weighting.

    Sources created closer to the event time are more reliable.
    The bonus is +0.05 for sources within 5 years of the event,
    scaling down to 0 for sources 50+ years after.

    Primary sources created at the time of the event get full bonus.

    Args:
        source_date: When the source was created
        event_date: When the event occurred
        source_type: Classification of the source

    Returns:
        Temporal proximity bonus (-0.05 to +0.05)
    """
    MAX_BONUS = 0.05
    OPTIMAL_WINDOW_YEARS = 5
    DECAY_WINDOW_YEARS = 50

    # Primary official sources created at event time get max bonus
    if source_type in (EvidenceClass.PRIMARY_OFFICIAL, EvidenceClass.PRIMARY_GOVERNMENT):
        return MAX_BONUS

    if not source_date or not event_date:
        return 0.0

    years_after = (source_date.year - event_date.year)

    # Sources before the event are suspect (unless they're predictions like wills)
    if years_after < 0:
        return -0.05  # Penalty for anachronistic sources

    # Within optimal window: full bonus
    if years_after <= OPTIMAL_WINDOW_YEARS:
        return MAX_BONUS

    # Decay linearly from OPTIMAL to DECAY window
    if years_after <= DECAY_WINDOW_YEARS:
        decay_range = DECAY_WINDOW_YEARS - OPTIMAL_WINDOW_YEARS
        years_into_decay = years_after - OPTIMAL_WINDOW_YEARS
        return MAX_BONUS * (1 - years_into_decay / decay_range)

    # Beyond decay window: no bonus
    return 0.0


def detect_error_patterns(
    fact_type: FactType,
    proposed_value: Any,
    source_type: EvidenceClass,
    context: dict[str, Any] | None = None,
) -> list[tuple[ErrorPatternType, float]]:
    """Detect known genealogical error patterns and return penalties.

    Args:
        fact_type: Type of the fact being claimed
        proposed_value: The proposed value for the fact
        source_type: Classification of the source
        context: Additional context (e.g., other known facts about the person)

    Returns:
        List of (detected pattern, penalty) tuples
    """
    patterns: list[tuple[ErrorPatternType, float]] = []
    context = context or {}

    if fact_type == FactType.DEATH:
        # Tombstone Error: Death date rounded to Jan 1 or significant dates
        if isinstance(proposed_value, (datetime, str)):
            date_str = str(proposed_value)
            if "-01-01" in date_str or "-12-31" in date_str:
                patterns.append((ErrorPatternType.TOMBSTONE_ERROR, -0.10))

    if fact_type == FactType.BIRTH:
        # Military Age Padding: Check if person appears in military records with inflated age
        if context.get("has_military_records") and context.get("military_enlistment_year"):
            # If claimed birth year would make them under 18 at enlistment, suspect padding
            birth_year = None
            if isinstance(proposed_value, datetime):
                birth_year = proposed_value.year
            elif isinstance(proposed_value, str) and proposed_value.isdigit():
                birth_year = int(proposed_value)
            if birth_year:
                enlistment_year = context.get("military_enlistment_year")
                if enlistment_year - birth_year < 18:
                    patterns.append((ErrorPatternType.MILITARY_AGE_PADDING, -0.08))

        # Immigration Age Reduction: Common for young immigrants
        if context.get("has_immigration_records"):
            patterns.append((ErrorPatternType.IMMIGRATION_AGE_REDUCTION, -0.05))

    if fact_type in (FactType.BIRTH, FactType.DEATH) and source_type == EvidenceClass.PRIMARY_GOVERNMENT:
        # Census Approximation: Ages in census records are often rounded
        if context.get("source_is_census"):
            patterns.append((ErrorPatternType.CENSUS_APPROXIMATION, -0.07))

    # Generational Confusion: Father/son with same name
    if context.get("has_same_name_relative"):
        patterns.append((ErrorPatternType.GENERATIONAL_CONFUSION, -0.15))

    return patterns
