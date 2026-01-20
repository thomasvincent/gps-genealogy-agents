"""GPS Agentic Pipeline for genealogical research.

Implements the agentic architecture with explicit agent roles:
- QueryPlannerAgent: Creates SearchPlan with budgets and source ranking
- SourceExecutor: Executes searches according to the plan
- EntityResolverAgent: Clusters records into person entities
- EvidenceVerifierAgent: Evaluates evidence quality per GPS standards
- SynthesisAgent: Produces final synthesized output
- BudgetPolicyAgent: Manages resource allocation
- Manager: Orchestrates the full pipeline with run traces
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gps_agents.agents.schemas import (
    AgentRole,
    ContestedFieldOutput,
    EntityClusters,
    EvidenceScore,
    ExecutionResult,
    FieldEvidence,
    ManagerResponse,
    ResolvedEntity,
    RunTrace,
    SearchPlan,
    SourceBudget,
    SourceExecutionResult,
    Synthesis,
    TraceEventType,
)
from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.router import RecordType, Region, SearchRouter
from gps_agents.utils.normalize import normalize_name, normalize_place

if TYPE_CHECKING:
    from gps_agents.sources.base import GenealogySource


# ─────────────────────────────────────────────────────────────────────────────
# QueryPlannerAgent
# ─────────────────────────────────────────────────────────────────────────────


class QueryPlannerAgent:
    """Creates SearchPlan with budgets and source ranking.

    Responsibilities:
    - Generate surname variants for exhaustive search (GPS Pillar 1)
    - Determine optimal source selection and ordering
    - Allocate budgets based on region and record types
    - Apply guardrails to prevent overly broad queries
    """

    # Common surname transformations for variants
    SURNAME_TRANSFORMS = [
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
        ("berg", "burg"),
        ("burg", "berg"),
    ]

    def __init__(self, router: SearchRouter) -> None:
        self.router = router

    def create_plan(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        death_year: int | None = None,
        record_types: list[str] | None = None,
        region: str | None = None,
        max_sources: int | None = None,
        total_budget_seconds: float = 120.0,
    ) -> SearchPlan:
        """Create a search plan for the given parameters.

        Args:
            surname: Family name (required unless strong identifiers present)
            given_name: First/given name
            birth_year: Approximate birth year
            birth_place: Birth location
            death_year: Approximate death year
            record_types: Types of records to search
            region: Geographic region
            max_sources: Maximum number of sources to query
            total_budget_seconds: Total time budget

        Returns:
            SearchPlan with source budgets and configuration
        """
        # Generate surname variants
        variants = self._generate_variants(surname)

        # Determine region from birth_place if not explicit
        search_region = self._determine_region(birth_place or "", region)

        # Get recommended sources with priority ranking
        ranked_sources = self.router.rank_sources_for_query(
            SearchQuery(
                surname=surname,
                given_name=given_name,
                birth_year=birth_year,
                birth_place=birth_place,
                record_types=record_types or [],
            ),
            region=search_region,
        )

        # Apply max_sources limit
        if max_sources and len(ranked_sources) > max_sources:
            ranked_sources = ranked_sources[:max_sources]

        # Create source budgets based on ranking
        source_budgets = []
        per_source_timeout = min(30.0, total_budget_seconds / max(1, len(ranked_sources)))

        for source_name, priority in ranked_sources:
            # Higher priority sources get more results and time
            max_results = 50 if priority >= 2 else 30
            timeout = per_source_timeout * (1 + 0.2 * priority)

            source_budgets.append(SourceBudget(
                source_name=source_name,
                priority=priority,
                max_results=max_results,
                timeout_seconds=min(timeout, 45.0),
                retry_count=2 if priority >= 2 else 1,
            ))

        return SearchPlan(
            surname=surname,
            surname_variants=variants,
            given_name=given_name,
            birth_year=birth_year,
            birth_year_range=5,
            birth_place=birth_place,
            death_year=death_year,
            record_types=record_types or ["birth", "death", "marriage", "census"],
            region=str(search_region) if search_region else None,
            source_budgets=source_budgets,
            total_budget_seconds=total_budget_seconds,
            max_total_results=200,
            first_pass_enabled=True,
            first_pass_source_limit=5,
            second_pass_threshold=0.7,
        )

    def _generate_variants(self, name: str) -> list[str]:
        """Generate phonetic and spelling variants."""
        variants = [name]
        name_lower = name.lower()

        for old, new in self.SURNAME_TRANSFORMS:
            if old in name_lower:
                variant = name_lower.replace(old, new)
                variants.append(variant.title())

        return list(set(variants))

    def _determine_region(self, place: str, explicit_region: str | None) -> Region | None:
        """Determine search region from place or explicit specification."""
        region_mapping = {
            "belgium": Region.BELGIUM,
            "netherlands": Region.NETHERLANDS,
            "germany": Region.GERMANY,
            "france": Region.FRANCE,
            "ireland": Region.IRELAND,
            "scotland": Region.SCOTLAND,
            "england": Region.ENGLAND,
            "wales": Region.WALES,
            "jersey": Region.CHANNEL_ISLANDS,
            "guernsey": Region.CHANNEL_ISLANDS,
            "channel islands": Region.CHANNEL_ISLANDS,
            "usa": Region.USA,
            "united states": Region.USA,
            "canada": Region.CANADA,
        }

        if explicit_region:
            return region_mapping.get(explicit_region.lower())

        place_lower = place.lower()
        for keyword, region in region_mapping.items():
            if keyword in place_lower:
                return region

        return None


# ─────────────────────────────────────────────────────────────────────────────
# SourceExecutor
# ─────────────────────────────────────────────────────────────────────────────


class SourceExecutor:
    """Executes searches according to the SearchPlan.

    Responsibilities:
    - Execute searches on sources respecting budgets
    - Implement two-pass search strategy
    - Track execution metrics
    - Handle retries and timeouts
    """

    def __init__(self, router: SearchRouter) -> None:
        self.router = router

    async def execute(
        self,
        plan: SearchPlan,
        trace: RunTrace,
    ) -> ExecutionResult:
        """Execute the search plan.

        Args:
            plan: SearchPlan from QueryPlannerAgent
            trace: RunTrace for observability

        Returns:
            ExecutionResult with all records found
        """
        start_time = time.time()

        # Build query from plan
        query = SearchQuery(
            surname=plan.surname,
            surname_variants=plan.surname_variants,
            given_name=plan.given_name,
            birth_year=plan.birth_year,
            birth_year_range=plan.birth_year_range,
            birth_place=plan.birth_place,
            record_types=plan.record_types,
        )

        # First pass: limited sources
        first_pass_sources = plan.get_sources_by_priority()[:plan.first_pass_source_limit]

        trace.add_event(
            TraceEventType.EXECUTION_STARTED,
            AgentRole.EXECUTOR,
            f"Starting first pass with {len(first_pass_sources)} sources",
            {"sources": first_pass_sources, "pass": 1},
        )

        first_pass_results = await self._execute_sources(
            query, first_pass_sources, plan, trace
        )

        # Estimate confidence after first pass
        confidence = self._estimate_confidence(first_pass_results)

        result = ExecutionResult(
            plan_id=plan.plan_id,
            source_results=first_pass_results,
            all_records=[],
            pass_number=1,
            confidence_after_pass=confidence,
        )

        # Aggregate records from first pass
        for sr in first_pass_results:
            if sr.success:
                result.all_records.extend(sr.records)
                result.sources_searched.append(sr.source_name)
            else:
                result.sources_failed.append(sr.source_name)

        # Second pass if confidence is low
        if plan.first_pass_enabled and confidence < plan.second_pass_threshold:
            remaining_sources = [
                s for s in plan.get_sources_by_priority()
                if s not in first_pass_sources
            ]

            if remaining_sources:
                trace.add_event(
                    TraceEventType.EXECUTION_STARTED,
                    AgentRole.EXECUTOR,
                    f"Low confidence ({confidence:.2f}), expanding to {len(remaining_sources)} more sources",
                    {"sources": remaining_sources, "pass": 2},
                )

                second_pass_results = await self._execute_sources(
                    query, remaining_sources, plan, trace
                )

                result.source_results.extend(second_pass_results)
                result.pass_number = 2

                for sr in second_pass_results:
                    if sr.success:
                        result.all_records.extend(sr.records)
                        result.sources_searched.append(sr.source_name)
                    else:
                        result.sources_failed.append(sr.source_name)

                result.confidence_after_pass = self._estimate_confidence(
                    result.source_results
                )

        result.total_records = len(result.all_records)
        result.total_execution_time_ms = (time.time() - start_time) * 1000

        trace.add_event(
            TraceEventType.EXECUTION_COMPLETED,
            AgentRole.EXECUTOR,
            f"Execution complete: {result.total_records} records from {len(result.sources_searched)} sources",
            {
                "total_records": result.total_records,
                "sources_searched": result.sources_searched,
                "sources_failed": result.sources_failed,
                "passes": result.pass_number,
            },
            duration_ms=result.total_execution_time_ms,
        )

        return result

    async def _execute_sources(
        self,
        query: SearchQuery,
        source_names: list[str],
        plan: SearchPlan,
        trace: RunTrace,
    ) -> list[SourceExecutionResult]:
        """Execute search on a list of sources."""
        results = []

        # Get budget for each source
        budget_map = {b.source_name: b for b in plan.source_budgets}

        # Execute in parallel
        tasks = []
        for source_name in source_names:
            budget = budget_map.get(source_name, SourceBudget(source_name=source_name))
            tasks.append(self._execute_single(source_name, query, budget, trace))

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                results.append(SourceExecutionResult(
                    source_name="unknown",
                    success=False,
                    error=str(result),
                ))
            else:
                results.append(result)

        return results

    async def _execute_single(
        self,
        source_name: str,
        query: SearchQuery,
        budget: SourceBudget,
        trace: RunTrace,
    ) -> SourceExecutionResult:
        """Execute search on a single source with retries."""
        start_time = time.time()
        source = self.router._sources.get(source_name)

        if not source:
            return SourceExecutionResult(
                source_name=source_name,
                success=False,
                error=f"Source not registered: {source_name}",
            )

        last_error = None
        attempts = 0

        for attempt in range(budget.retry_count + 1):
            attempts = attempt + 1
            try:
                records = await asyncio.wait_for(
                    source.search(query),
                    timeout=budget.timeout_seconds,
                )

                # Limit results
                if len(records) > budget.max_results:
                    records = records[:budget.max_results]

                # Convert to dicts for schema
                record_dicts = [
                    {
                        "record_id": r.record_id,
                        "source": r.source,
                        "url": r.url,
                        "record_type": r.record_type,
                        "confidence_hint": r.confidence_hint,
                        "extracted_fields": r.extracted_fields,
                        "raw_data": r.raw_data,
                    }
                    for r in records
                ]

                trace.add_event(
                    TraceEventType.SOURCE_SEARCHED,
                    AgentRole.EXECUTOR,
                    f"Source {source_name}: {len(records)} records",
                    {"source": source_name, "count": len(records)},
                    duration_ms=(time.time() - start_time) * 1000,
                )

                return SourceExecutionResult(
                    source_name=source_name,
                    success=True,
                    records=record_dicts,
                    total_count=len(records),
                    search_time_ms=(time.time() - start_time) * 1000,
                    retry_count=attempts - 1,
                )

            except asyncio.TimeoutError:
                last_error = "timeout"
            except Exception as e:
                last_error = str(e)

        # All attempts failed
        trace.add_event(
            TraceEventType.SOURCE_FAILED,
            AgentRole.EXECUTOR,
            f"Source {source_name} failed after {attempts} attempts: {last_error}",
            {"source": source_name, "error": last_error, "attempts": attempts},
            error=last_error,
        )

        return SourceExecutionResult(
            source_name=source_name,
            success=False,
            error=last_error,
            search_time_ms=(time.time() - start_time) * 1000,
            retry_count=attempts - 1,
        )

    def _estimate_confidence(self, results: list[SourceExecutionResult]) -> float:
        """Estimate confidence from execution results."""
        if not results:
            return 0.0

        successful = [r for r in results if r.success]
        if not successful:
            return 0.0

        total_records = sum(r.total_count for r in successful)
        record_factor = min(1.0, total_records / 10)
        source_factor = len(successful) / len(results)

        return (record_factor + source_factor) / 2


# ─────────────────────────────────────────────────────────────────────────────
# EntityResolverAgent
# ─────────────────────────────────────────────────────────────────────────────


class EntityResolverAgent:
    """Clusters records into person entities.

    Responsibilities:
    - Compute content fingerprints for records
    - Group records by fingerprint
    - Select best values for each cluster
    - Apply corroboration boost for multi-source entities
    """

    def resolve(
        self,
        execution: ExecutionResult,
        trace: RunTrace,
    ) -> EntityClusters:
        """Resolve records into entity clusters.

        Args:
            execution: ExecutionResult from SourceExecutor
            trace: RunTrace for observability

        Returns:
            EntityClusters with resolved entities
        """
        start_time = time.time()

        # Group records by fingerprint
        clusters_by_fp: dict[str, list[dict]] = {}
        unresolved: list[str] = []

        for record in execution.all_records:
            fp = self._compute_fingerprint(record)
            if fp:
                if fp not in clusters_by_fp:
                    clusters_by_fp[fp] = []
                clusters_by_fp[fp].append(record)
            else:
                unresolved.append(record.get("record_id", "unknown"))

        # Build resolved entities
        entities: list[ResolvedEntity] = []

        for fingerprint, records in clusters_by_fp.items():
            entity = self._build_entity(fingerprint, records)
            entities.append(entity)

        # Sort by confidence
        entities.sort(key=lambda e: -e.cluster_confidence)

        result = EntityClusters(
            execution_id=execution.execution_id,
            entities=entities,
            unresolved_record_ids=unresolved,
            total_input_records=len(execution.all_records),
            total_entities=len(entities),
            multi_source_entities=sum(1 for e in entities if e.source_count > 1),
        )

        trace.add_event(
            TraceEventType.ENTITIES_RESOLVED,
            AgentRole.RESOLVER,
            f"Resolved {len(entities)} entities from {len(execution.all_records)} records",
            {
                "total_entities": len(entities),
                "multi_source": result.multi_source_entities,
                "unresolved": len(unresolved),
            },
            duration_ms=(time.time() - start_time) * 1000,
        )

        return result

    def _compute_fingerprint(self, record: dict) -> str | None:
        """Compute content fingerprint for a record."""
        fields = record.get("extracted_fields", {})
        if not fields:
            return None

        parts = []
        for key in ("full_name", "given_name", "surname", "birth_date", "birth_year", "birth_place"):
            val = fields.get(key)
            if val:
                normalized = str(val).lower().strip()
                parts.append(f"{key}:{normalized}")

        if len(parts) < 2:
            return None

        content = "|".join(sorted(parts))
        return hashlib.md5(content.encode()).hexdigest()

    def _build_entity(self, fingerprint: str, records: list[dict]) -> ResolvedEntity:
        """Build a resolved entity from clustered records."""
        sources = set()
        record_ids = []

        for r in records:
            sources.add(r.get("source", "unknown"))
            record_ids.append(r.get("record_id", "unknown"))

        # Select best values
        entity = ResolvedEntity(
            fingerprint=fingerprint,
            record_ids=record_ids,
            sources=list(sources),
            record_count=len(records),
            source_count=len(sources),
        )

        entity.best_name = self._best_value(records, ["full_name"])
        entity.best_birth_place = self._best_value(records, ["birth_place"])

        # Extract years
        birth_str = self._best_value(records, ["birth_year", "birth_date"])
        if birth_str:
            year_match = re.search(r"\b(1\d{3}|20\d{2})\b", str(birth_str))
            if year_match:
                entity.best_birth_year = int(year_match.group(1))

        death_str = self._best_value(records, ["death_year", "death_date"])
        if death_str:
            year_match = re.search(r"\b(1\d{3}|20\d{2})\b", str(death_str))
            if year_match:
                entity.best_death_year = int(year_match.group(1))

        # Calculate confidence with corroboration boost
        confidences = [r.get("confidence_hint", 0.5) for r in records]
        base_confidence = sum(confidences) / len(confidences)
        corroboration_boost = min(0.2, 0.05 * (len(sources) - 1))

        entity.cluster_confidence = min(1.0, base_confidence + corroboration_boost)
        entity.corroboration_boost = corroboration_boost

        return entity

    def _best_value(self, records: list[dict], field_names: list[str]) -> str | None:
        """Get best value from records for given fields."""
        candidates: list[tuple[str, float]] = []

        for record in records:
            confidence = record.get("confidence_hint", 0.5)
            fields = record.get("extracted_fields", {})
            for field in field_names:
                val = fields.get(field)
                if val:
                    candidates.append((str(val), confidence))
                    break

        if not candidates:
            return None

        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceVerifierAgent
# ─────────────────────────────────────────────────────────────────────────────


class EvidenceVerifierAgent:
    """Evaluates evidence quality per GPS standards.

    Responsibilities:
    - Classify source types (Original, Derivative, Authored)
    - Evaluate field-level evidence
    - Detect contested fields
    - Score GPS compliance
    """

    def verify(
        self,
        entity: ResolvedEntity,
        records: list[dict],
        trace: RunTrace,
    ) -> EvidenceScore:
        """Verify evidence for an entity.

        Args:
            entity: ResolvedEntity to verify
            records: Source records for this entity
            trace: RunTrace for observability

        Returns:
            EvidenceScore with verification results
        """
        start_time = time.time()

        # Classify source types
        original_count = 0
        derivative_count = 0
        authored_count = 0

        for record in records:
            source_type = self._classify_source(record)
            if source_type == "original":
                original_count += 1
            elif source_type == "authored":
                authored_count += 1
            else:
                derivative_count += 1

        # Evaluate field-level evidence
        field_evidence = self._evaluate_fields(records)

        # Count contested vs consensus
        contested_count = sum(1 for f in field_evidence if f.is_contested)
        consensus_count = sum(1 for f in field_evidence if f.is_consensus)

        # Calculate overall confidence
        if field_evidence:
            avg_consensus = sum(f.consensus_score for f in field_evidence) / len(field_evidence)
        else:
            avg_consensus = 0.5

        # GPS compliance score
        gps_score = self._calculate_gps_score(
            original_count, derivative_count, authored_count,
            contested_count, consensus_count, entity.source_count
        )

        # Determine if human review needed
        needs_review = contested_count > 0 and avg_consensus < 0.6
        review_reason = None
        if needs_review:
            contested_fields = [f.field_name for f in field_evidence if f.is_contested]
            review_reason = f"Contested fields: {', '.join(contested_fields)}"

        result = EvidenceScore(
            entity_id=entity.entity_id,
            field_evidence=field_evidence,
            overall_confidence=min(1.0, entity.cluster_confidence * avg_consensus),
            gps_compliance_score=gps_score,
            original_source_count=original_count,
            derivative_source_count=derivative_count,
            authored_source_count=authored_count,
            requires_human_review=needs_review,
            review_reason=review_reason,
        )

        trace.add_event(
            TraceEventType.EVIDENCE_VERIFIED,
            AgentRole.VERIFIER,
            f"Verified entity {entity.entity_id}: confidence={result.overall_confidence:.2f}, GPS={gps_score:.2f}",
            {
                "entity_id": entity.entity_id,
                "confidence": result.overall_confidence,
                "gps_score": gps_score,
                "contested_fields": contested_count,
                "requires_review": needs_review,
            },
            duration_ms=(time.time() - start_time) * 1000,
        )

        return result

    def _classify_source(self, record: dict) -> str:
        """Classify a source as original, derivative, or authored."""
        source = record.get("source", "").lower()
        record_type = record.get("record_type", "").lower()

        if any(kw in source for kw in ["parish", "civil", "church", "archive"]) and (
            "image" in record_type or "original" in record_type
        ):
            return "original"

        if any(kw in source for kw in ["tree", "wikitree", "gedcom", "compilation"]):
            return "authored"

        return "derivative"

    def _evaluate_fields(self, records: list[dict]) -> list[FieldEvidence]:
        """Evaluate evidence for all fields across records."""
        # Source weights
        source_weights = {"original": 3.0, "derivative": 2.0, "authored": 1.0}

        # Collect all field values
        field_values: dict[str, list[dict]] = {}

        for record in records:
            source_type = self._classify_source(record)
            confidence = record.get("confidence_hint", 0.5)
            weight = source_weights.get(source_type, 1.0) * confidence

            fields = record.get("extracted_fields", {})
            for field_name, value in fields.items():
                if value is None:
                    continue
                if field_name not in field_values:
                    field_values[field_name] = []
                field_values[field_name].append({
                    "value": value,
                    "source": record.get("source", "unknown"),
                    "confidence": confidence,
                    "source_type": source_type,
                    "weight": weight,
                })

        # Build field evidence
        results = []
        for field_name, values in field_values.items():
            evidence = self._build_field_evidence(field_name, values)
            results.append(evidence)

        return results

    def _build_field_evidence(self, field_name: str, values: list[dict]) -> FieldEvidence:
        """Build field evidence from collected values."""
        # Group by normalized value
        value_weights: dict[str, float] = {}
        for v in values:
            key = str(v["value"]).lower().strip()
            value_weights[key] = value_weights.get(key, 0) + v["weight"]

        sorted_values = sorted(value_weights.items(), key=lambda x: -x[1])

        if len(sorted_values) == 0:
            return FieldEvidence(field_name=field_name)

        total_weight = sum(w for _, w in sorted_values)
        top_weight = sorted_values[0][1]
        consensus_score = top_weight / total_weight if total_weight > 0 else 0

        # Find original value for best
        best_value = None
        for v in sorted(values, key=lambda x: -x["weight"]):
            if str(v["value"]).lower().strip() == sorted_values[0][0]:
                best_value = v["value"]
                break

        is_contested = len(sorted_values) > 1 and consensus_score < 0.7
        is_consensus = len(sorted_values) == 1 or consensus_score >= 0.7

        return FieldEvidence(
            field_name=field_name,
            values=values,
            best_value=best_value,
            consensus_score=consensus_score,
            is_contested=is_contested,
            is_consensus=is_consensus,
        )

    def _calculate_gps_score(
        self,
        original: int,
        derivative: int,
        authored: int,
        contested: int,
        consensus: int,
        source_count: int,
    ) -> float:
        """Calculate GPS compliance score."""
        # Factor 1: Source quality (original > derivative > authored)
        total_sources = original + derivative + authored
        if total_sources == 0:
            quality_factor = 0.0
        else:
            quality_factor = (original * 1.0 + derivative * 0.7 + authored * 0.4) / total_sources

        # Factor 2: Evidence agreement
        total_fields = contested + consensus
        if total_fields == 0:
            agreement_factor = 0.5
        else:
            agreement_factor = consensus / total_fields

        # Factor 3: Multi-source corroboration
        corroboration_factor = min(1.0, source_count / 3)

        # Weighted combination
        return (quality_factor * 0.4 + agreement_factor * 0.4 + corroboration_factor * 0.2)


# ─────────────────────────────────────────────────────────────────────────────
# SynthesisAgent
# ─────────────────────────────────────────────────────────────────────────────


class SynthesisAgent:
    """Produces final synthesized output (GPS Pillar 4).

    Responsibilities:
    - Merge best estimates from verified evidence
    - Document contested fields
    - Generate GPS-compliant citations
    - Recommend next steps
    """

    def synthesize(
        self,
        entity: ResolvedEntity,
        evidence: EvidenceScore,
        records: list[dict],
        trace: RunTrace,
    ) -> Synthesis:
        """Synthesize final output for an entity.

        Args:
            entity: ResolvedEntity
            evidence: EvidenceScore from verifier
            records: Source records
            trace: RunTrace for observability

        Returns:
            Synthesis with best estimate and recommendations
        """
        start_time = time.time()

        # Build best estimate from evidence
        best_estimate = {}
        contested_fields = []
        consensus_fields = []

        for field_ev in evidence.field_evidence:
            if field_ev.best_value is not None:
                best_estimate[field_ev.field_name] = field_ev.best_value

            if field_ev.is_contested:
                contested_fields.append(ContestedFieldOutput(
                    field=field_ev.field_name,
                    best_value=field_ev.best_value,
                    alternative_values=[
                        {"value": v["value"], "source": v["source"], "confidence": v["confidence"]}
                        for v in field_ev.values
                    ],
                    consensus_score=field_ev.consensus_score,
                ))
            elif field_ev.is_consensus:
                consensus_fields.append(field_ev.field_name)

        # Generate citations
        citations = self._generate_citations(records)

        # Generate next steps
        next_steps = self._generate_next_steps(evidence, entity)

        # Determine GPS compliance
        gps_compliant = (
            evidence.gps_compliance_score >= 0.7 and
            not evidence.requires_human_review and
            evidence.original_source_count > 0
        )

        gps_notes = None
        if not gps_compliant:
            notes = []
            if evidence.original_source_count == 0:
                notes.append("No original sources")
            if evidence.requires_human_review:
                notes.append(f"Needs review: {evidence.review_reason}")
            if evidence.gps_compliance_score < 0.7:
                notes.append(f"Low GPS score: {evidence.gps_compliance_score:.2f}")
            gps_notes = "; ".join(notes)

        result = Synthesis(
            entity_id=entity.entity_id,
            best_estimate=best_estimate,
            supporting_citations=citations,
            contested_fields=contested_fields,
            consensus_fields=consensus_fields,
            overall_confidence=evidence.overall_confidence,
            next_steps=next_steps,
            gps_compliant=gps_compliant,
            gps_notes=gps_notes,
        )

        trace.add_event(
            TraceEventType.SYNTHESIS_COMPLETED,
            AgentRole.SYNTHESIZER,
            f"Synthesis complete: GPS={gps_compliant}, confidence={result.overall_confidence:.2f}",
            {
                "entity_id": entity.entity_id,
                "gps_compliant": gps_compliant,
                "confidence": result.overall_confidence,
                "contested_count": len(contested_fields),
            },
            duration_ms=(time.time() - start_time) * 1000,
        )

        return result

    def _generate_citations(self, records: list[dict]) -> list[str]:
        """Generate GPS-compliant citations for records."""
        citations = []
        for record in records:
            parts = [record.get("source", "Unknown")]
            if record.get("record_id"):
                parts.append(f"record {record['record_id']}")
            if record.get("record_type"):
                parts.append(f"({record['record_type']})")
            if record.get("url"):
                parts.append(f"<{record['url']}>")
            citations.append(", ".join(parts))
        return list(set(citations))

    def _generate_next_steps(
        self,
        evidence: EvidenceScore,
        entity: ResolvedEntity,
    ) -> list[str]:
        """Generate recommended next steps."""
        steps = []

        if evidence.overall_confidence < 0.7:
            steps.append("Expand search to additional record types")

        if evidence.original_source_count == 0:
            steps.append("Seek original sources (parish records, civil registers)")

        if evidence.requires_human_review:
            steps.append(f"Manual review needed: {evidence.review_reason}")

        if entity.source_count < 2:
            steps.append("Corroborate with additional independent sources")

        if not steps:
            steps.append("Evidence sufficient for GPS compliance")

        return steps


# ─────────────────────────────────────────────────────────────────────────────
# BudgetPolicyAgent
# ─────────────────────────────────────────────────────────────────────────────


class BudgetPolicyAgent:
    """Manages resource allocation and budget enforcement.

    Responsibilities:
    - Validate search plans against budget constraints
    - Adjust source allocation based on results
    - Track resource consumption
    """

    def __init__(
        self,
        max_total_seconds: float = 300.0,
        max_sources: int = 20,
        max_results: int = 500,
    ) -> None:
        self.max_total_seconds = max_total_seconds
        self.max_sources = max_sources
        self.max_results = max_results

    def validate_plan(self, plan: SearchPlan, trace: RunTrace) -> tuple[bool, str | None]:
        """Validate a search plan against budget constraints.

        Returns:
            (is_valid, error_message)
        """
        # Check total budget
        if plan.total_budget_seconds > self.max_total_seconds:
            return False, f"Total budget {plan.total_budget_seconds}s exceeds max {self.max_total_seconds}s"

        # Check source count
        if len(plan.source_budgets) > self.max_sources:
            return False, f"Source count {len(plan.source_budgets)} exceeds max {self.max_sources}"

        # Check total max results
        total_results = sum(b.max_results for b in plan.source_budgets)
        if total_results > self.max_results:
            return False, f"Total results {total_results} exceeds max {self.max_results}"

        trace.add_event(
            TraceEventType.BUDGET_CHECK,
            AgentRole.BUDGET_POLICY,
            "Plan validated against budget constraints",
            {
                "budget_seconds": plan.total_budget_seconds,
                "source_count": len(plan.source_budgets),
                "max_results": total_results,
            },
        )

        return True, None

    def adjust_plan(self, plan: SearchPlan) -> SearchPlan:
        """Adjust a plan to fit within budget constraints."""
        adjusted = plan.model_copy()

        # Trim sources if needed
        if len(adjusted.source_budgets) > self.max_sources:
            adjusted.source_budgets = adjusted.source_budgets[:self.max_sources]

        # Reduce per-source results if total exceeds max
        total_results = sum(b.max_results for b in adjusted.source_budgets)
        if total_results > self.max_results and adjusted.source_budgets:
            factor = self.max_results / total_results
            for budget in adjusted.source_budgets:
                budget.max_results = max(1, int(budget.max_results * factor))

        # Cap total budget
        adjusted.total_budget_seconds = min(
            adjusted.total_budget_seconds,
            self.max_total_seconds
        )

        return adjusted


# ─────────────────────────────────────────────────────────────────────────────
# Manager (Orchestrates the Pipeline)
# ─────────────────────────────────────────────────────────────────────────────


class AgentPipelineManager:
    """Orchestrates the full agent pipeline.

    Manages the flow:
    QueryPlannerAgent → SourceExecutor → EntityResolverAgent →
    EvidenceVerifierAgent → SynthesisAgent

    With BudgetPolicyAgent oversight and full run traces.
    """

    def __init__(
        self,
        router: SearchRouter,
        budget_policy: BudgetPolicyAgent | None = None,
    ) -> None:
        self.router = router
        self.planner = QueryPlannerAgent(router)
        self.executor = SourceExecutor(router)
        self.resolver = EntityResolverAgent()
        self.verifier = EvidenceVerifierAgent()
        self.synthesizer = SynthesisAgent()
        self.budget_policy = budget_policy or BudgetPolicyAgent()

    async def run(
        self,
        surname: str,
        given_name: str | None = None,
        birth_year: int | None = None,
        birth_place: str | None = None,
        death_year: int | None = None,
        record_types: list[str] | None = None,
        region: str | None = None,
    ) -> ManagerResponse:
        """Run the full agent pipeline.

        Args:
            surname: Family name
            given_name: First/given name
            birth_year: Approximate birth year
            birth_place: Birth location
            death_year: Approximate death year
            record_types: Types of records to search
            region: Geographic region

        Returns:
            ManagerResponse with synthesis and full trace
        """
        trace = RunTrace(
            original_query={
                "surname": surname,
                "given_name": given_name,
                "birth_year": birth_year,
                "birth_place": birth_place,
                "death_year": death_year,
                "record_types": record_types,
                "region": region,
            }
        )

        try:
            # Step 1: Create search plan
            plan = self.planner.create_plan(
                surname=surname,
                given_name=given_name,
                birth_year=birth_year,
                birth_place=birth_place,
                death_year=death_year,
                record_types=record_types,
                region=region,
            )

            trace.add_event(
                TraceEventType.PLAN_CREATED,
                AgentRole.PLANNER,
                f"Created search plan with {len(plan.source_budgets)} sources",
                {"plan_id": plan.plan_id, "sources": plan.get_sources_by_priority()},
            )
            trace.search_plan = plan

            # Step 2: Validate against budget
            valid, error = self.budget_policy.validate_plan(plan, trace)
            if not valid:
                plan = self.budget_policy.adjust_plan(plan)
                trace.add_event(
                    TraceEventType.BUDGET_CHECK,
                    AgentRole.BUDGET_POLICY,
                    f"Plan adjusted: {error}",
                    {"adjusted": True},
                )

            # Step 3: Execute search
            execution = await self.executor.execute(plan, trace)
            trace.execution_result = execution
            trace.total_sources_searched = len(execution.sources_searched)
            trace.total_records_found = execution.total_records

            if execution.total_records == 0:
                trace.finalize(success=True)
                return ManagerResponse(
                    trace=trace,
                    success=True,
                    all_syntheses=[],
                )

            # Step 4: Resolve entities
            clusters = self.resolver.resolve(execution, trace)
            trace.entity_clusters = clusters
            trace.total_entities_resolved = clusters.total_entities

            if clusters.total_entities == 0:
                trace.finalize(success=True)
                return ManagerResponse(
                    trace=trace,
                    success=True,
                    all_syntheses=[],
                )

            # Step 5 & 6: Verify and synthesize each entity
            all_syntheses = []
            records_by_fp = self._group_records_by_fingerprint(execution.all_records)

            for entity in clusters.entities:
                entity_records = records_by_fp.get(entity.fingerprint, [])

                # Verify evidence
                evidence = self.verifier.verify(entity, entity_records, trace)
                trace.evidence_scores.append(evidence)

                # Synthesize output
                synthesis = self.synthesizer.synthesize(
                    entity, evidence, entity_records, trace
                )
                all_syntheses.append(synthesis)

            # Primary synthesis is highest confidence
            primary = all_syntheses[0] if all_syntheses else None
            trace.synthesis = primary

            trace.finalize(success=True)

            return ManagerResponse(
                synthesis=primary,
                all_syntheses=all_syntheses,
                trace=trace,
                success=True,
                requires_human_decision=any(
                    s.contested_fields for s in all_syntheses
                ),
            )

        except Exception as e:
            trace.add_event(
                TraceEventType.ERROR,
                AgentRole.MANAGER,
                f"Pipeline error: {str(e)}",
                error=str(e),
            )
            trace.finalize(success=False, error=str(e))

            return ManagerResponse(
                trace=trace,
                success=False,
                error=str(e),
            )

    def _group_records_by_fingerprint(self, records: list[dict]) -> dict[str, list[dict]]:
        """Group records by fingerprint."""
        groups: dict[str, list[dict]] = {}

        for record in records:
            fp = self.resolver._compute_fingerprint(record)
            if fp:
                if fp not in groups:
                    groups[fp] = []
                groups[fp].append(record)

        return groups
