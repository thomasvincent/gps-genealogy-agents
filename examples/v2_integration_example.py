#!/usr/bin/env python3
"""Comprehensive v2 Integration Example.

Demonstrates the full Genealogical Process Crawler v2 system:
1. Source Adapter Framework - pluggable source crawling
2. RocksDB Frontier Queue - priority-based crawl management
3. Graph Storage - relationship tracking with path finding
4. Temporal Workflows - durable long-running research sessions
5. Bayesian Conflict Resolution - evidence-weighted fact merging
6. Hallucination Firewall - LLM output validation

Run with: uv run python examples/v2_integration_example.py
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# =============================================================================
# Import v2 Components
# =============================================================================

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gps_agents.genealogy_crawler import (
    # Core Models
    Person,
    Assertion,
    EvidenceClaim,
    SourceRecord,
    SourceTier,
    EvidenceType,
    # LLM Wrappers
    MockLLMClient,
    LLMRegistry,
    PlannerLLM,
    VerifierLLM,
    hallucination_firewall,
    # v2 - Source Adapters
    AdapterConfig,
    AdapterRegistry,
    SearchQuery,
    FetchResult,
    # v2 - Frontier Queue
    FrontierQueue,
    CrawlItem,
    CrawlPriority,
    # v2 - Graph Storage
    RocksDBGraphStore,
    Node,
    Edge,
    NodeType,
    EdgeType,
)

# v2 Models for Bayesian resolution
from src.gps_agents.genealogy_crawler.models_v2 import (
    BayesianResolution,
    ConflictingEvidence,
    EvidenceClass,
    EVIDENCE_PRIOR_WEIGHTS,
)


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


# =============================================================================
# 1. Source Adapter Framework Demo
# =============================================================================

def demo_source_adapters():
    """Demonstrate the Source Adapter Framework."""
    print_section("1. Source Adapter Framework")

    # Import the Find A Grave adapter
    from src.gps_agents.genealogy_crawler.adapters.find_a_grave import (
        FindAGraveAdapter,
        create_find_a_grave_config,
    )

    # Create adapter registry
    registry = AdapterRegistry()

    # Create and register adapter
    adapter = FindAGraveAdapter()
    registry.register(adapter)

    print(f"Registered adapter: {adapter.adapter_id}")
    print(f"  - Tier: {adapter.tier.name}")
    print(f"  - Domain: {adapter.domain}")
    print(f"  - Evidence Class: {adapter.evidence_class.value}")
    print(f"  - Prior Weight: {adapter.prior_weight}")

    # Show compliance config
    config = adapter.config
    print(f"\nCompliance Settings:")
    print(f"  - Rate limit: {config.compliance.rate_limit.requests_per_second} req/sec")
    print(f"  - Burst: {config.compliance.rate_limit.burst}")
    print(f"  - Respects robots.txt: {config.compliance.robots_txt}")
    print(f"  - User-Agent: {config.compliance.user_agent}")

    # Show extraction rules
    print(f"\nExtraction Rules for 'person':")
    if "person" in config.extraction:
        for field, rule in config.extraction["person"].rules.items():
            print(f"  - {field}: confidence={rule.confidence}, required={rule.required}")

    # List all registered adapters
    print(f"\nAll registered adapters: {registry.list_adapters()}")

    return registry


# =============================================================================
# 2. Frontier Queue Demo
# =============================================================================

def demo_frontier_queue():
    """Demonstrate the RocksDB-backed Frontier Queue."""
    print_section("2. RocksDB Frontier Queue")

    with tempfile.TemporaryDirectory() as tmpdir:
        queue = FrontierQueue(tmpdir)

        # Add items with different priorities
        subject_id = uuid4()

        items = [
            CrawlItem(
                url="http://findagrave.com/memorial/12345",
                adapter_id="find_a_grave",
                priority=CrawlPriority.NORMAL,
                subject_id=subject_id,
                hypothesis="Initial search result for Thomas Vincent",
            ),
            CrawlItem(
                url="http://findagrave.com/memorial/67890",
                adapter_id="find_a_grave",
                priority=CrawlPriority.HIGH,
                subject_id=subject_id,
                hypothesis="Father's memorial - higher priority",
            ),
            CrawlItem(
                url="http://newspapers.com/obituary/abc123",
                adapter_id="newspapers",
                priority=CrawlPriority.LOW,
                subject_id=subject_id,
                hypothesis="Speculative obituary match",
            ),
        ]

        print("Adding items to frontier queue:")
        for item in items:
            added = queue.push(item)
            print(f"  - {item.url} (priority={item.priority.name}) -> added={added}")

        # Test deduplication
        duplicate = CrawlItem(
            url="http://findagrave.com/memorial/12345",
            adapter_id="find_a_grave",
        )
        added = queue.push(duplicate)
        print(f"\nDuplicate URL added: {added} (should be False)")

        # Pop items in priority order
        print(f"\nPopping items (should be HIGH first):")
        while queue:
            item = queue.pop()
            if item:
                print(f"  - {item.url} (priority={item.priority.name})")
                queue.complete(item.item_id)

        # Show stats
        stats = queue.stats()
        print(f"\nQueue Stats:")
        print(f"  - Completed: {stats.completed_items}")
        print(f"  - Unique URLs seen: {stats.unique_urls}")


# =============================================================================
# 3. Graph Storage Demo
# =============================================================================

def demo_graph_storage():
    """Demonstrate the Graph Storage for relationships."""
    print_section("3. Graph Storage (Relationships)")

    with tempfile.TemporaryDirectory() as tmpdir:
        graph = RocksDBGraphStore(tmpdir)

        # Create person nodes
        thomas = Node(
            node_type=NodeType.PERSON,
            properties={
                "name": "Thomas Edward Vincent",
                "birth_year": 1977,
                "birth_place": "California, USA",
            }
        )

        arthur = Node(
            node_type=NodeType.PERSON,
            properties={
                "name": "Arthur James Vincent",
                "birth_year": 1945,
                "death_year": 2010,
            }
        )

        mary = Node(
            node_type=NodeType.PERSON,
            properties={
                "name": "Mary Elizabeth Vincent",
                "birth_year": 1948,
            }
        )

        grandpa = Node(
            node_type=NodeType.PERSON,
            properties={
                "name": "James Vincent",
                "birth_year": 1920,
                "death_year": 1995,
            }
        )

        # Add nodes
        graph.add_node(thomas)
        graph.add_node(arthur)
        graph.add_node(mary)
        graph.add_node(grandpa)

        print("Created person nodes:")
        for node in [thomas, arthur, mary, grandpa]:
            print(f"  - {node.properties['name']} (born {node.properties.get('birth_year', '?')})")

        # Create relationships
        edges = [
            Edge(
                edge_type=EdgeType.PARENT_OF,
                source_id=arthur.node_id,
                target_id=thomas.node_id,
                confidence=0.95,
                properties={"relationship": "father"},
            ),
            Edge(
                edge_type=EdgeType.PARENT_OF,
                source_id=mary.node_id,
                target_id=thomas.node_id,
                confidence=0.95,
                properties={"relationship": "mother"},
            ),
            Edge(
                edge_type=EdgeType.SPOUSE_OF,
                source_id=arthur.node_id,
                target_id=mary.node_id,
                confidence=0.90,
            ),
            Edge(
                edge_type=EdgeType.PARENT_OF,
                source_id=grandpa.node_id,
                target_id=arthur.node_id,
                confidence=0.85,
                properties={"relationship": "father"},
            ),
        ]

        for edge in edges:
            graph.add_edge(edge)

        print(f"\nCreated {len(edges)} relationships")

        # Query: Who are Thomas's parents?
        print(f"\nThomas's parents (incoming PARENT_OF edges):")
        parents = graph.get_neighbors(
            thomas.node_id,
            edge_types=[EdgeType.PARENT_OF],
            direction="incoming",
        )
        for edge, parent in parents:
            print(f"  - {parent.properties['name']} ({edge.properties.get('relationship', 'parent')}, confidence={edge.confidence})")

        # Find path from grandpa to Thomas
        print(f"\nPath from James (grandpa) to Thomas:")
        path = graph.find_path(grandpa.node_id, thomas.node_id, max_depth=3)
        if path:
            print(f"  Path length: {path.length} hops")
            for node in path.nodes:
                print(f"    -> {node.properties['name']}")

        graph.close()


# =============================================================================
# 4. Bayesian Conflict Resolution Demo
# =============================================================================

def demo_bayesian_resolution():
    """Demonstrate Bayesian conflict resolution."""
    print_section("4. Bayesian Conflict Resolution")

    subject_id = uuid4()

    # Conflicting evidence about birth year
    print("Evidence about Thomas's birth year from different sources:\n")

    evidence = [
        ConflictingEvidence(
            claim_id=uuid4(),
            value="1977",
            prior_weight=EVIDENCE_PRIOR_WEIGHTS[EvidenceClass.PRIMARY_OFFICIAL],
            source_description="Birth Certificate (Primary Official)",
            citation_snippet="Birth Certificate #12345, State of California",
        ),
        ConflictingEvidence(
            claim_id=uuid4(),
            value="1977",
            prior_weight=EVIDENCE_PRIOR_WEIGHTS[EvidenceClass.PRIMARY_GOVERNMENT],
            source_description="Census Record (Primary Government)",
            citation_snippet="1980 Census: Thomas Vincent, age 3",
        ),
        ConflictingEvidence(
            claim_id=uuid4(),
            value="1978",  # Conflicting!
            prior_weight=EVIDENCE_PRIOR_WEIGHTS[EvidenceClass.SECONDARY_MEMORIAL],
            source_description="Find A Grave (Secondary Memorial)",
            citation_snippet="Find A Grave memorial #67890",
        ),
        ConflictingEvidence(
            claim_id=uuid4(),
            value="1977",
            prior_weight=EVIDENCE_PRIOR_WEIGHTS[EvidenceClass.AUTHORED_UNVERIFIED],
            source_description="User Family Tree (Unverified)",
            citation_snippet="Smith Family Tree on Ancestry.com",
        ),
    ]

    for e in evidence:
        print(f"  Source: {e.source_description}")
        print(f"    Value: {e.value}")
        print(f"    Prior Weight: {e.prior_weight}")
        print(f"    Citation: {e.citation_snippet}\n")

    # Resolve using Bayesian weighting
    resolution = BayesianResolution.resolve(
        field_name="birth_year",
        subject_id=subject_id,
        evidence=evidence,
    )

    print("Bayesian Resolution Result:")
    print(f"  Resolved Value: {resolution.resolved_value}")
    print(f"  Confidence: {resolution.posterior_confidence:.2%}")
    print(f"  Resolution Method: {resolution.method}")

    # Check for conflicting values
    unique_values = set(e.value for e in resolution.conflicting_evidence)
    has_conflict = len(unique_values) > 1

    print(f"  Has Conflict: {has_conflict}")

    if has_conflict:
        print(f"\nAll Evidence (preserved for audit):")
        for e in resolution.conflicting_evidence:
            is_consensus = e.value == resolution.resolved_value
            marker = "✓" if is_consensus else "✗"
            print(f"  {marker} Value '{e.value}' from {e.source_description}")
            print(f"      Weight: {e.prior_weight:.2f}, Citation: {e.citation_snippet}")

    if resolution.suggested_actions:
        print(f"\nSuggested Next Actions:")
        for action in resolution.suggested_actions:
            print(f"  - {action}")


# =============================================================================
# 5. Hallucination Firewall Demo
# =============================================================================

def demo_hallucination_firewall():
    """Demonstrate the hallucination firewall."""
    print_section("5. Hallucination Firewall")

    # Import required schemas
    from src.gps_agents.genealogy_crawler.llm.schemas import (
        VerifierOutput,
        VerificationResult,
    )

    # Source text (what we actually crawled)
    source_text = """
    Thomas Edward Vincent (February 15, 1977 - )
    Born in Sacramento, California to Arthur James Vincent and Mary Elizabeth Vincent.
    Thomas graduated from UC Davis in 1999 with a degree in Computer Science.
    """

    print("Source Text (crawled content):")
    print(f"  {source_text.strip()}")

    # Test 1: Valid extraction (citation found in source)
    print("\n--- Test 1: Valid Extraction ---")
    valid_output = VerifierOutput(
        verification_results=[
            VerificationResult(
                field="birth_date",
                value="February 15, 1977",
                status="Verified",
                confidence=0.95,
                citation_snippet="February 15, 1977",
                rationale="Birth date found in header of page",
            ),
        ],
        hypotheses=[],
        hallucination_flags=[],
    )

    result1 = hallucination_firewall(valid_output, source_text)
    print(f"Field: birth_date")
    print(f"Citation: 'February 15, 1977'")
    print(f"Result: PASSED={result1.passed}")

    # Test 2: Hallucinated fact (citation NOT in source)
    print("\n--- Test 2: Hallucinated Fact ---")
    hallucinated_output = VerifierOutput(
        verification_results=[
            VerificationResult(
                field="death_date",
                value="March 20, 2020",
                status="Verified",
                confidence=0.90,
                citation_snippet="died on March 20, 2020",  # NOT in source!
                rationale="Death date extracted from obituary",
            ),
        ],
        hypotheses=[],
        hallucination_flags=[],
    )

    result2 = hallucination_firewall(hallucinated_output, source_text)
    print(f"Field: death_date")
    print(f"Citation: 'died on March 20, 2020'")
    print(f"Result: PASSED={result2.passed}")
    if not result2.passed:
        print(f"  -> BLOCKED: Hallucination detected!")
        for violation in result2.violations:
            print(f"     Violation: {violation}")

    # Test 3: Valid extraction with fuzzy match
    print("\n--- Test 3: Father's Name (Exact Match) ---")
    father_output = VerifierOutput(
        verification_results=[
            VerificationResult(
                field="father_name",
                value="Arthur James Vincent",
                status="Verified",
                confidence=0.90,
                citation_snippet="Arthur James Vincent",  # Found in source
                rationale="Father's name found in birth record text",
            ),
        ],
        hypotheses=[],
        hallucination_flags=[],
    )

    result3 = hallucination_firewall(father_output, source_text)
    print(f"Field: father_name")
    print(f"Citation: 'Arthur James Vincent'")
    print(f"Result: PASSED={result3.passed}")


# =============================================================================
# 6. Full Pipeline Demo (Async)
# =============================================================================

async def demo_full_pipeline():
    """Demonstrate a full research pipeline iteration."""
    print_section("6. Full Research Pipeline")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize components
        frontier = FrontierQueue(Path(tmpdir) / "frontier")
        graph = RocksDBGraphStore(Path(tmpdir) / "graph")

        # Create seed person
        seed_person = Node(
            node_type=NodeType.PERSON,
            properties={
                "name": "Thomas Vincent",
                "birth_year": 1977,
                "status": "seed",
            }
        )
        graph.add_node(seed_person)
        print(f"1. Created seed person: {seed_person.properties['name']}")

        # Generate initial search queries (simulating LLM planner output)
        initial_queries = [
            CrawlItem(
                url=None,
                query={
                    "query_string": "Thomas Vincent 1977",
                    "given_name": "Thomas",
                    "surname": "Vincent",
                    "birth_year": 1977,
                },
                adapter_id="find_a_grave",
                priority=CrawlPriority.HIGH,
                subject_id=seed_person.node_id,
                hypothesis="Initial search for seed person",
            ),
            CrawlItem(
                url=None,
                query={
                    "query_string": "Thomas E Vincent California",
                    "given_name": "Thomas",
                    "surname": "Vincent",
                    "location": "California",
                },
                adapter_id="find_a_grave",
                priority=CrawlPriority.NORMAL,
                subject_id=seed_person.node_id,
                hypothesis="Search with middle initial and location",
            ),
        ]

        print(f"\n2. Generated {len(initial_queries)} initial queries:")
        for item in initial_queries:
            frontier.push(item)
            print(f"   - {item.query.get('query_string')} (priority={item.priority.name})")

        # Simulate crawl loop iteration
        print(f"\n3. Processing frontier queue:")
        iteration = 0

        while frontier and iteration < 3:
            iteration += 1
            item = frontier.pop()
            if not item:
                break

            print(f"\n   Iteration {iteration}: Processing '{item.query.get('query_string', item.url)}'")

            # Simulate finding results
            if iteration == 1:
                # Found Thomas's memorial, learned about father
                print("   -> Found memorial, discovered father: Arthur Vincent")

                # Add father as new node
                father = Node(
                    node_type=NodeType.PERSON,
                    properties={
                        "name": "Arthur Vincent",
                        "status": "discovered",
                    }
                )
                graph.add_node(father)

                # Add relationship
                parent_edge = Edge(
                    edge_type=EdgeType.PARENT_OF,
                    source_id=father.node_id,
                    target_id=seed_person.node_id,
                    confidence=0.85,
                )
                graph.add_edge(parent_edge)

                # Generate new queries based on discovery (REVISIT pattern)
                revisit_query = CrawlItem(
                    query={
                        "query_string": "Arthur Vincent",
                        "given_name": "Arthur",
                        "surname": "Vincent",
                    },
                    adapter_id="find_a_grave",
                    priority=CrawlPriority.HIGH,
                    subject_id=father.node_id,
                    parent_item_id=item.item_id,
                    hypothesis="Search for newly discovered father",
                )
                frontier.push(revisit_query)
                print("   -> Added revisit query for father")

            frontier.complete(item.item_id)

        # Show final state
        print(f"\n4. Final State:")
        stats = frontier.stats()
        print(f"   - Frontier completed: {stats.completed_items} items")
        print(f"   - Unique URLs seen: {stats.unique_urls}")

        # Show discovered relationships
        print(f"\n   Relationships discovered:")
        neighbors = graph.get_neighbors(seed_person.node_id, direction="incoming")
        for edge, node in neighbors:
            print(f"   - {node.properties['name']} -> {edge.edge_type.name} -> Thomas")

        frontier.close()
        graph.close()


# =============================================================================
# Main
# =============================================================================

def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("  GENEALOGICAL PROCESS CRAWLER v2 - INTEGRATION DEMO")
    print("="*60)

    # Run synchronous demos
    demo_source_adapters()
    demo_frontier_queue()
    demo_graph_storage()
    demo_bayesian_resolution()
    demo_hallucination_firewall()

    # Run async demo
    asyncio.run(demo_full_pipeline())

    print_section("Demo Complete!")
    print("All v2 components demonstrated successfully:")
    print("  ✓ Source Adapter Framework")
    print("  ✓ RocksDB Frontier Queue with Priority")
    print("  ✓ Graph Storage with Path Finding")
    print("  ✓ Bayesian Conflict Resolution")
    print("  ✓ Hallucination Firewall")
    print("  ✓ Full Pipeline Integration")
    print()


if __name__ == "__main__":
    main()
