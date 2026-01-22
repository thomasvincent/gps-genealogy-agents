"""Tests for Probabilistic Linkage module."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from gps_agents.genealogy_crawler.linkage import (
    ClusterDecision,
    ComparisonType,
    EntityCluster,
    FeatureComparison,
    LinkageDecision,
    LinkageProvenance,
    LinkageResult,
    MatchCandidate,
    MatchConfidence,
    CensusComparisonConfig,
    VitalRecordComparisonConfig,
)


class TestFeatureComparison:
    """Tests for FeatureComparison model."""

    def test_create_comparison(self):
        """Test basic comparison creation."""
        comparison = FeatureComparison(
            feature_name="surname",
            comparison_type=ComparisonType.JARO_WINKLER,
            value_left="Durham",
            value_right="Denham",
            similarity_score=0.78,
            match_weight=0.8,
            non_match_weight=-0.5,
        )

        assert comparison.feature_name == "surname"
        assert comparison.similarity_score == 0.78
        assert not comparison.is_match  # < 0.8

    def test_is_match_threshold(self):
        """Test match threshold at 0.8."""
        high_sim = FeatureComparison(
            feature_name="surname",
            comparison_type=ComparisonType.EXACT,
            value_left="Durham",
            value_right="Durham",
            similarity_score=1.0,
            match_weight=2.0,
            non_match_weight=-2.0,
        )
        assert high_sim.is_match is True

        low_sim = FeatureComparison(
            feature_name="surname",
            comparison_type=ComparisonType.JARO_WINKLER,
            value_left="Durham",
            value_right="Smith",
            similarity_score=0.3,
            match_weight=-1.0,
            non_match_weight=1.0,
        )
        assert low_sim.is_match is False

    def test_contributes_evidence(self):
        """Test evidence contribution check."""
        with_values = FeatureComparison(
            feature_name="birth_year",
            comparison_type=ComparisonType.NUMERIC_DISTANCE,
            value_left=1927,
            value_right=1928,
            similarity_score=0.9,
            match_weight=1.0,
            non_match_weight=-0.5,
        )
        assert with_values.contributes_evidence is True

        with_null = FeatureComparison(
            feature_name="birth_year",
            comparison_type=ComparisonType.NUMERIC_DISTANCE,
            value_left=None,
            value_right=1928,
            similarity_score=0.5,
            match_weight=0.0,
            non_match_weight=0.0,
        )
        assert with_null.contributes_evidence is False


class TestMatchCandidate:
    """Tests for MatchCandidate model."""

    @pytest.fixture
    def sample_candidate(self):
        """Create a sample match candidate."""
        comparisons = [
            FeatureComparison(
                feature_name="surname",
                comparison_type=ComparisonType.JARO_WINKLER,
                value_left="Durham",
                value_right="Durham",
                similarity_score=1.0,
                match_weight=2.5,
                non_match_weight=-2.5,
            ),
            FeatureComparison(
                feature_name="given_name",
                comparison_type=ComparisonType.JARO_WINKLER,
                value_left="Archie",
                value_right="Archer",
                similarity_score=0.85,
                match_weight=1.5,
                non_match_weight=-1.0,
            ),
            FeatureComparison(
                feature_name="birth_year",
                comparison_type=ComparisonType.NUMERIC_DISTANCE,
                value_left=1927,
                value_right=1927,
                similarity_score=1.0,
                match_weight=2.0,
                non_match_weight=-2.0,
            ),
        ]

        return MatchCandidate(
            record_id_left=uuid4(),
            record_id_right=uuid4(),
            name_left="Archie Durham",
            name_right="Archer Durham",
            feature_comparisons=comparisons,
            overall_probability=0.92,
            confidence=MatchConfidence.PROBABLE_MATCH,
        )

    def test_match_weight_sum(self, sample_candidate):
        """Test sum of match weights."""
        assert sample_candidate.match_weight_sum == 6.0  # 2.5 + 1.5 + 2.0

    def test_non_match_weight_sum(self, sample_candidate):
        """Test sum of non-match weights."""
        assert sample_candidate.non_match_weight_sum == -5.5  # -2.5 + -1.0 + -2.0

    def test_feature_summary(self, sample_candidate):
        """Test feature summary dictionary."""
        summary = sample_candidate.feature_summary
        assert summary["surname"] == 1.0
        assert summary["given_name"] == 0.85
        assert summary["birth_year"] == 1.0

    def test_strongest_evidence(self, sample_candidate):
        """Test getting strongest evidence features."""
        strongest = sample_candidate.get_strongest_evidence()
        assert len(strongest) == 3
        # Should be sorted by match weight descending
        assert strongest[0].feature_name == "surname"
        assert strongest[1].feature_name == "birth_year"


class TestLinkageDecision:
    """Tests for LinkageDecision model."""

    def test_merge_decision(self):
        """Test merge decision creation."""
        decision = LinkageDecision(
            record_id_left=uuid4(),
            record_id_right=uuid4(),
            decision=ClusterDecision.MERGE,
            probability=0.95,
            confidence=MatchConfidence.DEFINITE_MATCH,
        )

        assert decision.is_merge is True
        assert decision.needs_human_review is False

    def test_review_decision(self):
        """Test decision requiring review."""
        decision = LinkageDecision(
            record_id_left=uuid4(),
            record_id_right=uuid4(),
            decision=ClusterDecision.NEEDS_REVIEW,
            probability=0.65,
            confidence=MatchConfidence.UNCERTAIN,
        )

        assert decision.is_merge is False
        assert decision.needs_human_review is True

    def test_conflict_tracking(self):
        """Test conflict identification in decision."""
        decision = LinkageDecision(
            record_id_left=uuid4(),
            record_id_right=uuid4(),
            decision=ClusterDecision.MERGE,
            probability=0.88,
            confidence=MatchConfidence.PROBABLE_MATCH,
            conflicts_identified=["birth_year differs by 2 years"],
            conflict_resolution="Used source with higher evidence quality",
        )

        assert len(decision.conflicts_identified) == 1
        assert decision.conflict_resolution is not None


class TestEntityCluster:
    """Tests for EntityCluster model."""

    def test_create_cluster(self):
        """Test cluster creation."""
        canonical_id = uuid4()
        member_ids = [canonical_id, uuid4(), uuid4()]

        cluster = EntityCluster(
            canonical_id=canonical_id,
            canonical_name="Archie G Durham",
            member_ids=member_ids,
            internal_cohesion=0.92,
        )

        assert cluster.size == 3
        assert not cluster.is_singleton

    def test_singleton_cluster(self):
        """Test singleton cluster detection."""
        record_id = uuid4()
        cluster = EntityCluster(
            canonical_id=record_id,
            canonical_name="John Doe",
            member_ids=[record_id],
        )

        assert cluster.is_singleton is True
        assert cluster.size == 1

    def test_add_member(self):
        """Test adding a member to cluster."""
        canonical_id = uuid4()
        cluster = EntityCluster(
            canonical_id=canonical_id,
            canonical_name="Archie Durham",
            member_ids=[canonical_id],
        )

        new_id = uuid4()
        decision = LinkageDecision(
            record_id_left=canonical_id,
            record_id_right=new_id,
            decision=ClusterDecision.MERGE,
            probability=0.90,
            confidence=MatchConfidence.PROBABLE_MATCH,
        )

        cluster.add_member(new_id, decision)

        assert cluster.size == 2
        assert new_id in cluster.member_ids
        assert len(cluster.linkage_decisions) == 1


class TestLinkageProvenance:
    """Tests for LinkageProvenance tracking."""

    def test_provenance_creation(self):
        """Test provenance with full tracking."""
        provenance = LinkageProvenance(
            algorithm="splink",
            algorithm_version="3.0.0",
            match_threshold=0.85,
            review_threshold=0.50,
            blocking_rules=[
                "l.surname = r.surname",
                "l.birth_year = r.birth_year",
            ],
            records_compared=1000,
            candidates_generated=50,
            matches_found=25,
            em_iterations=10,
        )

        assert provenance.algorithm == "splink"
        assert provenance.match_threshold == 0.85
        assert len(provenance.blocking_rules) == 2
        assert provenance.em_iterations == 10


class TestLinkageResult:
    """Tests for LinkageResult wrapper."""

    def test_success_result(self):
        """Test successful linkage result."""
        clusters = [
            EntityCluster(
                canonical_id=uuid4(),
                canonical_name="Archie Durham",
                member_ids=[uuid4(), uuid4()],
            ),
            EntityCluster(
                canonical_id=uuid4(),
                canonical_name="Ruth Durham",
                member_ids=[uuid4()],
            ),
        ]

        provenance = LinkageProvenance(
            algorithm="splink",
            match_threshold=0.85,
        )

        result = LinkageResult.success_result(
            clusters=clusters,
            provenance=provenance,
        )

        assert result.success is True
        assert result.total_clusters_output == 2
        assert result.total_records_input == 3  # 2 + 1
        assert result.singleton_clusters == 1

    def test_reduction_ratio(self):
        """Test record reduction calculation."""
        clusters = [
            EntityCluster(
                canonical_id=uuid4(),
                canonical_name="Person",
                member_ids=[uuid4() for _ in range(5)],
            ),
        ]

        provenance = LinkageProvenance(
            algorithm="splink",
            match_threshold=0.85,
        )

        result = LinkageResult.success_result(
            clusters=clusters,
            provenance=provenance,
        )

        # 5 records -> 1 cluster = 80% reduction
        assert result.reduction_ratio == pytest.approx(0.8)

    def test_failure_result(self):
        """Test failed linkage result."""
        provenance = LinkageProvenance(
            algorithm="splink",
            match_threshold=0.85,
        )

        result = LinkageResult.failure_result(
            error="Splink not installed",
            provenance=provenance,
        )

        assert result.success is False
        assert result.error == "Splink not installed"


class TestCensusComparisonConfig:
    """Tests for CensusComparisonConfig."""

    def test_default_config(self):
        """Test default census configuration."""
        config = CensusComparisonConfig()

        assert config.config_name == "us_census_linkage"
        assert config.match_threshold == 0.85
        assert len(config.blocking_rules) > 0
        assert len(config.field_comparisons) > 0

    def test_field_comparisons(self):
        """Test that expected fields are configured."""
        config = CensusComparisonConfig()
        field_names = [fc.field_name for fc in config.field_comparisons]

        assert "surname" in field_names
        assert "given_name" in field_names
        assert "birth_year" in field_names
        assert "birth_place" in field_names
        assert "sex" in field_names

    def test_critical_fields(self):
        """Test critical field marking."""
        config = CensusComparisonConfig()

        surname_comp = next(
            fc for fc in config.field_comparisons if fc.field_name == "surname"
        )
        assert surname_comp.is_critical is True

        sex_comp = next(
            fc for fc in config.field_comparisons if fc.field_name == "sex"
        )
        assert sex_comp.is_critical is True

    def test_splink_settings(self):
        """Test Splink settings generation."""
        config = CensusComparisonConfig()
        settings = config.get_splink_settings()

        assert settings["link_type"] == "dedupe_only"
        assert settings["unique_id_column_name"] == "id"
        assert "comparisons" in settings


class TestVitalRecordComparisonConfig:
    """Tests for VitalRecordComparisonConfig."""

    def test_default_config(self):
        """Test default vital record configuration."""
        config = VitalRecordComparisonConfig()

        assert config.config_name == "vital_records_linkage"
        assert len(config.blocking_rules) > 0

    def test_has_parent_comparisons(self):
        """Test that parent name comparisons exist."""
        config = VitalRecordComparisonConfig()
        field_names = [fc.field_name for fc in config.field_comparisons]

        assert "father_name" in field_names
        assert "mother_name" in field_names


class TestMatchConfidence:
    """Tests for MatchConfidence enum."""

    def test_confidence_levels(self):
        """Test confidence level values."""
        assert MatchConfidence.DEFINITE_MATCH.value == "definite_match"
        assert MatchConfidence.PROBABLE_MATCH.value == "probable_match"
        assert MatchConfidence.POSSIBLE_MATCH.value == "possible_match"
        assert MatchConfidence.UNCERTAIN.value == "uncertain"
        assert MatchConfidence.PROBABLE_NON_MATCH.value == "probable_non_match"
        assert MatchConfidence.DEFINITE_NON_MATCH.value == "definite_non_match"


class TestComparisonType:
    """Tests for ComparisonType enum."""

    def test_comparison_types(self):
        """Test comparison type values."""
        assert ComparisonType.EXACT.value == "exact"
        assert ComparisonType.JARO_WINKLER.value == "jaro_winkler"
        assert ComparisonType.SOUNDEX.value == "soundex"
        assert ComparisonType.NUMERIC_DISTANCE.value == "numeric_distance"
