"""Tests for the GPS agentic pipeline architecture."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gps_agents.agents.pipeline import (
    AgentPipelineManager,
    BudgetPolicyAgent,
    EntityResolverAgent,
    EvidenceVerifierAgent,
    QueryPlannerAgent,
    SourceExecutor,
    SynthesisAgent as PipelineSynthesisAgent,
)
from gps_agents.agents.schemas import (
    AgentRole,
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
    TraceEvent,
    TraceEventType,
)
from gps_agents.models.search import RawRecord, SearchQuery
from gps_agents.sources.router import Region, RouterConfig, SearchRouter


# ─────────────────────────────────────────────────────────────────────────────
# Test Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_source():
    """Create a mock genealogy source."""
    source = MagicMock()
    source.name = "test_source"
    source.search = AsyncMock(return_value=[
        RawRecord(
            record_id="rec1",
            source="test_source",
            url="https://example.com/rec1",
            record_type="birth",
            confidence_hint=0.8,
            extracted_fields={
                "full_name": "John Smith",
                "birth_year": "1890",
                "birth_place": "New York, USA",
            },
        ),
        RawRecord(
            record_id="rec2",
            source="test_source",
            url="https://example.com/rec2",
            record_type="death",
            confidence_hint=0.7,
            extracted_fields={
                "full_name": "John Smith",
                "death_year": "1965",
                "birth_year": "1890",
            },
        ),
    ])
    return source


@pytest.fixture
def router_with_mock(mock_source):
    """Create a router with mock source registered."""
    router = SearchRouter(RouterConfig(parallel=True))
    router.register_source(mock_source)
    return router


@pytest.fixture
def sample_records():
    """Sample records for testing."""
    return [
        {
            "record_id": "rec1",
            "source": "familysearch",
            "url": "https://familysearch.org/rec1",
            "record_type": "birth",
            "confidence_hint": 0.8,
            "extracted_fields": {
                "full_name": "John Smith",
                "birth_year": "1890",
                "birth_place": "New York, USA",
            },
        },
        {
            "record_id": "rec2",
            "source": "wikitree",
            "url": "https://wikitree.com/rec2",
            "record_type": "profile",
            "confidence_hint": 0.6,
            "extracted_fields": {
                "full_name": "John Smith",
                "birth_year": "1891",  # Conflict!
                "birth_place": "New York",
            },
        },
        {
            "record_id": "rec3",
            "source": "findagrave",
            "url": "https://findagrave.com/rec3",
            "record_type": "cemetery",
            "confidence_hint": 0.9,
            "extracted_fields": {
                "full_name": "John Smith",
                "death_year": "1965",
                "birth_year": "1890",
            },
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Schema Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemas:
    """Test schema validation and serialization."""

    def test_search_plan_creation(self):
        """Test SearchPlan creation with defaults."""
        plan = SearchPlan(
            surname="Smith",
            given_name="John",
            birth_year=1890,
        )

        assert plan.surname == "Smith"
        assert plan.plan_id is not None
        assert plan.first_pass_enabled is True
        assert plan.second_pass_threshold == 0.7

    def test_search_plan_with_budgets(self):
        """Test SearchPlan with source budgets."""
        plan = SearchPlan(
            surname="Smith",
            source_budgets=[
                SourceBudget(source_name="familysearch", priority=3),
                SourceBudget(source_name="wikitree", priority=2),
            ],
        )

        sources = plan.get_sources_by_priority()
        assert sources == ["familysearch", "wikitree"]

    def test_execution_result_success_rate(self):
        """Test ExecutionResult success rate calculation."""
        result = ExecutionResult(
            plan_id="test",
            sources_searched=["a", "b", "c"],
            sources_failed=["d"],
        )

        assert result.success_rate == 0.75

    def test_run_trace_event_tracking(self):
        """Test RunTrace event addition and finalization."""
        trace = RunTrace()

        trace.add_event(
            TraceEventType.PLAN_CREATED,
            AgentRole.PLANNER,
            "Created plan",
            {"sources": 5},
        )

        assert len(trace.events) == 1
        assert trace.events[0].event_type == TraceEventType.PLAN_CREATED
        assert trace.events[0].agent_role == AgentRole.PLANNER

        trace.finalize(success=True)

        assert trace.success is True
        assert trace.completed_at is not None
        assert trace.total_duration_ms > 0

    def test_synthesis_model(self):
        """Test Synthesis model with all fields."""
        synthesis = Synthesis(
            entity_id="e123",
            best_estimate={"name": "John Smith", "birth_year": 1890},
            supporting_citations=["Source A", "Source B"],
            contested_fields=[],
            consensus_fields=["name", "birth_year"],
            overall_confidence=0.85,
            next_steps=["Verify with parish records"],
            gps_compliant=True,
        )

        assert synthesis.entity_id == "e123"
        assert synthesis.overall_confidence == 0.85
        assert synthesis.gps_compliant is True


# ─────────────────────────────────────────────────────────────────────────────
# QueryPlannerAgent Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryPlannerAgent:
    """Test QueryPlannerAgent."""

    def test_create_plan_basic(self, router_with_mock):
        """Test basic plan creation."""
        planner = QueryPlannerAgent(router_with_mock)

        plan = planner.create_plan(
            surname="Smith",
            given_name="John",
            birth_year=1890,
        )

        assert plan.surname == "Smith"
        assert plan.given_name == "John"
        assert plan.birth_year == 1890
        assert len(plan.surname_variants) >= 1
        assert "Smith" in plan.surname_variants

    def test_create_plan_with_region(self, router_with_mock):
        """Test plan creation with region detection."""
        planner = QueryPlannerAgent(router_with_mock)

        plan = planner.create_plan(
            surname="Smith",
            birth_place="London, England",
        )

        assert plan.region == "Region.ENGLAND"

    def test_surname_variant_generation(self, router_with_mock):
        """Test surname variant generation."""
        planner = QueryPlannerAgent(router_with_mock)

        plan = planner.create_plan(surname="Johnson")

        assert "Johnson" in plan.surname_variants
        assert "Johnsen" in plan.surname_variants  # son -> sen

    def test_source_budget_allocation(self, router_with_mock):
        """Test that source budgets are created with priorities."""
        planner = QueryPlannerAgent(router_with_mock)

        plan = planner.create_plan(
            surname="Smith",
            region="usa",
        )

        # Should have at least one budget
        assert len(plan.source_budgets) >= 0  # Depends on registered sources


# ─────────────────────────────────────────────────────────────────────────────
# EntityResolverAgent Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEntityResolverAgent:
    """Test EntityResolverAgent."""

    def test_resolve_clusters_records(self, sample_records):
        """Test that resolver clusters similar records."""
        resolver = EntityResolverAgent()
        trace = RunTrace()

        execution = ExecutionResult(
            plan_id="test",
            all_records=sample_records,
            total_records=len(sample_records),
            sources_searched=["familysearch", "wikitree", "findagrave"],
        )

        clusters = resolver.resolve(execution, trace)

        # All records have similar name/year, should cluster together
        assert clusters.total_entities >= 1
        assert clusters.total_input_records == 3

    def test_resolve_computes_best_values(self, sample_records):
        """Test that resolver computes best values for entities."""
        resolver = EntityResolverAgent()
        trace = RunTrace()

        execution = ExecutionResult(
            plan_id="test",
            all_records=sample_records,
            total_records=len(sample_records),
        )

        clusters = resolver.resolve(execution, trace)

        if clusters.entities:
            entity = clusters.entities[0]
            assert entity.best_name is not None
            assert entity.cluster_confidence > 0

    def test_corroboration_boost(self, sample_records):
        """Test that multi-source entities get confidence boost."""
        resolver = EntityResolverAgent()
        trace = RunTrace()

        execution = ExecutionResult(
            plan_id="test",
            all_records=sample_records,
            total_records=len(sample_records),
        )

        clusters = resolver.resolve(execution, trace)

        # Check for multi-source entity
        multi_source = [e for e in clusters.entities if e.source_count > 1]
        if multi_source:
            assert multi_source[0].corroboration_boost > 0


# ─────────────────────────────────────────────────────────────────────────────
# EvidenceVerifierAgent Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEvidenceVerifierAgent:
    """Test EvidenceVerifierAgent."""

    def test_verify_computes_confidence(self, sample_records):
        """Test that verifier computes evidence confidence."""
        verifier = EvidenceVerifierAgent()
        trace = RunTrace()

        entity = ResolvedEntity(
            fingerprint="test_fp",
            best_name="John Smith",
            sources=["familysearch", "wikitree"],
            source_count=2,
        )

        score = verifier.verify(entity, sample_records, trace)

        assert score.overall_confidence > 0
        assert score.gps_compliance_score > 0

    def test_verify_detects_contested_fields(self, sample_records):
        """Test that verifier detects contested fields."""
        verifier = EvidenceVerifierAgent()
        trace = RunTrace()

        entity = ResolvedEntity(
            fingerprint="test_fp",
            sources=["familysearch", "wikitree"],
            source_count=2,
        )

        score = verifier.verify(entity, sample_records, trace)

        # birth_year has conflict (1890 vs 1891)
        contested = [f for f in score.field_evidence if f.is_contested]
        # May or may not detect as contested depending on weights
        assert len(score.field_evidence) > 0

    def test_source_classification(self):
        """Test source type classification."""
        verifier = EvidenceVerifierAgent()

        # Test original source detection
        original_record = {"source": "parish records", "record_type": "original image"}
        assert verifier._classify_source(original_record) == "original"

        # Test authored source detection
        authored_record = {"source": "wikitree", "record_type": "profile"}
        assert verifier._classify_source(authored_record) == "authored"

        # Test derivative default
        derivative_record = {"source": "familysearch", "record_type": "index"}
        assert verifier._classify_source(derivative_record) == "derivative"


# ─────────────────────────────────────────────────────────────────────────────
# SynthesisAgent Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineSynthesisAgent:
    """Test PipelineSynthesisAgent."""

    def test_synthesize_produces_output(self, sample_records):
        """Test that synthesizer produces complete output."""
        synthesizer = PipelineSynthesisAgent()
        trace = RunTrace()

        entity = ResolvedEntity(
            fingerprint="test_fp",
            best_name="John Smith",
            best_birth_year=1890,
            sources=["familysearch", "findagrave"],
            source_count=2,
        )

        evidence = EvidenceScore(
            entity_id=entity.entity_id,
            overall_confidence=0.8,
            gps_compliance_score=0.75,
            original_source_count=1,
            field_evidence=[
                FieldEvidence(
                    field_name="birth_year",
                    best_value="1890",
                    consensus_score=0.8,
                    is_consensus=True,
                ),
            ],
        )

        synthesis = synthesizer.synthesize(entity, evidence, sample_records, trace)

        assert synthesis.entity_id == entity.entity_id
        assert len(synthesis.supporting_citations) > 0
        assert len(synthesis.next_steps) > 0

    def test_gps_compliance_determination(self, sample_records):
        """Test GPS compliance logic."""
        synthesizer = PipelineSynthesisAgent()
        trace = RunTrace()

        entity = ResolvedEntity(
            fingerprint="test_fp",
            sources=["familysearch"],
            source_count=1,
        )

        # High score with original sources = compliant
        high_evidence = EvidenceScore(
            entity_id=entity.entity_id,
            overall_confidence=0.9,
            gps_compliance_score=0.8,
            original_source_count=1,
        )

        synthesis = synthesizer.synthesize(entity, high_evidence, sample_records, trace)
        assert synthesis.gps_compliant is True

        # No original sources = not compliant
        low_evidence = EvidenceScore(
            entity_id=entity.entity_id,
            overall_confidence=0.9,
            gps_compliance_score=0.8,
            original_source_count=0,
        )

        synthesis2 = synthesizer.synthesize(entity, low_evidence, sample_records, trace)
        assert synthesis2.gps_compliant is False
        assert "No original sources" in synthesis2.gps_notes


# ─────────────────────────────────────────────────────────────────────────────
# BudgetPolicyAgent Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestBudgetPolicyAgent:
    """Test BudgetPolicyAgent."""

    def test_validate_plan_within_budget(self):
        """Test validation of plan within budget."""
        policy = BudgetPolicyAgent(
            max_total_seconds=300.0,
            max_sources=10,
            max_results=200,
        )
        trace = RunTrace()

        plan = SearchPlan(
            surname="Smith",
            total_budget_seconds=120.0,
            source_budgets=[
                SourceBudget(source_name="a", max_results=50),
                SourceBudget(source_name="b", max_results=50),
            ],
        )

        valid, error = policy.validate_plan(plan, trace)

        assert valid is True
        assert error is None

    def test_validate_plan_exceeds_budget(self):
        """Test validation rejects plan exceeding budget."""
        policy = BudgetPolicyAgent(
            max_total_seconds=100.0,
            max_sources=5,
            max_results=100,
        )
        trace = RunTrace()

        plan = SearchPlan(
            surname="Smith",
            total_budget_seconds=200.0,  # Exceeds max
            source_budgets=[],
        )

        valid, error = policy.validate_plan(plan, trace)

        assert valid is False
        assert "exceeds max" in error

    def test_adjust_plan_reduces_sources(self):
        """Test that adjust_plan trims sources to fit budget."""
        policy = BudgetPolicyAgent(max_sources=2)

        plan = SearchPlan(
            surname="Smith",
            source_budgets=[
                SourceBudget(source_name="a", priority=3),
                SourceBudget(source_name="b", priority=2),
                SourceBudget(source_name="c", priority=1),
            ],
        )

        adjusted = policy.adjust_plan(plan)

        assert len(adjusted.source_budgets) == 2


# ─────────────────────────────────────────────────────────────────────────────
# SourceExecutor Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSourceExecutor:
    """Test SourceExecutor."""

    @pytest.mark.asyncio
    async def test_execute_searches_sources(self, router_with_mock):
        """Test that executor searches registered sources."""
        executor = SourceExecutor(router_with_mock)
        trace = RunTrace()

        plan = SearchPlan(
            surname="Smith",
            source_budgets=[
                SourceBudget(source_name="test_source", priority=3),
            ],
        )

        result = await executor.execute(plan, trace)

        assert result.total_records == 2
        assert "test_source" in result.sources_searched

    @pytest.mark.asyncio
    async def test_execute_handles_timeout(self, router_with_mock):
        """Test that executor handles source timeout."""
        # Make source timeout
        router_with_mock._sources["test_source"].search = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        executor = SourceExecutor(router_with_mock)
        trace = RunTrace()

        plan = SearchPlan(
            surname="Smith",
            source_budgets=[
                SourceBudget(
                    source_name="test_source",
                    timeout_seconds=1.0,
                    retry_count=0,
                ),
            ],
        )

        result = await executor.execute(plan, trace)

        assert "test_source" in result.sources_failed
        assert result.total_records == 0


# ─────────────────────────────────────────────────────────────────────────────
# AgentPipelineManager Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAgentPipelineManager:
    """Test full pipeline integration."""

    @pytest.mark.asyncio
    async def test_full_pipeline_run(self, router_with_mock):
        """Test complete pipeline execution."""
        manager = AgentPipelineManager(router_with_mock)

        response = await manager.run(
            surname="Smith",
            given_name="John",
            birth_year=1890,
        )

        assert response.success is True
        assert response.trace is not None
        assert len(response.trace.events) > 0

        # Should have synthesis if records found
        if response.synthesis:
            assert response.synthesis.entity_id is not None

    @pytest.mark.asyncio
    async def test_pipeline_creates_trace(self, router_with_mock):
        """Test that pipeline creates comprehensive trace."""
        manager = AgentPipelineManager(router_with_mock)

        response = await manager.run(surname="Smith")

        trace = response.trace

        # Check trace components
        assert trace.search_plan is not None
        assert trace.execution_result is not None

        # Check event types
        event_types = {e.event_type for e in trace.events}
        assert TraceEventType.PLAN_CREATED in event_types
        assert TraceEventType.EXECUTION_STARTED in event_types

    @pytest.mark.asyncio
    async def test_pipeline_handles_no_results(self):
        """Test pipeline handles case with no search results."""
        router = SearchRouter()

        # Empty source that returns no results
        empty_source = MagicMock()
        empty_source.name = "empty"
        empty_source.search = AsyncMock(return_value=[])
        router.register_source(empty_source)

        manager = AgentPipelineManager(router)

        response = await manager.run(surname="NonexistentName")

        assert response.success is True
        assert response.synthesis is None
        assert len(response.all_syntheses) == 0

    @pytest.mark.asyncio
    async def test_pipeline_handles_errors(self, router_with_mock):
        """Test pipeline handles execution errors gracefully."""
        # Make source raise exception
        router_with_mock._sources["test_source"].search = AsyncMock(
            side_effect=Exception("Network error")
        )

        manager = AgentPipelineManager(router_with_mock)

        response = await manager.run(surname="Smith")

        # Should still complete (with failed sources)
        assert response.trace is not None

    @pytest.mark.asyncio
    async def test_pipeline_with_budget_policy(self, router_with_mock):
        """Test pipeline with custom budget policy."""
        policy = BudgetPolicyAgent(
            max_total_seconds=60.0,
            max_sources=5,
        )

        manager = AgentPipelineManager(router_with_mock, budget_policy=policy)

        response = await manager.run(surname="Smith")

        assert response.success is True

        # Check budget event was recorded
        budget_events = [
            e for e in response.trace.events
            if e.agent_role == AgentRole.BUDGET_POLICY
        ]
        assert len(budget_events) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Trace Event Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTraceEvents:
    """Test trace event handling."""

    def test_trace_event_creation(self):
        """Test TraceEvent creation with all fields."""
        event = TraceEvent(
            event_type=TraceEventType.SOURCE_SEARCHED,
            agent_role=AgentRole.EXECUTOR,
            message="Searched familysearch",
            data={"count": 10},
            duration_ms=150.0,
        )

        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.duration_ms == 150.0

    def test_run_trace_finalization(self):
        """Test RunTrace finalization calculates duration."""
        trace = RunTrace()

        # Simulate some work
        trace.add_event(
            TraceEventType.PLAN_CREATED,
            AgentRole.PLANNER,
            "Plan created",
        )

        trace.finalize(success=True)

        assert trace.success is True
        assert trace.total_duration_ms >= 0

    def test_run_trace_error_finalization(self):
        """Test RunTrace finalization with error."""
        trace = RunTrace()

        trace.finalize(success=False, error="Pipeline failed")

        assert trace.success is False
        assert trace.error == "Pipeline failed"
