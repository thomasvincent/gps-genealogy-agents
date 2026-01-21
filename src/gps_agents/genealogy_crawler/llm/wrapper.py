"""LLM wrapper with structured output enforcement and hallucination firewall.

This module provides a type-safe interface to LLM calls with:
- JSON schema enforcement via Pydantic models
- Hallucination firewall validating citations exist in source
- Role-specific prompts and output parsing
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .prompts import ROLE_PROMPTS
from .schemas import (
    ConflictAnalysisTiebreakerInput,
    ConflictAnalysisTiebreakerOutput,
    ConflictInput,
    ConflictOutput,
    ExtractionVerifierInput,
    ExtractionVerifierOutput,
    PlannerInput,
    PlannerOutput,
    QueryExpanderInput,
    QueryExpanderOutput,
    ResolverInput,
    ResolverOutput,
    VerifierInput,
    VerifierOutput,
)

if TYPE_CHECKING:
    from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Type variables for generic I/O
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


# =============================================================================
# Hallucination Firewall
# =============================================================================


class HallucinationViolation(str, Enum):
    """Formal violation codes for the Hallucination Firewall.

    These codes provide machine-readable rejection reasons when facts
    fail validation before being written to the knowledge graph.
    """
    # Citation & Evidence Issues (HF_001-HF_009)
    HF_001_CITATION_MISSING = "hf_001_citation_missing"
    HF_002_CITATION_NOT_IN_SOURCE = "hf_002_citation_not_in_source"
    HF_003_VALUE_NOT_IN_SOURCE = "hf_003_value_not_in_source"

    # Confidence & Scoring Issues (HF_010-HF_019)
    HF_010_LOW_CONFIDENCE = "hf_010_low_confidence"
    HF_011_CONFIDENCE_OUT_OF_BOUNDS = "hf_011_confidence_out_of_bounds"
    HF_012_CONFIDENCE_INFLATION = "hf_012_confidence_inflation"

    # Fact Classification Issues (HF_020-HF_029)
    HF_020_HYPOTHESIS_MARKED_AS_FACT = "hf_020_hypothesis_marked_as_fact"
    HF_021_INFERENCE_WITHOUT_EVIDENCE = "hf_021_inference_without_evidence"

    # Privacy & Compliance Issues (HF_030-HF_039)
    HF_030_PII_UNREDACTED = "hf_030_pii_unredacted"
    HF_031_LIVING_PERSON_EXPOSED = "hf_031_living_person_exposed"

    # Conflict & Provenance Issues (HF_040-HF_049)
    HF_040_CONFLICT_UNRESOLVED = "hf_040_conflict_unresolved"
    HF_041_CONTRADICTS_HIGHER_TIER = "hf_041_contradicts_higher_tier"
    HF_042_PROVENANCE_BROKEN = "hf_042_provenance_broken"

    # Chronology & Logic Issues (HF_050-HF_059)
    HF_050_CHRONOLOGY_IMPOSSIBLE = "hf_050_chronology_impossible"
    HF_051_DATE_BEFORE_BIRTH = "hf_051_date_before_birth"
    HF_052_DATE_AFTER_DEATH = "hf_052_date_after_death"


@dataclass
class HallucinationViolationDetail:
    """Detailed violation record with code and context."""
    code: HallucinationViolation
    message: str
    field: str | None = None
    expected: str | None = None
    actual: str | None = None


@dataclass
class HallucinationCheckResult:
    """Result of hallucination firewall validation."""
    passed: bool
    violations: list[HallucinationViolationDetail] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def violation_codes(self) -> list[HallucinationViolation]:
        """Get just the violation codes for quick filtering."""
        return [v.code for v in self.violations]

    @property
    def violation_messages(self) -> list[str]:
        """Get human-readable violation messages (backwards compatible)."""
        return [f"[{v.code.value}] {v.message}" for v in self.violations]

    def has_violation(self, code: HallucinationViolation) -> bool:
        """Check if a specific violation occurred."""
        return code in self.violation_codes


def check_citation_exists(citation: str, source_text: str, fuzzy: bool = False) -> bool:
    """Check if a citation snippet exists in source text.

    Args:
        citation: The citation snippet to find
        source_text: The full source text to search
        fuzzy: If True, allow minor whitespace/case differences
    """
    if not citation:
        return False

    if fuzzy:
        # Normalize whitespace and case for fuzzy matching
        norm_citation = " ".join(citation.lower().split())
        norm_source = " ".join(source_text.lower().split())
        return norm_citation in norm_source
    else:
        return citation in source_text


def hallucination_firewall(
    llm_output: VerifierOutput,
    source_text: str,
    strict: bool = True,
    min_confidence: float = 0.7,
) -> HallucinationCheckResult:
    """Validate LLM verifier output against source text.

    Implements the hallucination firewall checklist from the architecture doc.
    This is the final veto gate before facts are written to the ledger.

    Args:
        llm_output: The parsed VerifierOutput from the LLM
        source_text: The original source text used for extraction
        strict: If True, fail on any violation; if False, collect warnings
        min_confidence: Minimum confidence threshold for acceptance (default 0.7)

    Returns:
        HallucinationCheckResult with passed status and any violations
    """
    violations: list[HallucinationViolationDetail] = []
    warnings: list[str] = []

    # Check 1 & 2: Citation required and exists for verified fields
    for result in llm_output.verification_results:
        if result.status == "Verified":
            if not result.citation_snippet:
                violations.append(
                    HallucinationViolationDetail(
                        code=HallucinationViolation.HF_001_CITATION_MISSING,
                        message=f"Field '{result.field}' verified without citation",
                        field=result.field,
                    )
                )
            elif not check_citation_exists(result.citation_snippet, source_text, fuzzy=True):
                violations.append(
                    HallucinationViolationDetail(
                        code=HallucinationViolation.HF_002_CITATION_NOT_IN_SOURCE,
                        message=f"Citation not found in source for '{result.field}'",
                        field=result.field,
                        expected=result.citation_snippet[:100] if result.citation_snippet else None,
                    )
                )

        # Check 3-5: No invented data
        if result.status == "Verified" and result.value:
            value_str = str(result.value)
            # Simple check: value should appear somewhere in source
            if len(value_str) > 3 and value_str not in source_text:
                # Could be formatted differently, just warn
                warnings.append(
                    f"Value '{value_str}' for field '{result.field}' "
                    f"not found verbatim in source (may be reformatted)"
                )

        # Check: Low confidence warning
        if result.status == "Verified" and result.confidence < min_confidence:
            violations.append(
                HallucinationViolationDetail(
                    code=HallucinationViolation.HF_010_LOW_CONFIDENCE,
                    message=f"Confidence {result.confidence:.2f} below threshold {min_confidence}",
                    field=result.field,
                    expected=f">= {min_confidence}",
                    actual=f"{result.confidence:.2f}",
                )
            )

    # Check 6: Hypotheses must not be marked as facts
    for hypo in llm_output.hypotheses:
        if hypo.is_fact:
            violations.append(
                HallucinationViolationDetail(
                    code=HallucinationViolation.HF_020_HYPOTHESIS_MARKED_AS_FACT,
                    message=f"Hypothesis incorrectly marked as fact: '{hypo.text[:50]}...'",
                )
            )

    # Check 7: Confidence bounds (enforced by schema, but double-check)
    for result in llm_output.verification_results:
        if not (0.0 <= result.confidence <= 1.0):
            violations.append(
                HallucinationViolationDetail(
                    code=HallucinationViolation.HF_011_CONFIDENCE_OUT_OF_BOUNDS,
                    message=f"Invalid confidence {result.confidence} for field '{result.field}'",
                    field=result.field,
                    expected="0.0 <= confidence <= 1.0",
                    actual=str(result.confidence),
                )
            )

    passed = len(violations) == 0 if strict else True

    return HallucinationCheckResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
    )


# =============================================================================
# Abstract LLM Client
# =============================================================================


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> str:
        """Send a completion request to the LLM.

        Args:
            system_prompt: The system prompt defining the role
            user_message: The user message with input data
            temperature: Sampling temperature (0.0 for deterministic)

        Returns:
            The raw text response from the LLM
        """
        ...


class AnthropicClient(LLMClient):
    """Anthropic Claude client implementation."""

    def __init__(
        self,
        client: "Anthropic | None" = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the Anthropic client.

        Args:
            client: Optional pre-configured Anthropic client
            model: Model to use (default: Claude 3.5 Sonnet)
        """
        if client is None:
            from anthropic import Anthropic
            client = Anthropic()
        self._client = client
        self._model = model

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> str:
        """Send a completion request to Claude."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # Extract text from response
        if response.content and len(response.content) > 0:
            return response.content[0].text
        return ""


class MockLLMClient(LLMClient):
    """Mock client for testing."""

    def __init__(self, responses: dict[str, str] | None = None):
        """Initialize with predefined responses."""
        self._responses = responses or {}
        self._call_history: list[tuple[str, str]] = []

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> str:
        """Return mock response."""
        self._call_history.append((system_prompt, user_message))
        # Try to find a matching response
        for key, response in self._responses.items():
            if key in system_prompt or key in user_message:
                return response
        return "{}"


# =============================================================================
# Structured LLM Wrapper
# =============================================================================


class StructuredLLMWrapper(Generic[InputT, OutputT]):
    """Wrapper for LLM calls with structured I/O enforcement.

    This wrapper:
    1. Serializes Pydantic input to JSON
    2. Calls the LLM with role-specific prompt
    3. Parses response into Pydantic output
    4. Validates output structure
    """

    def __init__(
        self,
        client: LLMClient,
        role: str,
        input_schema: type[InputT],
        output_schema: type[OutputT],
        temperature: float = 0.0,
    ):
        """Initialize the wrapper.

        Args:
            client: The LLM client to use
            role: Role name (planner, verifier, resolver, conflict_analyst)
            input_schema: Pydantic model for input validation
            output_schema: Pydantic model for output validation
            temperature: Sampling temperature
        """
        self._client = client
        self._role = role
        self._input_schema = input_schema
        self._output_schema = output_schema
        self._temperature = temperature

        if role not in ROLE_PROMPTS:
            raise ValueError(f"Unknown role: {role}. Valid: {list(ROLE_PROMPTS.keys())}")

        self._system_prompt = ROLE_PROMPTS[role]

    def _build_user_message(self, input_data: InputT) -> str:
        """Build user message from input data."""
        schema_json = self._output_schema.model_json_schema()

        return f"""\
INPUT:
{input_data.model_dump_json(indent=2)}

OUTPUT SCHEMA:
{json.dumps(schema_json, indent=2)}

Respond with valid JSON matching the schema exactly. Do not include any text outside the JSON object.
"""

    def _parse_response(self, response: str) -> OutputT:
        """Parse LLM response into output schema."""
        # Try to extract JSON from response
        response = response.strip()

        # Handle markdown code blocks
        if response.startswith("```"):
            lines = response.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            response = "\n".join(json_lines)

        # Parse JSON
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}") from e

        # Validate against schema
        try:
            return self._output_schema.model_validate(data)
        except ValidationError as e:
            raise ValueError(f"LLM response doesn't match schema: {e}") from e

    def invoke(self, input_data: InputT, max_retries: int = 2) -> OutputT:
        """Invoke the LLM with structured I/O.

        Args:
            input_data: Validated input data
            max_retries: Number of retries on parse failure

        Returns:
            Validated output data

        Raises:
            ValueError: If response cannot be parsed after retries
        """
        user_message = self._build_user_message(input_data)

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self._client.complete(
                    system_prompt=self._system_prompt,
                    user_message=user_message,
                    temperature=self._temperature,
                )
                return self._parse_response(response)
            except ValueError as e:
                last_error = e
                logger.warning(
                    f"LLM parse attempt {attempt + 1} failed: {e}"
                )
                if attempt < max_retries:
                    # Slightly increase temperature for retry
                    self._temperature = min(0.3, self._temperature + 0.1)

        raise ValueError(
            f"Failed to get valid response after {max_retries + 1} attempts: {last_error}"
        )


# =============================================================================
# Role-Specific Wrappers
# =============================================================================


class PlannerLLM:
    """Wrapper for the Planner/Orchestrator LLM role."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="planner",
            input_schema=PlannerInput,
            output_schema=PlannerOutput,
            temperature=0.1,  # Slight creativity for planning
        )

    def plan(self, input_data: PlannerInput) -> PlannerOutput:
        """Generate a research plan."""
        return self._wrapper.invoke(input_data)


class VerifierLLM:
    """Wrapper for the LLM Verifier role with hallucination firewall."""

    def __init__(self, client: LLMClient, strict: bool = True):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="verifier",
            input_schema=VerifierInput,
            output_schema=VerifierOutput,
            temperature=0.0,  # Deterministic for verification
        )
        self._strict = strict

    def verify(
        self,
        input_data: VerifierInput,
    ) -> tuple[VerifierOutput, HallucinationCheckResult]:
        """Verify extracted fields and run hallucination firewall.

        Returns:
            Tuple of (VerifierOutput, HallucinationCheckResult)
        """
        output = self._wrapper.invoke(input_data)

        # Run hallucination firewall
        firewall_result = hallucination_firewall(
            llm_output=output,
            source_text=input_data.raw_text,
            strict=self._strict,
        )

        return output, firewall_result


class ResolverLLM:
    """Wrapper for the Entity Resolver LLM role."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="resolver",
            input_schema=ResolverInput,
            output_schema=ResolverOutput,
            temperature=0.0,
        )

    def resolve(self, input_data: ResolverInput) -> ResolverOutput:
        """Determine if two person records should be merged."""
        return self._wrapper.invoke(input_data)


class ConflictAnalystLLM:
    """Wrapper for the Conflict Analyst LLM role."""

    def __init__(self, client: LLMClient):
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="conflict_analyst",
            input_schema=ConflictInput,
            output_schema=ConflictOutput,
            temperature=0.0,
        )

    def analyze(self, input_data: ConflictInput) -> ConflictOutput:
        """Analyze and resolve conflicting evidence."""
        return self._wrapper.invoke(input_data)


class ExtractionVerifierLLM:
    """Wrapper for the Extraction Verifier LLM role.

    Validates extracted facts against source text, ensuring each confirmed
    field has an exact quote from the source document.
    """

    def __init__(self, client: LLMClient, strict: bool = True):
        """Initialize the extraction verifier.

        Args:
            client: The LLM client to use
            strict: If True, apply strict validation on quotes
        """
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="extraction_verifier",
            input_schema=ExtractionVerifierInput,
            output_schema=ExtractionVerifierOutput,
            temperature=0.0,  # Deterministic for verification
        )
        self._strict = strict

    def verify(
        self,
        input_data: ExtractionVerifierInput,
    ) -> tuple[ExtractionVerifierOutput, HallucinationCheckResult]:
        """Verify extracted fields against source text.

        Args:
            input_data: Input with raw_text and candidate extractions

        Returns:
            Tuple of (ExtractionVerifierOutput, HallucinationCheckResult)
        """
        output = self._wrapper.invoke(input_data)

        # Run hallucination check on the exact quotes
        violations: list[str] = []
        warnings: list[str] = []

        for field in output.verified_fields:
            if field.status == "Confirmed" and field.exact_quote:
                # Check that the exact quote actually exists in source
                if not check_citation_exists(
                    field.exact_quote, input_data.raw_text, fuzzy=True
                ):
                    violations.append(
                        f"Exact quote not found in source for '{field.field}': "
                        f"'{field.exact_quote[:50]}...'"
                    )

        firewall_result = HallucinationCheckResult(
            passed=len(violations) == 0 if self._strict else True,
            violations=violations,
            warnings=warnings,
        )

        return output, firewall_result

    def verify_simple(
        self, raw_text: str, extractions: dict[str, Any]
    ) -> ExtractionVerifierOutput:
        """Simplified verification interface.

        Args:
            raw_text: The source document text
            extractions: Dictionary of field -> value extractions

        Returns:
            ExtractionVerifierOutput with verified fields
        """
        from .schemas import ExtractedField

        input_data = ExtractionVerifierInput(
            raw_text=raw_text,
            candidate_extraction=[
                ExtractedField(field=k, value=v) for k, v in extractions.items()
            ],
        )
        output, _ = self.verify(input_data)
        return output


class QueryExpanderLLM:
    """Wrapper for the Query Expander (Clue Agent) LLM role.

    Analyzes confirmed facts and suggests strategic follow-up queries
    to fill gaps in genealogical research.
    """

    def __init__(self, client: LLMClient):
        """Initialize the query expander.

        Args:
            client: The LLM client to use
        """
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="query_expander",
            input_schema=QueryExpanderInput,
            output_schema=QueryExpanderOutput,
            temperature=0.2,  # Slight creativity for query generation
        )

    def expand(self, input_data: QueryExpanderInput) -> QueryExpanderOutput:
        """Generate follow-up queries based on confirmed facts.

        Args:
            input_data: Input with confirmed facts and research context

        Returns:
            QueryExpanderOutput with suggested deep search queries
        """
        return self._wrapper.invoke(input_data)

    def expand_simple(
        self,
        subject_name: str,
        confirmed_facts: dict[str, Any],
        already_searched: list[str] | None = None,
    ) -> QueryExpanderOutput:
        """Simplified query expansion interface.

        Args:
            subject_name: Name of the research subject
            confirmed_facts: Dictionary of field -> value confirmed facts
            already_searched: Optional list of queries already executed

        Returns:
            QueryExpanderOutput with suggested queries
        """
        from .schemas import ConfirmedFact

        input_data = QueryExpanderInput(
            subject_name=subject_name,
            confirmed_facts=[
                ConfirmedFact(field=k, value=v, confidence=0.9)
                for k, v in confirmed_facts.items()
            ],
            already_searched=already_searched or [],
        )
        return self.expand(input_data)


class ConflictAnalystTiebreakerLLM:
    """Wrapper for the Conflict Analyst Tie-Breaker LLM role.

    Performs forensic analysis of competing assertions to determine the
    most reliable value using:
    - Temporal proximity scoring (+0.05 for sources closer to event)
    - Error pattern detection (Tombstone Error, Military Age Padding, etc.)
    - Negative evidence consideration
    - Tie-breaker query generation
    """

    # High-stakes fields that warrant lower human review thresholds
    HIGH_STAKES_FIELDS = {"birth", "death", "parent_child", "birth_date", "death_date"}

    # Confidence differential threshold for automatic resolution
    RESOLUTION_THRESHOLD = 0.15
    HIGH_STAKES_THRESHOLD = 0.10

    def __init__(self, client: LLMClient):
        """Initialize the conflict analyst tie-breaker.

        Args:
            client: The LLM client to use
        """
        self._wrapper = StructuredLLMWrapper(
            client=client,
            role="conflict_analyst_tiebreaker",
            input_schema=ConflictAnalysisTiebreakerInput,
            output_schema=ConflictAnalysisTiebreakerOutput,
            temperature=0.0,  # Deterministic for conflict resolution
        )

    def analyze(
        self, input_data: ConflictAnalysisTiebreakerInput
    ) -> ConflictAnalysisTiebreakerOutput:
        """Analyze competing assertions and determine resolution strategy.

        Args:
            input_data: Input with competing assertions and context

        Returns:
            ConflictAnalysisTiebreakerOutput with analysis and recommendations
        """
        return self._wrapper.invoke(input_data)

    def analyze_simple(
        self,
        subject_id: str,
        subject_name: str,
        fact_type: str,
        competing_values: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> ConflictAnalysisTiebreakerOutput:
        """Simplified interface for conflict analysis.

        Args:
            subject_id: UUID of the subject
            subject_name: Display name
            fact_type: Type of fact in conflict
            competing_values: List of competing value dictionaries
            context: Optional subject context

        Returns:
            ConflictAnalysisTiebreakerOutput with analysis
        """
        input_data = ConflictAnalysisTiebreakerInput(
            subject_id=subject_id,
            subject_name=subject_name,
            fact_type=fact_type,
            competing_assertions=competing_values,
            subject_context=context or {},
        )
        return self.analyze(input_data)

    def should_escalate_to_human(
        self,
        output: ConflictAnalysisTiebreakerOutput,
        fact_type: str,
    ) -> bool:
        """Determine if conflict should be escalated to human review.

        Args:
            output: The analysis output from the LLM
            fact_type: Type of fact in conflict

        Returns:
            True if human review is recommended
        """
        if output.resolution_status == "human_review_required":
            return True

        # High-stakes fields have lower thresholds
        threshold = (
            self.HIGH_STAKES_THRESHOLD
            if fact_type.lower() in self.HIGH_STAKES_FIELDS
            else self.RESOLUTION_THRESHOLD
        )

        # If confidence is low and we have multiple assertions
        if output.current_confidence < 0.70:
            return True

        # Check if there's a clear winner
        if output.current_winning_assertion_index is None:
            return True

        return False


# =============================================================================
# Factory
# =============================================================================


@dataclass
class LLMRegistry:
    """Registry of LLM role wrappers for the crawler."""
    planner: PlannerLLM
    verifier: VerifierLLM
    resolver: ResolverLLM
    conflict_analyst: ConflictAnalystLLM
    conflict_analyst_tiebreaker: ConflictAnalystTiebreakerLLM
    extraction_verifier: ExtractionVerifierLLM
    query_expander: QueryExpanderLLM


def create_llm_registry(
    client: LLMClient | None = None,
    strict_verification: bool = True,
) -> LLMRegistry:
    """Create a registry of all LLM role wrappers.

    Args:
        client: LLM client to use (creates AnthropicClient if None)
        strict_verification: If True, fail on hallucination violations

    Returns:
        LLMRegistry with all role wrappers initialized
    """
    if client is None:
        client = AnthropicClient()

    return LLMRegistry(
        planner=PlannerLLM(client),
        verifier=VerifierLLM(client, strict=strict_verification),
        resolver=ResolverLLM(client),
        conflict_analyst=ConflictAnalystLLM(client),
        conflict_analyst_tiebreaker=ConflictAnalystTiebreakerLLM(client),
        extraction_verifier=ExtractionVerifierLLM(client, strict=strict_verification),
        query_expander=QueryExpanderLLM(client),
    )
