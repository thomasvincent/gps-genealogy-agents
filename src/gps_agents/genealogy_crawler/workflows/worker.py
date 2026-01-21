"""Temporal Worker for executing genealogy crawler workflows.

The worker runs activities and workflows on behalf of the Temporal server.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

try:
    from temporalio.client import Client
    from temporalio.worker import Worker
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False
    Client = None
    Worker = None

from .activities import (
    CrawlActivity,
    ExtractionActivity,
    ExtractionVerificationActivity,
    QueryExpansionActivity,
    ResolutionActivity,
    VerificationActivity,
)
from .workflows import (
    EnrichmentLoopWorkflow,
    ResearchSessionWorkflow,
    SourceCrawlWorkflow,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Configuration for the Temporal worker."""
    temporal_address: str = "localhost:7233"
    namespace: str = "default"
    task_queue: str = "genealogy-crawler"

    # Activity dependencies
    adapters: dict[str, Any] = field(default_factory=dict)
    llm_registry: Any = None

    # Worker settings
    max_concurrent_activities: int = 10
    max_concurrent_workflow_tasks: int = 5


class CrawlerWorker:
    """Temporal worker for the genealogy crawler.

    Registers and runs all workflows and activities.
    """

    def __init__(self, config: WorkerConfig) -> None:
        """Initialize the worker.

        Args:
            config: Worker configuration
        """
        self.config = config
        self._client: Any = None
        self._worker: Any = None

        # Initialize activity instances with dependencies
        self._crawl_activity = CrawlActivity(adapters=config.adapters)
        self._extraction_activity = ExtractionActivity(adapters=config.adapters)
        self._verification_activity = VerificationActivity(llm_registry=config.llm_registry)
        self._resolution_activity = ResolutionActivity()
        self._extraction_verification_activity = ExtractionVerificationActivity(
            llm_registry=config.llm_registry
        )
        self._query_expansion_activity = QueryExpansionActivity(
            llm_registry=config.llm_registry
        )

    async def connect(self) -> None:
        """Connect to the Temporal server."""
        if not TEMPORAL_AVAILABLE:
            logger.warning("Temporal not available, running in mock mode")
            return

        self._client = await Client.connect(
            self.config.temporal_address,
            namespace=self.config.namespace,
        )
        logger.info(f"Connected to Temporal at {self.config.temporal_address}")

    async def start(self) -> None:
        """Start the worker.

        The worker will run until stop() is called or the context is cancelled.
        """
        if not TEMPORAL_AVAILABLE:
            logger.warning("Temporal not available, worker not started")
            return

        if self._client is None:
            await self.connect()

        # Create worker with all workflows and activities
        self._worker = Worker(
            self._client,
            task_queue=self.config.task_queue,
            workflows=[
                ResearchSessionWorkflow,
                SourceCrawlWorkflow,
                EnrichmentLoopWorkflow,
            ],
            activities=[
                self._crawl_activity.crawl_url,
                self._crawl_activity.search_source,
                self._extraction_activity.extract_claims,
                self._verification_activity.verify_claim,
                self._resolution_activity.resolve_conflicts,
                self._extraction_verification_activity.verify_extraction,
                self._query_expansion_activity.expand_queries,
            ],
        )

        logger.info(f"Starting worker on task queue: {self.config.task_queue}")
        await self._worker.run()

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        if self._worker:
            self._worker.shutdown()
            logger.info("Worker shutdown initiated")

    async def start_research_session(
        self,
        session_id: str,
        subject_name: str,
        **kwargs: Any,
    ) -> str:
        """Start a new research session workflow.

        Args:
            session_id: Unique session identifier
            subject_name: Name of the research subject
            **kwargs: Additional configuration options

        Returns:
            Workflow ID
        """
        if not TEMPORAL_AVAILABLE:
            logger.warning("Temporal not available, session not started")
            return session_id

        if self._client is None:
            await self.connect()

        from .workflows import ResearchSessionConfig

        config = ResearchSessionConfig(
            session_id=session_id,
            subject_name=subject_name,
            subject_birth_year=kwargs.get("birth_year"),
            subject_death_year=kwargs.get("death_year"),
            subject_location=kwargs.get("location"),
            max_requests=kwargs.get("max_requests", 100),
            max_duration_minutes=kwargs.get("max_duration_minutes", 60),
            target_confidence=kwargs.get("target_confidence", 0.85),
            enabled_adapters=kwargs.get("enabled_adapters", []),
        )

        handle = await self._client.start_workflow(
            ResearchSessionWorkflow.run,
            config,
            id=session_id,
            task_queue=self.config.task_queue,
        )

        logger.info(f"Started research session workflow: {session_id}")
        return handle.id

    async def get_session_state(self, session_id: str) -> dict[str, Any]:
        """Query the state of a research session.

        Args:
            session_id: The workflow ID

        Returns:
            Current session state
        """
        if not TEMPORAL_AVAILABLE:
            return {"status": "mock", "session_id": session_id}

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(session_id)
        state = await handle.query(ResearchSessionWorkflow.get_state)

        return {
            "session_id": state.session_id,
            "status": state.status,
            "requests_made": state.requests_made,
            "claims_extracted": state.claims_extracted,
            "current_confidence": state.current_confidence,
            "frontier_size": state.frontier_size,
        }

    async def pause_session(self, session_id: str) -> None:
        """Pause a running research session.

        Args:
            session_id: The workflow ID
        """
        if not TEMPORAL_AVAILABLE:
            return

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(session_id)
        await handle.signal(ResearchSessionWorkflow.pause)
        logger.info(f"Paused session: {session_id}")

    async def resume_session(self, session_id: str) -> None:
        """Resume a paused research session.

        Args:
            session_id: The workflow ID
        """
        if not TEMPORAL_AVAILABLE:
            return

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(session_id)
        await handle.signal(ResearchSessionWorkflow.resume)
        logger.info(f"Resumed session: {session_id}")

    async def stop_session(self, session_id: str) -> None:
        """Stop a research session.

        Args:
            session_id: The workflow ID
        """
        if not TEMPORAL_AVAILABLE:
            return

        if self._client is None:
            await self.connect()

        handle = self._client.get_workflow_handle(session_id)
        await handle.signal(ResearchSessionWorkflow.stop)
        logger.info(f"Stopped session: {session_id}")


def create_worker(
    temporal_address: str = "localhost:7233",
    task_queue: str = "genealogy-crawler",
    adapters: dict[str, Any] | None = None,
    llm_registry: Any = None,
) -> CrawlerWorker:
    """Create a configured crawler worker.

    Args:
        temporal_address: Temporal server address
        task_queue: Task queue name
        adapters: Dictionary of source adapters
        llm_registry: LLM registry for verification

    Returns:
        Configured CrawlerWorker instance
    """
    config = WorkerConfig(
        temporal_address=temporal_address,
        task_queue=task_queue,
        adapters=adapters or {},
        llm_registry=llm_registry,
    )

    return CrawlerWorker(config)


async def run_worker_cli() -> None:
    """CLI entry point for running the worker."""
    import argparse

    parser = argparse.ArgumentParser(description="Genealogy Crawler Worker")
    parser.add_argument(
        "--temporal-address",
        default="localhost:7233",
        help="Temporal server address",
    )
    parser.add_argument(
        "--task-queue",
        default="genealogy-crawler",
        help="Task queue name",
    )

    args = parser.parse_args()

    worker = create_worker(
        temporal_address=args.temporal_address,
        task_queue=args.task_queue,
    )

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(run_worker_cli())
