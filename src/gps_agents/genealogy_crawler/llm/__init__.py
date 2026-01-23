"""LLM wrapper module for the genealogy crawler.

Provides type-safe, structured I/O wrappers for LLM roles with
hallucination firewall validation and idempotency caching.
"""
from .idempotency import (
    ContentFingerprint,
    IdempotencyCache,
    LLMCache,
    PersistentIdempotencyCache,
    fingerprint_input,
    fingerprint_raw_text,
    get_global_cache,
    set_global_cache,
)
from .prompts import ROLE_PROMPTS
from .schemas import (
    Citation,
    CompetingClaim,
    ConflictAnalysisTiebreakerInput,
    ConflictAnalysisTiebreakerOutput,
    ConflictInput,
    ConflictOutput,
    ConfirmedFact,
    DeepSearchQuery,
    ErrorPatternHypothesis,
    EvidenceRanking,
    ExtractedField,
    ExtractionVerifierInput,
    ExtractionVerifierOutput,
    FeatureScore,
    Hypothesis,
    NegativeEvidenceIndicator,
    PlannerAction,
    PlannerInput,
    PlannerOutput,
    QueryExpanderInput,
    QueryExpanderOutput,
    ResolverInput,
    ResolverOutput,
    RevisitRecommendation,
    TiebreakerQuery,
    VerificationResult,
    VerifiedExtraction,
    VerifierInput,
    VerifierOutput,
)
from .wrapper import (
    AnthropicClient,
    ConflictAnalystLLM,
    ConflictAnalystTiebreakerLLM,
    ExtractionVerifierLLM,
    HallucinationCheckResult,
    HallucinationViolation,
    HallucinationViolationDetail,
    LLMClient,
    LLMRegistry,
    MockLLMClient,
    PlannerLLM,
    QueryExpanderLLM,
    ResolverLLM,
    StructuredLLMWrapper,
    VerifierLLM,
    check_citation_exists,
    create_llm_registry,
    hallucination_firewall,
)

__all__ = [
    # Idempotency
    "ContentFingerprint",
    "IdempotencyCache",
    "LLMCache",
    "PersistentIdempotencyCache",
    "fingerprint_input",
    "fingerprint_raw_text",
    "get_global_cache",
    "set_global_cache",
    # Clients
    "LLMClient",
    "AnthropicClient",
    "MockLLMClient",
    # Wrappers
    "StructuredLLMWrapper",
    "PlannerLLM",
    "VerifierLLM",
    "ResolverLLM",
    "ConflictAnalystLLM",
    "ConflictAnalystTiebreakerLLM",
    "ExtractionVerifierLLM",
    "QueryExpanderLLM",
    "LLMRegistry",
    "create_llm_registry",
    # Schemas - Planner
    "PlannerInput",
    "PlannerOutput",
    "PlannerAction",
    "RevisitRecommendation",
    # Schemas - Verifier
    "VerifierInput",
    "VerifierOutput",
    "VerificationResult",
    "Hypothesis",
    "Citation",
    # Schemas - Resolver
    "ResolverInput",
    "ResolverOutput",
    "FeatureScore",
    # Schemas - Conflict
    "ConflictInput",
    "ConflictOutput",
    "CompetingClaim",
    "EvidenceRanking",
    # Schemas - Conflict Analyst Tie-Breaker
    "ConflictAnalysisTiebreakerInput",
    "ConflictAnalysisTiebreakerOutput",
    "ErrorPatternHypothesis",
    "TiebreakerQuery",
    "NegativeEvidenceIndicator",
    # Schemas - Extraction Verifier
    "ExtractionVerifierInput",
    "ExtractionVerifierOutput",
    "ExtractedField",
    "VerifiedExtraction",
    # Schemas - Query Expander
    "QueryExpanderInput",
    "QueryExpanderOutput",
    "ConfirmedFact",
    "DeepSearchQuery",
    # Hallucination Firewall
    "HallucinationCheckResult",
    "HallucinationViolation",
    "HallucinationViolationDetail",
    "hallucination_firewall",
    "check_citation_exists",
    # Prompts
    "ROLE_PROMPTS",
]
