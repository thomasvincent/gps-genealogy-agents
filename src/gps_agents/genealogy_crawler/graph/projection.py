"""CQRS Projection layer for syncing RocksDB ledger to Neo4j graph.

Implements eventual consistency between:
- Source of truth: RocksDB ledger (immutable evidence records)
- Read projection: Neo4j graph (optimized for relationship traversal)

The projection rebuilds from ledger events, enabling:
- Fast ancestor/descendant queries via Cypher
- Point-in-time reconstruction from ledger
- Idempotent sync operations
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from .graph_store import Edge, EdgeType, GraphStore, Node, NodeType
from .models import (
    ProjectionMetadata,
    ProjectionStatus,
    SyncEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

logger = logging.getLogger(__name__)


class ProjectionSyncError(Exception):
    """Error during projection sync."""

    def __init__(self, message: str, failed_events: list[SyncEvent] | None = None):
        super().__init__(message)
        self.failed_events = failed_events or []


class GraphProjection:
    """CQRS projection manager for genealogical graph.

    Syncs data from a source ledger to a target graph store,
    maintaining consistency and tracking sync state.

    Example:
        >>> projection = GraphProjection(
        ...     source_store=rocksdb_ledger,
        ...     target_store=neo4j_graph,
        ... )
        >>> await projection.sync()
        >>> print(projection.metadata.status)
        ProjectionStatus.SYNCED
    """

    def __init__(
        self,
        source_store: GraphStore,
        target_store: GraphStore,
        batch_size: int = 100,
    ) -> None:
        """Initialize projection manager.

        Args:
            source_store: Source of truth (typically RocksDB)
            target_store: Target projection (typically Neo4j)
            batch_size: Number of events to process per batch
        """
        self.source = source_store
        self.target = target_store
        self.batch_size = batch_size
        self._metadata = ProjectionMetadata()
        self._sync_handlers: dict[str, Callable] = {}
        self._event_queue: asyncio.Queue[SyncEvent] = asyncio.Queue()

    @property
    def metadata(self) -> ProjectionMetadata:
        """Get current projection metadata."""
        return self._metadata

    async def sync(self, full_rebuild: bool = False) -> ProjectionMetadata:
        """Synchronize projection with source ledger.

        Args:
            full_rebuild: If True, rebuild entire projection from scratch

        Returns:
            Updated projection metadata
        """
        start_time = datetime.now(UTC)
        self._metadata.status = ProjectionStatus.SYNCING

        try:
            if full_rebuild:
                await self._full_rebuild()
            else:
                await self._incremental_sync()

            self._metadata.status = ProjectionStatus.SYNCED
            self._metadata.last_sync_at = datetime.now(UTC)
            self._metadata.projection_version = self._metadata.ledger_version
            self._metadata.error_message = None

            end_time = datetime.now(UTC)
            self._metadata.sync_duration_ms = (end_time - start_time).total_seconds() * 1000

            logger.info(
                "Projection sync complete: %d nodes, %d edges in %.2fms",
                self._metadata.total_nodes,
                self._metadata.total_edges,
                self._metadata.sync_duration_ms,
            )

        except Exception as e:
            self._metadata.status = ProjectionStatus.ERROR
            self._metadata.error_message = str(e)
            logger.exception("Projection sync failed")
            raise ProjectionSyncError(str(e)) from e

        return self._metadata

    async def _full_rebuild(self) -> None:
        """Rebuild entire projection from source ledger."""
        logger.info("Starting full projection rebuild")

        # Clear target (if supported)
        await self._clear_target()

        # Sync all nodes
        nodes_synced = 0
        for node_type in NodeType:
            from .graph_store import GraphQuery
            query = GraphQuery(node_type=node_type, limit=self.batch_size)

            while True:
                nodes = self.source.query(query)
                if not nodes:
                    break

                for node in nodes:
                    self.target.add_node(node)
                    nodes_synced += 1

                query.offset += len(nodes)
                if len(nodes) < self.batch_size:
                    break

        self._metadata.total_nodes = nodes_synced
        logger.info("Synced %d nodes", nodes_synced)

        # Sync all edges by traversing nodes
        edges_synced = 0
        seen_edges: set[UUID] = set()

        from .graph_store import GraphQuery
        query = GraphQuery(limit=self.batch_size)
        query.offset = 0

        while True:
            nodes = self.source.query(query)
            if not nodes:
                break

            for node in nodes:
                neighbors = self.source.get_neighbors(node.node_id, direction="outgoing")
                for edge, _ in neighbors:
                    if edge.edge_id not in seen_edges:
                        self.target.add_edge(edge)
                        seen_edges.add(edge.edge_id)
                        edges_synced += 1

            query.offset += len(nodes)
            if len(nodes) < self.batch_size:
                break

        self._metadata.total_edges = edges_synced
        logger.info("Synced %d edges", edges_synced)

    async def _incremental_sync(self) -> None:
        """Apply incremental changes from source to target."""
        events_processed = 0

        while not self._event_queue.empty():
            event = await self._event_queue.get()

            try:
                await self._apply_event(event)
                events_processed += 1
            except Exception as e:
                logger.warning("Failed to apply event %s: %s", event.event_id, e)
                raise ProjectionSyncError(
                    f"Failed at event {event.event_id}",
                    failed_events=[event],
                ) from e

        logger.info("Applied %d incremental events", events_processed)

    async def _apply_event(self, event: SyncEvent) -> None:
        """Apply a single sync event to target."""
        if event.event_type == "node_added":
            node = self.source.get_node(event.entity_id)
            if node:
                self.target.add_node(node)
                self._metadata.total_nodes += 1

        elif event.event_type == "node_updated":
            node = self.source.get_node(event.entity_id)
            if node:
                self.target.update_node(node)

        elif event.event_type == "node_deleted":
            self.target.delete_node(event.entity_id)
            self._metadata.total_nodes -= 1

        elif event.event_type == "edge_added":
            edge = self.source.get_edge(event.entity_id)
            if edge:
                self.target.add_edge(edge)
                self._metadata.total_edges += 1

        elif event.event_type == "edge_deleted":
            self.target.delete_edge(event.entity_id)
            self._metadata.total_edges -= 1

    async def _clear_target(self) -> None:
        """Clear all data from target store."""
        # This would need store-specific implementation
        # For Neo4j: MATCH (n) DETACH DELETE n
        logger.info("Clearing target projection")

    def queue_event(self, event: SyncEvent) -> None:
        """Queue an event for incremental sync."""
        self._event_queue.put_nowait(event)
        self._metadata.ledger_version = event.new_version
        self._metadata.status = ProjectionStatus.STALE

    def create_node_added_event(self, node: Node) -> SyncEvent:
        """Create event for node addition."""
        return SyncEvent(
            event_type="node_added",
            entity_id=node.node_id,
            new_version=self._metadata.ledger_version + 1,
            changes=node.to_dict(),
        )

    def create_edge_added_event(self, edge: Edge) -> SyncEvent:
        """Create event for edge addition."""
        return SyncEvent(
            event_type="edge_added",
            entity_id=edge.edge_id,
            new_version=self._metadata.ledger_version + 1,
            changes=edge.to_dict(),
        )


class PersonProjector:
    """Projects person entities to graph nodes.

    Transforms person records from various sources into standardized
    graph nodes with consistent properties.
    """

    def __init__(self, projection: GraphProjection) -> None:
        self.projection = projection

    def project_person(
        self,
        person_id: UUID,
        name: str,
        *,
        birth_year: int | None = None,
        death_year: int | None = None,
        gender: str | None = None,
        **extra_properties: Any,
    ) -> Node:
        """Create a person node for projection.

        Args:
            person_id: Unique identifier
            name: Full name
            birth_year: Year of birth (optional)
            death_year: Year of death (optional)
            gender: Gender (optional)
            **extra_properties: Additional properties

        Returns:
            Node ready for graph storage
        """
        properties = {
            "name": name,
            **extra_properties,
        }

        if birth_year is not None:
            properties["birth_year"] = birth_year
        if death_year is not None:
            properties["death_year"] = death_year
        if gender is not None:
            properties["gender"] = gender

        return Node(
            node_id=person_id,
            node_type=NodeType.PERSON,
            properties=properties,
        )

    def project_parent_child(
        self,
        parent_id: UUID,
        child_id: UUID,
        *,
        parent_role: str = "parent",  # "father", "mother", or "parent"
        confidence: float = 1.0,
    ) -> Edge:
        """Create parent-child relationship edge.

        Args:
            parent_id: Parent person ID
            child_id: Child person ID
            parent_role: Role of parent ("father", "mother", "parent")
            confidence: Confidence in relationship

        Returns:
            Edge representing parent-child relationship
        """
        return Edge(
            edge_type=EdgeType.PARENT_OF,
            source_id=parent_id,
            target_id=child_id,
            properties={"parent_role": parent_role},
            confidence=confidence,
        )

    def project_spouse(
        self,
        person_a_id: UUID,
        person_b_id: UUID,
        *,
        marriage_year: int | None = None,
        divorce_year: int | None = None,
        confidence: float = 1.0,
    ) -> Edge:
        """Create spouse relationship edge.

        Args:
            person_a_id: First person ID
            person_b_id: Second person ID
            marriage_year: Year of marriage (optional)
            divorce_year: Year of divorce (optional)
            confidence: Confidence in relationship

        Returns:
            Edge representing spousal relationship
        """
        properties: dict[str, Any] = {}
        if marriage_year is not None:
            properties["marriage_year"] = marriage_year
        if divorce_year is not None:
            properties["divorce_year"] = divorce_year

        return Edge(
            edge_type=EdgeType.SPOUSE_OF,
            source_id=person_a_id,
            target_id=person_b_id,
            properties=properties,
            confidence=confidence,
        )


class EvidenceProjector:
    """Projects evidence and citations to graph.

    Links persons to their supporting evidence nodes.
    """

    def __init__(self, projection: GraphProjection) -> None:
        self.projection = projection

    def project_source(
        self,
        source_id: UUID,
        title: str,
        *,
        citation: str | None = None,
        repository: str | None = None,
        **extra_properties: Any,
    ) -> Node:
        """Create a source node for projection.

        Args:
            source_id: Unique identifier
            title: Source title
            citation: Full citation (optional)
            repository: Repository name (optional)
            **extra_properties: Additional properties

        Returns:
            Node ready for graph storage
        """
        properties = {
            "title": title,
            **extra_properties,
        }

        if citation is not None:
            properties["citation"] = citation
        if repository is not None:
            properties["repository"] = repository

        return Node(
            node_id=source_id,
            node_type=NodeType.SOURCE,
            properties=properties,
        )

    def project_citation_link(
        self,
        person_id: UUID,
        source_id: UUID,
        *,
        page_reference: str | None = None,
        extracted_data: dict[str, Any] | None = None,
    ) -> Edge:
        """Link a person to supporting source.

        Args:
            person_id: Person node ID
            source_id: Source node ID
            page_reference: Page/item reference (optional)
            extracted_data: Data extracted from source (optional)

        Returns:
            Edge linking person to source
        """
        properties: dict[str, Any] = {}
        if page_reference is not None:
            properties["page_reference"] = page_reference
        if extracted_data is not None:
            properties["extracted_data"] = extracted_data

        return Edge(
            edge_type=EdgeType.CITED_IN,
            source_id=person_id,
            target_id=source_id,
            properties=properties,
        )
