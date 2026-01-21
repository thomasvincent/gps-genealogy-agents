"""Temporal Activities for genealogy crawler tasks.

Activities are the individual units of work that workflows execute.
Each activity is retryable and can run on distributed workers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

try:
    from temporalio import activity
    from temporalio.common import RetryPolicy
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False
    # Create dummy decorators for development
    class activity:
        @staticmethod
        def defn(func):
            return func

    class RetryPolicy:
        def __init__(self, **kwargs):
            pass

if TYPE_CHECKING:
    from ..adapters import FetchResult, SearchQuery, SourceAdapter
    from ..models_v2 import EvidenceClaim

logger = logging.getLogger(__name__)


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=3,
    non_retryable_error_types=["PermissionError", "ValueError"],
)


@dataclass
class CrawlInput:
    """Input for crawl activity."""
    url: str | None = None
    query: dict[str, Any] = field(default_factory=dict)
    adapter_id: str = ""
    subject_id: str | None = None


@dataclass
class CrawlOutput:
    """Output from crawl activity."""
    url: str
    content: str
    content_type: str = "text/html"
    status_code: int = 200
    fetched_at: str = ""
    from_cache: bool = False
    error: str | None = None


@dataclass
class ExtractionInput:
    """Input for extraction activity."""
    content: str
    url: str
    adapter_id: str
    entity_type: str = "person"


@dataclass
class ExtractionOutput:
    """Output from extraction activity."""
    claims: list[dict[str, Any]] = field(default_factory=list)
    extraction_method: str = "deterministic"
    error: str | None = None


@dataclass
class VerificationInput:
    """Input for verification activity."""
    claim: dict[str, Any]
    source_content: str
    subject_id: str


@dataclass
class VerificationOutput:
    """Output from verification activity."""
    claim_id: str
    verified: bool
    confidence: float = 0.0
    hallucination_detected: bool = False
    error: str | None = None


@dataclass
class ResolutionInput:
    """Input for conflict resolution activity."""
    subject_id: str
    field_name: str
    claims: list[dict[str, Any]]


@dataclass
class ResolutionOutput:
    """Output from conflict resolution activity."""
    subject_id: str
    field_name: str
    resolved_value: Any = None
    confidence: float = 0.0
    resolution_method: str = "bayesian"
    contributing_claims: list[str] = field(default_factory=list)
    error: str | None = None


class CrawlActivity:
    """Activity for crawling URLs using source adapters.

    Handles compliance (rate limiting, robots.txt) and caching.
    """

    def __init__(self, adapters: dict[str, Any] | None = None):
        """Initialize with adapter registry.

        Args:
            adapters: Dictionary of adapter_id -> SourceAdapter
        """
        self.adapters = adapters or {}

    @activity.defn
    async def crawl_url(self, input: CrawlInput) -> CrawlOutput:
        """Fetch a URL using the appropriate adapter.

        Args:
            input: Crawl input with URL and adapter ID

        Returns:
            CrawlOutput with content or error
        """
        if not input.url:
            return CrawlOutput(
                url="",
                content="",
                error="No URL provided",
            )

        adapter = self.adapters.get(input.adapter_id)
        if adapter is None:
            return CrawlOutput(
                url=input.url,
                content="",
                error=f"Unknown adapter: {input.adapter_id}",
            )

        try:
            logger.info(f"Crawling {input.url} with adapter {input.adapter_id}")
            result = await adapter.fetch(input.url)

            return CrawlOutput(
                url=result.url,
                content=result.content,
                content_type=result.content_type,
                status_code=result.status_code,
                fetched_at=result.fetched_at.isoformat(),
                from_cache=result.from_cache,
            )

        except PermissionError as e:
            # Don't retry permission errors (robots.txt blocked)
            return CrawlOutput(
                url=input.url,
                content="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            logger.warning(f"Crawl failed for {input.url}: {e}")
            return CrawlOutput(
                url=input.url,
                content="",
                error=str(e),
            )

    @activity.defn
    async def search_source(self, input: CrawlInput) -> list[dict[str, Any]]:
        """Execute a search query on a source.

        Args:
            input: Crawl input with query and adapter ID

        Returns:
            List of search result dictionaries
        """
        adapter = self.adapters.get(input.adapter_id)
        if adapter is None:
            return []

        try:
            from ..adapters import SearchQuery

            query = SearchQuery(
                query_string=input.query.get("query_string", ""),
                given_name=input.query.get("given_name"),
                surname=input.query.get("surname"),
                birth_year=input.query.get("birth_year"),
                death_year=input.query.get("death_year"),
                location=input.query.get("location"),
            )

            results = []
            async for result in adapter.search(query):
                results.append({
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "relevance_score": result.relevance_score,
                })

            logger.info(f"Search returned {len(results)} results from {input.adapter_id}")
            return results

        except Exception as e:
            logger.warning(f"Search failed on {input.adapter_id}: {e}")
            return []


class ExtractionActivity:
    """Activity for extracting evidence claims from content."""

    def __init__(self, adapters: dict[str, Any] | None = None):
        """Initialize with adapter registry.

        Args:
            adapters: Dictionary of adapter_id -> SourceAdapter
        """
        self.adapters = adapters or {}

    @activity.defn
    async def extract_claims(self, input: ExtractionInput) -> ExtractionOutput:
        """Extract evidence claims from fetched content.

        Args:
            input: Extraction input with content and adapter ID

        Returns:
            ExtractionOutput with claims or error
        """
        adapter = self.adapters.get(input.adapter_id)
        if adapter is None:
            return ExtractionOutput(
                error=f"Unknown adapter: {input.adapter_id}",
            )

        try:
            from ..adapters import FetchResult

            # Recreate FetchResult for extraction
            fetch_result = FetchResult(
                url=input.url,
                content=input.content,
            )

            claims = adapter.extract(fetch_result, input.entity_type)

            return ExtractionOutput(
                claims=[{
                    "claim_id": str(c.source_reference_id),
                    "claim_type": c.claim_type,
                    "claim_text": c.claim_text,
                    "claim_value": c.claim_value,
                    "citation_snippet": c.citation_snippet,
                    "prior_weight": c.prior_weight,
                    "extraction_method": c.extraction_method,
                } for c in claims],
                extraction_method="deterministic",
            )

        except Exception as e:
            logger.warning(f"Extraction failed: {e}")
            return ExtractionOutput(
                error=str(e),
            )


class VerificationActivity:
    """Activity for verifying extracted claims.

    Uses LLM hallucination firewall to validate citations.
    """

    def __init__(self, llm_registry: Any | None = None):
        """Initialize with LLM registry.

        Args:
            llm_registry: Registry of LLM wrappers
        """
        self.llm_registry = llm_registry

    @activity.defn
    async def verify_claim(self, input: VerificationInput) -> VerificationOutput:
        """Verify a claim against source content.

        Uses hallucination firewall to ensure citations appear in source.

        Args:
            input: Verification input with claim and source content

        Returns:
            VerificationOutput with verification result
        """
        try:
            from ..llm import hallucination_firewall

            claim_text = input.claim.get("claim_text", "")
            citation = input.claim.get("citation_snippet", "")

            # Run hallucination firewall
            result = hallucination_firewall(
                claim=claim_text,
                citations=[citation],
                source_texts=[input.source_content],
            )

            return VerificationOutput(
                claim_id=input.claim.get("claim_id", ""),
                verified=result.passed,
                confidence=result.confidence,
                hallucination_detected=not result.passed,
            )

        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return VerificationOutput(
                claim_id=input.claim.get("claim_id", ""),
                verified=False,
                error=str(e),
            )


class ResolutionActivity:
    """Activity for resolving conflicting evidence using Bayesian weighting."""

    @activity.defn
    async def resolve_conflicts(self, input: ResolutionInput) -> ResolutionOutput:
        """Resolve conflicting claims using Bayesian evidence weighting.

        Args:
            input: Resolution input with claims to resolve

        Returns:
            ResolutionOutput with resolved value and confidence
        """
        try:
            from ..models_v2 import BayesianResolution, ConflictingEvidence

            # Convert claims to ConflictingEvidence
            evidence = []
            for claim in input.claims:
                evidence.append(ConflictingEvidence(
                    claim_id=UUID(claim.get("claim_id", str(uuid4()))),
                    value=claim.get("claim_value"),
                    prior_weight=claim.get("prior_weight", 0.5),
                    source_description=claim.get("source_description", "Unknown"),
                    citation_snippet=claim.get("citation_snippet", ""),
                ))

            # Run Bayesian resolution
            resolution = BayesianResolution.resolve(
                field_name=input.field_name,
                subject_id=UUID(input.subject_id),
                evidence=evidence,
            )

            return ResolutionOutput(
                subject_id=input.subject_id,
                field_name=input.field_name,
                resolved_value=resolution.resolved_value,
                confidence=resolution.posterior_confidence,
                resolution_method="bayesian",
                contributing_claims=[str(e.claim_id) for e in evidence],
            )

        except Exception as e:
            logger.warning(f"Resolution failed: {e}")
            return ResolutionOutput(
                subject_id=input.subject_id,
                field_name=input.field_name,
                error=str(e),
            )


# =============================================================================
# Extraction Verification Activity (LLM-powered)
# =============================================================================


@dataclass
class ExtractionVerificationInput:
    """Input for LLM extraction verification activity."""
    raw_text: str
    candidate_extractions: list[dict[str, Any]]


@dataclass
class VerifiedField:
    """A single verified field from extraction verification."""
    field: str
    value: Any
    status: str  # "Confirmed", "NotFound", "Corrected"
    confidence: float
    exact_quote: str | None = None
    corrected_value: Any | None = None
    rationale: str = ""


@dataclass
class ExtractionVerificationOutput:
    """Output from LLM extraction verification activity."""
    verified_fields: list[VerifiedField] = field(default_factory=list)
    overall_confidence: float = 0.0
    hallucination_flags: list[str] = field(default_factory=list)
    firewall_passed: bool = True
    error: str | None = None


class ExtractionVerificationActivity:
    """Activity for verifying extracted data using LLM with hallucination firewall.

    Uses ExtractionVerifierLLM to validate that each extracted field
    has supporting evidence (exact quote) in the source text.
    """

    def __init__(self, llm_registry: Any | None = None):
        """Initialize with LLM registry.

        Args:
            llm_registry: Registry of LLM wrappers (must have extraction_verifier)
        """
        self.llm_registry = llm_registry

    @activity.defn
    async def verify_extraction(
        self, input: ExtractionVerificationInput
    ) -> ExtractionVerificationOutput:
        """Verify extracted fields against source text using LLM.

        Args:
            input: Verification input with raw_text and candidate extractions

        Returns:
            ExtractionVerificationOutput with verified fields
        """
        if self.llm_registry is None:
            return ExtractionVerificationOutput(
                error="LLM registry not configured",
            )

        try:
            from ..llm import ExtractedField, ExtractionVerifierInput

            # Build input for LLM
            llm_input = ExtractionVerifierInput(
                raw_text=input.raw_text,
                candidate_extraction=[
                    ExtractedField(field=e.get("field", ""), value=e.get("value"))
                    for e in input.candidate_extractions
                ],
            )

            # Run verification with hallucination firewall
            output, firewall_result = self.llm_registry.extraction_verifier.verify(
                llm_input
            )

            # Convert to activity output
            verified_fields = [
                VerifiedField(
                    field=f.field,
                    value=f.value,
                    status=f.status,
                    confidence=f.confidence,
                    exact_quote=f.exact_quote,
                    corrected_value=f.corrected_value,
                    rationale=f.rationale,
                )
                for f in output.verified_fields
            ]

            return ExtractionVerificationOutput(
                verified_fields=verified_fields,
                overall_confidence=output.overall_confidence,
                hallucination_flags=output.hallucination_flags + firewall_result.violations,
                firewall_passed=firewall_result.passed,
            )

        except Exception as e:
            logger.warning(f"Extraction verification failed: {e}")
            return ExtractionVerificationOutput(
                error=str(e),
            )


# =============================================================================
# Query Expansion Activity (LLM-powered)
# =============================================================================


@dataclass
class QueryExpansionInput:
    """Input for LLM query expansion activity."""
    subject_name: str
    confirmed_facts: list[dict[str, Any]]
    research_goals: list[str] = field(default_factory=list)
    already_searched: list[str] = field(default_factory=list)


@dataclass
class SuggestedQuery:
    """A suggested follow-up query from the Clue Agent."""
    query_string: str
    target_source_type: str
    reasoning: str
    priority: float = 0.5
    expected_fields: list[str] = field(default_factory=list)


@dataclass
class QueryExpansionOutput:
    """Output from LLM query expansion activity."""
    analysis: str = ""
    suggested_queries: list[SuggestedQuery] = field(default_factory=list)
    research_hypotheses: list[str] = field(default_factory=list)
    error: str | None = None


class QueryExpansionActivity:
    """Activity for expanding research queries using LLM Clue Agent.

    Uses QueryExpanderLLM to analyze confirmed facts and suggest
    strategic follow-up queries to fill gaps in genealogical research.
    """

    def __init__(self, llm_registry: Any | None = None):
        """Initialize with LLM registry.

        Args:
            llm_registry: Registry of LLM wrappers (must have query_expander)
        """
        self.llm_registry = llm_registry

    @activity.defn
    async def expand_queries(
        self, input: QueryExpansionInput
    ) -> QueryExpansionOutput:
        """Generate follow-up queries based on confirmed facts.

        Args:
            input: Expansion input with subject info and confirmed facts

        Returns:
            QueryExpansionOutput with suggested queries
        """
        if self.llm_registry is None:
            return QueryExpansionOutput(
                error="LLM registry not configured",
            )

        try:
            from ..llm import ConfirmedFact, QueryExpanderInput

            # Build input for LLM
            llm_input = QueryExpanderInput(
                subject_name=input.subject_name,
                confirmed_facts=[
                    ConfirmedFact(
                        field=f.get("field", ""),
                        value=f.get("value"),
                        confidence=f.get("confidence", 0.9),
                        source_snippet=f.get("source_snippet"),
                    )
                    for f in input.confirmed_facts
                ],
                research_goals=input.research_goals,
                already_searched=input.already_searched,
            )

            # Run query expansion
            output = self.llm_registry.query_expander.expand(llm_input)

            # Convert to activity output
            suggested_queries = [
                SuggestedQuery(
                    query_string=q.query_string,
                    target_source_type=q.target_source_type,
                    reasoning=q.reasoning,
                    priority=q.priority,
                    expected_fields=q.expected_fields,
                )
                for q in output.deep_search_queries
            ]

            return QueryExpansionOutput(
                analysis=output.analysis,
                suggested_queries=suggested_queries,
                research_hypotheses=output.research_hypotheses,
            )

        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return QueryExpansionOutput(
                error=str(e),
            )
