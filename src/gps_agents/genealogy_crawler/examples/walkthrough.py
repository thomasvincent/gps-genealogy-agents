"""Example walkthrough of the genealogy crawler.

Demonstrates the complete flow:
1. Initialize with a seed person
2. Generate search queries
3. Mock LLM verification
4. Entity resolution
5. Conflict analysis
6. State persistence

Run with: uv run python -m gps_agents.genealogy_crawler.examples.walkthrough
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from gps_agents.genealogy_crawler import (
    # Models
    Person,
    Event,
    EventType,
    SourceRecord,
    SourceTier,
    EvidenceClaim,
    EvidenceType,
    Assertion,
    AssertionStatus,
    ClueItem,
    HypothesisType,
    CrawlerState,
    # LLM
    MockLLMClient,
    create_llm_registry,
    VerifierInput,
    VerifierOutput,
    VerificationResult,
    Hypothesis,
    hallucination_firewall,
    # Orchestrator
    Orchestrator,
    generate_person_queries,
    # Storage
    CrawlerStorage,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_verifier_response() -> str:
    """Create a mock verifier response JSON."""
    return json.dumps({
        "verification_results": [
            {
                "field": "birth_date",
                "value": "1850-01-15",
                "status": "Verified",
                "confidence": 0.9,
                "citation_snippet": "born January 15, 1850",
                "rationale": "Explicit date found in obituary text"
            },
            {
                "field": "death_date",
                "value": "1920-03-20",
                "status": "Verified",
                "confidence": 0.85,
                "citation_snippet": "died March 20, 1920",
                "rationale": "Date mentioned in death notice"
            },
            {
                "field": "birth_place",
                "value": "Boston, Massachusetts",
                "status": "Verified",
                "confidence": 0.8,
                "citation_snippet": "native of Boston, Massachusetts",
                "rationale": "Place explicitly stated"
            }
        ],
        "hypotheses": [
            {
                "type": "parental_discovery",
                "text": "John Smith Jr. implies father named John Smith Sr.",
                "evidence_hint": "Jr. suffix in name",
                "priority": 0.7,
                "suggested_queries": ["John Smith Sr. Boston 1820"],
                "is_fact": False
            }
        ],
        "hallucination_flags": []
    })


def example_verification_flow():
    """Demonstrate the LLM verification flow with hallucination firewall."""
    logger.info("=" * 60)
    logger.info("VERIFICATION FLOW EXAMPLE")
    logger.info("=" * 60)

    # Simulate source text
    source_text = """
    OBITUARY - John Smith Jr.

    John Smith Jr., born January 15, 1850, a native of Boston, Massachusetts,
    passed away on March 20, 1920. He was a respected merchant and community
    leader for over 40 years. He is survived by his wife Mary and three children.

    Funeral services will be held at First Baptist Church on March 23.
    """

    # Create verifier input
    verifier_input = VerifierInput(
        url="https://newspapers.example.com/obituary/12345",
        raw_text=source_text,
        extracted_fields={
            "name": "John Smith Jr.",
            "birth_date": "1850-01-15",
            "death_date": "1920-03-20",
            "birth_place": "Boston, Massachusetts",
        },
        existing_citations=[],
    )

    # Create mock LLM client with predefined response
    # The key must match something in the system prompt
    mock_client = MockLLMClient(responses={
        "Verification Agent": create_mock_verifier_response(),
    })

    # Create LLM registry with mock client
    registry = create_llm_registry(client=mock_client, strict_verification=True)

    # Call verifier
    logger.info("\n1. Calling LLM Verifier...")
    output, firewall_result = registry.verifier.verify(verifier_input)

    # Display results
    logger.info("\n2. Verification Results:")
    for result in output.verification_results:
        logger.info(f"   - {result.field}: {result.value}")
        logger.info(f"     Status: {result.status}, Confidence: {result.confidence}")
        logger.info(f"     Citation: \"{result.citation_snippet}\"")

    logger.info("\n3. Generated Hypotheses:")
    for hypo in output.hypotheses:
        logger.info(f"   - [{hypo.type}] {hypo.text}")
        logger.info(f"     is_fact: {hypo.is_fact} (must be False)")
        logger.info(f"     Suggested queries: {hypo.suggested_queries}")

    # Run hallucination firewall
    logger.info("\n4. Hallucination Firewall Check:")
    logger.info(f"   Passed: {firewall_result.passed}")
    if firewall_result.violations:
        logger.info(f"   Violations: {firewall_result.violations}")
    if firewall_result.warnings:
        logger.info(f"   Warnings: {firewall_result.warnings}")

    return output


def example_orchestrator_flow():
    """Demonstrate the orchestrator flow."""
    logger.info("\n" + "=" * 60)
    logger.info("ORCHESTRATOR FLOW EXAMPLE")
    logger.info("=" * 60)

    # Create seed person
    seed_person = Person(
        canonical_name="John Smith Jr.",
        given_name="John",
        surname="Smith",
        birth_date_earliest=datetime(1850, 1, 15, tzinfo=UTC),
        birth_date_display="January 15, 1850",
        death_date_earliest=datetime(1920, 3, 20, tzinfo=UTC),
        death_date_display="March 20, 1920",
        birth_place="Boston, Massachusetts",
        confidence=0.5,
    )

    logger.info(f"\n1. Created seed person: {seed_person.canonical_name}")
    logger.info(f"   ID: {seed_person.id}")
    logger.info(f"   Birth: {seed_person.birth_date_display}")
    logger.info(f"   Death: {seed_person.death_date_display}")

    # Generate queries
    logger.info("\n2. Generating search queries...")
    queries = generate_person_queries(seed_person)
    logger.info(f"   Generated {len(queries)} queries:")
    for q in queries[:5]:
        logger.info(f"   - \"{q.query_string}\" (priority: {q.priority})")

    # Create orchestrator with mock LLM
    # Key must match system prompt content
    mock_client = MockLLMClient(responses={
        "Orchestrator": json.dumps({
            "reasoning": "Initial search strategy",
            "next_actions": [],
            "query_expansions": [],
            "revisit_schedule": [],
            "should_stop": False,
            "stop_reason": None,
        }),
    })
    registry = create_llm_registry(client=mock_client)
    orchestrator = Orchestrator(llm_registry=registry)

    # Initialize state
    logger.info("\n3. Initializing crawler state...")
    state = orchestrator.initialize_from_seed(seed_person)
    logger.info(f"   Session ID: {state.session_id}")
    logger.info(f"   Frontier queue size: {len(state.frontier_queue)}")
    logger.info(f"   Persons in graph: {len(state.persons)}")

    # Run a few steps
    logger.info("\n4. Running crawler steps...")
    for i in range(3):
        continued = orchestrator.step(state)
        logger.info(f"   Step {i+1}: continued={continued}, iterations={state.iteration_count}")
        if not continued:
            break

    return state


def example_storage_flow():
    """Demonstrate storage persistence."""
    logger.info("\n" + "=" * 60)
    logger.info("STORAGE FLOW EXAMPLE")
    logger.info("=" * 60)

    # Create in-memory storage
    storage = CrawlerStorage(":memory:")
    logger.info("\n1. Created in-memory storage")

    # Create some test data
    person1 = Person(
        canonical_name="John Smith Sr.",
        given_name="John",
        surname="Smith",
        birth_date_display="c. 1820",
        death_date_display="1890",
    )

    person2 = Person(
        canonical_name="John Smith Jr.",
        given_name="John",
        surname="Smith",
        birth_date_display="1850",
        death_date_display="1920",
    )

    source = SourceRecord(
        url="https://newspapers.example.com/obituary/12345",
        source_name="Example Newspapers Archive",
        source_tier=SourceTier.TIER_0,
        raw_text="Obituary text...",
    )
    source.compute_content_hash(source.raw_text or "")

    # Save data
    logger.info("\n2. Saving data...")
    storage.save_person(person1)
    storage.save_person(person2)
    storage.save_source_record(source)
    logger.info(f"   Saved person: {person1.canonical_name}")
    logger.info(f"   Saved person: {person2.canonical_name}")
    logger.info(f"   Saved source: {source.url}")

    # Load data
    logger.info("\n3. Loading data...")
    loaded_person = storage.get_person(person1.id)
    logger.info(f"   Loaded: {loaded_person.canonical_name}")

    all_persons = storage.list_persons()
    logger.info(f"   Total persons: {len(all_persons)}")

    # Save and load full state
    logger.info("\n4. Saving full crawler state...")
    state = CrawlerState()
    state.add_person(person1)
    state.add_person(person2)
    state.seed_person_id = person2.id
    state.iteration_count = 5
    state.budget_used = 100.0

    storage.save_state(state)
    logger.info(f"   Saved state: {state.session_id}")

    loaded_state = storage.load_state(state.session_id)
    logger.info(f"   Loaded state with {len(loaded_state.persons)} persons")
    logger.info(f"   Iteration count: {loaded_state.iteration_count}")
    logger.info(f"   Budget used: {loaded_state.budget_used}")

    storage.close()
    return loaded_state


def example_clue_generation():
    """Demonstrate clue/hypothesis generation."""
    logger.info("\n" + "=" * 60)
    logger.info("CLUE GENERATION EXAMPLE")
    logger.info("=" * 60)

    # Create a clue from LLM hypothesis
    clue = ClueItem(
        hypothesis_type=HypothesisType.PARENTAL_DISCOVERY,
        hypothesis_text="John Smith Jr. implies father named John Smith Sr.",
        related_person_id=uuid4(),  # Would be the junior's UUID
        suggested_queries=[
            "John Smith Sr. Boston 1820",
            "John Smith father Boston 1850",
        ],
        evidence_hint="Jr. suffix in name",
        triggering_snippet="John Smith Jr., born January 15, 1850",
        priority=0.7,
        is_fact=False,  # CRITICAL: hypotheses are never facts
    )

    logger.info("\n1. Created hypothesis clue:")
    logger.info(f"   Type: {clue.hypothesis_type.value}")
    logger.info(f"   Text: {clue.hypothesis_text}")
    logger.info(f"   is_fact: {clue.is_fact} (enforced False)")
    logger.info(f"   Priority: {clue.priority}")
    logger.info(f"   Suggested queries: {clue.suggested_queries}")

    # Show how this would be added to state
    state = CrawlerState()
    state.add_clue(clue)
    logger.info(f"\n2. Added to clue queue. Queue size: {len(state.clue_queue)}")

    # Pop and process
    popped = state.pop_clue()
    logger.info(f"3. Popped clue: {popped.hypothesis_type.value}")

    return clue


def main():
    """Run all example flows."""
    logger.info("GENEALOGY CRAWLER WALKTHROUGH")
    logger.info("=" * 60)
    logger.info("This demonstrates the complete crawler flow.")
    logger.info("=" * 60)

    # Run examples
    example_verification_flow()
    example_orchestrator_flow()
    example_storage_flow()
    example_clue_generation()

    logger.info("\n" + "=" * 60)
    logger.info("WALKTHROUGH COMPLETE")
    logger.info("=" * 60)
    logger.info("\nKey concepts demonstrated:")
    logger.info("1. LLM Verification with hallucination firewall")
    logger.info("2. Orchestrator initialization and stepping")
    logger.info("3. SQLite storage for state persistence")
    logger.info("4. Clue/hypothesis generation with is_fact=False invariant")
    logger.info("\nAll hypotheses remain labeled as hypotheses (is_fact=False)")
    logger.info("until independently verified through the evidence chain.")


if __name__ == "__main__":
    main()
