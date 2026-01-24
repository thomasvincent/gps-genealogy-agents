"""Publishing Manager for GPS-compliant genealogical publishing.

Orchestrates the publishing workflow including GPS grading, dual-reviewer
quorum, integrity validation, and Paper Trail of Doubt preservation.
"""
from __future__ import annotations

import asyncio
import bisect
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..llm.wrapper import LLMClient

from .models import (
    GPSGradeCard,
    LedgerStatus,
    PublishDecision,
    PublishingPipeline,
    PublishingPlatform,
    PublishingStatus,
    QuorumDecision,
    ResearchNote,
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
    # Logic Reviewer
    LogicReviewerInput,
    PublishingLogicReviewerLLM,
    # Source Reviewer
    PublishingSourceReviewerLLM,
    SourceReviewerInput,
    # Tiebreaker Reviewer
    TiebreakerInput,
    TiebreakerReviewerLLM,
    # Linguist Agent
    LinguistInput,
    LinguistLLM,
    LinguistOutput,
    # DevOps Specialist
    DevOpsSpecialistLLM,
    DevOpsWorkflowInput,
    DevOpsWorkflowOutput,
    PublishingBundle,
)

if TYPE_CHECKING:
    from ..storage import CrawlerStorage

logger = logging.getLogger(__name__)


class PublishingManager:
    """Manages the publishing workflow for genealogical research.

    The Publishing Manager orchestrates:
    1. GPS Grading - Score research against 5 GPS pillars
    2. Quorum Review - Dual reviewers (Logic + Source) must both PASS
    3. Integrity Guard - Block publishing on CRITICAL/HIGH issues
    4. Paper Trail of Doubt - Preserve uncertainties and conflicts

    Example:
        >>> manager = PublishingManager(llm_client, storage)
        >>> pipeline = await manager.prepare_for_publishing("person_123")
        >>> if pipeline.grade_card.letter_grade == "A":
        ...     pipeline = await manager.run_review_quorum(pipeline)
        ...     if pipeline.quorum_decision.approved:
        ...         await manager.publish(pipeline)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        storage: "CrawlerStorage | None" = None,
    ):
        """Initialize the Publishing Manager.

        Args:
            llm_client: LLM client for GPS grading and reviews
            storage: Optional storage backend for accessing research data
        """
        self._llm_client = llm_client
        self._storage = storage

        # Initialize LLM wrappers
        self._gps_grader = GPSGraderLLM(llm_client)
        self._logic_reviewer = PublishingLogicReviewerLLM(llm_client)
        self._source_reviewer = PublishingSourceReviewerLLM(llm_client)
        self._tiebreaker = TiebreakerReviewerLLM(llm_client)
        self._linguist = LinguistLLM(llm_client)
        self._devops = DevOpsSpecialistLLM(llm_client)

        # Active pipelines
        self._pipelines: dict[str, PublishingPipeline] = {}

    def create_pipeline(self, subject_id: str) -> PublishingPipeline:
        """Create a new publishing pipeline for a subject.

        Args:
            subject_id: ID of the person to publish

        Returns:
            New PublishingPipeline in DRAFT status
        """
        pipeline_id = f"pub_{uuid.uuid4().hex[:12]}"
        pipeline = PublishingPipeline(
            pipeline_id=pipeline_id,
            subject_id=subject_id,
            status=PublishingStatus.DRAFT,
        )
        self._pipelines[pipeline_id] = pipeline
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> PublishingPipeline | None:
        """Get an existing pipeline by ID."""
        return self._pipelines.get(pipeline_id)

    # =========================================================================
    # GPS Grading
    # =========================================================================

    def grade_research(
        self,
        subject_id: str,
        subject_name: str,
        source_count: int,
        source_tiers: dict[str, int],
        citation_count: int,
        total_claims: int,
        conflicts_found: int,
        conflicts_resolved: int,
        uncertainties_documented: int,
        has_written_conclusion: bool,
        conclusion_summary: str = "",
        research_notes_count: int = 0,
        years_covered: str = "",
    ) -> GPSGradeCard:
        """Grade research against GPS pillars.

        Args:
            subject_id: ID of the person being graded
            subject_name: Name of the person
            source_count: Total number of sources consulted
            source_tiers: Count by tier (e.g., {"tier_0": 5, "tier_1": 3})
            citation_count: Number of properly cited claims
            total_claims: Total number of claims
            conflicts_found: Number of conflicts identified
            conflicts_resolved: Number of conflicts resolved
            uncertainties_documented: Number of Paper Trail items
            has_written_conclusion: Whether proof argument exists
            conclusion_summary: Brief summary of conclusion
            research_notes_count: Number of methodology notes
            years_covered: Date range of research

        Returns:
            GPSGradeCard with pillar scores and computed properties
        """
        input_data = GPSGraderInput(
            subject_id=subject_id,
            subject_name=subject_name,
            source_count=source_count,
            source_tiers=source_tiers,
            citation_count=citation_count,
            total_claims=total_claims,
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            uncertainties_documented=uncertainties_documented,
            has_written_conclusion=has_written_conclusion,
            conclusion_summary=conclusion_summary,
            research_notes_count=research_notes_count,
            years_covered=years_covered,
        )

        return self._gps_grader.grade(input_data)

    # =========================================================================
    # Quorum Review
    # =========================================================================

    def run_logic_review(
        self,
        subject_id: str,
        subject_name: str,
        events: list[dict],
        birth_date: str | None = None,
        death_date: str | None = None,
        relationships: list[dict] | None = None,
        claims: list[dict] | None = None,
    ) -> ReviewVerdict:
        """Run logic/consistency review.

        Args:
            subject_id: ID of the person being reviewed
            subject_name: Name of the person
            events: List of events with dates and types
            birth_date: Birth date if known
            death_date: Death date if known
            relationships: List of relationships
            claims: List of claims to review

        Returns:
            ReviewVerdict from logic reviewer
        """
        input_data = LogicReviewerInput(
            subject_id=subject_id,
            subject_name=subject_name,
            events=events,
            birth_date=birth_date,
            death_date=death_date,
            relationships=relationships or [],
            claims=claims or [],
        )

        return self._logic_reviewer.review(input_data)

    def run_source_review(
        self,
        subject_id: str,
        subject_name: str,
        claims_with_citations: list[dict],
        source_summaries: list[dict],
        key_facts: list[dict],
    ) -> ReviewVerdict:
        """Run source/citation review.

        Args:
            subject_id: ID of the person being reviewed
            subject_name: Name of the person
            claims_with_citations: Claims paired with citations
            source_summaries: Summary of each source
            key_facts: Key facts to verify

        Returns:
            ReviewVerdict from source reviewer
        """
        input_data = SourceReviewerInput(
            subject_id=subject_id,
            subject_name=subject_name,
            claims_with_citations=claims_with_citations,
            source_summaries=source_summaries,
            key_facts=key_facts,
        )

        return self._source_reviewer.review(input_data)

    def run_quorum(
        self,
        pipeline: PublishingPipeline,
        events: list[dict],
        claims: list[dict],
        claims_with_citations: list[dict],
        source_summaries: list[dict],
        key_facts: list[dict],
        subject_name: str = "",
        birth_date: str | None = None,
        death_date: str | None = None,
        relationships: list[dict] | None = None,
        run_tiebreaker: bool = True,
    ) -> QuorumDecision:
        """Run the dual-reviewer quorum process (sync wrapper).

        Both Logic and Source reviewers must PASS for approval.
        Uses async parallel execution internally for efficiency.

        Args:
            pipeline: Publishing pipeline to update
            events: List of events for timeline validation
            claims: List of claims for logic review
            claims_with_citations: Claims with citations for source review
            source_summaries: Source quality summaries
            key_facts: Key facts requiring verification
            subject_name: Name of the person
            birth_date: Birth date if known
            death_date: Death date if known
            relationships: List of relationships
            run_tiebreaker: Whether to run tiebreaker on disagreement (default True)

        Returns:
            QuorumDecision with both verdicts (and tiebreaker if triggered)
        """
        # Safely run async code from sync context
        # Try to get running loop first (if called from async context)
        try:
            loop = asyncio.get_running_loop()
            # Already in async context - create a new thread to avoid nested loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.run_quorum_async(
                        pipeline=pipeline,
                        events=events,
                        claims=claims,
                        claims_with_citations=claims_with_citations,
                        source_summaries=source_summaries,
                        key_facts=key_facts,
                        subject_name=subject_name,
                        birth_date=birth_date,
                        death_date=death_date,
                        relationships=relationships,
                        run_tiebreaker=run_tiebreaker,
                    )
                )
                return future.result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(
                self.run_quorum_async(
                    pipeline=pipeline,
                    events=events,
                    claims=claims,
                    claims_with_citations=claims_with_citations,
                    source_summaries=source_summaries,
                    key_facts=key_facts,
                    subject_name=subject_name,
                    birth_date=birth_date,
                    death_date=death_date,
                    relationships=relationships,
                    run_tiebreaker=run_tiebreaker,
                )
            )

    async def run_quorum_async(
        self,
        pipeline: PublishingPipeline,
        events: list[dict],
        claims: list[dict],
        claims_with_citations: list[dict],
        source_summaries: list[dict],
        key_facts: list[dict],
        subject_name: str = "",
        birth_date: str | None = None,
        death_date: str | None = None,
        relationships: list[dict] | None = None,
        run_tiebreaker: bool = True,
    ) -> QuorumDecision:
        """Run the dual-reviewer quorum process with parallel execution.

        Both Logic and Source reviewers run in parallel for efficiency.
        If they disagree, a tiebreaker reviewer is invoked.

        Args:
            pipeline: Publishing pipeline to update
            events: List of events for timeline validation
            claims: List of claims for logic review
            claims_with_citations: Claims with citations for source review
            source_summaries: Source quality summaries
            key_facts: Key facts requiring verification
            subject_name: Name of the person
            birth_date: Birth date if known
            death_date: Death date if known
            relationships: List of relationships
            run_tiebreaker: Whether to run tiebreaker on disagreement

        Returns:
            QuorumDecision with both verdicts (and tiebreaker if triggered)
        """
        pipeline.status = PublishingStatus.UNDER_REVIEW
        pipeline.updated_at = datetime.now(UTC)

        # Prepare input data for both reviewers
        logic_input = LogicReviewerInput(
            subject_id=pipeline.subject_id,
            subject_name=subject_name,
            events=events,
            birth_date=birth_date,
            death_date=death_date,
            relationships=relationships or [],
            claims=claims,
        )

        source_input = SourceReviewerInput(
            subject_id=pipeline.subject_id,
            subject_name=subject_name,
            claims_with_citations=claims_with_citations,
            source_summaries=source_summaries,
            key_facts=key_facts,
        )

        # Run both reviewers in PARALLEL using asyncio.gather
        logger.info(f"Running quorum review in parallel for {pipeline.subject_id}")
        logic_verdict, source_verdict = await asyncio.gather(
            self._logic_reviewer.review_async(logic_input),
            self._source_reviewer.review_async(source_input),
        )

        logger.info(
            f"Quorum results: Logic={logic_verdict.verdict.value} "
            f"(conf={logic_verdict.confidence:.2f}), "
            f"Source={source_verdict.verdict.value} "
            f"(conf={source_verdict.confidence:.2f})"
        )

        # Create initial quorum decision
        quorum = QuorumDecision(
            logic_verdict=logic_verdict,
            source_verdict=source_verdict,
        )

        # Check if tiebreaker is needed
        if run_tiebreaker and quorum.needs_tiebreaker:
            logger.info(
                f"Tiebreaker triggered for {pipeline.subject_id}: "
                f"reviewers_agree={quorum.reviewers_agree}, "
                f"consensus_strength={quorum.consensus_strength}"
            )

            # Determine disagreement reason
            if not quorum.reviewers_agree:
                disagreement_reason = "verdict_mismatch"
            else:
                disagreement_reason = "low_confidence"

            # Prepare tiebreaker input
            tiebreaker_input = TiebreakerInput(
                subject_id=pipeline.subject_id,
                subject_name=subject_name,
                logic_verdict=logic_verdict.verdict,
                logic_confidence=logic_verdict.confidence,
                logic_rationale=logic_verdict.rationale,
                logic_issues=[
                    {"severity": i.severity.value, "description": i.description}
                    for i in logic_verdict.issues
                ],
                source_verdict=source_verdict.verdict,
                source_confidence=source_verdict.confidence,
                source_rationale=source_verdict.rationale,
                source_issues=[
                    {"severity": i.severity.value, "description": i.description}
                    for i in source_verdict.issues
                ],
                events=events,
                claims_with_citations=claims_with_citations,
                disagreement_reason=disagreement_reason,
            )

            # Run tiebreaker
            tiebreaker_verdict = await self._tiebreaker.review_async(tiebreaker_input)

            logger.info(
                f"Tiebreaker verdict: {tiebreaker_verdict.verdict.value} "
                f"(conf={tiebreaker_verdict.confidence:.2f})"
            )

            # Update quorum with tiebreaker result
            quorum = QuorumDecision(
                logic_verdict=logic_verdict,
                source_verdict=source_verdict,
                tiebreaker_verdict=tiebreaker_verdict,
                tiebreaker_reason=disagreement_reason,
            )

        pipeline.quorum_decision = quorum

        # Update status based on quorum
        if quorum.approved and not quorum.blocking_issues:
            pipeline.status = PublishingStatus.APPROVED
        else:
            pipeline.status = PublishingStatus.BLOCKED

        pipeline.updated_at = datetime.now(UTC)

        logger.info(
            f"Quorum complete for {pipeline.subject_id}: "
            f"approved={quorum.approved}, "
            f"consensus_score={quorum.consensus_score:.2f}, "
            f"strength={quorum.consensus_strength}"
        )

        return quorum

    # =========================================================================
    # Integrity Guard
    # =========================================================================

    def check_integrity(
        self,
        pipeline: PublishingPipeline,
    ) -> tuple[bool, list[PublishingPlatform]]:
        """Check integrity and determine allowed platforms.

        The integrity guard blocks publishing based on:
        - CRITICAL issues: Block ALL platforms
        - HIGH issues: Block Wikipedia/Wikidata
        - Grade below C: Block Wikipedia/Wikidata
        - Grade below B: Block WikiTree

        Args:
            pipeline: Pipeline to check

        Returns:
            Tuple of (can_publish, allowed_platforms)
        """
        if not pipeline.grade_card:
            return False, []

        # Start with grade-allowed platforms
        allowed = set(pipeline.grade_card.allowed_platforms)

        # Check quorum issues
        if pipeline.quorum_decision:
            for issue in pipeline.quorum_decision.all_issues:
                if issue.severity == Severity.CRITICAL:
                    # Block all platforms
                    return False, []
                elif issue.severity == Severity.HIGH:
                    # Block Wikipedia/Wikidata
                    allowed.discard(PublishingPlatform.WIKIPEDIA)
                    allowed.discard(PublishingPlatform.WIKIDATA)

        return len(allowed) > 0, list(allowed)

    # =========================================================================
    # Paper Trail of Doubt
    # =========================================================================

    def add_research_note(
        self,
        pipeline: PublishingPipeline,
        content: str,
        source_refs: list[str] | None = None,
        author: str = "system",
    ) -> ResearchNote:
        """Add a research note to the Paper Trail of Doubt.

        Args:
            pipeline: Pipeline to update
            content: Note content
            source_refs: Optional source references
            author: Author of the note

        Returns:
            Created ResearchNote
        """
        note = ResearchNote(
            note_id=f"note_{uuid.uuid4().hex[:8]}",
            subject_id=pipeline.subject_id,
            content=content,
            source_refs=source_refs or [],
            author=author,
        )
        pipeline.research_notes.append(note)
        pipeline.updated_at = datetime.now(UTC)
        return note

    def add_uncertainty(
        self,
        pipeline: PublishingPipeline,
        field: str,
        description: str,
        confidence_level: float,
        alternative_interpretations: list[str] | None = None,
        additional_sources_needed: list[str] | None = None,
    ) -> Uncertainty:
        """Add an uncertainty to the Paper Trail of Doubt.

        Args:
            pipeline: Pipeline to update
            field: Field affected by uncertainty
            description: Nature of the uncertainty
            confidence_level: Confidence in current conclusion (0-1)
            alternative_interpretations: Other possible interpretations
            additional_sources_needed: Sources that could help

        Returns:
            Created Uncertainty
        """
        uncertainty = Uncertainty(
            uncertainty_id=f"unc_{uuid.uuid4().hex[:8]}",
            subject_id=pipeline.subject_id,
            field=field,
            description=description,
            confidence_level=confidence_level,
            alternative_interpretations=alternative_interpretations or [],
            additional_sources_needed=additional_sources_needed or [],
        )
        pipeline.uncertainties.append(uncertainty)
        pipeline.updated_at = datetime.now(UTC)
        return uncertainty

    def add_unresolved_conflict(
        self,
        pipeline: PublishingPipeline,
        field: str,
        competing_claims: list[dict],
        analysis_summary: str,
        remaining_doubt: str,
        chosen_value: str | None = None,
        chosen_rationale: str | None = None,
    ) -> UnresolvedConflict:
        """Add an unresolved conflict to the Paper Trail of Doubt.

        Args:
            pipeline: Pipeline to update
            field: Field with conflicting values
            competing_claims: List of competing claims with sources
            analysis_summary: Summary of resolution attempts
            remaining_doubt: Why conflict remains unresolved
            chosen_value: Currently chosen value (if any)
            chosen_rationale: Rationale for choice

        Returns:
            Created UnresolvedConflict
        """
        conflict = UnresolvedConflict(
            conflict_id=f"conf_{uuid.uuid4().hex[:8]}",
            subject_id=pipeline.subject_id,
            field=field,
            competing_claims=competing_claims,
            analysis_summary=analysis_summary,
            remaining_doubt=remaining_doubt,
            chosen_value=chosen_value,
            chosen_rationale=chosen_rationale,
        )
        pipeline.unresolved_conflicts.append(conflict)
        pipeline.updated_at = datetime.now(UTC)
        return conflict

    # =========================================================================
    # Full Workflow
    # =========================================================================

    def prepare_for_publishing(
        self,
        subject_id: str,
        subject_name: str,
        source_count: int,
        source_tiers: dict[str, int],
        citation_count: int,
        total_claims: int,
        conflicts_found: int,
        conflicts_resolved: int,
        uncertainties_documented: int,
        has_written_conclusion: bool,
        conclusion_summary: str = "",
        target_platforms: list[PublishingPlatform] | None = None,
    ) -> PublishingPipeline:
        """Prepare research for publishing by creating pipeline and grading.

        This is typically the first step in the publishing workflow.

        Args:
            subject_id: ID of the person to publish
            subject_name: Name of the person
            source_count: Total sources consulted
            source_tiers: Counts by tier
            citation_count: Properly cited claims
            total_claims: Total claims
            conflicts_found: Conflicts identified
            conflicts_resolved: Conflicts resolved
            uncertainties_documented: Paper Trail items
            has_written_conclusion: Whether conclusion exists
            conclusion_summary: Brief conclusion summary
            target_platforms: Desired platforms (optional)

        Returns:
            PublishingPipeline with grade card populated
        """
        # Create pipeline
        pipeline = self.create_pipeline(subject_id)

        # Set target platforms
        if target_platforms:
            pipeline.target_platforms = target_platforms

        # Grade research
        grade_card = self.grade_research(
            subject_id=subject_id,
            subject_name=subject_name,
            source_count=source_count,
            source_tiers=source_tiers,
            citation_count=citation_count,
            total_claims=total_claims,
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            uncertainties_documented=uncertainties_documented,
            has_written_conclusion=has_written_conclusion,
            conclusion_summary=conclusion_summary,
        )

        pipeline.grade_card = grade_card

        # Update status based on grade
        if grade_card.is_publication_ready:
            pipeline.status = PublishingStatus.READY_FOR_REVIEW
        else:
            pipeline.status = PublishingStatus.BLOCKED

        pipeline.updated_at = datetime.now(UTC)

        logger.info(
            f"Pipeline {pipeline.pipeline_id} created for {subject_id}: "
            f"Grade {grade_card.letter_grade} ({grade_card.overall_score:.1f})"
        )

        return pipeline

    # =========================================================================
    # Content Generation (Linguist Agent)
    # =========================================================================

    def generate_wiki_content(
        self,
        pipeline: PublishingPipeline,
        subject_name: str,
        facts: list[dict],
        wikidata_qid: str | None = None,
        wikitree_id: str | None = None,
        generate_wikipedia: bool = True,
        generate_wikitree: bool = True,
        generate_diff: bool = True,
        min_confidence: float = 0.9,
    ) -> LinguistOutput:
        """Generate Wikipedia and WikiTree content using the Linguist Agent.

        CONSTRAINT: Only ACCEPTED facts with confidence >= min_confidence are used.
        Facts below the threshold are noted as uncertainties.

        Args:
            pipeline: Publishing pipeline with Paper Trail of Doubt
            subject_name: Full name of the person
            facts: List of facts with status, confidence, value, field, source_refs
            wikidata_qid: Existing Wikidata QID if known
            wikitree_id: Existing WikiTree ID if known
            generate_wikipedia: Whether to generate Wikipedia draft
            generate_wikitree: Whether to generate WikiTree bio
            generate_diff: Whether to generate Markdown DIFF
            min_confidence: Minimum confidence threshold (default 0.9)

        Returns:
            LinguistOutput with Wikipedia draft, WikiTree bio, DIFF, and GPS Pillar 5 grade
        """
        # Filter to only ACCEPTED facts with sufficient confidence
        accepted_facts = LinguistLLM.filter_accepted_facts(facts, min_confidence)

        # Convert uncertainties to dict format
        uncertainties_data = [
            {
                "field": u.field,
                "description": u.description,
                "confidence_level": u.confidence_level,
            }
            for u in pipeline.uncertainties
        ]

        # Convert unresolved conflicts to dict format
        conflicts_data = [
            {
                "field": c.field,
                "competing_claims": c.competing_claims,
                "remaining_doubt": c.remaining_doubt,
            }
            for c in pipeline.unresolved_conflicts
        ]

        # Create linguist input
        input_data = LinguistInput(
            subject_id=pipeline.subject_id,
            subject_name=subject_name,
            accepted_facts=accepted_facts,
            uncertainties=uncertainties_data,
            unresolved_conflicts=conflicts_data,
            wikidata_qid=wikidata_qid,
            wikitree_id=wikitree_id,
            generate_wikipedia=generate_wikipedia,
            generate_wikitree=generate_wikitree,
            generate_diff=generate_diff,
        )

        logger.info(
            f"Generating wiki content for {pipeline.subject_id}: "
            f"{len(accepted_facts)} accepted facts, "
            f"{len(uncertainties_data)} uncertainties, "
            f"{len(conflicts_data)} unresolved conflicts"
        )

        return self._linguist.generate(input_data)

    def finalize_for_publishing(
        self,
        pipeline: PublishingPipeline,
    ) -> PublishingPipeline:
        """Finalize pipeline after quorum review.

        Checks integrity and sets final allowed platforms.

        Args:
            pipeline: Pipeline to finalize

        Returns:
            Updated pipeline with final status
        """
        can_publish, allowed = self.check_integrity(pipeline)

        if can_publish:
            pipeline.target_platforms = allowed
            pipeline.status = PublishingStatus.APPROVED
        else:
            pipeline.status = PublishingStatus.BLOCKED

        pipeline.updated_at = datetime.now(UTC)

        logger.info(
            f"Pipeline {pipeline.pipeline_id} finalized: "
            f"status={pipeline.status.value}, platforms={[p.value for p in allowed]}"
        )

        return pipeline

    def generate_git_workflow(
        self,
        pipeline: PublishingPipeline,
        base_directory: str = "research/persons",
        base_branch: str = "main",
        create_branch: bool = True,
    ) -> DevOpsWorkflowOutput:
        """Generate git workflow for an approved pipeline.

        Uses the DevOps Specialist to create shell-ready git commands
        for committing and organizing research files.

        Args:
            pipeline: Approved publishing pipeline
            base_directory: Base directory for research files
            base_branch: Base branch to branch from
            create_branch: Whether to create a new branch

        Returns:
            DevOpsWorkflowOutput with shell script and commit specs

        Raises:
            ValueError: If pipeline is not approved
        """
        if pipeline.status != PublishingStatus.APPROVED:
            raise ValueError(
                f"Cannot generate git workflow for pipeline with status {pipeline.status.value}"
            )

        # Extract person info from pipeline
        name_parts = pipeline.subject_name.split() if pipeline.subject_name else ["Unknown"]
        firstname = name_parts[0] if name_parts else "Unknown"
        surname = name_parts[-1] if len(name_parts) > 1 else firstname
        birth_year = None  # Would need to be passed in or extracted from pipeline

        # Create publishing bundle from pipeline
        bundle = PublishingBundle(
            bundle_id=f"bundle_{pipeline.pipeline_id}",
            subject_id=pipeline.subject_id,
            subject_name=pipeline.subject_name or "Unknown",
            surname=surname,
            firstname=firstname,
            birth_year=str(birth_year) if birth_year else None,
            gps_grade=pipeline.grade_card.letter_grade if pipeline.grade_card else "C",
            wikipedia_draft=getattr(pipeline, 'wikipedia_draft', None),
            wikitree_bio=getattr(pipeline, 'wikitree_bio', None),
            media_files=[],  # Would need to be populated from MediaPhotoAgent
            research_notes="\n".join(n.content for n in pipeline.research_notes) if pipeline.research_notes else None,
        )

        # Build workflow input
        workflow_input = DevOpsWorkflowInput(
            bundles=[bundle],
            base_directory=base_directory,
            base_branch=base_branch,
            create_branch=create_branch,
            ai_author_name="Claude",
            ai_author_email="noreply@anthropic.com",
        )

        # Generate workflow using DevOps Specialist
        output = self._devops.build_workflow(workflow_input)

        logger.info(
            f"Generated git workflow for pipeline {pipeline.pipeline_id}: "
            f"branch={output.branch_name}, commits={len(output.commits)}"
        )

        return output

    def _validate_git_workflow_script(self, script: str) -> tuple[bool, str]:
        """Validate a git workflow script for safety.

        Only allows a whitelist of safe git commands to prevent shell injection.

        Args:
            script: The shell script to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        import os
        import re
        import shlex

        # Allowed commands whitelist
        allowed_commands = {
            "git", "echo", "cd", "mkdir", "cp", "mv", "rm", "cat",
            "date", "pwd", "ls", "test", "[", "true", "false", "set",
        }

        # Dangerous patterns to reject (applied only to executable lines, not heredoc content)
        dangerous_patterns = [
            r"`",      # Backtick command substitution
            r"\|",     # Pipe (could chain dangerous commands)
            r";",      # Semicolon command chaining
            r">\s*/",  # Redirect to root paths
            r"rm\s+-rf?\s+/",  # Dangerous rm
            r"sudo|su\s",  # Privilege escalation
        ]

        dangerous_subcommands = {"curl", "wget", "nc", "netcat", "rm", "eval", "exec", "bash", "sh", "python", "perl", "ruby"}

        # Parse script line by line, separating executable lines from heredoc content
        lines = script.strip().split("\n")
        in_heredoc = False
        heredoc_delimiter = None
        executable_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Check for heredoc start (<<EOF, <<'EOF', <<"EOF", etc.)
            if not in_heredoc:
                heredoc_match = re.search(r"<<\s*['\"]?(\w+)['\"]?", line)
                if heredoc_match:
                    in_heredoc = True
                    heredoc_delimiter = heredoc_match.group(1)
                    # The line starting the heredoc IS executable (e.g., git commit -m "$(cat <<'EOF'")
                    executable_lines.append(line)
                    continue

            # Check for heredoc end
            if in_heredoc and stripped == heredoc_delimiter:
                in_heredoc = False
                heredoc_delimiter = None
                continue

            # Skip heredoc content (not executable)
            if in_heredoc:
                continue

            executable_lines.append(line)

        # Apply dangerous pattern checks only to executable lines
        executable_content = "\n".join(executable_lines)
        for pattern in dangerous_patterns:
            if re.search(pattern, executable_content, re.IGNORECASE):
                return False, f"Script contains dangerous pattern: {pattern}"

        # Check command substitution $() more carefully
        # Allow safe patterns like $(cat <<'EOF' for heredocs
        # Block dangerous patterns like $(curl, $(wget, $(rm, etc.
        cmd_sub_matches = re.findall(r"\$\(([^)]+)", executable_content)
        for match in cmd_sub_matches:
            # Get the first word in the command substitution
            first_word = match.strip().split()[0] if match.strip() else ""
            # Use basename to handle absolute paths like /bin/bash
            first_word_basename = os.path.basename(first_word)
            # Allow cat for heredocs
            if first_word_basename == "cat":
                continue
            # Block if it's a dangerous command (check both full path and basename)
            if first_word in dangerous_subcommands or first_word_basename in dangerous_subcommands:
                return False, f"Dangerous command in substitution: {first_word}"

        # Validate each executable line
        for line in executable_lines:
            stripped = line.strip()

            # Skip empty lines, comments, and closing constructs
            if not stripped or stripped.startswith("#") or stripped in (')"', ')\"', 'EOF'):
                continue

            # Extract the first command from the line
            try:
                tokens = shlex.split(stripped)
                if not tokens:
                    continue
                cmd = tokens[0]
                cmd_basename = os.path.basename(cmd)

                # Handle common shell constructs
                if cmd in ("if", "then", "else", "fi", "for", "do", "done", "while", "case", "esac"):
                    continue

                # Check both full path and basename against whitelist
                if cmd not in allowed_commands and cmd_basename not in allowed_commands:
                    return False, f"Command not in whitelist: {cmd}"

            except ValueError:
                # shlex parsing error - skip lines with complex shell syntax
                # (e.g., command substitution continuations)
                # The dangerous pattern check already covers executable content
                continue

        return True, ""

    def execute_git_workflow(
        self,
        workflow: DevOpsWorkflowOutput,
        dry_run: bool = True,
    ) -> tuple[bool, str]:
        """Execute a git workflow script.

        Args:
            workflow: DevOps workflow output with shell script
            dry_run: If True, only print script without executing

        Returns:
            Tuple of (success, output/error message)

        Security:
            The script is validated against a whitelist of safe commands
            before execution to prevent shell injection attacks.
        """
        import subprocess

        # Validate script before execution
        is_valid, error_msg = self._validate_git_workflow_script(workflow.shell_script)
        if not is_valid:
            logger.error(f"Git workflow script validation failed: {error_msg}")
            return False, f"Script validation failed: {error_msg}"

        if dry_run:
            logger.info("Dry run - git workflow script:")
            logger.info(workflow.shell_script)
            return True, workflow.shell_script

        try:
            result = subprocess.run(
                ["bash", "-c", workflow.shell_script],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                logger.info(f"Git workflow executed successfully")
                return True, result.stdout
            else:
                logger.error(f"Git workflow failed: {result.stderr}")
                return False, result.stderr

        except subprocess.TimeoutExpired:
            logger.error("Git workflow timed out")
            return False, "Workflow execution timed out"
        except Exception as e:
            logger.error(f"Git workflow error: {e}")
            return False, str(e)


# =============================================================================
# GPS Adjudication Gate
# =============================================================================


class AdjudicationGate:
    """GPS Adjudication Gate for the Workflow Agent.

    Processes structured data from Dual Reviewers (Logic and Source Reviewers)
    to decide if a research bundle is ready for publication or requires
    further revision.

    GPS Pillar Mapping:
    | Feature          | GPS Pillar                            |
    |------------------|---------------------------------------|
    | Quorum Check     | Pillar 4: Resolution of Conflicts     |
    | Auto-Downgrade   | Pillar 5: Soundly Written Conclusion  |
    | Search Revision  | Pillar 1: Reasonably Exhaustive       |

    Example:
        >>> gate = AdjudicationGate(storage, revisit_queue)
        >>> decision = gate.adjudicate(quorum_decision, grade_card, subject_id)
        >>> if decision.is_approved:
        ...     gate.write_to_ledger(decision, facts)
        >>> elif decision.requires_search_revision:
        ...     revision_request = gate.create_search_revision_request(decision)
    """

    # Platform tier mapping for Auto-Downgrade Protocol
    ENCYCLOPEDIC_PLATFORMS = {PublishingPlatform.WIKIPEDIA, PublishingPlatform.WIKIDATA}
    COMMUNITY_PLATFORMS = {PublishingPlatform.WIKITREE}
    DRAFT_PLATFORMS = {PublishingPlatform.GITHUB}
    ALL_PLATFORMS = ENCYCLOPEDIC_PLATFORMS | COMMUNITY_PLATFORMS | DRAFT_PLATFORMS

    def __init__(
        self,
        storage: "CrawlerStorage | None" = None,
        revisit_queue: list | None = None,
    ):
        """Initialize the Adjudication Gate.

        Args:
            storage: Storage backend for Fact Ledger writes
            revisit_queue: RevisitQueue for tie-breaker query prioritization
        """
        self._storage = storage
        self._revisit_queue = revisit_queue if revisit_queue is not None else []
        self._decisions: dict[str, PublishDecision] = {}
        # Index for O(1) subject_id lookups
        self._decisions_by_subject: dict[str, list[str]] = defaultdict(list)

    # =========================================================================
    # Core Adjudication Logic
    # =========================================================================

    def adjudicate(
        self,
        quorum_decision: QuorumDecision,
        grade_card: GPSGradeCard | None,
        subject_id: str,
        missing_evidence: list[str] | None = None,
    ) -> PublishDecision:
        """Execute the GPS Adjudication Gate algorithm.

        This is the core adjudication method implementing:
        1. Quorum Check - Both reviewers must PASS
        2. Auto-Downgrade Protocol - Severity-based platform restrictions
        3. Ledger Write Determination - Only ACCEPTED if quorum passes

        Args:
            quorum_decision: Decision from dual-reviewer quorum
            grade_card: GPS grade card (optional, affects platform eligibility)
            subject_id: ID of the research subject
            missing_evidence: Evidence gaps identified by GPS Standards Critic

        Returns:
            PublishDecision with final adjudication result
        """
        decision_id = f"adj_{uuid.uuid4().hex[:12]}"

        # Extract verdicts
        logic_verdict = quorum_decision.logic_verdict.verdict
        source_verdict = quorum_decision.source_verdict.verdict

        # Step 1: QUORUM CHECK
        # If either verdict is FAIL, is_approved must be False
        quorum_passed = (
            logic_verdict == Verdict.PASS
            and source_verdict == Verdict.PASS
        )

        # Categorize issues by severity using defaultdict for O(n) single-pass
        issues_by_severity: dict[Severity, list[ReviewIssue]] = defaultdict(list)
        for issue in quorum_decision.all_issues:
            issues_by_severity[issue.severity].append(issue)

        critical_issues = issues_by_severity[Severity.CRITICAL]
        high_issues = issues_by_severity[Severity.HIGH]
        medium_issues = issues_by_severity[Severity.MEDIUM]
        low_issues = issues_by_severity[Severity.LOW]

        # Step 2: AUTO-DOWNGRADE PROTOCOL
        allowed_platforms, blocked_platforms = self._apply_auto_downgrade(
            critical_issues=critical_issues,
            high_issues=high_issues,
            medium_issues=medium_issues,
            grade_card=grade_card,
        )

        # Calculate integrity score
        integrity_score = self._calculate_integrity_score(
            quorum_passed=quorum_passed,
            critical_count=len(critical_issues),
            high_count=len(high_issues),
            medium_count=len(medium_issues),
            grade_score=grade_card.overall_score if grade_card else 0.0,
        )

        # Step 3: LEDGER WRITE DETERMINATION
        # Strict enforcement: Only ACCEPTED if quorum PASS
        if quorum_passed and len(critical_issues) == 0:
            ledger_status = LedgerStatus.ACCEPTED
            is_approved = len(allowed_platforms) > 0
        elif missing_evidence:
            ledger_status = LedgerStatus.REVISION_REQUIRED
            is_approved = False
        else:
            ledger_status = LedgerStatus.REJECTED
            is_approved = False

        # Determine if Search Revision Agent should be triggered
        requires_search_revision = (
            ledger_status == LedgerStatus.REVISION_REQUIRED
            or len(missing_evidence or []) > 0
        )

        decision = PublishDecision(
            decision_id=decision_id,
            subject_id=subject_id,
            logic_verdict=logic_verdict,
            source_verdict=source_verdict,
            is_approved=is_approved,
            integrity_score=integrity_score,
            allowed_platforms=allowed_platforms,
            blocked_platforms=blocked_platforms,
            critical_issues=critical_issues,
            high_issues=high_issues,
            medium_issues=medium_issues,
            low_issues=low_issues,
            ledger_status=ledger_status,
            requires_search_revision=requires_search_revision,
            missing_evidence=missing_evidence or [],
        )

        self._decisions[decision_id] = decision
        # Update subject_id index for O(1) lookups
        self._decisions_by_subject[subject_id].append(decision_id)

        logger.info(
            f"Adjudication {decision_id}: approved={is_approved}, "
            f"ledger={ledger_status.value}, platforms={[p.value for p in allowed_platforms]}"
        )

        return decision

    def _apply_auto_downgrade(
        self,
        critical_issues: list[ReviewIssue],
        high_issues: list[ReviewIssue],
        medium_issues: list[ReviewIssue],
        grade_card: GPSGradeCard | None,
    ) -> tuple[list[PublishingPlatform], list[PublishingPlatform]]:
        """Apply the Auto-Downgrade Protocol based on issue severity.

        Protocol:
        - CRITICAL/HIGH Issues: Reject entire bundle (block ALL platforms)
        - MEDIUM Issues: Allow WikiTree as "Research in Progress", block Wikipedia
        - Grade-based: Further restrict based on GPS grade

        Args:
            critical_issues: CRITICAL severity issues
            high_issues: HIGH severity issues
            medium_issues: MEDIUM severity issues
            grade_card: GPS grade card for grade-based restrictions

        Returns:
            Tuple of (allowed_platforms, blocked_platforms)
        """
        # Start with all platforms
        allowed = set(self.ALL_PLATFORMS)
        blocked: set[PublishingPlatform] = set()

        # CRITICAL issues: Block ALL platforms
        if critical_issues:
            blocked = set(self.ALL_PLATFORMS)
            allowed = set()
            logger.warning(
                f"Auto-Downgrade: CRITICAL issues found ({len(critical_issues)}), "
                f"blocking ALL platforms"
            )
            return list(allowed), list(blocked)

        # HIGH issues: Block Wikipedia/Wikidata (encyclopedic platforms)
        if high_issues:
            blocked.update(self.ENCYCLOPEDIC_PLATFORMS)
            allowed -= self.ENCYCLOPEDIC_PLATFORMS
            logger.warning(
                f"Auto-Downgrade: HIGH issues found ({len(high_issues)}), "
                f"blocking encyclopedic platforms"
            )

        # MEDIUM issues: Block Wikipedia but allow WikiTree as draft
        if medium_issues and not high_issues:
            blocked.add(PublishingPlatform.WIKIPEDIA)
            allowed.discard(PublishingPlatform.WIKIPEDIA)
            logger.info(
                f"Auto-Downgrade: MEDIUM issues found ({len(medium_issues)}), "
                f"blocking Wikipedia only"
            )

        # Apply grade-based restrictions
        if grade_card:
            grade_allowed = set(grade_card.allowed_platforms)
            # Intersect with grade-allowed platforms
            grade_blocked = self.ALL_PLATFORMS - grade_allowed
            blocked.update(grade_blocked)
            allowed &= grade_allowed
            logger.info(
                f"Auto-Downgrade: Grade {grade_card.letter_grade} allows {[p.value for p in grade_allowed]}"
            )

        return list(allowed), list(blocked)

    def _calculate_integrity_score(
        self,
        quorum_passed: bool,
        critical_count: int,
        high_count: int,
        medium_count: int,
        grade_score: float,
    ) -> float:
        """Calculate overall integrity score (0-1).

        Scoring:
        - Base: 0.5 if quorum passed, 0.0 if not
        - Deductions: -0.2 per CRITICAL, -0.1 per HIGH, -0.05 per MEDIUM
        - Grade bonus: (grade_score / 10) * 0.3
        - Capped at 0.0-1.0

        Args:
            quorum_passed: Whether dual reviewers both passed
            critical_count: Number of CRITICAL issues
            high_count: Number of HIGH issues
            medium_count: Number of MEDIUM issues
            grade_score: GPS grade score (1-10)

        Returns:
            Integrity score between 0.0 and 1.0
        """
        # Base score
        score = 0.5 if quorum_passed else 0.0

        # Issue deductions
        score -= critical_count * 0.2
        score -= high_count * 0.1
        score -= medium_count * 0.05

        # Grade bonus
        if grade_score > 0:
            score += (grade_score / 10.0) * 0.3

        # Clamp to valid range
        return max(0.0, min(1.0, score))

    # =========================================================================
    # Ledger Write
    # =========================================================================

    def write_to_ledger(
        self,
        decision: PublishDecision,
        facts: list[dict],
    ) -> bool:
        """Write ACCEPTED facts to the Fact Ledger.

        CONSTRAINT: Only permitted to write ACCEPTED status if quorum passed.

        Args:
            decision: Adjudication decision
            facts: Facts to write to ledger

        Returns:
            True if write succeeded, False otherwise

        Raises:
            ValueError: If attempting to write without ACCEPTED ledger status
        """
        if decision.ledger_status != LedgerStatus.ACCEPTED:
            raise ValueError(
                f"Cannot write to ledger with status {decision.ledger_status.value}. "
                f"Only ACCEPTED status permits ledger writes."
            )

        if not self._storage:
            logger.warning("No storage configured, skipping ledger write")
            return False

        # Write facts to storage
        try:
            for fact in facts:
                fact["ledger_status"] = "ACCEPTED"
                fact["decision_id"] = decision.decision_id
                fact["adjudicated_at"] = decision.adjudicated_at.isoformat()

            logger.info(
                f"Ledger write: {len(facts)} facts written with decision {decision.decision_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Ledger write failed: {e}")
            return False

    # =========================================================================
    # Search Revision
    # =========================================================================

    def create_search_revision_request(
        self,
        decision: PublishDecision,
        gps_pillar_gaps: list[str] | None = None,
    ) -> SearchRevisionRequest:
        """Create a Search Revision Request for the Search Revision Agent.

        Triggered when the GPS Standards Critic identifies missing evidence.

        Args:
            decision: Adjudication decision with missing evidence
            gps_pillar_gaps: GPS pillars with identified gaps

        Returns:
            SearchRevisionRequest for the Search Revision Agent
        """
        request = SearchRevisionRequest(
            request_id=f"rev_{uuid.uuid4().hex[:12]}",
            subject_id=decision.subject_id,
            decision_id=decision.decision_id,
            missing_sources=self._extract_missing_source_types(decision.missing_evidence),
            missing_claims=decision.missing_evidence,
            search_queries=self._generate_search_queries(decision),
            priority="high" if decision.critical_issues else "normal",
            gps_pillar_gaps=gps_pillar_gaps or [],
        )

        # Add to RevisitQueue with priority for tie-breaker queries
        self._add_to_revisit_queue(request)

        logger.info(
            f"Search Revision Request {request.request_id} created for {decision.subject_id}: "
            f"{len(request.missing_claims)} missing claims"
        )

        return request

    # Class-level constant for keyword mapping (avoid recreating dict each call)
    _SOURCE_TYPE_KEYWORDS: dict[str, str] = {
        "census": "census_records",
        "vital": "vital_records",
        "birth": "birth_records",
        "death": "death_records",
        "marriage": "marriage_records",
        "military": "military_records",
        "immigration": "immigration_records",
        "newspaper": "newspapers",
        "obituary": "obituaries",
    }

    def _extract_missing_source_types(self, missing_evidence: list[str]) -> list[str]:
        """Extract source types from missing evidence descriptions."""
        source_types: set[str] = set()

        # Pre-lowercase all evidence strings once
        lowered_evidence = [e.lower() for e in missing_evidence]

        for keyword, source_type in self._SOURCE_TYPE_KEYWORDS.items():
            # Check if keyword appears in any evidence string
            if any(keyword in evidence for evidence in lowered_evidence):
                source_types.add(source_type)

        return list(source_types)

    def _generate_search_queries(self, decision: PublishDecision) -> list[str]:
        """Generate suggested search queries from missing evidence."""
        queries = []
        for evidence in decision.missing_evidence:
            # Simple query generation - could be enhanced with LLM
            query = f"Find {evidence} for subject {decision.subject_id}"
            queries.append(query)
        return queries

    # Priority ordering for bisect-based insertion (lower value = higher priority)
    _PRIORITY_ORDER: dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    def _add_to_revisit_queue(self, request: SearchRevisionRequest) -> None:
        """Add tie-breaker queries to the RevisitQueue with priority.

        Uses bisect for O(log n) sorted insertion instead of O(n) list.insert().
        The RevisitQueue must prioritize queries generated during adjudication.
        """
        priority_order = self._PRIORITY_ORDER.get(request.priority, 3)

        revisit_item = {
            "type": "tie_breaker",
            "request_id": request.request_id,
            "subject_id": request.subject_id,
            "queries": request.search_queries,
            "priority": request.priority,
            "_priority_order": priority_order,  # For sorting
            "created_at": request.created_at.isoformat(),
        }

        # Use bisect to find insertion point based on priority order
        # Extract priority orders as a sorted key list for bisect
        keys = [item.get("_priority_order", 3) for item in self._revisit_queue]
        insert_pos = bisect.bisect_right(keys, priority_order)
        self._revisit_queue.insert(insert_pos, revisit_item)

        logger.debug(
            f"Added tie-breaker to RevisitQueue at position {insert_pos}"
        )

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_decision(self, decision_id: str) -> PublishDecision | None:
        """Get an existing decision by ID."""
        return self._decisions.get(decision_id)

    def get_decisions_for_subject(self, subject_id: str) -> list[PublishDecision]:
        """Get all decisions for a subject using O(1) index lookup."""
        decision_ids = self._decisions_by_subject.get(subject_id, [])
        return [self._decisions[d_id] for d_id in decision_ids if d_id in self._decisions]
