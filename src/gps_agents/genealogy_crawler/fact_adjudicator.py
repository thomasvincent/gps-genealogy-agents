"""Fact Adjudicator for validating and resolving genealogical claims.

The FactAdjudicator is responsible for:
1. Comparing ExtractedClaim against RawSourceSnippet to verify explicit support
2. Normalizing dates to ISO-8601 format
3. Detecting living persons (flag + heuristic) and applying REDACTION MASK
4. Creating CompetingAssertion objects when conflicts are detected
5. Triggering Conflict Analyst tie-breaker workflow for resolution

This implements the "Paper Trail of Doubt" concept - no data is discarded,
all competing claims are preserved inline in the graph.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from .models_v2 import (
    CompetingAssertion,
    DatePrecision,
    ErrorPatternType,
    EvidenceClass,
    FactType,
    FuzzyDate,
    NegativeEvidence,
    Person,
    ResolutionStatus,
    calculate_temporal_proximity_bonus,
    detect_error_patterns,
    is_living,
    normalize_date_to_iso8601,
)

if TYPE_CHECKING:
    from .llm.wrapper import LLMRegistry
    from .llm.schemas import ConflictAnalysisTiebreakerOutput

logger = logging.getLogger(__name__)


# Living person redaction mask
LIVING_PERSON_MASK = "[LIVING PERSON - DATA PROTECTED]"

# High-stakes fact types that require stricter review
HIGH_STAKES_FACT_TYPES = {
    FactType.BIRTH,
    FactType.DEATH,
}


@dataclass
class AdjudicationResult:
    """Result of adjudicating a claim against existing data."""
    claim_id: UUID
    accepted: bool
    normalized_value: Any
    normalized_date_iso: str | None = None
    date_precision: DatePrecision | None = None

    # Conflict detection
    conflict_detected: bool = False
    competing_assertion: CompetingAssertion | None = None

    # Living person detection
    living_person_detected: bool = False
    redacted: bool = False

    # Validation details
    citation_found_in_source: bool = False
    hallucination_detected: bool = False
    rationale: str = ""

    # Error patterns
    detected_patterns: list[ErrorPatternType] = field(default_factory=list)
    pattern_penalty: float = 0.0


@dataclass
class ConflictResolutionResult:
    """Result of running the conflict resolution workflow."""
    conflict_group_id: UUID
    resolved: bool = False
    winning_assertion_id: UUID | None = None
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING_REVIEW
    confidence: float = 0.0
    tie_breaker_queries: list[str] = field(default_factory=list)
    human_review_required: bool = False
    rationale: str = ""


class FactAdjudicator:
    """Validates extracted claims and manages conflict resolution.

    The FactAdjudicator orchestrates the validation workflow:
    1. Check if citation exists in source text (hallucination firewall)
    2. Normalize dates to ISO-8601
    3. Detect living persons and apply redaction
    4. Check for conflicts with existing assertions
    5. Create CompetingAssertion if conflict detected
    6. Trigger tie-breaker workflow for resolution
    """

    def __init__(
        self,
        llm_registry: "LLMRegistry | None" = None,
        existing_assertions: dict[str, list[Any]] | None = None,
        strict_citation_check: bool = True,
    ):
        """Initialize the FactAdjudicator.

        Args:
            llm_registry: Registry of LLM wrappers for conflict analysis
            existing_assertions: Map of subject_id -> list of existing assertions
            strict_citation_check: If True, reject claims without citation in source
        """
        self.llm_registry = llm_registry
        self.existing_assertions = existing_assertions or {}
        self.strict_citation_check = strict_citation_check

        # Track competing assertions by subject and fact type
        self._competing_assertions: dict[str, list[CompetingAssertion]] = {}

    def adjudicate_claim(
        self,
        claim: dict[str, Any],
        source_text: str,
        subject_id: UUID,
        fact_type: FactType,
        source_metadata: dict[str, Any] | None = None,
        subject_context: dict[str, Any] | None = None,
    ) -> AdjudicationResult:
        """Adjudicate a single claim against source text and existing data.

        Args:
            claim: The extracted claim dictionary with keys:
                - claim_text: The textual claim
                - claim_value: The extracted value
                - citation_snippet: Quote from source supporting claim
                - prior_weight: Bayesian prior weight
            source_text: The raw source document text
            subject_id: UUID of the subject (person/relationship/event)
            fact_type: Type of fact being claimed
            source_metadata: Optional metadata about the source (date, type, tier)
            subject_context: Optional context about the subject for pattern detection

        Returns:
            AdjudicationResult with validation and conflict details
        """
        claim_id = UUID(claim.get("claim_id", str(uuid4())))
        claim_value = claim.get("claim_value")
        citation = claim.get("citation_snippet", "")
        prior_weight = claim.get("prior_weight", 0.5)

        source_metadata = source_metadata or {}
        subject_context = subject_context or {}

        result = AdjudicationResult(
            claim_id=claim_id,
            accepted=False,
            normalized_value=claim_value,
        )

        # Step 1: Check citation exists in source (hallucination firewall)
        if citation:
            result.citation_found_in_source = self._check_citation_exists(
                citation, source_text
            )
            if not result.citation_found_in_source:
                result.hallucination_detected = True
                result.rationale = f"Citation not found in source: '{citation[:50]}...'"
                if self.strict_citation_check:
                    return result

        # Step 2: Normalize dates
        if fact_type in (FactType.BIRTH, FactType.DEATH, FactType.MARRIAGE):
            normalized, precision = self._normalize_date(claim_value)
            result.normalized_value = normalized
            result.normalized_date_iso = normalized
            result.date_precision = precision

        # Step 3: Detect living person
        if self._should_check_living_status(fact_type, subject_context):
            is_alive = self._detect_living_person(
                fact_type, result.normalized_value, subject_context
            )
            if is_alive:
                result.living_person_detected = True
                result.redacted = True
                result.normalized_value = LIVING_PERSON_MASK
                result.rationale = "Living person detected - data redacted"
                result.accepted = True
                return result

        # Step 4: Detect error patterns
        source_type = source_metadata.get(
            "evidence_class", EvidenceClass.SECONDARY_PUBLISHED
        )
        patterns = detect_error_patterns(
            fact_type, result.normalized_value, source_type, subject_context
        )
        if patterns:
            result.detected_patterns = [p[0] for p in patterns]
            result.pattern_penalty = sum(p[1] for p in patterns)

        # Step 5: Calculate temporal proximity bonus
        source_date = source_metadata.get("source_date")
        event_date = self._extract_event_date(result.normalized_value, fact_type)
        temporal_bonus = calculate_temporal_proximity_bonus(
            source_date, event_date, source_type
        )

        # Step 6: Check for conflicts with existing assertions
        existing = self._get_existing_assertions(subject_id, fact_type)
        if existing:
            conflict = self._detect_conflict(result.normalized_value, existing)
            if conflict:
                result.conflict_detected = True
                result.competing_assertion = self._create_competing_assertion(
                    subject_id=subject_id,
                    fact_type=fact_type,
                    proposed_value=result.normalized_value,
                    evidence_claim_ids=[claim_id],
                    prior_weight=prior_weight,
                    temporal_bonus=temporal_bonus,
                    patterns=result.detected_patterns,
                    pattern_penalty=result.pattern_penalty,
                    existing_assertions=existing,
                )
                result.rationale = (
                    f"Conflict detected with existing assertion(s). "
                    f"Created CompetingAssertion {result.competing_assertion.id}"
                )

        result.accepted = True
        return result

    def resolve_conflicts(
        self,
        subject_id: UUID,
        fact_type: FactType,
        subject_name: str = "Unknown",
        subject_context: dict[str, Any] | None = None,
    ) -> ConflictResolutionResult:
        """Run the conflict resolution workflow for a subject's competing assertions.

        This triggers the Conflict Analyst tie-breaker LLM to analyze
        competing assertions and determine the resolution strategy.

        Args:
            subject_id: UUID of the subject
            fact_type: Type of fact in conflict
            subject_name: Display name for the subject
            subject_context: Context about the subject for pattern detection

        Returns:
            ConflictResolutionResult with resolution details
        """
        key = f"{subject_id}:{fact_type.value}"
        competing = self._competing_assertions.get(key, [])

        if len(competing) < 2:
            return ConflictResolutionResult(
                conflict_group_id=uuid4(),
                resolved=True,
                rationale="No conflict to resolve (fewer than 2 competing assertions)",
            )

        conflict_group_id = competing[0].conflict_group_id or uuid4()

        # If no LLM registry, return pending status
        if self.llm_registry is None:
            return ConflictResolutionResult(
                conflict_group_id=conflict_group_id,
                resolution_status=ResolutionStatus.PENDING_REVIEW,
                rationale="LLM registry not configured - manual review required",
                human_review_required=True,
            )

        # Build input for Conflict Analyst
        tiebreaker_input = self._build_tiebreaker_input(
            subject_id, subject_name, fact_type, competing, subject_context
        )

        # Run tie-breaker analysis
        output = self.llm_registry.conflict_analyst_tiebreaker.analyze(tiebreaker_input)

        return self._process_tiebreaker_output(
            output, competing, conflict_group_id, fact_type
        )

    def get_pending_conflicts(
        self, subject_id: UUID | None = None
    ) -> list[CompetingAssertion]:
        """Get all pending competing assertions, optionally filtered by subject.

        Args:
            subject_id: Optional filter by subject

        Returns:
            List of CompetingAssertion objects with PENDING_REVIEW status
        """
        pending = []
        for key, assertions in self._competing_assertions.items():
            for assertion in assertions:
                if assertion.status == ResolutionStatus.PENDING_REVIEW:
                    if subject_id is None or assertion.subject_id == subject_id:
                        pending.append(assertion)
        return pending

    def trigger_recursive_healing(
        self,
        resolved_assertion: CompetingAssertion,
    ) -> list[UUID]:
        """Trigger recursive healing when a conflict is resolved.

        When a conflict is resolved, downstream relationships that depend
        on the resolved value may need to be re-evaluated.

        Args:
            resolved_assertion: The assertion that was just resolved

        Returns:
            List of subject IDs that need re-evaluation
        """
        # This would integrate with the graph store to find dependent assertions
        # For now, return empty list - implementation depends on graph store
        logger.info(
            f"Recursive healing triggered for {resolved_assertion.subject_id}, "
            f"fact_type={resolved_assertion.fact_type}"
        )
        return []

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _check_citation_exists(
        self, citation: str, source_text: str, fuzzy: bool = True
    ) -> bool:
        """Check if a citation snippet exists in source text."""
        if not citation or not source_text:
            return False

        if fuzzy:
            # Normalize whitespace and case
            norm_citation = " ".join(citation.lower().split())
            norm_source = " ".join(source_text.lower().split())
            return norm_citation in norm_source
        else:
            return citation in source_text

    def _normalize_date(self, value: Any) -> tuple[str, DatePrecision]:
        """Normalize a date value to ISO-8601 format."""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d"), DatePrecision.EXACT
        if isinstance(value, str):
            return normalize_date_to_iso8601(value)
        if isinstance(value, FuzzyDate):
            if value.date:
                return value.date.strftime("%Y-%m-%d"), value.precision
            return value.display, value.precision
        return str(value), DatePrecision.APPROXIMATE

    def _should_check_living_status(
        self, fact_type: FactType, context: dict[str, Any]
    ) -> bool:
        """Determine if living status check should be performed."""
        # Always check for birth/death dates on persons
        if fact_type in (FactType.BIRTH, FactType.DEATH):
            return context.get("subject_type", "person") == "person"
        return False

    def _detect_living_person(
        self,
        fact_type: FactType,
        value: Any,
        context: dict[str, Any],
    ) -> bool:
        """Detect if the subject is likely a living person.

        Uses both explicit flags and heuristic rules (100-year rule).
        """
        # Explicit flag takes precedence
        if context.get("living_flag") is True:
            return True

        # If we have a death date, person is not living
        if fact_type == FactType.DEATH and value and value != LIVING_PERSON_MASK:
            return False

        # 100-year heuristic for birth dates
        if fact_type == FactType.BIRTH and value:
            try:
                # Extract year from normalized date
                if isinstance(value, str):
                    parts = value.split("-")
                    if parts and parts[0].isdigit():
                        birth_year = int(parts[0])
                        current_year = datetime.now(UTC).year
                        age = current_year - birth_year
                        if age < 100:
                            return True
                        if age >= 120:
                            return False
            except (ValueError, IndexError):
                pass

        # Check for modern indicators
        modern_indicators = ["email", "phone", "social_media"]
        for indicator in modern_indicators:
            if indicator in context:
                return True

        # Default to conservative assumption (living)
        return context.get("assume_living", True)

    def _extract_event_date(
        self, value: Any, fact_type: FactType
    ) -> datetime | None:
        """Extract a datetime from a value for temporal proximity calculation."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Try to parse ISO-8601
                if "-" in value:
                    parts = value.replace("/", "-").split("-")
                    if len(parts) >= 1 and parts[0].isdigit():
                        year = int(parts[0])
                        month = int(parts[1]) if len(parts) > 1 else 1
                        day = int(parts[2]) if len(parts) > 2 else 1
                        return datetime(year, month, day, tzinfo=UTC)
            except (ValueError, IndexError):
                pass
        return None

    def _get_existing_assertions(
        self, subject_id: UUID, fact_type: FactType
    ) -> list[Any]:
        """Get existing assertions for a subject and fact type."""
        key = str(subject_id)
        all_assertions = self.existing_assertions.get(key, [])
        return [
            a for a in all_assertions
            if getattr(a, "fact_type", None) == fact_type
            or (isinstance(a, dict) and a.get("fact_type") == fact_type.value)
        ]

    def _detect_conflict(
        self, new_value: Any, existing: list[Any]
    ) -> bool:
        """Detect if a new value conflicts with existing assertions."""
        new_str = str(new_value).lower().strip()

        for assertion in existing:
            existing_value = (
                assertion.proposed_value
                if hasattr(assertion, "proposed_value")
                else assertion.get("value", assertion.get("proposed_value"))
            )
            existing_str = str(existing_value).lower().strip()

            # Values are different = conflict
            if new_str != existing_str:
                return True

        return False

    def _create_competing_assertion(
        self,
        subject_id: UUID,
        fact_type: FactType,
        proposed_value: Any,
        evidence_claim_ids: list[UUID],
        prior_weight: float,
        temporal_bonus: float,
        patterns: list[ErrorPatternType],
        pattern_penalty: float,
        existing_assertions: list[Any],
    ) -> CompetingAssertion:
        """Create a CompetingAssertion for a conflicting claim."""
        # Generate or get conflict group ID
        conflict_group_id = None
        for existing in existing_assertions:
            if hasattr(existing, "conflict_group_id") and existing.conflict_group_id:
                conflict_group_id = existing.conflict_group_id
                break
        if conflict_group_id is None:
            conflict_group_id = uuid4()

        assertion = CompetingAssertion(
            subject_id=subject_id,
            fact_type=fact_type,
            proposed_value=proposed_value,
            evidence_claim_ids=evidence_claim_ids,
            prior_weight=prior_weight,
            temporal_proximity_bonus=temporal_bonus,
            detected_patterns=patterns,
            pattern_penalty=pattern_penalty,
            conflict_group_id=conflict_group_id,
            status=ResolutionStatus.PENDING_REVIEW,
        )

        # Store in competing assertions map
        key = f"{subject_id}:{fact_type.value}"
        if key not in self._competing_assertions:
            self._competing_assertions[key] = []
        self._competing_assertions[key].append(assertion)

        return assertion

    def _build_tiebreaker_input(
        self,
        subject_id: UUID,
        subject_name: str,
        fact_type: FactType,
        competing: list[CompetingAssertion],
        context: dict[str, Any] | None,
    ) -> "ConflictAnalysisTiebreakerInput":
        """Build input for the Conflict Analyst tie-breaker."""
        from .llm.schemas import ConflictAnalysisTiebreakerInput

        return ConflictAnalysisTiebreakerInput(
            subject_id=str(subject_id),
            subject_name=subject_name,
            fact_type=fact_type.value,
            competing_assertions=[
                {
                    "id": str(a.id),
                    "proposed_value": a.proposed_value,
                    "prior_weight": a.prior_weight,
                    "temporal_bonus": a.temporal_proximity_bonus,
                    "detected_patterns": [p.value for p in a.detected_patterns],
                    "pattern_penalty": a.pattern_penalty,
                    "evidence_claim_ids": [str(e) for e in a.evidence_claim_ids],
                }
                for a in competing
            ],
            subject_context=context or {},
        )

    def _process_tiebreaker_output(
        self,
        output: "ConflictAnalysisTiebreakerOutput",
        competing: list[CompetingAssertion],
        conflict_group_id: UUID,
        fact_type: FactType,
    ) -> ConflictResolutionResult:
        """Process the output from Conflict Analyst tie-breaker."""
        result = ConflictResolutionResult(
            conflict_group_id=conflict_group_id,
            confidence=output.current_confidence,
            tie_breaker_queries=[q.query_string for q in output.tie_breaker_queries],
            rationale=output.analysis,
        )

        # Map resolution status
        status_map = {
            "resolved": ResolutionStatus.RESOLVED,
            "pending_tiebreaker": ResolutionStatus.PENDING_REVIEW,
            "insufficient_evidence": ResolutionStatus.INSUFFICIENT_EVIDENCE,
            "human_review_required": ResolutionStatus.HUMAN_REVIEW_REQUIRED,
        }
        result.resolution_status = status_map.get(
            output.resolution_status, ResolutionStatus.PENDING_REVIEW
        )

        # Check if human review is required
        should_escalate = (
            self.llm_registry.conflict_analyst_tiebreaker.should_escalate_to_human(
                output, fact_type.value
            )
            if self.llm_registry
            else True
        )
        result.human_review_required = should_escalate

        # If resolved, mark the winning assertion
        if output.resolution_status == "resolved" and output.current_winning_assertion_index is not None:
            result.resolved = True
            winner_idx = output.current_winning_assertion_index
            if 0 <= winner_idx < len(competing):
                winner = competing[winner_idx]
                result.winning_assertion_id = winner.id
                winner.mark_resolved(
                    ResolutionStatus.RESOLVED,
                    output.analysis,
                    "conflict_analyst_tiebreaker",
                )

                # Mark losers as rejected
                for i, assertion in enumerate(competing):
                    if i != winner_idx:
                        assertion.mark_resolved(
                            ResolutionStatus.REJECTED,
                            f"Rejected in favor of assertion {winner.id}",
                            "conflict_analyst_tiebreaker",
                        )

        return result
