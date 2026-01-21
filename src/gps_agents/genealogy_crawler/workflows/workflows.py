"""Temporal Workflow definitions for genealogy research.

Workflows are the durable orchestration units that coordinate activities
and maintain state across failures and restarts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

try:
    from temporalio import workflow
    from temporalio.common import RetryPolicy
    TEMPORAL_AVAILABLE = True

    with workflow.unsafe.imports_passed_through():
        from .activities import (
            CrawlActivity,
            CrawlInput,
            CrawlOutput,
            ExtractionActivity,
            ExtractionInput,
            ExtractionOutput,
            ResolutionActivity,
            ResolutionInput,
            ResolutionOutput,
            VerificationActivity,
            VerificationInput,
            VerificationOutput,
        )
except ImportError:
    TEMPORAL_AVAILABLE = False
    # Create dummy decorators for development
    class workflow:
        @staticmethod
        def defn(cls):
            return cls

        @staticmethod
        def run(func):
            return func

        @staticmethod
        def signal(func):
            return func

        @staticmethod
        def query(func):
            return func

        class Info:
            @staticmethod
            def workflow_id():
                return "test-workflow"

    # Import activities directly
    from .activities import (
        CrawlActivity,
        CrawlInput,
        CrawlOutput,
        ExtractionActivity,
        ExtractionInput,
        ExtractionOutput,
        ResolutionActivity,
        ResolutionInput,
        ResolutionOutput,
        VerificationActivity,
        VerificationInput,
        VerificationOutput,
    )

logger = logging.getLogger(__name__)


@dataclass
class ResearchSessionConfig:
    """Configuration for a research session."""
    session_id: str = field(default_factory=lambda: str(uuid4()))
    subject_name: str = ""
    subject_birth_year: int | None = None
    subject_death_year: int | None = None
    subject_location: str | None = None

    # Budget constraints
    max_requests: int = 100
    max_duration_minutes: int = 60
    target_confidence: float = 0.85

    # Source preferences
    enabled_adapters: list[str] = field(default_factory=list)
    tier_priority: list[int] = field(default_factory=lambda: [0, 1, 2])


@dataclass
class ResearchSessionState:
    """State of a research session."""
    session_id: str = ""
    status: str = "pending"  # pending, running, paused, completed, failed

    # Progress tracking
    requests_made: int = 0
    claims_extracted: int = 0
    claims_verified: int = 0
    conflicts_resolved: int = 0
    current_confidence: float = 0.0

    # Frontier state
    frontier_size: int = 0
    completed_urls: int = 0

    # Results
    facts_discovered: list[dict[str, Any]] = field(default_factory=list)
    relationships_found: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None


@workflow.defn
class ResearchSessionWorkflow:
    """Main workflow for a genealogical research session.

    Orchestrates the iterative enrichment loop:
    1. Search sources for relevant records
    2. Crawl and extract evidence
    3. Verify claims against sources
    4. Resolve conflicts using Bayesian weighting
    5. Generate new hypotheses and repeat
    """

    def __init__(self) -> None:
        self.state = ResearchSessionState()
        self.config = ResearchSessionConfig()
        self.should_pause = False
        self.should_stop = False

    @workflow.run
    async def run(self, config: ResearchSessionConfig) -> ResearchSessionState:
        """Execute the research session workflow.

        Args:
            config: Session configuration

        Returns:
            Final session state
        """
        self.config = config
        self.state.session_id = config.session_id
        self.state.status = "running"

        logger.info(f"Starting research session {config.session_id} for {config.subject_name}")

        try:
            # Phase 1: Initial search across sources
            await self._execute_initial_search()

            # Phase 2: Iterative enrichment loop
            while not self._should_stop():
                if self.should_pause:
                    self.state.status = "paused"
                    await workflow.wait_condition(lambda: not self.should_pause)
                    self.state.status = "running"

                # Execute one enrichment iteration
                made_progress = await self._execute_enrichment_iteration()

                if not made_progress:
                    logger.info("No more progress possible, stopping enrichment")
                    break

            self.state.status = "completed"

        except Exception as e:
            logger.error(f"Research session failed: {e}")
            self.state.status = "failed"
            self.state.error_message = str(e)

        return self.state

    async def _execute_initial_search(self) -> None:
        """Execute initial search across enabled sources."""
        search_input = CrawlInput(
            query={
                "query_string": self.config.subject_name,
                "given_name": self.config.subject_name.split()[0] if " " in self.config.subject_name else None,
                "surname": self.config.subject_name.split()[-1] if " " in self.config.subject_name else None,
                "birth_year": self.config.subject_birth_year,
                "death_year": self.config.subject_death_year,
                "location": self.config.subject_location,
            },
        )

        for adapter_id in self.config.enabled_adapters:
            if self._budget_exceeded():
                break

            search_input.adapter_id = adapter_id

            if TEMPORAL_AVAILABLE:
                results = await workflow.execute_activity(
                    CrawlActivity.search_source,
                    search_input,
                    start_to_close_timeout=timedelta(minutes=5),
                )
            else:
                # Mock for development
                results = []

            self.state.requests_made += 1
            self.state.frontier_size += len(results)

            logger.info(f"Initial search on {adapter_id} found {len(results)} results")

    async def _execute_enrichment_iteration(self) -> bool:
        """Execute one iteration of the enrichment loop.

        Returns:
            True if progress was made
        """
        if self.state.frontier_size == 0:
            return False

        # In real implementation, would pop from frontier queue
        # For now, simulate processing
        self.state.frontier_size -= 1
        self.state.completed_urls += 1

        # Execute child workflow for source crawl
        if TEMPORAL_AVAILABLE:
            crawl_result = await workflow.execute_child_workflow(
                SourceCrawlWorkflow.run,
                CrawlInput(url="http://example.com/test", adapter_id="test"),
                id=f"{self.state.session_id}-crawl-{self.state.completed_urls}",
            )
        else:
            crawl_result = {}

        return True

    def _should_stop(self) -> bool:
        """Check if session should stop."""
        if self.should_stop:
            return True
        if self._budget_exceeded():
            return True
        if self.state.current_confidence >= self.config.target_confidence:
            return True
        return False

    def _budget_exceeded(self) -> bool:
        """Check if budget constraints are exceeded."""
        return self.state.requests_made >= self.config.max_requests

    @workflow.signal
    async def pause(self) -> None:
        """Signal to pause the workflow."""
        self.should_pause = True

    @workflow.signal
    async def resume(self) -> None:
        """Signal to resume the workflow."""
        self.should_pause = False

    @workflow.signal
    async def stop(self) -> None:
        """Signal to stop the workflow."""
        self.should_stop = True

    @workflow.query
    def get_state(self) -> ResearchSessionState:
        """Query the current workflow state."""
        return self.state


@workflow.defn
class SourceCrawlWorkflow:
    """Workflow for crawling a single source URL.

    Handles the fetch -> extract -> verify pipeline for one URL.
    """

    @workflow.run
    async def run(self, input: CrawlInput) -> dict[str, Any]:
        """Execute the source crawl workflow.

        Args:
            input: Crawl input with URL and adapter ID

        Returns:
            Dictionary with extracted and verified claims
        """
        result = {
            "url": input.url,
            "claims": [],
            "verified_claims": [],
            "error": None,
        }

        try:
            # Step 1: Crawl the URL
            if TEMPORAL_AVAILABLE:
                crawl_output = await workflow.execute_activity(
                    CrawlActivity.crawl_url,
                    input,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=5),
                    ),
                )
            else:
                crawl_output = CrawlOutput(url=input.url or "", content="")

            if crawl_output.error:
                result["error"] = crawl_output.error
                return result

            # Step 2: Extract claims
            extraction_input = ExtractionInput(
                content=crawl_output.content,
                url=crawl_output.url,
                adapter_id=input.adapter_id,
            )

            if TEMPORAL_AVAILABLE:
                extraction_output = await workflow.execute_activity(
                    ExtractionActivity.extract_claims,
                    extraction_input,
                    start_to_close_timeout=timedelta(minutes=5),
                )
            else:
                extraction_output = ExtractionOutput()

            result["claims"] = extraction_output.claims

            # Step 3: Verify each claim
            for claim in extraction_output.claims:
                verification_input = VerificationInput(
                    claim=claim,
                    source_content=crawl_output.content,
                    subject_id=input.subject_id or "",
                )

                if TEMPORAL_AVAILABLE:
                    verification_output = await workflow.execute_activity(
                        VerificationActivity.verify_claim,
                        verification_input,
                        start_to_close_timeout=timedelta(minutes=1),
                    )
                else:
                    verification_output = VerificationOutput(
                        claim_id=claim.get("claim_id", ""),
                        verified=True,
                    )

                if verification_output.verified:
                    result["verified_claims"].append({
                        **claim,
                        "verification_confidence": verification_output.confidence,
                    })

        except Exception as e:
            result["error"] = str(e)

        return result


@workflow.defn
class EnrichmentLoopWorkflow:
    """Workflow for a single enrichment loop iteration.

    Processes a batch of frontier items and generates new hypotheses.
    """

    @workflow.run
    async def run(
        self,
        session_id: str,
        batch_size: int = 10,
    ) -> dict[str, Any]:
        """Execute one enrichment loop iteration.

        Args:
            session_id: Parent research session ID
            batch_size: Number of frontier items to process

        Returns:
            Dictionary with processing results
        """
        result = {
            "processed": 0,
            "claims_found": 0,
            "new_hypotheses": 0,
            "conflicts_resolved": 0,
        }

        # In real implementation:
        # 1. Pop batch_size items from frontier queue
        # 2. Execute SourceCrawlWorkflow for each
        # 3. Aggregate claims and resolve conflicts
        # 4. Generate new hypotheses

        logger.info(f"Enrichment loop for session {session_id}, batch size {batch_size}")

        return result
