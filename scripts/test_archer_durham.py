#!/usr/bin/env python3
"""Test script to research Archer Durham born in Pasadena, California in 1932.

This demonstrates the genealogy crawler's capabilities including:
- Search query generation
- Source tier prioritization
- GPS pillar compliance
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def test_query_generation():
    """Test generating search queries for Archer Durham."""
    from gps_agents.genealogy_crawler import (
        Person,
        generate_person_queries,
    )

    # Create seed person: Archer Durham
    archer = Person(
        canonical_name="Archer Durham",
        given_name="Archer",
        surname="Durham",
        birth_date_earliest=datetime(1932, 1, 1, tzinfo=UTC),
        birth_date_latest=datetime(1932, 12, 31, tzinfo=UTC),
        birth_date_display="1932",
        birth_place="Pasadena, California",
        confidence=0.5,  # Starting confidence
    )

    logger.info("=" * 60)
    logger.info("ARCHER DURHAM - GPS GENEALOGY RESEARCH")
    logger.info("=" * 60)
    logger.info(f"\nSeed Person: {archer.canonical_name}")
    logger.info(f"  Born: {archer.birth_date_display}")
    logger.info(f"  Birth Place: {archer.birth_place}")
    logger.info(f"  Person ID: {archer.id}")

    # Generate search queries
    logger.info("\n" + "-" * 40)
    logger.info("GENERATED SEARCH QUERIES")
    logger.info("-" * 40)

    queries = generate_person_queries(archer)
    logger.info(f"Generated {len(queries)} queries:\n")

    for i, q in enumerate(queries, 1):
        logger.info(f"  {i}. \"{q.query_string}\"")
        logger.info(f"     Priority: {q.priority:.2f} | Source Tiers: {q.source_tiers or ['general']}")

    return archer, queries


def test_search_revision_agent():
    """Test the Search Revision Agent for Archer Durham."""
    from gps_agents.genealogy_crawler import (
        SearchRevisionAgentLLM,
        SearchRevisionInput,
        MissingSourceClass,
    )
    from gps_agents.genealogy_crawler.llm import MockLLMClient

    logger.info("\n" + "=" * 60)
    logger.info("SEARCH REVISION AGENT")
    logger.info("=" * 60)

    # Create mock client
    client = MockLLMClient()
    agent = SearchRevisionAgentLLM(client)

    # Generate phonetic variants
    logger.info("\n1. Phonetic Name Variants:")
    variants = agent.generate_name_variants("Durham", "Archer")
    for v in variants:
        logger.info(f"   - {v.variant} ({v.variant_type}, confidence: {v.confidence:.2f})")

    # Generate Soundex
    soundex = agent.generate_soundex("Durham")
    logger.info(f"\n2. Soundex for 'Durham': {soundex}")

    # Identify regional archives
    logger.info("\n3. Regional Archives for California:")
    archives = agent.identify_regional_archives(
        locations=["Pasadena, California"],
        country_of_origin=None,
    )
    for arch in archives:
        logger.info(f"   - {arch.name} ({arch.archive_type})")
        logger.info(f"     Coverage: {arch.coverage_start_year or '?'} - {arch.coverage_end_year or '?'}")

    # Generate date ranges
    logger.info("\n4. Date Ranges for Birth Year 1932:")
    date_ranges = agent.generate_date_ranges(1932, None, padding_years=2)
    for dr in date_ranges:
        logger.info(f"   - {dr.expanded_start} to {dr.expanded_end} ({dr.reason})")

    # Generate negative searches
    logger.info("\n5. Negative Search Targets:")
    negative = agent.generate_negative_searches(
        subject_name="Archer Durham",
        known_locations=["Pasadena, California"],
        birth_year=1932,
        death_year=None,
    )
    for neg in negative:
        logger.info(f"   - {neg.expected_record_type} in {neg.expected_location}")
        logger.info(f"     Time period: {neg.time_period}")
        logger.info(f"     Significance: {neg.significance}")

    return agent


def test_orchestrator_initialization():
    """Test Orchestrator initialization with Archer Durham."""
    from gps_agents.genealogy_crawler import (
        Person,
        Orchestrator,
        create_llm_registry,
        CrawlerState,
    )
    from gps_agents.genealogy_crawler.llm import MockLLMClient
    import json

    logger.info("\n" + "=" * 60)
    logger.info("ORCHESTRATOR INITIALIZATION")
    logger.info("=" * 60)

    # Create seed person
    archer = Person(
        canonical_name="Archer Durham",
        given_name="Archer",
        surname="Durham",
        birth_date_earliest=datetime(1932, 1, 1, tzinfo=UTC),
        birth_date_latest=datetime(1932, 12, 31, tzinfo=UTC),
        birth_date_display="1932",
        birth_place="Pasadena, California",
    )

    # Create mock LLM client
    mock_client = MockLLMClient(responses={
        "Orchestrator": json.dumps({
            "reasoning": "Starting GPS-compliant research for Archer Durham",
            "next_actions": [
                "Search 1940 US Census for Archer Durham in Pasadena",
                "Search California birth records 1932",
                "Search Pasadena city directories 1932-1950",
            ],
            "query_expansions": [
                {"original": "Archer Durham", "expanded": "Archer L Durham"},
                {"original": "Archer Durham", "expanded": "A. Durham"},
            ],
            "revisit_schedule": [],
            "should_stop": False,
            "stop_reason": None,
        }),
    })

    # Create registry and orchestrator
    registry = create_llm_registry(client=mock_client)
    orchestrator = Orchestrator(llm_registry=registry)

    # Initialize from seed
    state = orchestrator.initialize_from_seed(archer)

    logger.info(f"\nSession ID: {state.session_id}")
    logger.info(f"Seed Person: {archer.canonical_name}")
    logger.info(f"Frontier Queue Size: {len(state.frontier_queue)}")
    logger.info(f"Persons in Graph: {len(state.persons)}")

    logger.info("\nFrontier Queue (top 5):")
    for i, item in enumerate(list(state.frontier_queue)[:5], 1):
        logger.info(f"  {i}. Priority: {item.priority:.2f} | Query: {item.query_string[:50]}...")

    return state


def test_publishing_pipeline():
    """Test publishing pipeline readiness for Archer Durham."""
    from gps_agents.genealogy_crawler.publishing import (
        PublishingManager,
        GPSGradeCard,
        GPSPillarScore,
        GPSPillar,
    )
    from gps_agents.genealogy_crawler.llm import MockLLMClient

    logger.info("\n" + "=" * 60)
    logger.info("PUBLISHING PIPELINE (SIMULATION)")
    logger.info("=" * 60)

    client = MockLLMClient()
    manager = PublishingManager(client)

    # Create a pipeline
    pipeline = manager.create_pipeline("archer-durham-1932")
    pipeline.subject_name = "Archer Durham"

    logger.info(f"\nPipeline ID: {pipeline.pipeline_id}")
    logger.info(f"Status: {pipeline.status.value}")

    # Simulate GPS grading (what would happen after research)
    logger.info("\nSimulated GPS Grade Card:")
    grade_card = GPSGradeCard(
        subject_id="archer-durham-1932",
        pillar_scores=[
            GPSPillarScore(
                pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH,
                score=7.5,
                rationale="Good coverage of census records, need more vital records",
                improvements_needed=["Locate California birth certificate", "Check SSDI"],
            ),
            GPSPillarScore(
                pillar=GPSPillar.COMPLETE_CITATIONS,
                score=8.0,
                rationale="Citations follow Evidence Explained format",
            ),
            GPSPillarScore(
                pillar=GPSPillar.ANALYSIS_AND_CORRELATION,
                score=7.8,
                rationale="Sources correlated, minor gaps in timeline",
            ),
            GPSPillarScore(
                pillar=GPSPillar.CONFLICT_RESOLUTION,
                score=8.5,
                rationale="No major conflicts identified",
            ),
            GPSPillarScore(
                pillar=GPSPillar.WRITTEN_CONCLUSION,
                score=7.0,
                rationale="Conclusion drafted, needs more detail",
                improvements_needed=["Expand proof argument", "Add research notes"],
            ),
        ],
    )

    logger.info(f"  Overall Score: {grade_card.overall_score:.2f}")
    logger.info(f"  Letter Grade: {grade_card.letter_grade}")
    logger.info(f"  Publication Ready: {grade_card.is_publication_ready}")
    logger.info(f"  Allowed Platforms: {[p.value for p in grade_card.allowed_platforms]}")

    # Show lowest pillar
    lowest = grade_card.get_lowest_pillar()
    if lowest:
        logger.info(f"\n  Lowest Pillar: {lowest.pillar.value}")
        logger.info(f"    Score: {lowest.score}")
        logger.info(f"    Improvements: {lowest.improvements_needed}")

    return pipeline, grade_card


def main():
    """Run all tests for Archer Durham."""
    logger.info("\n" + "#" * 60)
    logger.info("GPS GENEALOGY AGENTS - ARCHER DURHAM TEST")
    logger.info("#" * 60)
    logger.info("\nTarget: Archer Durham")
    logger.info("Birth: 1932, Pasadena, California")
    logger.info("#" * 60)

    # Run tests
    archer, queries = test_query_generation()
    agent = test_search_revision_agent()
    state = test_orchestrator_initialization()
    pipeline, grade_card = test_publishing_pipeline()

    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Seed Person ID: {archer.id}")
    logger.info(f"  Queries Generated: {len(queries)}")
    logger.info(f"  Orchestrator Session: {state.session_id}")
    logger.info(f"  Frontier Items: {len(state.frontier_queue)}")
    logger.info(f"  GPS Grade: {grade_card.letter_grade} ({grade_card.overall_score:.2f})")
    logger.info(f"  Publication Platforms: {[p.value for p in grade_card.allowed_platforms]}")
    logger.info("\n" + "=" * 60)
    logger.info("NEXT STEPS FOR LIVE RESEARCH:")
    logger.info("=" * 60)
    logger.info("1. Run: uv run gps-agents crawl person --given Archer --surname Durham \\")
    logger.info("        --birth-year 1932 --birth-place 'Pasadena, California' -v")
    logger.info("2. Or: uv run gps-agents research 'Find Archer Durham born 1932 Pasadena'")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
