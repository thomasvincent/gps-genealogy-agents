"""GPS Search, Retrieval, and Review-Orchestrator Agent.

Conducts GPS-compliant genealogical searches, prevents duplicate records,
evaluates evidence quality, and handles conflict escalation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from gps_agents.agents.base import BaseAgent
from gps_agents.gramps.merge import (
    MatchConfidence,
    MatchResult,
    PersonMatcher,
)
from gps_agents.gramps.models import Event, EventType, GrampsDate, Name, Person
from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.router import Region, SearchRouter

if TYPE_CHECKING:
    from gps_agents.gramps.client import GrampsClient


class OrchestratorAction(str, Enum):
    """Actions the orchestrator can take."""
    SEARCH = "search"
    MATCH = "match"
    FORMAT_REPORT = "format_report"
    NEEDS_HUMAN_DECISION = "needs_human_decision"


class SourceType(str, Enum):
    """Evidence source classification per GPS standards."""
    ORIGINAL = "Original"      # Created at or near the event
    DERIVATIVE = "Derivative"  # Index, transcription, abstract
    AUTHORED = "Authored"      # Compiled from other sources


class EvidenceClassification(str, Enum):
    """Evidence classification for GPS analysis."""
    DIRECT = "direct"
    INDIRECT = "indirect"
    NEGATIVE = "negative"


@dataclass
class ConflictInfo:
    """Information about a detected conflict."""
    field: str
    value_a: Any
    value_b: Any
    source_a: str
    source_b: str
    confidence_a: float
    confidence_b: float


class OrchestratorResult(BaseModel):
    """Structured result from the orchestrator."""

    model: str = Field(description="Entity type: Person, Event, Source")
    data: dict = Field(default_factory=dict, description="Entity data")
    source_citation: str = Field(default="", description="GPS-compliant citation")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    source_type: SourceType = Field(default=SourceType.AUTHORED)


class OrchestratorResponse(BaseModel):
    """JSON response from the orchestrator agent."""

    action: OrchestratorAction
    parameters: dict = Field(default_factory=dict)
    results: list[OrchestratorResult] = Field(default_factory=list)
    justification: str | None = None
    next_step: str = Field(description="Recommendation for next action")

    # Optional fields for match/conflict cases
    gramps_match: MatchResult | None = None
    conflicts: list[dict] | None = None


# Region mapping for search routing
REGION_MAPPING: dict[str, Region] = {
    "belgium": Region.BELGIUM,
    "netherlands": Region.NETHERLANDS,
    "germany": Region.GERMANY,
    "france": Region.FRANCE,
    "ireland": Region.IRELAND,
    "scotland": Region.SCOTLAND,
    "england": Region.ENGLAND,
    "wales": Region.WALES,
    "channel islands": Region.CHANNEL_ISLANDS,
    "jersey": Region.CHANNEL_ISLANDS,
    "guernsey": Region.CHANNEL_ISLANDS,
    "usa": Region.USA,
    "united states": Region.USA,
    "canada": Region.CANADA,
}


class SearchOrchestratorAgent(BaseAgent):
    """
    GPS Search, Retrieval, and Review-Orchestrator Agent.

    Responsibilities:
    - Conduct GPS-compliant genealogical searches
    - Prevent duplicate records via Gramps matching
    - Evaluate evidence quality
    - Escalate conflicts for human review

    Never invents facts. Always returns valid JSON.
    """

    name = "search_orchestrator"
    prompt_file = "search_orchestrator.txt"
    default_provider = "anthropic"

    # Confidence thresholds
    MIN_AUTO_ACCEPT = 0.80      # Auto-accept threshold
    MIN_SUGGEST_REVIEW = 0.60   # Suggest for human review
    MIN_EXPAND_SEARCH = 0.75    # Below this, recommend expansion

    def __init__(
        self,
        router: SearchRouter | None = None,
        gramps_client: GrampsClient | None = None,
        **kwargs,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            router: SearchRouter for multi-source searches
            gramps_client: GrampsClient for duplicate detection
        """
        super().__init__(**kwargs)
        self.router = router
        self.gramps_client = gramps_client
        self._matcher: PersonMatcher | None = None

        if gramps_client:
            self._matcher = PersonMatcher(gramps_client)

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process an orchestration request.

        Args:
            state: Workflow state containing the task

        Returns:
            Updated state with orchestrator response
        """
        task = state.get("task", "")
        context = state.get("context", {})

        # Parse the request
        request = await self._parse_request(task, context)

        # Execute based on action type
        if request.get("action") == "search":
            response = await self._execute_search(request, context)
        elif request.get("action") == "match":
            response = await self._execute_match(request, context)
        elif request.get("action") == "format_report":
            response = await self._execute_format(request, context)
        else:
            response = await self._execute_search(request, context)

        state["orchestrator_response"] = response.model_dump()
        return state

    async def search(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        region: str | None = None,
        record_types: list[str] | None = None,
        check_gramps: bool = True,
    ) -> OrchestratorResponse:
        """Execute a GPS-compliant search with duplicate detection.

        Args:
            surname: Family name
            given_name: First/given name
            birth_year: Approximate birth year
            birth_place: Birth location
            region: Geographic region for routing
            record_types: Types of records to search
            check_gramps: Whether to check for existing Gramps records

        Returns:
            OrchestratorResponse with results or match info
        """
        # Build search query with expanded parameters per GPS Pillar 1
        query = self._build_exhaustive_query(
            surname=surname,
            given_name=given_name,
            birth_year=birth_year,
            birth_place=birth_place,
            record_types=record_types,
        )

        # Check Gramps for existing record first
        if check_gramps and self._matcher:
            existing_match = await self._check_gramps_match(
                surname=surname,
                given_name=given_name,
                birth_year=birth_year,
            )
            if existing_match and existing_match.confidence != MatchConfidence.UNLIKELY:
                return OrchestratorResponse(
                    action=OrchestratorAction.MATCH,
                    parameters={"query": query.model_dump()},
                    results=[],
                    justification=(
                        f"Probable match found in Gramps: "
                        f"{existing_match.matched_person.display_name if existing_match.matched_person else 'Unknown'} "
                        f"(confidence: {existing_match.confidence.value}, score: {existing_match.match_score:.1f})"
                    ),
                    next_step=(
                        "Review existing record before creating duplicate. "
                        f"Gramps ID: {existing_match.matched_handle}"
                    ),
                    gramps_match=existing_match,
                )

        # Determine region for smart routing
        search_region = self._determine_region(birth_place or "", region)

        # Execute multi-source search
        results: list[OrchestratorResult] = []
        sources_searched: list[str] = []

        if self.router:
            unified_result = await self.router.search(
                query=query,
                region=search_region,
            )
            sources_searched = unified_result.sources_searched

            # Process and evaluate each record
            for record in unified_result.results:
                evaluated = self._evaluate_evidence(record)
                results.append(evaluated)

        # Check for conflicts
        conflicts = self._detect_conflicts(results)

        # Calculate overall confidence
        overall_confidence = self._calculate_overall_confidence(results)

        # Determine action and next step
        if conflicts:
            if self._can_resolve_conflicts(conflicts):
                resolved_results = self._resolve_conflicts(results, conflicts)
                return OrchestratorResponse(
                    action=OrchestratorAction.SEARCH,
                    parameters={"query": query.model_dump(), "region": str(search_region)},
                    results=resolved_results,
                    justification="Conflicts resolved using evidence quality weighting",
                    next_step=self._recommend_next_step(overall_confidence, sources_searched),
                )
            return OrchestratorResponse(
                action=OrchestratorAction.NEEDS_HUMAN_DECISION,
                parameters={"query": query.model_dump()},
                results=results,
                justification="Conflicting evidence requires human review",
                next_step="Present options to researcher for decision",
                conflicts=[self._conflict_to_dict(c) for c in conflicts],
            )

        return OrchestratorResponse(
            action=OrchestratorAction.SEARCH,
            parameters={
                "query": query.model_dump(),
                "region": str(search_region) if search_region else None,
                "sources_searched": sources_searched,
            },
            results=results,
            justification=f"Found {len(results)} records from {len(sources_searched)} sources",
            next_step=self._recommend_next_step(overall_confidence, sources_searched),
        )

    def _build_exhaustive_query(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        record_types: list[str] | None = None,
    ) -> SearchQuery:
        """Build a GPS Pillar 1 compliant exhaustive search query."""
        # Generate surname variants
        surname_variants = self._generate_name_variants(surname)

        # Set date range (+/- 5-10 years per GPS Pillar 1)
        birth_year_range = 5

        return SearchQuery(
            surname=surname,
            surname_variants=surname_variants,
            given_name=given_name,
            birth_year=birth_year,
            birth_year_range=birth_year_range,
            birth_place=birth_place,
            record_types=record_types or ["birth", "death", "marriage", "census"],
        )

    def _generate_name_variants(self, name: str) -> list[str]:
        """Generate phonetic and spelling variants of a name."""
        variants = [name]

        # Common surname transformations
        transformations = [
            ("son", "sen"),
            ("sen", "son"),
            ("ck", "k"),
            ("k", "ck"),
            ("ph", "f"),
            ("f", "ph"),
            ("ie", "y"),
            ("y", "ie"),
            ("mann", "man"),
            ("man", "mann"),
        ]

        name_lower = name.lower()
        for old, new in transformations:
            if old in name_lower:
                variant = name_lower.replace(old, new)
                variants.append(variant.title())

        return list(set(variants))

    def _determine_region(self, place: str, explicit_region: str | None) -> Region | None:
        """Determine the search region from place or explicit specification."""
        if explicit_region:
            return REGION_MAPPING.get(explicit_region.lower())

        place_lower = place.lower()
        for keyword, region in REGION_MAPPING.items():
            if keyword in place_lower:
                return region

        return None

    async def _check_gramps_match(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
    ) -> MatchResult | None:
        """Check for existing match in Gramps database."""
        if not self._matcher or not self.gramps_client:
            return None

        # Create a candidate person for matching
        candidate = Person(
            names=[Name(given=given_name or "", surname=surname)],
        )

        if birth_year:
            candidate.birth = Event(
                event_type=EventType.BIRTH,
                date=GrampsDate(year=birth_year),
            )

        matches = self._matcher.find_matches(candidate, threshold=50.0, limit=1)
        return matches[0] if matches else None

    def _evaluate_evidence(self, record: RawRecord) -> OrchestratorResult:
        """Evaluate evidence quality per GPS standards."""
        # Determine source type
        source_type = self._classify_source(record)

        # Calculate confidence based on:
        # 1. Source originality
        # 2. Proximity to event
        # 3. Internal consistency
        base_confidence = record.confidence_hint or 0.5

        # Adjust for source type
        source_adjustments = {
            SourceType.ORIGINAL: 0.2,
            SourceType.DERIVATIVE: 0.0,
            SourceType.AUTHORED: -0.1,
        }
        confidence = base_confidence + source_adjustments.get(source_type, 0)
        confidence = max(0.0, min(1.0, confidence))

        # Build GPS-compliant citation
        citation = self._format_citation(record)

        return OrchestratorResult(
            model="Person",
            data=record.extracted_fields,
            source_citation=citation,
            confidence=confidence,
            source_type=source_type,
        )

    def _classify_source(self, record: RawRecord) -> SourceType:
        """Classify a source as Original, Derivative, or Authored."""
        source_lower = record.source.lower()
        record_type = record.record_type.lower() if record.record_type else ""

        # Original sources
        if any(kw in source_lower for kw in ["parish", "civil", "church", "archive"]) and (
            "image" in record_type or "original" in record_type
        ):
            return SourceType.ORIGINAL

        # Derivative sources
        if any(kw in source_lower for kw in ["index", "transcript", "abstract"]):
            return SourceType.DERIVATIVE

        # Authored sources (trees, compilations)
        if any(kw in source_lower for kw in ["tree", "wikitree", "gedcom", "compilation"]):
            return SourceType.AUTHORED

        # Default to derivative for most database records
        return SourceType.DERIVATIVE

    def _format_citation(self, record: RawRecord) -> str:
        """Format a GPS-compliant source citation."""
        parts = []

        # Repository
        parts.append(record.source)

        # Record identification
        if record.record_id:
            parts.append(f"record {record.record_id}")

        if record.record_type:
            parts.append(f"({record.record_type})")

        # Access info
        if record.url:
            parts.append(f"<{record.url}>")

        if record.accessed_at:
            parts.append(f"accessed {record.accessed_at.strftime('%d %b %Y')}")

        return ", ".join(parts)

    def _detect_conflicts(self, results: list[OrchestratorResult]) -> list[ConflictInfo]:
        """Detect conflicting claims between results."""
        conflicts = []

        # Compare each pair of results
        for i, result_a in enumerate(results):
            for result_b in results[i + 1:]:
                for field in ["birth_year", "birth_date", "death_year", "death_date", "birth_place"]:
                    val_a = result_a.data.get(field)
                    val_b = result_b.data.get(field)

                    if val_a and val_b and val_a != val_b:
                        conflicts.append(ConflictInfo(
                            field=field,
                            value_a=val_a,
                            value_b=val_b,
                            source_a=result_a.source_citation,
                            source_b=result_b.source_citation,
                            confidence_a=result_a.confidence,
                            confidence_b=result_b.confidence,
                        ))

        return conflicts

    def _can_resolve_conflicts(self, conflicts: list[ConflictInfo]) -> bool:
        """Determine if conflicts can be automatically resolved."""
        for conflict in conflicts:
            # If confidences are too close, can't auto-resolve
            if abs(conflict.confidence_a - conflict.confidence_b) < 0.2:
                return False
        return True

    def _resolve_conflicts(
        self,
        results: list[OrchestratorResult],
        _conflicts: list[ConflictInfo],
    ) -> list[OrchestratorResult]:
        """Resolve conflicts by preferring higher-confidence sources."""
        # For now, just sort by confidence and return
        # A more sophisticated approach would merge data
        return sorted(results, key=lambda r: r.confidence, reverse=True)

    def _conflict_to_dict(self, conflict: ConflictInfo) -> dict:
        """Convert conflict info to dictionary for JSON output."""
        return {
            "field": conflict.field,
            "value_a": str(conflict.value_a),
            "value_b": str(conflict.value_b),
            "source_a": conflict.source_a,
            "source_b": conflict.source_b,
            "confidence_a": conflict.confidence_a,
            "confidence_b": conflict.confidence_b,
        }

    def _calculate_overall_confidence(self, results: list[OrchestratorResult]) -> float:
        """Calculate overall confidence from multiple results."""
        if not results:
            return 0.0

        # Weight by source type
        weighted_sum = 0.0
        total_weight = 0.0

        for result in results:
            weight = {
                SourceType.ORIGINAL: 3.0,
                SourceType.DERIVATIVE: 2.0,
                SourceType.AUTHORED: 1.0,
            }.get(result.source_type, 1.0)

            weighted_sum += result.confidence * weight
            total_weight += weight

        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _recommend_next_step(
        self,
        confidence: float,
        sources_searched: list[str],
    ) -> str:
        """Recommend next steps based on confidence and coverage."""
        recommendations = []

        if confidence < self.MIN_EXPAND_SEARCH:
            recommendations.append("Expand search to additional record types")

            # Suggest specific sources not yet searched
            all_sources = {"familysearch", "wikitree", "findmypast", "geneanet", "findagrave"}
            unsearched = all_sources - set(sources_searched)
            if unsearched:
                recommendations.append(f"Search: {', '.join(list(unsearched)[:3])}")

        if confidence < 0.60:
            recommendations.append("Consider name variants and phonetic spellings")
            recommendations.append("Expand date range to +/- 10 years")

        if not recommendations:
            recommendations.append("Evidence sufficient for GPS compliance")

        return "; ".join(recommendations)

    async def _parse_request(
        self,
        task: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Parse a natural language request into structured parameters."""
        # For simple requests, try to extract structured data
        prompt = f"""
        Parse this genealogical search request into structured parameters.

        Request: {task}
        Context: {json.dumps(context)}

        Return JSON:
        {{
            "action": "search" | "match" | "format_report",
            "surname": "family name",
            "given_name": "first name or null",
            "birth_year": year or null,
            "birth_place": "location or null",
            "region": "region or null",
            "record_types": ["list", "of", "record", "types"] or null
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {"action": "search"}

    async def _execute_search(
        self,
        request: dict[str, Any],
        _context: dict[str, Any],
    ) -> OrchestratorResponse:
        """Execute a search request."""
        return await self.search(
            surname=request.get("surname", ""),
            given_name=request.get("given_name"),
            birth_year=request.get("birth_year"),
            birth_place=request.get("birth_place"),
            region=request.get("region"),
            record_types=request.get("record_types"),
        )

    async def _execute_match(
        self,
        request: dict[str, Any],
        _context: dict[str, Any],
    ) -> OrchestratorResponse:
        """Execute a Gramps match check."""
        match = await self._check_gramps_match(
            surname=request.get("surname", ""),
            given_name=request.get("given_name"),
            birth_year=request.get("birth_year"),
        )

        if match:
            return OrchestratorResponse(
                action=OrchestratorAction.MATCH,
                parameters=request,
                results=[],
                gramps_match=match,
                justification=f"Match found with confidence {match.confidence.value}",
                next_step="Review match and decide whether to merge or create new record",
            )

        return OrchestratorResponse(
            action=OrchestratorAction.SEARCH,
            parameters=request,
            results=[],
            justification="No match found in Gramps",
            next_step="Proceed with search to gather evidence",
        )

    async def _execute_format(
        self,
        request: dict[str, Any],
        _context: dict[str, Any],
    ) -> OrchestratorResponse:
        """Execute a format/report request."""
        # This would format results into a GPS-compliant report
        return OrchestratorResponse(
            action=OrchestratorAction.FORMAT_REPORT,
            parameters=request,
            results=[],
            justification="Report formatting requested",
            next_step="Generate GPS-compliant proof summary",
        )

    def to_json(self, response: OrchestratorResponse) -> str:
        """Serialize response to JSON string."""
        return response.model_dump_json(indent=2)
