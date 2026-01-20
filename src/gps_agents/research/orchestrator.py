"""Research orchestrator for memory-aware genealogy searches.

Connects the MemoryPlugin to the SearchRouter to:
1. Load existing facts before searching
2. Enrich queries with known information
3. Extract new facts from results
4. Iteratively refine searches with discoveries
5. Store new facts back to memory
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.research.evaluator import (
    MatchConfidence,
    MatchScore,
    PersonProfile,
    RelevanceEvaluator,
    build_profile_from_facts,
)

# Optional LLM evaluator import
try:
    from gps_agents.research.llm_evaluator import LLMRelevanceEvaluator
    LLM_EVALUATOR_AVAILABLE = True
except ImportError:
    LLM_EVALUATOR_AVAILABLE = False
    LLMRelevanceEvaluator = None  # type: ignore[misc, assignment]
from gps_agents.sk.plugins.memory import MemoryPlugin
from gps_agents.sources.router import (
    Region,
    RouterConfig,
    SearchRouter,
    UnifiedSearchResult,
)

if TYPE_CHECKING:
    from gps_agents.sources.base import GenealogySource

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFact:
    """A fact extracted from a search result."""

    statement: str
    fact_type: str  # name, birth, death, marriage, residence, relationship
    confidence: float
    source_url: str | None = None
    source_name: str = ""
    raw_value: str = ""  # The actual extracted value (e.g., "1844", "Tennessee")


@dataclass
class ResearchSession:
    """Tracks state across an iterative research session."""

    subject_name: str
    known_facts: list[dict] = field(default_factory=list)
    discovered_facts: list[ExtractedFact] = field(default_factory=list)
    search_iterations: int = 0
    sources_queried: set[str] = field(default_factory=set)
    results_by_iteration: list[UnifiedSearchResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Evaluation tracking
    evaluated_records: list[tuple[RawRecord, MatchScore]] = field(default_factory=list)
    filtered_out_records: list[tuple[RawRecord, MatchScore]] = field(default_factory=list)
    profile: PersonProfile | None = None


class OrchestratorConfig(BaseModel):
    """Configuration for the research orchestrator."""

    max_iterations: int = Field(default=3, description="Max search refinement iterations")
    min_confidence_for_refinement: float = Field(
        default=0.7, description="Min confidence to use a fact for query refinement"
    )
    store_discoveries: bool = Field(default=True, description="Store new facts to memory")
    parallel_extraction: bool = Field(default=True, description="Extract facts in parallel")
    year_tolerance: int = Field(default=5, description="Year range tolerance for matching")
    min_match_confidence: MatchConfidence = Field(
        default=MatchConfidence.POSSIBLE,
        description="Minimum confidence to consider a record relevant",
    )
    evaluate_results: bool = Field(
        default=True, description="Filter results through relevance evaluator"
    )
    use_llm_evaluator: bool = Field(
        default=False,
        description="Use LLM-enhanced evaluator for ambiguous cases (requires ANTHROPIC_API_KEY)",
    )
    llm_cache_dir: str | None = Field(
        default=None,
        description="Directory for LLM response caching (GPTCache)",
    )


class ResearchOrchestrator:
    """Orchestrates memory-aware genealogy research.

    Connects the semantic memory system to the search router for:
    - Pre-search fact loading
    - Query enrichment with known facts
    - Post-search fact extraction
    - Iterative search refinement
    - Discovery persistence
    """

    # Patterns for extracting facts from text
    YEAR_PATTERN = re.compile(r"\b(1[789]\d{2}|20[0-2]\d)\b")
    DATE_PATTERN = re.compile(
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{1,2},? \d{4}|\d{4}[-/]\d{2}[-/]\d{2})"
    )
    STATE_ABBREV_PATTERN = re.compile(r"\b([A-Z]{2})\b")
    LOCATION_KEYWORDS = ["county", "city", "town", "township", "parish", "state"]

    # US state abbreviations to full names
    US_STATES = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
        "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
        "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
        "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
        "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
        "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
        "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
        "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming",
    }

    def __init__(
        self,
        router: SearchRouter,
        memory: MemoryPlugin | None = None,
        config: OrchestratorConfig | None = None,
        research_dir: Path | None = None,
    ) -> None:
        """Initialize the research orchestrator.

        Args:
            router: Search router with registered sources
            memory: Optional semantic memory plugin
            config: Orchestrator configuration
            research_dir: Directory for file-based research storage
        """
        self.router = router
        self.memory = memory
        self.config = config or OrchestratorConfig()
        self.research_dir = research_dir or Path("research")
        self._current_session: ResearchSession | None = None

    async def research(
        self,
        surname: str,
        given_name: str | None = None,
        region: Region | None = None,
        initial_facts: list[dict] | None = None,
    ) -> ResearchSession:
        """Conduct a memory-aware research session.

        This is the main entry point. It will:
        1. Load any existing facts about this person
        2. Build an enriched search query
        3. Search across sources
        4. Extract new facts from results
        5. Iteratively refine if new facts narrow the search
        6. Store discoveries

        Args:
            surname: Subject's surname
            given_name: Subject's given name (optional)
            region: Geographic region hint
            initial_facts: Any facts already known

        Returns:
            ResearchSession with all results and discoveries
        """
        subject_name = f"{given_name} {surname}".strip() if given_name else surname

        # Start session
        session = ResearchSession(subject_name=subject_name)
        self._current_session = session

        logger.info("Starting research session for: %s", subject_name)

        # 1. Load existing facts from memory
        known_facts = await self._load_known_facts(surname, given_name)
        if initial_facts:
            known_facts.extend(initial_facts)
        session.known_facts = known_facts

        logger.info("Loaded %d known facts", len(known_facts))

        # 2. Build profile and evaluator from known facts
        profile = build_profile_from_facts(surname, given_name, known_facts)
        session.profile = profile

        # Choose evaluator: LLM-enhanced or rule-based
        evaluator = None
        if self.config.evaluate_results:
            if (self.config.use_llm_evaluator and
                LLM_EVALUATOR_AVAILABLE and
                LLMRelevanceEvaluator is not None):
                try:
                    evaluator = LLMRelevanceEvaluator(
                        profile=profile,
                        use_llm=True,
                        use_cache=True,
                        cache_dir=self.config.llm_cache_dir,
                    )
                    logger.info("Using LLM-enhanced evaluator")
                except Exception as e:
                    logger.warning("Failed to create LLM evaluator, falling back to rule-based: %s", e)
                    evaluator = RelevanceEvaluator(profile)
            else:
                evaluator = RelevanceEvaluator(profile)

        logger.info(
            "Built profile: birth=%s, death=%s, places=%s",
            profile.birth_year,
            profile.death_year,
            profile.residence_places,
        )

        # 3. Build initial query enriched with known facts
        query = self._build_enriched_query(surname, given_name, known_facts)

        # 4. Iterative search loop
        for iteration in range(self.config.max_iterations):
            session.search_iterations = iteration + 1
            logger.info("Search iteration %d", iteration + 1)

            # Search
            result = await self.router.search(query, region=region)
            session.results_by_iteration.append(result)
            session.sources_queried.update(result.sources_searched)

            if not result.results:
                logger.info("No results in iteration %d", iteration + 1)
                break

            # 5. Evaluate relevance of results
            if evaluator:
                relevant_records = []
                for record in result.results:
                    score = evaluator.evaluate(record)
                    if score.confidence.value in [
                        MatchConfidence.DEFINITE.value,
                        MatchConfidence.LIKELY.value,
                        MatchConfidence.POSSIBLE.value,
                    ][:list(MatchConfidence).index(self.config.min_match_confidence) + 1]:
                        relevant_records.append(record)
                        session.evaluated_records.append((record, score))
                    else:
                        session.filtered_out_records.append((record, score))
                        logger.debug(
                            "Filtered out record: %s (score=%.2f, conflicts=%s)",
                            record.record_id,
                            score.overall_score,
                            score.conflict_reasons,
                        )

                logger.info(
                    "Relevance filter: %d/%d records passed",
                    len(relevant_records),
                    len(result.results),
                )
                records_to_process = relevant_records
            else:
                records_to_process = result.results

            if not records_to_process:
                logger.info("No relevant records in iteration %d", iteration + 1)
                break

            # 6. Extract facts from relevant results only
            new_facts = await self._extract_facts_from_results(records_to_process)

            # Filter to high-confidence facts not already known
            novel_facts = self._filter_novel_facts(new_facts, session)

            if not novel_facts:
                logger.info("No new facts discovered in iteration %d", iteration + 1)
                break

            session.discovered_facts.extend(novel_facts)
            logger.info("Discovered %d new facts", len(novel_facts))

            # Check if new facts can refine the query
            refined_query = self._refine_query(query, novel_facts)
            if refined_query == query:
                logger.info("Query cannot be further refined")
                break

            query = refined_query
            logger.info("Refined query for next iteration")

        # 4. Store discoveries to memory
        if self.config.store_discoveries and session.discovered_facts:
            await self._store_discoveries(session)

        self._current_session = None
        return session

    async def _load_known_facts(
        self, surname: str, given_name: str | None
    ) -> list[dict]:
        """Load existing facts about a person from memory and files.

        Args:
            surname: Subject's surname
            given_name: Subject's given name

        Returns:
            List of fact dictionaries
        """
        facts = []

        # 1. Check semantic memory
        if self.memory:
            search_query = f"{given_name} {surname}".strip() if given_name else surname
            try:
                result_json = self.memory.search_similar_facts(
                    query=search_query,
                    n_results=20,
                    status_filter="ACCEPTED",
                )
                results = json.loads(result_json)
                if isinstance(results, list):
                    for r in results:
                        if r.get("distance", 1.0) < 0.5:  # Close semantic match
                            facts.append({
                                "statement": r.get("statement", ""),
                                "confidence": 1.0 - r.get("distance", 0.5),
                                "source": "memory",
                                "metadata": r.get("metadata", {}),
                            })
            except Exception as e:
                logger.warning("Error loading from memory: %s", e)

        # 2. Check file-based research
        subject_slug = self._slugify(f"{given_name}-{surname}" if given_name else surname)
        research_paths = [
            self.research_dir / "wiki_plans" / subject_slug / "facts.json",
            self.research_dir / "subjects" / subject_slug / "facts.json",
            self.research_dir / subject_slug / "facts.json",
        ]

        for path in research_paths:
            if path.exists():
                try:
                    with open(path) as f:
                        file_facts = json.load(f)
                    if isinstance(file_facts, list):
                        for fact in file_facts:
                            facts.append({
                                "statement": fact.get("statement", ""),
                                "confidence": fact.get("confidence", 0.8),
                                "source": str(path),
                                "sources": fact.get("sources", []),
                            })
                except Exception as e:
                    logger.warning("Error loading facts from %s: %s", path, e)

        return facts

    def _build_enriched_query(
        self,
        surname: str,
        given_name: str | None,
        known_facts: list[dict],
    ) -> SearchQuery:
        """Build a SearchQuery enriched with known facts.

        Args:
            surname: Subject's surname
            given_name: Subject's given name
            known_facts: Known facts to extract query parameters from

        Returns:
            Enriched SearchQuery
        """
        query = SearchQuery(surname=surname, given_name=given_name)

        for fact in known_facts:
            statement = fact.get("statement", "").lower()
            confidence = fact.get("confidence", 0.5)

            if confidence < self.config.min_confidence_for_refinement:
                continue

            # Extract birth year
            if "born" in statement and not query.birth_year:
                years = self.YEAR_PATTERN.findall(statement)
                if years:
                    query.birth_year = int(years[0])

            # Extract death year
            if ("died" in statement or "death" in statement) and not query.death_year:
                years = self.YEAR_PATTERN.findall(statement)
                if years:
                    query.death_year = int(years[0])

            # Extract birth place
            if "born" in statement and "in " in statement and not query.birth_place:
                # Extract location after "in"
                match = re.search(r"born[^,]*in ([^,.]+)", statement)
                if match:
                    query.birth_place = match.group(1).strip()

            # Extract death place
            if ("died" in statement or "death" in statement) and not query.death_place:
                match = re.search(r"(?:died|death)[^,]*in ([^,.]+)", statement)
                if match:
                    query.death_place = match.group(1).strip()

            # Extract spouse
            if ("married" in statement or "wife" in statement or "husband" in statement) and not query.spouse_name:
                # Simple extraction - look for capitalized names after keywords
                match = re.search(r"(?:married|wife|husband)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
                if match:
                    query.spouse_name = match.group(1)

            # Extract father
            if ("father" in statement or "son of" in statement) and not query.father_name:
                match = re.search(r"(?:father|son of)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
                if match:
                    query.father_name = match.group(1)

            # Extract mother
            if ("mother" in statement or "daughter of" in statement) and not query.mother_name:
                match = re.search(r"(?:mother|daughter of)[^,]*?([A-Z][a-z]+ [A-Z][a-z]+)", fact.get("statement", ""))
                if match:
                    query.mother_name = match.group(1)

            # Extract state
            if not query.state:
                for abbrev, full_name in self.US_STATES.items():
                    if abbrev in fact.get("statement", "") or full_name.lower() in statement:
                        query.state = abbrev
                        break

        return query

    async def _extract_facts_from_results(
        self, records: list[RawRecord]
    ) -> list[ExtractedFact]:
        """Extract facts from search results.

        Args:
            records: List of search result records

        Returns:
            List of extracted facts
        """
        if self.config.parallel_extraction:
            tasks = [self._extract_facts_from_record(r) for r in records]
            results = await asyncio.gather(*tasks)
            facts = []
            for result in results:
                facts.extend(result)
            return facts
        else:
            facts = []
            for record in records:
                facts.extend(await self._extract_facts_from_record(record))
            return facts

    async def _extract_facts_from_record(self, record: RawRecord) -> list[ExtractedFact]:
        """Extract facts from a single record.

        Args:
            record: A search result record

        Returns:
            List of extracted facts
        """
        facts = []
        extracted = record.extracted_fields
        raw = record.raw_data

        # Base confidence from record
        base_confidence = record.confidence_hint or 0.6

        # Extract name facts
        if extracted.get("name") or extracted.get("full_name"):
            name = extracted.get("name") or extracted.get("full_name")
            if name:
                facts.append(ExtractedFact(
                    statement=f"Name: {name}",
                    fact_type="name",
                    confidence=base_confidence,
                    source_url=record.url,
                    source_name=record.source,
                    raw_value=str(name),
                ))

        # Extract birth facts
        birth_year = extracted.get("birth_year") or extracted.get("birth_date")
        if birth_year:
            facts.append(ExtractedFact(
                statement=f"Birth year: {birth_year}",
                fact_type="birth",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(birth_year),
            ))

        birth_place = extracted.get("birth_place") or extracted.get("birthplace")
        if birth_place:
            facts.append(ExtractedFact(
                statement=f"Birth place: {birth_place}",
                fact_type="birth",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(birth_place),
            ))

        # Extract death facts
        death_year = extracted.get("death_year") or extracted.get("death_date")
        if death_year:
            facts.append(ExtractedFact(
                statement=f"Death year: {death_year}",
                fact_type="death",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(death_year),
            ))

        death_place = extracted.get("death_place") or extracted.get("deathplace")
        if death_place:
            facts.append(ExtractedFact(
                statement=f"Death place: {death_place}",
                fact_type="death",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(death_place),
            ))

        # Extract location facts
        location = extracted.get("location") or extracted.get("residence")
        if location:
            facts.append(ExtractedFact(
                statement=f"Location: {location}",
                fact_type="residence",
                confidence=base_confidence * 0.8,  # Slightly lower confidence for general location
                source_url=record.url,
                source_name=record.source,
                raw_value=str(location),
            ))

        # Extract relationship facts
        spouse = extracted.get("spouse") or extracted.get("spouse_name")
        if spouse:
            facts.append(ExtractedFact(
                statement=f"Spouse: {spouse}",
                fact_type="relationship",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(spouse),
            ))

        father = extracted.get("father") or extracted.get("father_name")
        if father:
            facts.append(ExtractedFact(
                statement=f"Father: {father}",
                fact_type="relationship",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(father),
            ))

        mother = extracted.get("mother") or extracted.get("mother_name")
        if mother:
            facts.append(ExtractedFact(
                statement=f"Mother: {mother}",
                fact_type="relationship",
                confidence=base_confidence,
                source_url=record.url,
                source_name=record.source,
                raw_value=str(mother),
            ))

        # Try to extract from raw text if available
        raw_text = raw.get("text") or raw.get("content") or raw.get("snippet", "")
        if raw_text and isinstance(raw_text, str):
            text_facts = self._extract_facts_from_text(
                raw_text, record.url, record.source, base_confidence * 0.7
            )
            facts.extend(text_facts)

        return facts

    def _extract_facts_from_text(
        self,
        text: str,
        source_url: str | None,
        source_name: str,
        base_confidence: float,
    ) -> list[ExtractedFact]:
        """Extract facts from unstructured text.

        Args:
            text: Raw text to extract from
            source_url: Source URL
            source_name: Source name
            base_confidence: Base confidence for extracted facts

        Returns:
            List of extracted facts
        """
        facts = []
        text_lower = text.lower()

        # Look for birth patterns
        birth_match = re.search(
            r"(?:born|birth|b\.)\s*(?:on\s+)?(?:in\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{1,2},? \d{4}|\d{4})",
            text_lower,
        )
        if birth_match:
            facts.append(ExtractedFact(
                statement=f"Birth date: {birth_match.group(1)}",
                fact_type="birth",
                confidence=base_confidence,
                source_url=source_url,
                source_name=source_name,
                raw_value=birth_match.group(1),
            ))

        # Look for death patterns
        death_match = re.search(
            r"(?:died|death|d\.)\s*(?:on\s+)?(?:in\s+)?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\w+ \d{1,2},? \d{4}|\d{4})",
            text_lower,
        )
        if death_match:
            facts.append(ExtractedFact(
                statement=f"Death date: {death_match.group(1)}",
                fact_type="death",
                confidence=base_confidence,
                source_url=source_url,
                source_name=source_name,
                raw_value=death_match.group(1),
            ))

        # Look for location patterns with state abbreviations
        for abbrev, state_name in self.US_STATES.items():
            if f" {abbrev} " in text or f" {abbrev}," in text or f" {abbrev}." in text:
                # Look for county/city before state
                loc_match = re.search(
                    rf"([A-Z][a-zA-Z\s]+(?:County|City|Town)?)\s*,?\s*{abbrev}",
                    text,
                )
                if loc_match:
                    facts.append(ExtractedFact(
                        statement=f"Location: {loc_match.group(1)}, {state_name}",
                        fact_type="residence",
                        confidence=base_confidence * 0.8,
                        source_url=source_url,
                        source_name=source_name,
                        raw_value=f"{loc_match.group(1)}, {state_name}",
                    ))
                break

        return facts

    def _filter_novel_facts(
        self, new_facts: list[ExtractedFact], session: ResearchSession
    ) -> list[ExtractedFact]:
        """Filter out facts we already know.

        Args:
            new_facts: Newly extracted facts
            session: Current research session

        Returns:
            List of novel (not already known) facts
        """
        novel = []
        known_statements = {f.get("statement", "").lower() for f in session.known_facts}
        discovered_statements = {f.statement.lower() for f in session.discovered_facts}

        for fact in new_facts:
            if fact.confidence < self.config.min_confidence_for_refinement:
                continue

            statement_lower = fact.statement.lower()

            # Check if already known
            if statement_lower in known_statements or statement_lower in discovered_statements:
                continue

            # Check for semantic similarity (simple check)
            is_duplicate = False
            for known in known_statements | discovered_statements:
                # If the raw value is already known, skip
                if fact.raw_value and fact.raw_value.lower() in known:
                    is_duplicate = True
                    break

            if not is_duplicate:
                novel.append(fact)

        return novel

    def _refine_query(
        self, current_query: SearchQuery, new_facts: list[ExtractedFact]
    ) -> SearchQuery:
        """Refine a query based on newly discovered facts.

        Args:
            current_query: Current search query
            new_facts: Newly discovered facts

        Returns:
            Refined query (or same query if no refinement possible)
        """
        # Create a copy of the query
        refined = current_query.model_copy()
        changed = False

        for fact in new_facts:
            if fact.confidence < self.config.min_confidence_for_refinement:
                continue

            # Refine birth year
            if fact.fact_type == "birth" and not refined.birth_year:
                years = self.YEAR_PATTERN.findall(fact.raw_value)
                if years:
                    refined.birth_year = int(years[0])
                    changed = True

            # Refine death year
            if fact.fact_type == "death" and not refined.death_year:
                years = self.YEAR_PATTERN.findall(fact.raw_value)
                if years:
                    refined.death_year = int(years[0])
                    changed = True

            # Refine birth place
            if fact.fact_type == "birth" and "place" in fact.statement.lower() and not refined.birth_place:
                refined.birth_place = fact.raw_value
                changed = True

            # Refine residence/state
            if fact.fact_type == "residence" and not refined.state:
                for abbrev in self.US_STATES:
                    if abbrev in fact.raw_value:
                        refined.state = abbrev
                        changed = True
                        break

            # Refine spouse
            if fact.fact_type == "relationship" and "spouse" in fact.statement.lower() and not refined.spouse_name:
                refined.spouse_name = fact.raw_value
                changed = True

            # Refine father
            if fact.fact_type == "relationship" and "father" in fact.statement.lower() and not refined.father_name:
                refined.father_name = fact.raw_value
                changed = True

            # Refine mother
            if fact.fact_type == "relationship" and "mother" in fact.statement.lower() and not refined.mother_name:
                refined.mother_name = fact.raw_value
                changed = True

        return refined if changed else current_query

    async def _store_discoveries(self, session: ResearchSession) -> None:
        """Store discovered facts to memory.

        Args:
            session: Research session with discoveries
        """
        if not self.memory:
            logger.info("No memory plugin configured, skipping storage")
            return

        for fact in session.discovered_facts:
            try:
                # Generate a unique ID
                fact_id = f"{session.subject_name}-{fact.fact_type}-{hash(fact.statement)}"

                metadata = {
                    "subject": session.subject_name,
                    "fact_type": fact.fact_type,
                    "confidence": str(fact.confidence),
                    "source": fact.source_name,
                    "source_url": fact.source_url or "",
                    "discovered_at": datetime.now(UTC).isoformat(),
                    "status": "DISCOVERED",
                }

                self.memory.store_fact(
                    fact_id=fact_id,
                    statement=fact.statement,
                    metadata_json=json.dumps(metadata),
                )
                logger.debug("Stored fact: %s", fact.statement)

            except Exception as e:
                logger.warning("Error storing fact: %s", e)

        # Store research context
        try:
            context_text = (
                f"Research session for {session.subject_name}: "
                f"searched {len(session.sources_queried)} sources over "
                f"{session.search_iterations} iterations, "
                f"discovered {len(session.discovered_facts)} new facts"
            )
            self.memory.store_research_context(
                context_text=context_text,
                context_type="search_strategy",
                related_facts=json.dumps([f.statement for f in session.discovered_facts[:10]]),
            )
        except Exception as e:
            logger.warning("Error storing research context: %s", e)

    def _slugify(self, text: str) -> str:
        """Convert text to a URL-safe slug.

        Args:
            text: Text to slugify

        Returns:
            Slugified text
        """
        slug = text.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        return slug.strip("-")

    async def quick_search(
        self,
        surname: str,
        given_name: str | None = None,
        region: Region | None = None,
    ) -> UnifiedSearchResult:
        """Quick search without iterative refinement.

        Still loads known facts to enrich the query, but only does one iteration.

        Args:
            surname: Subject's surname
            given_name: Subject's given name
            region: Geographic region hint

        Returns:
            Search results
        """
        # Load known facts
        known_facts = await self._load_known_facts(surname, given_name)

        # Build enriched query
        query = self._build_enriched_query(surname, given_name, known_facts)

        # Single search
        return await self.router.search(query, region=region)

    def get_session_summary(self, session: ResearchSession) -> dict:
        """Get a summary of a research session.

        Args:
            session: Research session to summarize

        Returns:
            Summary dictionary
        """
        total_results = sum(
            len(r.results) for r in session.results_by_iteration
        )

        return {
            "subject": session.subject_name,
            "known_facts_loaded": len(session.known_facts),
            "iterations": session.search_iterations,
            "sources_queried": list(session.sources_queried),
            "total_results": total_results,
            "facts_discovered": len(session.discovered_facts),
            "discovered_facts": [
                {
                    "statement": f.statement,
                    "type": f.fact_type,
                    "confidence": f.confidence,
                    "source": f.source_name,
                }
                for f in session.discovered_facts
            ],
            "duration_seconds": (
                datetime.now(UTC) - session.started_at
            ).total_seconds(),
        }
