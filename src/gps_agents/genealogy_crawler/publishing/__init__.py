"""Publishing Manager module for GPS-compliant genealogical publishing.

This module provides orchestration for synchronized publishing across
Wikipedia, Wikidata, WikiTree, and GitHub while maintaining GPS compliance.

Key Components:
- PublishingManager: Main orchestrator for publishing workflow
- GPSGradeCard: Scores research against 5 GPS pillars
- QuorumDecision: Dual reviewer (Logic + Source) verdicts
- Paper Trail of Doubt: Uncertainties, conflicts, research notes

Example:
    >>> from gps_agents.genealogy_crawler.publishing import (
    ...     PublishingManager,
    ...     GPSGradeCard,
    ...     PublishingPlatform,
    ... )
    >>>
    >>> manager = PublishingManager(llm_client)
    >>> pipeline = manager.prepare_for_publishing(
    ...     subject_id="person_123",
    ...     subject_name="John Smith",
    ...     source_count=12,
    ...     source_tiers={"tier_0": 5, "tier_1": 4, "tier_2": 3},
    ...     citation_count=45,
    ...     total_claims=50,
    ...     conflicts_found=3,
    ...     conflicts_resolved=2,
    ...     uncertainties_documented=1,
    ...     has_written_conclusion=True,
    ... )
    >>>
    >>> if pipeline.grade_card.letter_grade == "A":
    ...     # Grade A - eligible for all platforms
    ...     print(f"Allowed: {pipeline.grade_card.allowed_platforms}")
"""
from .manager import AdjudicationGate, PublishingManager
from .models import (
    GPSGradeCard,
    GPSPillar,
    GPSPillarScore,
    LedgerStatus,
    PublishDecision,
    PublishingPipeline,
    PublishingPlatform,
    PublishingStatus,
    QuorumDecision,
    ResearchNote,
    ReviewerType,
    ReviewIssue,
    ReviewVerdict,
    SearchRevisionRequest,
    Severity,
    Uncertainty,
    UnresolvedConflict,
    Verdict,
)
from .reviewers import (
    # GPS Grader
    GPSGraderInput,
    GPSGraderLLM,
    GPSGraderOutput,
    # Logic Reviewer
    LogicReviewerInput,
    LogicReviewerOutput,
    PublishingLogicReviewerLLM,
    # Source Reviewer
    PublishingSourceReviewerLLM,
    SourceReviewerInput,
    SourceReviewerOutput,
    # Linguist Agent
    AcceptedFact,
    GPSPillar5Grade,
    LinguistInput,
    LinguistLLM,
    LinguistOutput,
    WikipediaDraft,
    WikiTreeBio,
    # Media & Photo Agent
    DownloadQueueItem,
    MediaLicense,
    MediaMetadata,
    MediaPhotoAgentInput,
    MediaPhotoAgentLLM,
    MediaPhotoAgentOutput,
    MediaType,
    PhotoSource,
    PhotoTarget,
    SubjectConfidence,
    # Search Revision Agent
    DateRange,
    MissingSourceClass,
    NameVariant,
    NegativeSearchTarget,
    RegionalArchive,
    SearchRevisionAgentLLM,
    SearchRevisionInput,
    SearchRevisionOutput,
    SearchStrategy,
    TiebreakerSearchQuery,
    # DevOps Specialist
    CommitType,
    DevOpsSpecialistLLM,
    DevOpsWorkflowInput,
    DevOpsWorkflowOutput,
    GitCommitSpec,
    GitFileOperation,
    PublishingBundle,
)
from .validators import GPSPillarValidator, IntegrityValidator
from .validators.gps_pillars import GPSValidationSummary, PillarValidationResult
from .validators.integrity import IntegrityCheckResult

__all__ = [
    # Manager & Adjudication Gate
    "PublishingManager",
    "AdjudicationGate",
    # Models - Enums
    "GPSPillar",
    "Severity",
    "PublishingStatus",
    "ReviewerType",
    "Verdict",
    "PublishingPlatform",
    "LedgerStatus",
    # Models - GPS Grading
    "GPSPillarScore",
    "GPSGradeCard",
    # Models - Review/Quorum
    "ReviewIssue",
    "ReviewVerdict",
    "QuorumDecision",
    # Models - Adjudication Gate
    "PublishDecision",
    "SearchRevisionRequest",
    # Models - Paper Trail of Doubt
    "ResearchNote",
    "Uncertainty",
    "UnresolvedConflict",
    # Models - Pipeline
    "PublishingPipeline",
    # LLM Wrappers - GPS Grader
    "GPSGraderLLM",
    # LLM Wrappers - Reviewers
    "PublishingLogicReviewerLLM",
    "PublishingSourceReviewerLLM",
    # LLM Wrappers - Linguist Agent
    "LinguistLLM",
    # LLM Schemas - GPS Grader
    "GPSGraderInput",
    "GPSGraderOutput",
    # LLM Schemas - Reviewers
    "LogicReviewerInput",
    "LogicReviewerOutput",
    "SourceReviewerInput",
    "SourceReviewerOutput",
    # LLM Schemas - Linguist Agent
    "AcceptedFact",
    "LinguistInput",
    "LinguistOutput",
    "WikipediaDraft",
    "WikiTreeBio",
    "GPSPillar5Grade",
    # LLM Wrappers - Media & Photo Agent
    "MediaPhotoAgentLLM",
    # LLM Schemas - Media & Photo Agent
    "PhotoSource",
    "MediaLicense",
    "MediaType",
    "SubjectConfidence",
    "PhotoTarget",
    "MediaMetadata",
    "DownloadQueueItem",
    "MediaPhotoAgentInput",
    "MediaPhotoAgentOutput",
    # LLM Wrappers - Search Revision Agent
    "SearchRevisionAgentLLM",
    # LLM Schemas - Search Revision Agent
    "SearchStrategy",
    "MissingSourceClass",
    "NameVariant",
    "DateRange",
    "RegionalArchive",
    "NegativeSearchTarget",
    "TiebreakerSearchQuery",
    "SearchRevisionInput",
    "SearchRevisionOutput",
    # LLM Wrappers - DevOps Specialist
    "DevOpsSpecialistLLM",
    # LLM Schemas - DevOps Specialist
    "CommitType",
    "PublishingBundle",
    "GitFileOperation",
    "GitCommitSpec",
    "DevOpsWorkflowInput",
    "DevOpsWorkflowOutput",
    # Validators
    "GPSPillarValidator",
    "IntegrityValidator",
    "GPSValidationSummary",
    "PillarValidationResult",
    "IntegrityCheckResult",
]
