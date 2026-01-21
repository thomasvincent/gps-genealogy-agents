"""Tests for the v2 Genealogy Crawler components.

Tests the Source Adapter Framework, RocksDB-backed Frontier Queue,
Graph Storage, and Temporal Workflows.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

import pytest

from gps_agents.genealogy_crawler.adapters import (
    AdapterConfig,
    ComplianceConfig,
    ExtractionConfig,
    FetchResult,
    RateLimiter,
    SearchQuery,
    SearchResult,
)
from gps_agents.genealogy_crawler.adapters.base import RateLimitConfig
from gps_agents.genealogy_crawler.frontier import (
    CrawlItem,
    CrawlPriority,
    FrontierQueue,
    FrontierStats,
)
from gps_agents.genealogy_crawler.graph import (
    Edge,
    EdgeType,
    GraphQuery,
    Node,
    NodeType,
    PathResult,
    RocksDBGraphStore,
)
from gps_agents.genealogy_crawler.models_v2 import (
    BayesianResolution,
    ConflictingEvidence,
    EvidenceClass,
    SourceTier,
)
from gps_agents.genealogy_crawler.workflows import (
    CrawlActivity,
    ExtractionActivity,
    ResolutionActivity,
    VerificationActivity,
)
from gps_agents.genealogy_crawler.workflows.activities import (
    CrawlInput,
    CrawlOutput,
    ExtractionInput,
    ExtractionOutput,
    ResolutionInput,
    ResolutionOutput,
    VerificationInput,
    VerificationOutput,
)
from gps_agents.genealogy_crawler.workflows.workflows import (
    ResearchSessionConfig,
    ResearchSessionState,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_db"


@pytest.fixture
def frontier_queue(temp_db_path: Path) -> FrontierQueue:
    """Create a frontier queue with temporary storage."""
    queue = FrontierQueue(temp_db_path / "frontier")
    yield queue
    queue.close()


@pytest.fixture
def graph_store(temp_db_path: Path) -> RocksDBGraphStore:
    """Create a graph store with temporary storage."""
    store = RocksDBGraphStore(temp_db_path / "graph")
    yield store
    store.close()


@pytest.fixture
def sample_adapter_config() -> AdapterConfig:
    """Create a sample adapter configuration."""
    return AdapterConfig(
        adapter_id="test_source",
        display_name="Test Source",
        tier=1,
        domain="example.com",
        base_url="https://example.com",
        evidence_class="secondary_published",
        prior_weight=0.7,
        compliance=ComplianceConfig(
            robots_txt=True,
            rate_limit={"requests_per_second": 1.0, "burst": 5},
        ),
    )


# =============================================================================
# Frontier Queue Tests
# =============================================================================


class TestCrawlItem:
    """Tests for CrawlItem dataclass."""

    def test_create_with_defaults(self):
        """Test creating a crawl item with default values."""
        item = CrawlItem(url="https://example.com/person/123")

        assert item.url == "https://example.com/person/123"
        assert item.priority == CrawlPriority.NORMAL
        assert item.adapter_id == ""
        assert item.retry_count == 0
        assert item.max_retries == 3
        assert isinstance(item.item_id, UUID)
        assert isinstance(item.created_at, datetime)

    def test_content_hash_deterministic(self):
        """Test that content hash is consistent for same content."""
        item1 = CrawlItem(url="https://example.com/test", adapter_id="test")
        item2 = CrawlItem(url="https://example.com/test", adapter_id="test")

        assert item1.content_hash == item2.content_hash

    def test_content_hash_different_for_different_urls(self):
        """Test that content hash differs for different URLs."""
        item1 = CrawlItem(url="https://example.com/test1")
        item2 = CrawlItem(url="https://example.com/test2")

        assert item1.content_hash != item2.content_hash

    def test_serialization_roundtrip(self):
        """Test that items can be serialized and deserialized."""
        item = CrawlItem(
            url="https://example.com/test",
            adapter_id="test_adapter",
            priority=CrawlPriority.HIGH,
            hypothesis="Testing hypothesis",
            subject_id=uuid4(),
        )

        data = item.to_dict()
        restored = CrawlItem.from_dict(data)

        assert restored.url == item.url
        assert restored.adapter_id == item.adapter_id
        assert restored.priority == item.priority
        assert restored.hypothesis == item.hypothesis
        assert restored.subject_id == item.subject_id


class TestCrawlPriority:
    """Tests for CrawlPriority enum."""

    def test_priority_ordering(self):
        """Test that priority values are ordered correctly."""
        assert CrawlPriority.CRITICAL < CrawlPriority.HIGH
        assert CrawlPriority.HIGH < CrawlPriority.NORMAL
        assert CrawlPriority.NORMAL < CrawlPriority.LOW
        assert CrawlPriority.LOW < CrawlPriority.BACKGROUND

    def test_priority_values(self):
        """Test specific priority values."""
        assert CrawlPriority.CRITICAL == 0
        assert CrawlPriority.HIGH == 10
        assert CrawlPriority.NORMAL == 50
        assert CrawlPriority.LOW == 80
        assert CrawlPriority.BACKGROUND == 100


class TestFrontierQueue:
    """Tests for FrontierQueue operations."""

    def test_push_and_pop(self, frontier_queue: FrontierQueue):
        """Test basic push and pop operations."""
        item = CrawlItem(url="https://example.com/1")
        assert frontier_queue.push(item) is True
        assert len(frontier_queue) == 1

        popped = frontier_queue.pop()
        assert popped is not None
        assert popped.url == "https://example.com/1"
        assert len(frontier_queue) == 0

    def test_priority_ordering(self, frontier_queue: FrontierQueue):
        """Test that items are popped in priority order."""
        low = CrawlItem(url="https://example.com/low", priority=CrawlPriority.LOW)
        high = CrawlItem(url="https://example.com/high", priority=CrawlPriority.HIGH)
        normal = CrawlItem(url="https://example.com/normal", priority=CrawlPriority.NORMAL)

        # Push in random order
        frontier_queue.push(low)
        frontier_queue.push(high)
        frontier_queue.push(normal)

        # Should pop in priority order
        assert frontier_queue.pop().url == "https://example.com/high"
        assert frontier_queue.pop().url == "https://example.com/normal"
        assert frontier_queue.pop().url == "https://example.com/low"

    def test_duplicate_detection(self, frontier_queue: FrontierQueue):
        """Test that duplicate URLs are rejected."""
        item1 = CrawlItem(url="https://example.com/same", adapter_id="test")
        item2 = CrawlItem(url="https://example.com/same", adapter_id="test")

        assert frontier_queue.push(item1) is True
        assert frontier_queue.push(item2) is False
        assert len(frontier_queue) == 1

    def test_push_many(self, frontier_queue: FrontierQueue):
        """Test batch pushing of items."""
        items = [
            CrawlItem(url=f"https://example.com/{i}")
            for i in range(10)
        ]

        added = frontier_queue.push_many(items)
        assert added == 10
        assert len(frontier_queue) == 10

    def test_peek_without_removing(self, frontier_queue: FrontierQueue):
        """Test peeking at items without removing them."""
        items = [
            CrawlItem(url=f"https://example.com/{i}", priority=CrawlPriority.NORMAL)
            for i in range(5)
        ]
        for item in items:
            frontier_queue.push(item)

        peeked = frontier_queue.peek(3)
        assert len(peeked) == 3
        assert len(frontier_queue) == 5  # Items still in queue

    def test_complete_item(self, frontier_queue: FrontierQueue):
        """Test marking an item as completed."""
        item = CrawlItem(url="https://example.com/1")
        frontier_queue.push(item)

        popped = frontier_queue.pop()
        assert frontier_queue.complete(popped.item_id) is True

        stats = frontier_queue.stats()
        assert stats.completed_items == 1
        assert stats.pending_items == 0

    def test_fail_with_requeue(self, frontier_queue: FrontierQueue):
        """Test failing an item with requeue."""
        # Use NORMAL priority - it should get demoted to LOW on failure
        item = CrawlItem(url="https://example.com/1", max_retries=3, priority=CrawlPriority.NORMAL)
        frontier_queue.push(item, check_duplicate=False)

        popped = frontier_queue.pop()
        assert frontier_queue.fail(popped.item_id, requeue=True) is True

        # Item should be requeued with increased retry count
        assert len(frontier_queue) == 1
        requeued = frontier_queue.pop()
        assert requeued.retry_count == 1
        # Priority should have been demoted: NORMAL -> LOW
        assert requeued.priority == CrawlPriority.LOW

    def test_fail_without_requeue(self, frontier_queue: FrontierQueue):
        """Test failing an item without requeue."""
        item = CrawlItem(url="https://example.com/1")
        frontier_queue.push(item, check_duplicate=False)

        popped = frontier_queue.pop()
        assert frontier_queue.fail(popped.item_id, requeue=False) is True
        assert len(frontier_queue) == 0

        stats = frontier_queue.stats()
        assert stats.failed_items == 1

    def test_stats(self, frontier_queue: FrontierQueue):
        """Test statistics gathering."""
        items = [
            CrawlItem(url=f"https://example.com/{i}", priority=CrawlPriority.HIGH, adapter_id="test")
            for i in range(3)
        ]
        for item in items:
            frontier_queue.push(item)

        stats = frontier_queue.stats()
        assert isinstance(stats, FrontierStats)
        assert stats.pending_items == 3
        assert stats.items_by_priority.get("HIGH", 0) == 3
        assert stats.items_by_adapter.get("test", 0) == 3

    def test_clear(self, frontier_queue: FrontierQueue):
        """Test clearing the queue."""
        for i in range(5):
            frontier_queue.push(CrawlItem(url=f"https://example.com/{i}"))

        frontier_queue.clear()
        assert len(frontier_queue) == 0

    def test_empty_queue_pop_returns_none(self, frontier_queue: FrontierQueue):
        """Test that popping from empty queue returns None."""
        assert frontier_queue.pop() is None


# =============================================================================
# Graph Storage Tests
# =============================================================================


class TestNode:
    """Tests for Node dataclass."""

    def test_create_node(self):
        """Test creating a node."""
        node = Node(
            node_type=NodeType.PERSON,
            properties={"name": "John Smith", "birth_year": 1850},
        )

        assert isinstance(node.node_id, UUID)
        assert node.node_type == NodeType.PERSON
        assert node.properties["name"] == "John Smith"

    def test_node_serialization(self):
        """Test node serialization roundtrip."""
        node = Node(
            node_type=NodeType.EVENT,
            properties={"event_type": "birth", "date": "1850-03-15"},
        )

        data = node.to_dict()
        restored = Node.from_dict(data)

        assert restored.node_id == node.node_id
        assert restored.node_type == node.node_type
        assert restored.properties == node.properties


class TestEdge:
    """Tests for Edge dataclass."""

    def test_create_edge(self):
        """Test creating an edge."""
        source_id = uuid4()
        target_id = uuid4()

        edge = Edge(
            edge_type=EdgeType.PARENT_OF,
            source_id=source_id,
            target_id=target_id,
            confidence=0.95,
        )

        assert edge.edge_type == EdgeType.PARENT_OF
        assert edge.source_id == source_id
        assert edge.target_id == target_id
        assert edge.confidence == 0.95

    def test_edge_serialization(self):
        """Test edge serialization roundtrip."""
        edge = Edge(
            edge_type=EdgeType.SPOUSE_OF,
            source_id=uuid4(),
            target_id=uuid4(),
            properties={"marriage_date": "1875"},
        )

        data = edge.to_dict()
        restored = Edge.from_dict(data)

        assert restored.edge_id == edge.edge_id
        assert restored.edge_type == edge.edge_type
        assert restored.source_id == edge.source_id
        assert restored.target_id == edge.target_id


class TestRocksDBGraphStore:
    """Tests for RocksDB-backed graph storage."""

    def test_add_and_get_node(self, graph_store: RocksDBGraphStore):
        """Test adding and retrieving a node."""
        node = Node(
            node_type=NodeType.PERSON,
            properties={"name": "Jane Doe"},
        )

        added = graph_store.add_node(node)
        retrieved = graph_store.get_node(node.node_id)

        assert retrieved is not None
        assert retrieved.node_id == node.node_id
        assert retrieved.properties["name"] == "Jane Doe"

    def test_update_node(self, graph_store: RocksDBGraphStore):
        """Test updating a node."""
        node = Node(
            node_type=NodeType.PERSON,
            properties={"name": "John"},
        )
        graph_store.add_node(node)

        node.properties["name"] = "John Smith"
        graph_store.update_node(node)

        retrieved = graph_store.get_node(node.node_id)
        assert retrieved.properties["name"] == "John Smith"

    def test_delete_node(self, graph_store: RocksDBGraphStore):
        """Test deleting a node."""
        node = Node(node_type=NodeType.PERSON)
        graph_store.add_node(node)

        assert graph_store.delete_node(node.node_id) is True
        assert graph_store.get_node(node.node_id) is None

    def test_add_and_get_edge(self, graph_store: RocksDBGraphStore):
        """Test adding and retrieving an edge."""
        parent = Node(node_type=NodeType.PERSON, properties={"name": "Parent"})
        child = Node(node_type=NodeType.PERSON, properties={"name": "Child"})
        graph_store.add_node(parent)
        graph_store.add_node(child)

        edge = Edge(
            edge_type=EdgeType.PARENT_OF,
            source_id=parent.node_id,
            target_id=child.node_id,
        )
        graph_store.add_edge(edge)

        retrieved = graph_store.get_edge(edge.edge_id)
        assert retrieved is not None
        assert retrieved.edge_type == EdgeType.PARENT_OF
        assert retrieved.source_id == parent.node_id
        assert retrieved.target_id == child.node_id

    def test_delete_edge(self, graph_store: RocksDBGraphStore):
        """Test deleting an edge."""
        n1 = Node(node_type=NodeType.PERSON)
        n2 = Node(node_type=NodeType.PERSON)
        graph_store.add_node(n1)
        graph_store.add_node(n2)

        edge = Edge(edge_type=EdgeType.SIBLING_OF, source_id=n1.node_id, target_id=n2.node_id)
        graph_store.add_edge(edge)

        assert graph_store.delete_edge(edge.edge_id) is True
        assert graph_store.get_edge(edge.edge_id) is None

    def test_get_neighbors(self, graph_store: RocksDBGraphStore):
        """Test getting neighboring nodes."""
        # Create family: parent -> child1, parent -> child2
        parent = Node(node_type=NodeType.PERSON, properties={"name": "Parent"})
        child1 = Node(node_type=NodeType.PERSON, properties={"name": "Child 1"})
        child2 = Node(node_type=NodeType.PERSON, properties={"name": "Child 2"})

        for node in [parent, child1, child2]:
            graph_store.add_node(node)

        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=parent.node_id, target_id=child1.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=parent.node_id, target_id=child2.node_id))

        neighbors = graph_store.get_neighbors(parent.node_id, direction="outgoing")
        assert len(neighbors) == 2

        child_names = {n.properties["name"] for _, n in neighbors}
        assert "Child 1" in child_names
        assert "Child 2" in child_names

    def test_get_neighbors_with_edge_type_filter(self, graph_store: RocksDBGraphStore):
        """Test filtering neighbors by edge type."""
        person = Node(node_type=NodeType.PERSON, properties={"name": "Person"})
        parent = Node(node_type=NodeType.PERSON, properties={"name": "Parent"})
        spouse = Node(node_type=NodeType.PERSON, properties={"name": "Spouse"})

        for node in [person, parent, spouse]:
            graph_store.add_node(node)

        graph_store.add_edge(Edge(edge_type=EdgeType.CHILD_OF, source_id=person.node_id, target_id=parent.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.SPOUSE_OF, source_id=person.node_id, target_id=spouse.node_id))

        # Filter for only SPOUSE_OF
        neighbors = graph_store.get_neighbors(person.node_id, edge_types=[EdgeType.SPOUSE_OF])
        assert len(neighbors) == 1
        assert neighbors[0][1].properties["name"] == "Spouse"

    def test_find_path(self, graph_store: RocksDBGraphStore):
        """Test finding path between nodes."""
        # Create lineage: grandparent -> parent -> child
        grandparent = Node(node_type=NodeType.PERSON, properties={"name": "Grandparent"})
        parent = Node(node_type=NodeType.PERSON, properties={"name": "Parent"})
        child = Node(node_type=NodeType.PERSON, properties={"name": "Child"})

        for node in [grandparent, parent, child]:
            graph_store.add_node(node)

        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=grandparent.node_id, target_id=parent.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=parent.node_id, target_id=child.node_id))

        path = graph_store.find_path(grandparent.node_id, child.node_id)
        assert path is not None
        assert path.length == 2
        assert len(path.nodes) == 3

    def test_find_path_no_connection(self, graph_store: RocksDBGraphStore):
        """Test that find_path returns None for unconnected nodes."""
        n1 = Node(node_type=NodeType.PERSON)
        n2 = Node(node_type=NodeType.PERSON)
        graph_store.add_node(n1)
        graph_store.add_node(n2)

        path = graph_store.find_path(n1.node_id, n2.node_id)
        assert path is None

    def test_query_by_node_type(self, graph_store: RocksDBGraphStore):
        """Test querying nodes by type."""
        person = Node(node_type=NodeType.PERSON, properties={"name": "John"})
        event = Node(node_type=NodeType.EVENT, properties={"type": "birth"})
        graph_store.add_node(person)
        graph_store.add_node(event)

        query = GraphQuery(node_type=NodeType.PERSON)
        results = graph_store.query(query)

        assert len(results) == 1
        assert results[0].node_type == NodeType.PERSON

    def test_query_by_properties(self, graph_store: RocksDBGraphStore):
        """Test querying nodes by properties."""
        john = Node(node_type=NodeType.PERSON, properties={"name": "John", "birth_year": 1850})
        jane = Node(node_type=NodeType.PERSON, properties={"name": "Jane", "birth_year": 1855})
        graph_store.add_node(john)
        graph_store.add_node(jane)

        query = GraphQuery(node_properties={"name": "John"})
        results = graph_store.query(query)

        assert len(results) == 1
        assert results[0].properties["name"] == "John"


# =============================================================================
# Source Adapter Tests
# =============================================================================


class TestAdapterConfig:
    """Tests for AdapterConfig."""

    def test_create_config(self, sample_adapter_config: AdapterConfig):
        """Test creating an adapter configuration."""
        assert sample_adapter_config.adapter_id == "test_source"
        assert sample_adapter_config.tier == 1
        assert sample_adapter_config.prior_weight == 0.7

    def test_source_tier_property(self, sample_adapter_config: AdapterConfig):
        """Test source tier enum conversion."""
        # SourceTier uses TIER_0, TIER_1, TIER_2 (tier=1 -> TIER_1)
        assert sample_adapter_config.source_tier == SourceTier.TIER_1

    def test_evidence_class_property(self, sample_adapter_config: AdapterConfig):
        """Test evidence class enum conversion."""
        assert sample_adapter_config.evidence_class_enum == EvidenceClass.SECONDARY_PUBLISHED


class TestSearchQuery:
    """Tests for SearchQuery."""

    def test_create_query(self):
        """Test creating a search query."""
        query = SearchQuery(
            query_string="John Smith",
            given_name="John",
            surname="Smith",
            birth_year=1850,
        )

        assert query.query_string == "John Smith"
        assert query.given_name == "John"
        assert query.birth_year == 1850

    def test_format_param(self):
        """Test parameter template formatting."""
        query = SearchQuery(
            query_string="John Smith",
            given_name="John",
            surname="Smith",
            birth_year=1850,
        )

        result = query.format_param("fn={given_name}&ln={surname}&by={birth_year}")
        assert result == "fn=John&ln=Smith&by=1850"


class TestFetchResult:
    """Tests for FetchResult."""

    def test_create_result(self):
        """Test creating a fetch result."""
        result = FetchResult(
            url="https://example.com/page",
            content="<html>content</html>",
            status_code=200,
        )

        assert result.url == "https://example.com/page"
        assert result.status_code == 200
        assert result.from_cache is False

    def test_content_hash(self):
        """Test content hash generation."""
        result = FetchResult(url="https://example.com", content="test content")
        assert isinstance(result.content_hash, str)
        assert len(result.content_hash) == 64  # SHA256 hex


class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_within_burst(self):
        """Test acquiring tokens within burst limit."""
        # RateLimitConfig is imported from adapters.base at top of file
        config = RateLimitConfig(requests_per_second=10.0, burst=5)
        limiter = RateLimiter(config)

        # Should acquire immediately up to burst
        for _ in range(5):
            await limiter.acquire()  # Should not block


# =============================================================================
# Workflow Activity Tests
# =============================================================================


class TestCrawlActivity:
    """Tests for CrawlActivity."""

    def test_init_with_adapters(self):
        """Test initializing with adapter registry."""
        activity = CrawlActivity(adapters={})
        assert activity.adapters == {}

    @pytest.mark.asyncio
    async def test_crawl_url_no_adapter(self):
        """Test crawling with unknown adapter returns error."""
        activity = CrawlActivity(adapters={})
        input_data = CrawlInput(url="https://example.com", adapter_id="unknown")

        result = await activity.crawl_url(input_data)

        assert result.error is not None
        assert "Unknown adapter" in result.error

    @pytest.mark.asyncio
    async def test_crawl_url_no_url(self):
        """Test crawling without URL returns error."""
        activity = CrawlActivity(adapters={})
        input_data = CrawlInput(adapter_id="test")

        result = await activity.crawl_url(input_data)

        assert result.error is not None
        assert "No URL" in result.error


class TestExtractionActivity:
    """Tests for ExtractionActivity."""

    def test_init(self):
        """Test initialization."""
        activity = ExtractionActivity(adapters={})
        assert activity.adapters == {}


class TestVerificationActivity:
    """Tests for VerificationActivity."""

    def test_init(self):
        """Test initialization."""
        activity = VerificationActivity(llm_registry=None)
        assert activity.llm_registry is None


class TestResolutionActivity:
    """Tests for ResolutionActivity."""

    @pytest.mark.asyncio
    async def test_resolve_single_claim(self):
        """Test resolution with single claim (no conflict)."""
        activity = ResolutionActivity()
        input_data = ResolutionInput(
            subject_id=str(uuid4()),
            field_name="birth_year",
            claims=[{
                "claim_id": str(uuid4()),
                "claim_value": 1850,  # Activity expects claim_value, not value
                "prior_weight": 0.9,
                "source_description": "Birth Certificate",
                "citation_snippet": "Born 1850",
            }],
        )

        result = await activity.resolve_conflicts(input_data)

        assert result.error is None, f"Resolution failed: {result.error}"
        assert result.resolved_value == 1850
        assert result.confidence > 0


# =============================================================================
# Workflow Configuration Tests
# =============================================================================


class TestResearchSessionConfig:
    """Tests for ResearchSessionConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ResearchSessionConfig(subject_name="John Smith")

        assert config.subject_name == "John Smith"
        assert config.max_requests == 100
        assert config.target_confidence == 0.85

    def test_custom_config(self):
        """Test custom configuration."""
        config = ResearchSessionConfig(
            subject_name="Jane Doe",
            subject_birth_year=1850,
            max_requests=50,
            target_confidence=0.9,
            enabled_adapters=["wikipedia", "findagrave"],
        )

        assert config.subject_birth_year == 1850
        assert config.max_requests == 50
        assert len(config.enabled_adapters) == 2


class TestResearchSessionState:
    """Tests for ResearchSessionState."""

    def test_default_state(self):
        """Test default state values."""
        state = ResearchSessionState()

        assert state.status == "pending"
        assert state.requests_made == 0
        assert state.claims_extracted == 0

    def test_state_tracking(self):
        """Test state updates."""
        state = ResearchSessionState(session_id="test-123")
        state.status = "running"
        state.requests_made = 10
        state.claims_extracted = 25

        assert state.session_id == "test-123"
        assert state.status == "running"
        assert state.requests_made == 10


# =============================================================================
# Bayesian Resolution Tests
# =============================================================================


class TestBayesianResolution:
    """Tests for Bayesian conflict resolution."""

    def test_single_source_resolution(self):
        """Test resolution with single evidence source."""
        evidence = [
            ConflictingEvidence(
                claim_id=uuid4(),
                value=1850,
                prior_weight=0.9,
                source_description="Birth Certificate",
                citation_snippet="Born in 1850",
            ),
        ]

        resolution = BayesianResolution.resolve(
            field_name="birth_year",
            subject_id=uuid4(),
            evidence=evidence,
        )

        assert resolution.resolved_value == 1850
        assert resolution.posterior_confidence > 0

    def test_conflicting_evidence_resolution(self):
        """Test resolution with conflicting evidence."""
        evidence = [
            ConflictingEvidence(
                claim_id=uuid4(),
                value=1850,
                prior_weight=0.95,
                source_description="Birth Certificate",
                citation_snippet="Born 1850",
            ),
            ConflictingEvidence(
                claim_id=uuid4(),
                value=1851,
                prior_weight=0.6,
                source_description="Census Record",
                citation_snippet="Age 29 in 1880",
            ),
        ]

        resolution = BayesianResolution.resolve(
            field_name="birth_year",
            subject_id=uuid4(),
            evidence=evidence,
        )

        # Higher weighted evidence should win
        assert resolution.resolved_value == 1850

    def test_empty_evidence(self):
        """Test resolution with no evidence raises ValueError."""
        with pytest.raises(ValueError, match="No evidence to resolve"):
            BayesianResolution.resolve(
                field_name="birth_year",
                subject_id=uuid4(),
                evidence=[],
            )


# =============================================================================
# Extraction Verifier LLM Tests
# =============================================================================


class TestExtractionVerifierSchemas:
    """Test Extraction Verifier schema validation."""

    def test_verified_extraction_requires_quote_for_confirmed(self):
        """Confirmed status requires exact_quote."""
        from gps_agents.genealogy_crawler.llm import VerifiedExtraction

        # Should raise without exact_quote
        with pytest.raises(ValueError, match="must have an exact_quote"):
            VerifiedExtraction(
                field="birth_date",
                value="1845",
                status="Confirmed",
                confidence=0.9,
                rationale="Found in source",
            )

    def test_verified_extraction_confirmed_with_quote(self):
        """Confirmed status works with exact_quote."""
        from gps_agents.genealogy_crawler.llm import VerifiedExtraction

        result = VerifiedExtraction(
            field="birth_date",
            value="1845",
            status="Confirmed",
            confidence=0.9,
            exact_quote="born in 1845",
            rationale="Found in source",
        )
        assert result.status == "Confirmed"
        assert result.exact_quote == "born in 1845"

    def test_verified_extraction_not_found(self):
        """NotFound status doesn't require quote."""
        from gps_agents.genealogy_crawler.llm import VerifiedExtraction

        result = VerifiedExtraction(
            field="death_date",
            value="1900",
            status="NotFound",
            confidence=0.0,
            rationale="Not mentioned in source",
        )
        assert result.status == "NotFound"

    def test_verified_extraction_corrected_requires_value(self):
        """Corrected status requires corrected_value."""
        from gps_agents.genealogy_crawler.llm import VerifiedExtraction

        with pytest.raises(ValueError, match="must have a corrected_value"):
            VerifiedExtraction(
                field="birth_date",
                value="1845",
                status="Corrected",
                confidence=0.8,
                rationale="Close but not exact",
            )

    def test_extraction_verifier_input(self):
        """Test ExtractionVerifierInput construction."""
        from gps_agents.genealogy_crawler.llm import (
            ExtractedField,
            ExtractionVerifierInput,
        )

        input_data = ExtractionVerifierInput(
            raw_text="John Smith was born in 1845 in Ireland.",
            candidate_extraction=[
                ExtractedField(field="name", value="John Smith"),
                ExtractedField(field="birth_year", value="1845"),
            ],
        )
        assert len(input_data.candidate_extraction) == 2

    def test_extraction_verifier_output(self):
        """Test ExtractionVerifierOutput construction."""
        from gps_agents.genealogy_crawler.llm import (
            ExtractionVerifierOutput,
            VerifiedExtraction,
        )

        output = ExtractionVerifierOutput(
            verified_fields=[
                VerifiedExtraction(
                    field="name",
                    value="John Smith",
                    status="Confirmed",
                    confidence=0.95,
                    exact_quote="John Smith",
                    rationale="Exact match",
                ),
            ],
            overall_confidence=0.95,
            hallucination_flags=[],
        )
        assert len(output.verified_fields) == 1
        assert output.overall_confidence == 0.95


class TestQueryExpanderSchemas:
    """Test Query Expander schema validation."""

    def test_confirmed_fact(self):
        """Test ConfirmedFact construction."""
        from gps_agents.genealogy_crawler.llm import ConfirmedFact

        fact = ConfirmedFact(
            field="birth_place",
            value="Ireland",
            confidence=0.9,
            source_snippet="born in Ireland",
        )
        assert fact.field == "birth_place"
        assert fact.confidence == 0.9

    def test_deep_search_query(self):
        """Test DeepSearchQuery construction."""
        from gps_agents.genealogy_crawler.llm import DeepSearchQuery

        query = DeepSearchQuery(
            query_string="John Smith immigration New York 1860-1870",
            target_source_type="immigration",
            reasoning="Irish immigrants typically arrived via New York",
            priority=0.8,
            expected_fields=["arrival_date", "ship_name"],
        )
        assert query.priority == 0.8
        assert "immigration" in query.target_source_type

    def test_query_expander_input(self):
        """Test QueryExpanderInput construction."""
        from gps_agents.genealogy_crawler.llm import (
            ConfirmedFact,
            QueryExpanderInput,
        )

        input_data = QueryExpanderInput(
            subject_name="John Smith",
            confirmed_facts=[
                ConfirmedFact(field="birth_year", value="1845", confidence=0.9),
                ConfirmedFact(field="birth_place", value="Ireland", confidence=0.85),
            ],
            research_goals=["Find immigration record"],
            already_searched=["John Smith genealogy"],
        )
        assert input_data.subject_name == "John Smith"
        assert len(input_data.confirmed_facts) == 2

    def test_query_expander_output(self):
        """Test QueryExpanderOutput construction."""
        from gps_agents.genealogy_crawler.llm import (
            DeepSearchQuery,
            QueryExpanderOutput,
        )

        output = QueryExpanderOutput(
            analysis="Based on Irish birth, suggest immigration search",
            deep_search_queries=[
                DeepSearchQuery(
                    query_string="John Smith immigration",
                    target_source_type="immigration",
                    reasoning="Follow up on birth location",
                ),
            ],
            research_hypotheses=["May have arrived via New York"],
        )
        assert len(output.deep_search_queries) == 1


class TestExtractionVerificationActivity:
    """Test ExtractionVerificationActivity."""

    def test_init_without_registry(self):
        """Activity initializes without LLM registry."""
        from gps_agents.genealogy_crawler.workflows import (
            ExtractionVerificationActivity,
        )

        activity = ExtractionVerificationActivity()
        assert activity.llm_registry is None

    @pytest.mark.asyncio
    async def test_verify_extraction_no_registry(self):
        """Activity returns error when registry not configured."""
        from gps_agents.genealogy_crawler.workflows.activities import (
            ExtractionVerificationActivity,
            ExtractionVerificationInput,
        )

        activity = ExtractionVerificationActivity()
        input_data = ExtractionVerificationInput(
            raw_text="John Smith was born in 1845.",
            candidate_extractions=[{"field": "name", "value": "John Smith"}],
        )

        result = await activity.verify_extraction(input_data)
        assert result.error == "LLM registry not configured"


class TestQueryExpansionActivity:
    """Test QueryExpansionActivity."""

    def test_init_without_registry(self):
        """Activity initializes without LLM registry."""
        from gps_agents.genealogy_crawler.workflows import QueryExpansionActivity

        activity = QueryExpansionActivity()
        assert activity.llm_registry is None

    @pytest.mark.asyncio
    async def test_expand_queries_no_registry(self):
        """Activity returns error when registry not configured."""
        from gps_agents.genealogy_crawler.workflows.activities import (
            QueryExpansionActivity,
            QueryExpansionInput,
        )

        activity = QueryExpansionActivity()
        input_data = QueryExpansionInput(
            subject_name="John Smith",
            confirmed_facts=[{"field": "birth_year", "value": "1845"}],
        )

        result = await activity.expand_queries(input_data)
        assert result.error == "LLM registry not configured"


# =============================================================================
# Integration Tests
# =============================================================================


class TestCrawlerIntegration:
    """Integration tests for crawler components working together."""

    def test_frontier_to_graph_workflow(self, frontier_queue: FrontierQueue, graph_store: RocksDBGraphStore):
        """Test items flowing from frontier to graph storage."""
        # Add crawl item
        subject_id = uuid4()
        item = CrawlItem(
            url="https://example.com/person/123",
            adapter_id="test",
            subject_id=subject_id,
        )
        frontier_queue.push(item)

        # Process item
        popped = frontier_queue.pop()
        assert popped is not None

        # Store result in graph
        node = Node(
            node_type=NodeType.PERSON,
            properties={
                "source_url": popped.url,
                "name": "John Smith",
            },
        )
        graph_store.add_node(node)

        # Mark complete
        frontier_queue.complete(popped.item_id)

        # Verify
        stats = frontier_queue.stats()
        assert stats.completed_items == 1

        retrieved = graph_store.get_node(node.node_id)
        assert retrieved.properties["source_url"] == "https://example.com/person/123"

    def test_family_tree_construction(self, graph_store: RocksDBGraphStore):
        """Test constructing a family tree in the graph."""
        # Create family members
        grandfather = Node(node_type=NodeType.PERSON, properties={"name": "Grandfather", "birth_year": 1850})
        grandmother = Node(node_type=NodeType.PERSON, properties={"name": "Grandmother", "birth_year": 1852})
        father = Node(node_type=NodeType.PERSON, properties={"name": "Father", "birth_year": 1880})
        mother = Node(node_type=NodeType.PERSON, properties={"name": "Mother", "birth_year": 1885})
        child = Node(node_type=NodeType.PERSON, properties={"name": "Child", "birth_year": 1910})

        for person in [grandfather, grandmother, father, mother, child]:
            graph_store.add_node(person)

        # Create relationships
        graph_store.add_edge(Edge(edge_type=EdgeType.SPOUSE_OF, source_id=grandfather.node_id, target_id=grandmother.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=grandfather.node_id, target_id=father.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=grandmother.node_id, target_id=father.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.SPOUSE_OF, source_id=father.node_id, target_id=mother.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=father.node_id, target_id=child.node_id))
        graph_store.add_edge(Edge(edge_type=EdgeType.PARENT_OF, source_id=mother.node_id, target_id=child.node_id))

        # Find path from grandfather to child
        path = graph_store.find_path(grandfather.node_id, child.node_id)
        assert path is not None
        assert path.length == 2  # grandfather -> father -> child

        # Query all people
        query = GraphQuery(node_type=NodeType.PERSON)
        people = graph_store.query(query)
        assert len(people) == 5


# =============================================================================
# Fact Adjudicator Tests
# =============================================================================


class TestResolutionStatus:
    """Tests for ResolutionStatus enum."""

    def test_status_values(self):
        """Test that all expected statuses exist."""
        from gps_agents.genealogy_crawler.models_v2 import ResolutionStatus

        assert ResolutionStatus.PENDING_REVIEW == "pending_review"
        assert ResolutionStatus.RESOLVED == "resolved"
        assert ResolutionStatus.REJECTED == "rejected"
        assert ResolutionStatus.INSUFFICIENT_EVIDENCE == "insufficient_evidence"
        assert ResolutionStatus.HUMAN_REVIEW_REQUIRED == "human_review_required"

    def test_status_is_string_enum(self):
        """Test that statuses can be used as strings."""
        from gps_agents.genealogy_crawler.models_v2 import ResolutionStatus

        status = ResolutionStatus.PENDING_REVIEW
        assert isinstance(status, str)
        assert status.value == "pending_review"
        assert str(status.value) == "pending_review"


class TestErrorPatternType:
    """Tests for ErrorPatternType enum."""

    def test_error_pattern_values(self):
        """Test that all expected error patterns exist."""
        from gps_agents.genealogy_crawler.models_v2 import ErrorPatternType

        assert ErrorPatternType.TOMBSTONE_ERROR == "tombstone_error"
        assert ErrorPatternType.MILITARY_AGE_PADDING == "military_age_padding"
        assert ErrorPatternType.IMMIGRATION_AGE_REDUCTION == "immigration_age_reduction"
        assert ErrorPatternType.CENSUS_APPROXIMATION == "census_approximation"
        assert ErrorPatternType.CLERICAL_TRANSCRIPTION == "clerical_transcription"
        assert ErrorPatternType.GENERATIONAL_CONFUSION == "generational_confusion"


class TestCompetingAssertion:
    """Tests for CompetingAssertion model."""

    def test_create_with_defaults(self):
        """Test creating a competing assertion with default values."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
            ResolutionStatus,
        )

        subject_id = uuid4()
        assertion = CompetingAssertion(
            subject_id=subject_id,
            fact_type=FactType.BIRTH,
            proposed_value="1850-01-15",
        )

        assert assertion.subject_id == subject_id
        assert assertion.fact_type == FactType.BIRTH
        assert assertion.proposed_value == "1850-01-15"
        assert assertion.status == ResolutionStatus.PENDING_REVIEW
        assert assertion.prior_weight == 0.5
        assert assertion.temporal_proximity_bonus == 0.0
        assert assertion.pattern_penalty == 0.0
        assert assertion.negative_evidence_modifier == 0.0
        assert isinstance(assertion.id, UUID)
        assert isinstance(assertion.created_at, datetime)

    def test_final_weight_basic(self):
        """Test final_weight computation with default values."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
        )

        assertion = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
            prior_weight=0.8,
        )

        assert assertion.final_weight == 0.8

    def test_final_weight_with_temporal_bonus(self):
        """Test final_weight with temporal proximity bonus."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
        )

        assertion = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
            prior_weight=0.7,
            temporal_proximity_bonus=0.05,
        )

        assert assertion.final_weight == 0.75

    def test_final_weight_with_penalties(self):
        """Test final_weight with pattern penalty and negative evidence."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            ErrorPatternType,
            FactType,
        )

        assertion = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.DEATH,
            proposed_value="1900-01-01",
            prior_weight=0.8,
            temporal_proximity_bonus=0.05,
            detected_patterns=[ErrorPatternType.TOMBSTONE_ERROR],
            pattern_penalty=-0.10,
            negative_evidence_modifier=-0.05,
        )

        # 0.8 + 0.05 - 0.10 - 0.05 = 0.70
        assert assertion.final_weight == pytest.approx(0.70)

    def test_final_weight_clamps_to_bounds(self):
        """Test that final_weight is clamped between 0 and 1."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
        )

        # Test upper bound
        assertion_high = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
            prior_weight=0.95,
            temporal_proximity_bonus=0.05,  # Would exceed 1.0
        )
        assert assertion_high.final_weight == 1.0

        # Test lower bound
        assertion_low = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
            prior_weight=0.1,
            pattern_penalty=-0.15,
            negative_evidence_modifier=-0.1,  # Would go below 0
        )
        assert assertion_low.final_weight == 0.0

    def test_mark_resolved(self):
        """Test marking an assertion as resolved."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
            ResolutionStatus,
        )

        assertion = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
        )

        assertion.mark_resolved(
            ResolutionStatus.RESOLVED,
            "Selected as winner based on primary source evidence",
            "conflict_analyst_tiebreaker",
        )

        assert assertion.status == ResolutionStatus.RESOLVED
        assert "primary source" in assertion.rationale
        assert assertion.resolved_by == "conflict_analyst_tiebreaker"
        assert assertion.resolved_at is not None

    def test_posterior_weight_overrides_prior(self):
        """Test that posterior_weight is used when available."""
        from gps_agents.genealogy_crawler.models_v2 import (
            CompetingAssertion,
            FactType,
        )

        assertion = CompetingAssertion(
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            proposed_value="1850",
            prior_weight=0.5,
            posterior_weight=0.9,
        )

        # Should use posterior_weight (0.9) not prior_weight (0.5)
        assert assertion.final_weight == 0.9


class TestNegativeEvidence:
    """Tests for NegativeEvidence model."""

    def test_create_negative_evidence(self):
        """Test creating a negative evidence record."""
        from gps_agents.genealogy_crawler.models_v2 import NegativeEvidence

        assertion_id = uuid4()
        evidence = NegativeEvidence(
            expected_record_type="death_certificate",
            expected_jurisdiction="Philadelphia County, PA",
            related_assertion_id=assertion_id,
            confidence_reduction=0.08,
            reasoning="No death record found in vital records for claimed 1850 death",
        )

        assert evidence.expected_record_type == "death_certificate"
        assert evidence.expected_jurisdiction == "Philadelphia County, PA"
        assert evidence.related_assertion_id == assertion_id
        assert evidence.confidence_reduction == 0.08
        assert evidence.search_thoroughness == "standard"
        assert isinstance(evidence.id, UUID)


class TestNormalizeDateToISO8601:
    """Tests for normalize_date_to_iso8601 function."""

    def test_full_date_dmy(self):
        """Test normalizing 'DD Mon YYYY' format."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("25 Dec 1900")
        assert result == "1900-12-25"
        assert precision == DatePrecision.EXACT

    def test_full_date_mdy(self):
        """Test normalizing 'Mon DD, YYYY' format."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("December 25, 1900")
        assert result == "1900-12-25"
        assert precision == DatePrecision.EXACT

    def test_month_year_only(self):
        """Test normalizing month and year only."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("December 1900")
        assert result == "1900-12"
        assert precision == DatePrecision.YEAR_MONTH

    def test_year_only(self):
        """Test normalizing year only."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("1900")
        assert result == "1900"
        assert precision == DatePrecision.YEAR

    def test_approximate_date_abt(self):
        """Test normalizing approximate dates with 'abt'."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("abt 1900")
        assert result == "1900"
        assert precision == DatePrecision.APPROXIMATE

    def test_approximate_date_circa(self):
        """Test normalizing approximate dates with 'circa'."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("circa 1900")
        assert result == "1900"
        assert precision == DatePrecision.APPROXIMATE

    def test_decade(self):
        """Test normalizing decade format."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("1890s")
        assert result == "1890/1899"
        assert precision == DatePrecision.DECADE

    def test_date_range(self):
        """Test normalizing date ranges."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("bet 1888 and 1892")
        assert result == "1888/1892"
        assert precision == DatePrecision.RANGE

    def test_before_date(self):
        """Test normalizing 'before' dates."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("before 1890")
        assert result == "/1890"
        assert precision == DatePrecision.BEFORE

    def test_after_date(self):
        """Test normalizing 'after' dates."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("after 1890")
        assert result == "1890/"
        assert precision == DatePrecision.AFTER

    def test_iso_format_passthrough(self):
        """Test that ISO format passes through unchanged."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("1900-12-25")
        assert result == "1900-12-25"
        assert precision == DatePrecision.EXACT

    def test_empty_string(self):
        """Test handling empty string."""
        from gps_agents.genealogy_crawler.models_v2 import (
            DatePrecision,
            normalize_date_to_iso8601,
        )

        result, precision = normalize_date_to_iso8601("")
        assert result == ""
        assert precision == DatePrecision.APPROXIMATE


class TestCalculateTemporalProximityBonus:
    """Tests for calculate_temporal_proximity_bonus function."""

    def test_primary_official_gets_max_bonus(self):
        """Test that primary official sources get max bonus regardless of date."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        # Even without dates, primary official gets max
        bonus = calculate_temporal_proximity_bonus(
            None, None, EvidenceClass.PRIMARY_OFFICIAL
        )
        assert bonus == 0.05

    def test_within_optimal_window(self):
        """Test bonus for sources within 5 years of event."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        source_date = datetime(1855, 1, 1, tzinfo=UTC)
        event_date = datetime(1850, 1, 1, tzinfo=UTC)

        bonus = calculate_temporal_proximity_bonus(
            source_date, event_date, EvidenceClass.SECONDARY_PUBLISHED
        )
        assert bonus == 0.05

    def test_decay_period(self):
        """Test bonus decay between 5 and 50 years."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        source_date = datetime(1880, 1, 1, tzinfo=UTC)  # 30 years after
        event_date = datetime(1850, 1, 1, tzinfo=UTC)

        bonus = calculate_temporal_proximity_bonus(
            source_date, event_date, EvidenceClass.SECONDARY_PUBLISHED
        )
        # 30 years is halfway through 45-year decay window
        # Expected: ~0.027 (approximately half of max bonus)
        assert 0.02 < bonus < 0.03

    def test_beyond_decay_window(self):
        """Test no bonus for sources 50+ years after event."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        source_date = datetime(1920, 1, 1, tzinfo=UTC)  # 70 years after
        event_date = datetime(1850, 1, 1, tzinfo=UTC)

        bonus = calculate_temporal_proximity_bonus(
            source_date, event_date, EvidenceClass.SECONDARY_PUBLISHED
        )
        assert bonus == 0.0

    def test_anachronistic_source_penalty(self):
        """Test penalty for sources dated before the event."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        source_date = datetime(1840, 1, 1, tzinfo=UTC)  # 10 years BEFORE
        event_date = datetime(1850, 1, 1, tzinfo=UTC)

        bonus = calculate_temporal_proximity_bonus(
            source_date, event_date, EvidenceClass.SECONDARY_PUBLISHED
        )
        assert bonus == -0.05

    def test_missing_dates_returns_zero(self):
        """Test that missing dates return zero bonus."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            calculate_temporal_proximity_bonus,
        )

        bonus = calculate_temporal_proximity_bonus(
            None, datetime(1850, 1, 1, tzinfo=UTC), EvidenceClass.SECONDARY_PUBLISHED
        )
        assert bonus == 0.0


class TestDetectErrorPatterns:
    """Tests for detect_error_patterns function."""

    def test_tombstone_error_jan_1(self):
        """Test detection of tombstone error with Jan 1 date."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        patterns = detect_error_patterns(
            FactType.DEATH,
            "1900-01-01",
            EvidenceClass.SECONDARY_MEMORIAL,
        )

        assert len(patterns) == 1
        assert patterns[0][0] == ErrorPatternType.TOMBSTONE_ERROR
        assert patterns[0][1] == -0.10

    def test_tombstone_error_dec_31(self):
        """Test detection of tombstone error with Dec 31 date."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        patterns = detect_error_patterns(
            FactType.DEATH,
            "1900-12-31",
            EvidenceClass.SECONDARY_MEMORIAL,
        )

        assert len(patterns) == 1
        assert patterns[0][0] == ErrorPatternType.TOMBSTONE_ERROR

    def test_military_age_padding(self):
        """Test detection of military age padding."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        context = {
            "has_military_records": True,
            "military_enlistment_year": 1862,  # Would be 12 if born in 1850
        }

        patterns = detect_error_patterns(
            FactType.BIRTH,
            "1850",  # Would make them 12 at enlistment
            EvidenceClass.PRIMARY_GOVERNMENT,
            context,
        )

        pattern_types = [p[0] for p in patterns]
        assert ErrorPatternType.MILITARY_AGE_PADDING in pattern_types

    def test_immigration_age_reduction(self):
        """Test detection of immigration age reduction pattern."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        context = {"has_immigration_records": True}

        patterns = detect_error_patterns(
            FactType.BIRTH,
            "1850",
            EvidenceClass.PRIMARY_GOVERNMENT,
            context,
        )

        pattern_types = [p[0] for p in patterns]
        assert ErrorPatternType.IMMIGRATION_AGE_REDUCTION in pattern_types

    def test_census_approximation(self):
        """Test detection of census approximation pattern."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        context = {"source_is_census": True}

        patterns = detect_error_patterns(
            FactType.BIRTH,
            "1850",
            EvidenceClass.PRIMARY_GOVERNMENT,
            context,
        )

        pattern_types = [p[0] for p in patterns]
        assert ErrorPatternType.CENSUS_APPROXIMATION in pattern_types

    def test_generational_confusion(self):
        """Test detection of generational confusion pattern."""
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        context = {"has_same_name_relative": True}

        patterns = detect_error_patterns(
            FactType.BIRTH,
            "1850",
            EvidenceClass.SECONDARY_PUBLISHED,
            context,
        )

        pattern_types = [p[0] for p in patterns]
        assert ErrorPatternType.GENERATIONAL_CONFUSION in pattern_types
        # Generational confusion has highest penalty
        penalty = [p[1] for p in patterns if p[0] == ErrorPatternType.GENERATIONAL_CONFUSION][0]
        assert penalty == -0.15

    def test_no_patterns_for_normal_date(self):
        """Test that normal dates don't trigger false positives."""
        from gps_agents.genealogy_crawler.models_v2 import (
            EvidenceClass,
            FactType,
            detect_error_patterns,
        )

        patterns = detect_error_patterns(
            FactType.DEATH,
            "1900-06-15",  # Normal date, not Jan 1 or Dec 31
            EvidenceClass.PRIMARY_OFFICIAL,
        )

        assert len(patterns) == 0


class TestFactAdjudicator:
    """Tests for FactAdjudicator class."""

    def test_adjudicate_claim_with_valid_citation(self):
        """Test adjudicating a claim with a valid citation."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import FactType

        adjudicator = FactAdjudicator()

        claim = {
            "claim_id": str(uuid4()),
            "claim_text": "Birth date of John Smith",
            "claim_value": "25 Dec 1850",
            "citation_snippet": "John Smith was born on the 25th of December, 1850",
            "prior_weight": 0.7,
        }

        source_text = """
        The records show that John Smith was born on the 25th of December, 1850
        in Philadelphia County, Pennsylvania.
        """

        result = adjudicator.adjudicate_claim(
            claim=claim,
            source_text=source_text,
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
        )

        assert result.accepted is True
        assert result.citation_found_in_source is True
        assert result.hallucination_detected is False
        assert result.normalized_date_iso == "1850-12-25"

    def test_adjudicate_claim_detects_hallucination(self):
        """Test that hallucinated citations are detected."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import FactType

        adjudicator = FactAdjudicator(strict_citation_check=True)

        claim = {
            "claim_id": str(uuid4()),
            "claim_text": "Birth date of John Smith",
            "claim_value": "25 Dec 1850",
            "citation_snippet": "born in the year 1850 on Christmas day",  # NOT in source
            "prior_weight": 0.7,
        }

        source_text = "John Smith was born sometime in the 1850s."

        result = adjudicator.adjudicate_claim(
            claim=claim,
            source_text=source_text,
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
        )

        assert result.accepted is False
        assert result.citation_found_in_source is False
        assert result.hallucination_detected is True

    def test_adjudicate_claim_detects_living_person(self):
        """Test detection of living persons."""
        from gps_agents.genealogy_crawler.fact_adjudicator import (
            FactAdjudicator,
            LIVING_PERSON_MASK,
        )
        from gps_agents.genealogy_crawler.models_v2 import FactType

        adjudicator = FactAdjudicator()

        claim = {
            "claim_id": str(uuid4()),
            "claim_value": "1990-05-15",  # Within 100-year rule
            "citation_snippet": "",
            "prior_weight": 0.7,
        }

        result = adjudicator.adjudicate_claim(
            claim=claim,
            source_text="Born May 15, 1990",
            subject_id=uuid4(),
            fact_type=FactType.BIRTH,
            subject_context={"subject_type": "person"},
        )

        assert result.living_person_detected is True
        assert result.redacted is True
        assert result.normalized_value == LIVING_PERSON_MASK

    def test_adjudicate_claim_detects_conflict(self):
        """Test detection of conflicts with existing assertions."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import FactType

        subject_id = uuid4()

        # Existing assertion says birth is 1850
        existing_assertions = {
            str(subject_id): [
                {"fact_type": "birth", "value": "1850-01-01"}
            ]
        }

        adjudicator = FactAdjudicator(
            existing_assertions=existing_assertions,
            strict_citation_check=False,
        )

        # New claim says birth is 1852
        claim = {
            "claim_id": str(uuid4()),
            "claim_value": "1852-03-15",
            "citation_snippet": "",
            "prior_weight": 0.6,
        }

        result = adjudicator.adjudicate_claim(
            claim=claim,
            source_text="",
            subject_id=subject_id,
            fact_type=FactType.BIRTH,
        )

        assert result.conflict_detected is True
        assert result.competing_assertion is not None
        assert result.competing_assertion.proposed_value == "1852-03-15"

    def test_adjudicate_claim_detects_error_patterns(self):
        """Test detection of known error patterns."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import (
            ErrorPatternType,
            FactType,
        )

        adjudicator = FactAdjudicator(strict_citation_check=False)

        claim = {
            "claim_id": str(uuid4()),
            "claim_value": "1900-01-01",  # Suspicious Jan 1 death
            "citation_snippet": "",
            "prior_weight": 0.7,
        }

        result = adjudicator.adjudicate_claim(
            claim=claim,
            source_text="",
            subject_id=uuid4(),
            fact_type=FactType.DEATH,
            subject_context={"assume_living": False},  # Don't trigger living detection
        )

        assert ErrorPatternType.TOMBSTONE_ERROR in result.detected_patterns
        assert result.pattern_penalty == -0.10

    def test_get_pending_conflicts(self):
        """Test retrieving pending conflicts."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import FactType

        subject_id = uuid4()

        existing_assertions = {
            str(subject_id): [{"fact_type": "birth", "value": "1850-01-01"}]
        }

        adjudicator = FactAdjudicator(
            existing_assertions=existing_assertions,
            strict_citation_check=False,
        )

        # Create a conflict
        claim = {
            "claim_id": str(uuid4()),
            "claim_value": "1852-03-15",
            "prior_weight": 0.6,
        }

        adjudicator.adjudicate_claim(
            claim=claim,
            source_text="",
            subject_id=subject_id,
            fact_type=FactType.BIRTH,
        )

        pending = adjudicator.get_pending_conflicts()
        assert len(pending) == 1
        assert pending[0].proposed_value == "1852-03-15"

    def test_resolve_conflicts_without_llm(self):
        """Test conflict resolution returns pending when no LLM configured."""
        from gps_agents.genealogy_crawler.fact_adjudicator import FactAdjudicator
        from gps_agents.genealogy_crawler.models_v2 import FactType, ResolutionStatus

        subject_id = uuid4()

        existing_assertions = {
            str(subject_id): [{"fact_type": "birth", "value": "1850-01-01"}]
        }

        adjudicator = FactAdjudicator(
            existing_assertions=existing_assertions,
            strict_citation_check=False,
        )

        # Create two conflicting claims
        for value in ["1852-03-15", "1851-06-20"]:
            adjudicator.adjudicate_claim(
                claim={"claim_id": str(uuid4()), "claim_value": value, "prior_weight": 0.6},
                source_text="",
                subject_id=subject_id,
                fact_type=FactType.BIRTH,
            )

        result = adjudicator.resolve_conflicts(
            subject_id=subject_id,
            fact_type=FactType.BIRTH,
            subject_name="John Smith",
        )

        assert result.resolution_status == ResolutionStatus.PENDING_REVIEW
        assert result.human_review_required is True
        assert "LLM registry not configured" in result.rationale


class TestConflictAnalysisTiebreakerSchemas:
    """Tests for Conflict Analyst Tie-Breaker schemas."""

    def test_tiebreaker_input_creation(self):
        """Test creating ConflictAnalysisTiebreakerInput."""
        from gps_agents.genealogy_crawler.llm.schemas import (
            ConflictAnalysisTiebreakerInput,
        )

        input_data = ConflictAnalysisTiebreakerInput(
            subject_id=str(uuid4()),
            subject_name="John Smith",
            fact_type="birth",
            competing_assertions=[
                {
                    "id": str(uuid4()),
                    "proposed_value": "1850-01-01",
                    "prior_weight": 0.7,
                },
                {
                    "id": str(uuid4()),
                    "proposed_value": "1852-03-15",
                    "prior_weight": 0.6,
                },
            ],
        )

        assert input_data.subject_name == "John Smith"
        assert input_data.fact_type == "birth"
        assert len(input_data.competing_assertions) == 2

    def test_tiebreaker_output_creation(self):
        """Test creating ConflictAnalysisTiebreakerOutput."""
        from gps_agents.genealogy_crawler.llm.schemas import (
            ConflictAnalysisTiebreakerOutput,
        )

        output = ConflictAnalysisTiebreakerOutput(
            analysis="Based on primary source evidence, the 1850 date is more reliable.",
            current_winning_assertion_index=0,
            current_confidence=0.85,
            resolution_status="resolved",
            preserve_all=True,
        )

        assert output.current_winning_assertion_index == 0
        assert output.current_confidence == 0.85
        assert output.resolution_status == "resolved"
        assert output.preserve_all is True

    def test_error_pattern_hypothesis(self):
        """Test ErrorPatternHypothesis schema."""
        from gps_agents.genealogy_crawler.llm.schemas import ErrorPatternHypothesis

        hypothesis = ErrorPatternHypothesis(
            pattern_type="tombstone_error",
            affected_assertion_index=1,
            explanation="The December 31 date is suspicious for death records.",
            likelihood=0.7,
            suggested_penalty=-0.10,
        )

        assert hypothesis.pattern_type == "tombstone_error"
        assert hypothesis.likelihood == 0.7
        assert hypothesis.affected_assertion_index == 1
        assert hypothesis.suggested_penalty == -0.10

    def test_tiebreaker_query(self):
        """Test TiebreakerQuery schema."""
        from gps_agents.genealogy_crawler.llm.schemas import TiebreakerQuery

        query = TiebreakerQuery(
            query_string="Philadelphia County death records 1850-1855",
            target_source_type="vital records",
            target_tier=1,
            reasoning="Primary source should settle the date conflict",
            expected_resolution="confirm_a",
            priority=0.8,
        )

        assert query.query_string == "Philadelphia County death records 1850-1855"
        assert query.target_tier == 1
        assert query.expected_resolution == "confirm_a"

    def test_negative_evidence_indicator(self):
        """Test NegativeEvidenceIndicator schema."""
        from gps_agents.genealogy_crawler.llm.schemas import NegativeEvidenceIndicator

        indicator = NegativeEvidenceIndicator(
            expected_record="burial_record",
            jurisdiction="Philadelphia County, PA",
            time_range="1850-1855",
            affects_assertion_index=0,
            confidence_reduction=0.05,
            reasoning="No burial record found at expected cemetery",
        )

        assert indicator.expected_record == "burial_record"
        assert indicator.confidence_reduction == 0.05
        assert indicator.affects_assertion_index == 0


# =============================================================================
# Hallucination Firewall Tests
# =============================================================================


class TestHallucinationViolation:
    """Tests for the HallucinationViolation enum."""

    def test_enum_values_follow_naming_convention(self):
        """Test that all enum values follow the hf_XXX pattern."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        for violation in HallucinationViolation:
            assert violation.value.startswith("hf_"), (
                f"Violation {violation.name} value should start with 'hf_'"
            )

    def test_citation_violations_exist(self):
        """Test that citation-related violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_001_CITATION_MISSING
        assert HallucinationViolation.HF_002_CITATION_NOT_IN_SOURCE
        assert HallucinationViolation.HF_003_VALUE_NOT_IN_SOURCE

    def test_confidence_violations_exist(self):
        """Test that confidence-related violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_010_LOW_CONFIDENCE
        assert HallucinationViolation.HF_011_CONFIDENCE_OUT_OF_BOUNDS
        assert HallucinationViolation.HF_012_CONFIDENCE_INFLATION

    def test_fact_classification_violations_exist(self):
        """Test that fact classification violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_020_HYPOTHESIS_MARKED_AS_FACT
        assert HallucinationViolation.HF_021_INFERENCE_WITHOUT_EVIDENCE

    def test_privacy_violations_exist(self):
        """Test that privacy violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_030_PII_UNREDACTED
        assert HallucinationViolation.HF_031_LIVING_PERSON_EXPOSED

    def test_conflict_violations_exist(self):
        """Test that conflict-related violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_040_CONFLICT_UNRESOLVED
        assert HallucinationViolation.HF_041_CONTRADICTS_HIGHER_TIER
        assert HallucinationViolation.HF_042_PROVENANCE_BROKEN

    def test_chronology_violations_exist(self):
        """Test that chronology violation codes exist."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        assert HallucinationViolation.HF_050_CHRONOLOGY_IMPOSSIBLE
        assert HallucinationViolation.HF_051_DATE_BEFORE_BIRTH
        assert HallucinationViolation.HF_052_DATE_AFTER_DEATH

    def test_enum_is_string_based(self):
        """Test that enum values can be used as strings."""
        from gps_agents.genealogy_crawler import HallucinationViolation

        violation = HallucinationViolation.HF_001_CITATION_MISSING
        assert violation.value == "hf_001_citation_missing"
        assert isinstance(violation.value, str)


class TestHallucinationViolationDetail:
    """Tests for the HallucinationViolationDetail dataclass."""

    def test_basic_creation(self):
        """Test creating a violation detail with required fields."""
        from gps_agents.genealogy_crawler import (
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        detail = HallucinationViolationDetail(
            code=HallucinationViolation.HF_001_CITATION_MISSING,
            message="Missing citation for birth date field",
        )

        assert detail.code == HallucinationViolation.HF_001_CITATION_MISSING
        assert detail.message == "Missing citation for birth date field"
        assert detail.field is None
        assert detail.expected is None
        assert detail.actual is None

    def test_full_creation_with_context(self):
        """Test creating a violation detail with all fields."""
        from gps_agents.genealogy_crawler import (
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        detail = HallucinationViolationDetail(
            code=HallucinationViolation.HF_010_LOW_CONFIDENCE,
            message="Confidence 0.5 below threshold 0.7",
            field="birth_date",
            expected=">= 0.7",
            actual="0.5",
        )

        assert detail.code == HallucinationViolation.HF_010_LOW_CONFIDENCE
        assert detail.field == "birth_date"
        assert detail.expected == ">= 0.7"
        assert detail.actual == "0.5"


class TestHallucinationCheckResult:
    """Tests for the HallucinationCheckResult dataclass."""

    def test_passed_result(self):
        """Test a check result that passes."""
        from gps_agents.genealogy_crawler import HallucinationCheckResult

        result = HallucinationCheckResult(passed=True)

        assert result.passed is True
        assert result.violations == []
        assert result.warnings == []

    def test_failed_result_with_violations(self):
        """Test a check result with violations."""
        from gps_agents.genealogy_crawler import (
            HallucinationCheckResult,
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        violations = [
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_001_CITATION_MISSING,
                message="Missing citation",
                field="birth_date",
            ),
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_010_LOW_CONFIDENCE,
                message="Low confidence",
                field="death_date",
            ),
        ]

        result = HallucinationCheckResult(passed=False, violations=violations)

        assert result.passed is False
        assert len(result.violations) == 2

    def test_violation_codes_property(self):
        """Test the violation_codes property returns just the codes."""
        from gps_agents.genealogy_crawler import (
            HallucinationCheckResult,
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        violations = [
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_001_CITATION_MISSING,
                message="Missing citation",
            ),
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_020_HYPOTHESIS_MARKED_AS_FACT,
                message="Hypothesis marked as fact",
            ),
        ]

        result = HallucinationCheckResult(passed=False, violations=violations)
        codes = result.violation_codes

        assert HallucinationViolation.HF_001_CITATION_MISSING in codes
        assert HallucinationViolation.HF_020_HYPOTHESIS_MARKED_AS_FACT in codes

    def test_violation_messages_property(self):
        """Test the violation_messages property returns formatted messages."""
        from gps_agents.genealogy_crawler import (
            HallucinationCheckResult,
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        violations = [
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_001_CITATION_MISSING,
                message="Missing citation for field",
            ),
        ]

        result = HallucinationCheckResult(passed=False, violations=violations)
        messages = result.violation_messages

        assert len(messages) == 1
        assert "[hf_001_citation_missing]" in messages[0]
        assert "Missing citation for field" in messages[0]

    def test_has_violation_method(self):
        """Test the has_violation method."""
        from gps_agents.genealogy_crawler import (
            HallucinationCheckResult,
            HallucinationViolation,
            HallucinationViolationDetail,
        )

        violations = [
            HallucinationViolationDetail(
                code=HallucinationViolation.HF_001_CITATION_MISSING,
                message="Missing citation",
            ),
        ]

        result = HallucinationCheckResult(passed=False, violations=violations)

        assert result.has_violation(HallucinationViolation.HF_001_CITATION_MISSING)
        assert not result.has_violation(HallucinationViolation.HF_010_LOW_CONFIDENCE)

    def test_result_with_warnings(self):
        """Test a check result with warnings."""
        from gps_agents.genealogy_crawler import HallucinationCheckResult

        warnings = [
            "Value 'John' not found verbatim in source",
            "Date format differs from source",
        ]

        result = HallucinationCheckResult(passed=True, warnings=warnings)

        assert result.passed is True
        assert len(result.warnings) == 2


class TestHallucinationFirewall:
    """Tests for the hallucination_firewall function.

    Note: Some violation codes (HF_001, HF_011) are enforced by Pydantic schema
    validators and cannot be triggered at runtime. The hallucination_firewall
    checks for them as defense-in-depth but tests use valid schema inputs.
    """

    def test_valid_output_passes(self):
        """Test that valid output passes the firewall."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.85,
                    citation_snippet="born January 15, 1850",
                    rationale="Date found in original source text",
                )
            ],
            hypotheses=[],
            overall_confidence=0.85,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850 in Philadelphia"

        result = hallucination_firewall(output, source_text)

        assert result.passed is True
        assert len(result.violations) == 0

    def test_citation_not_in_source_fails(self):
        """Test that fabricated citation triggers HF_002."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            HallucinationViolation,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.85,
                    citation_snippet="born February 20, 1850",  # Not in source
                    rationale="Found in document",
                )
            ],
            hypotheses=[],
            overall_confidence=0.85,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850"

        result = hallucination_firewall(output, source_text)

        assert result.passed is False
        assert result.has_violation(HallucinationViolation.HF_002_CITATION_NOT_IN_SOURCE)

    def test_low_confidence_fails(self):
        """Test that low confidence triggers HF_010."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            HallucinationViolation,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.5,  # Below default 0.7 threshold
                    citation_snippet="born January 15, 1850",
                    rationale="Date found but partially illegible",
                )
            ],
            hypotheses=[],
            overall_confidence=0.5,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850"

        result = hallucination_firewall(output, source_text)

        assert result.passed is False
        assert result.has_violation(HallucinationViolation.HF_010_LOW_CONFIDENCE)

    def test_custom_confidence_threshold(self):
        """Test custom min_confidence parameter."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.6,
                    citation_snippet="born January 15, 1850",
                    rationale="Date found in source",
                )
            ],
            hypotheses=[],
            overall_confidence=0.6,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850"

        # Should fail with default 0.7 threshold
        result_default = hallucination_firewall(output, source_text)
        assert result_default.passed is False

        # Should pass with 0.5 threshold
        result_lowered = hallucination_firewall(output, source_text, min_confidence=0.5)
        assert result_lowered.passed is True

    def test_non_strict_mode_collects_violations(self):
        """Test that non-strict mode collects violations but passes."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            HallucinationViolation,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.5,  # Low confidence triggers HF_010
                    citation_snippet="born January 15, 1850",
                    rationale="Date found but uncertain",
                )
            ],
            hypotheses=[],
            overall_confidence=0.5,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850"

        result = hallucination_firewall(output, source_text, strict=False)

        assert result.passed is True  # Passes in non-strict mode
        assert len(result.violations) > 0  # But violations still recorded
        assert result.has_violation(HallucinationViolation.HF_010_LOW_CONFIDENCE)

    def test_multiple_violations_collected(self):
        """Test that multiple violations are collected."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            HallucinationViolation,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.5,  # Low confidence
                    citation_snippet="born January 15, 1850",
                    rationale="Date found but uncertain",
                ),
                VerificationResult(
                    field="death_date",
                    status="Verified",
                    value="1920-03-10",
                    confidence=0.6,  # Also low confidence
                    citation_snippet="departed March 10, 1920",  # Not in source
                    rationale="Death date inferred from obituary",
                ),
            ],
            hypotheses=[],
            overall_confidence=0.5,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith was born January 15, 1850 and died March 10, 1920"

        result = hallucination_firewall(output, source_text)

        assert result.passed is False
        # Should have multiple violations: low confidence on birth, citation not
        # found on death, low confidence on death
        assert len(result.violations) >= 3
        assert result.has_violation(HallucinationViolation.HF_002_CITATION_NOT_IN_SOURCE)
        assert result.has_violation(HallucinationViolation.HF_010_LOW_CONFIDENCE)

    def test_unverified_status_skips_citation_checks(self):
        """Test that unverified results don't require citations."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="NotFound",  # Not verified, no citation needed
                    value=None,
                    confidence=0.8,
                    citation_snippet=None,
                    rationale="Birth date not found in document",
                )
            ],
            hypotheses=[],
            overall_confidence=0.8,
            suggested_revisit_sources=[],
        )
        source_text = "John Smith moved to Philadelphia"

        result = hallucination_firewall(output, source_text)

        assert result.passed is True
        assert len(result.violations) == 0

    def test_fuzzy_citation_matching(self):
        """Test that citation matching is fuzzy (case and whitespace insensitive)."""
        from gps_agents.genealogy_crawler import (
            hallucination_firewall,
            VerifierOutput,
            VerificationResult,
        )

        output = VerifierOutput(
            verification_results=[
                VerificationResult(
                    field="birth_date",
                    status="Verified",
                    value="1850-01-15",
                    confidence=0.85,
                    # Citation with different case/spacing than source
                    citation_snippet="Born  January 15,  1850",
                    rationale="Date found in record",
                )
            ],
            hypotheses=[],
            overall_confidence=0.85,
            suggested_revisit_sources=[],
        )
        # Source has different case and spacing
        source_text = "John Smith was born January 15, 1850"

        result = hallucination_firewall(output, source_text)

        assert result.passed is True  # Fuzzy matching should pass
