"""Publishing Manager for GPS-compliant genealogical publishing.

Orchestrates the publishing workflow including GPS grading, dual-reviewer
quorum, integrity validation, and Paper Trail of Doubt preservation.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from ..llm.wrapper import LLMClient

from .models import (
    GPSGradeCard,
    PublishingPipeline,
    PublishingPlatform,
    PublishingStatus,
    QuorumDecision,
    ResearchNote,
    ReviewVerdict,
    Severity,
    Uncertainty,
    UnresolvedConflict,
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
    # Linguist Agent
    AcceptedFact,
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
    ) -> QuorumDecision:
        """Run the dual-reviewer quorum process.

        Both Logic and Source reviewers must PASS for approval.

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

        Returns:
            QuorumDecision with both verdicts
        """
        pipeline.status = PublishingStatus.UNDER_REVIEW
        pipeline.updated_at = datetime.utcnow()

        # Run both reviewers
        logic_verdict = self.run_logic_review(
            subject_id=pipeline.subject_id,
            subject_name=subject_name,
            events=events,
            birth_date=birth_date,
            death_date=death_date,
            relationships=relationships,
            claims=claims,
        )

        source_verdict = self.run_source_review(
            subject_id=pipeline.subject_id,
            subject_name=subject_name,
            claims_with_citations=claims_with_citations,
            source_summaries=source_summaries,
            key_facts=key_facts,
        )

        quorum = QuorumDecision(
            logic_verdict=logic_verdict,
            source_verdict=source_verdict,
        )

        pipeline.quorum_decision = quorum

        # Update status based on quorum
        if quorum.approved and not quorum.blocking_issues:
            pipeline.status = PublishingStatus.APPROVED
        else:
            pipeline.status = PublishingStatus.BLOCKED

        pipeline.updated_at = datetime.utcnow()

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
        pipeline.updated_at = datetime.utcnow()
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
        pipeline.updated_at = datetime.utcnow()
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
        pipeline.updated_at = datetime.utcnow()
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

        pipeline.updated_at = datetime.utcnow()

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

        pipeline.updated_at = datetime.utcnow()

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
        """
        import subprocess

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
