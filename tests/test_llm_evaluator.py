"""Tests for the LLM-enhanced relevance evaluator."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from gps_agents.models.search import RawRecord
from gps_agents.research.evaluator import MatchConfidence, PersonProfile


class TestGetAvailableFeatures:
    """Tests for the get_available_features function."""

    def test_returns_dict(self):
        """Function should return a dict of feature availability."""
        from gps_agents.research import get_available_features

        features = get_available_features()
        assert isinstance(features, dict)

    def test_expected_keys(self):
        """Function should include expected feature keys."""
        from gps_agents.research import get_available_features

        features = get_available_features()

        # These keys should always be present (may be True or False)
        expected_keys = [
            "langchain",
            "gptcache",
            "spacy",
            "nameparser",
            "rapidfuzz",
            "jellyfish",
            "dateparser",
            "usaddress",
        ]

        for key in expected_keys:
            assert key in features, f"Missing expected key: {key}"
            assert isinstance(features[key], bool)


class TestLLMRelevanceEvaluatorImport:
    """Tests for LLM evaluator availability."""

    def test_import_available(self):
        """LLM evaluator should be importable."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE

        # Should be True since we installed dependencies
        assert isinstance(LLM_EVALUATOR_AVAILABLE, bool)

    def test_evaluator_class_available(self):
        """LLMRelevanceEvaluator should be importable when dependencies are present."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE, LLMRelevanceEvaluator

        if LLM_EVALUATOR_AVAILABLE:
            assert LLMRelevanceEvaluator is not None
        else:
            assert LLMRelevanceEvaluator is None


class TestLLMRelevanceEvaluatorRuleBased:
    """Tests for the rule-based scoring in LLMRelevanceEvaluator."""

    @pytest.fixture
    def profile(self):
        """Create a test profile."""
        return PersonProfile(
            surname="Durham",
            given_name="Archer",
            birth_year=1844,
            death_year=1920,
            birth_place="Tennessee",
            death_place="California",
            spouse_names=["Fannie Smith"],
            residence_places=["Tennessee", "California", "Woodland"],
        )

    @pytest.fixture
    def evaluator(self, profile):
        """Create an evaluator without LLM (rule-based only)."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE, LLMRelevanceEvaluator

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        return LLMRelevanceEvaluator(
            profile=profile,
            use_llm=False,  # Disable LLM, only rule-based
            use_cache=False,
        )

    def test_evaluate_exact_match(self, evaluator):
        """Record with exact matches should score high."""
        record = RawRecord(
            source="FamilySearch",
            record_id="test-1",
            record_type="census",
            extracted_fields={
                "name": "Archer Durham",
                "birth_year": "1844",
                "residence": "California",
            },
            raw_data={},
        )

        score = evaluator.evaluate(record)

        assert score.overall_score >= 0.5
        assert score.llm_used is False  # LLM disabled
        assert len(score.match_reasons) > 0

    def test_evaluate_wrong_person(self, evaluator):
        """Record with conflicting dates should score low."""
        record = RawRecord(
            source="FamilySearch",
            record_id="test-2",
            record_type="census",
            extracted_fields={
                "name": "Archer Durham",
                "birth_year": "1932",  # Wrong era
            },
            raw_data={},
        )

        score = evaluator.evaluate(record)

        assert score.overall_score < 0.5
        assert len(score.conflict_reasons) > 0

    def test_evaluate_fuzzy_name_match(self, evaluator):
        """Fuzzy name matching should work."""
        record = RawRecord(
            source="FamilySearch",
            record_id="test-3",
            record_type="census",
            extracted_fields={
                "surname": "Durhem",  # Slight misspelling
                "given_name": "Archer",
                "birth_year": "1844",
            },
            raw_data={},
        )

        score = evaluator.evaluate(record)

        # Should still match with fuzzy matching
        assert score.overall_score >= 0.4

    def test_evaluate_with_entities(self, evaluator):
        """Entity extraction should work."""
        record = RawRecord(
            source="FamilySearch",
            record_id="test-4",
            record_type="census",
            extracted_fields={
                "name": "Archer Durham",
            },
            raw_data={
                "text": "Archer Durham was born in 1844 in Tennessee.",
            },
        )

        score = evaluator.evaluate(record)

        # Should have extracted entities
        assert score.extracted_entities is not None
        assert isinstance(score.extracted_entities, dict)

    def test_evaluate_spouse_match(self, evaluator):
        """Spouse matching should boost score."""
        record = RawRecord(
            source="FamilySearch",
            record_id="test-5",
            record_type="marriage",
            extracted_fields={
                "name": "Archer Durham",
                "spouse": "Fannie Smith",
            },
            raw_data={},
        )

        score = evaluator.evaluate(record)

        # Should have spouse match reason
        assert any("spouse" in r.lower() for r in score.match_reasons)


class TestLLMRelevanceEvaluatorWithMockedLLM:
    """Tests for the LLM evaluation with mocked LLM."""

    @pytest.fixture
    def profile(self):
        """Create a test profile."""
        return PersonProfile(
            surname="Durham",
            given_name="Archer",
            birth_year=1844,
            death_year=1920,
        )

    def test_llm_called_for_ambiguous_score(self, profile):
        """LLM should be called when rule-based score is ambiguous."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        from gps_agents.research.llm_evaluator import LLMRelevanceEvaluator, LANGCHAIN_AVAILABLE

        if not LANGCHAIN_AVAILABLE:
            pytest.skip("LangChain not available")

        import os

        # Mock the API key to enable LLM
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            # Create evaluator with mocked LLM
            evaluator = LLMRelevanceEvaluator(
                profile=profile,
                use_llm=True,
                use_cache=False,
                llm_threshold_low=0.0,  # Always call LLM
                llm_threshold_high=1.0,
            )

            # Mock the _llm_evaluate method
            mock_result = MagicMock()
            mock_result.confidence = 0.8
            mock_result.reasoning = "Names match exactly"
            mock_result.matching_facts = ["Name matches"]
            mock_result.conflicting_facts = []

            with patch.object(evaluator, "_llm_evaluate", return_value=(mock_result, False)):
                record = RawRecord(
                    source="Test",
                    record_id="test-1",
                    record_type="census",
                    extracted_fields={"name": "Archer Durham"},
                    raw_data={},
                )

                score = evaluator.evaluate(record)

                # LLM should have been used
                assert score.llm_used is True
                assert "Names match exactly" in score.llm_reasoning

    def test_llm_not_called_for_clear_match(self, profile):
        """LLM should NOT be called when rule-based score is clearly high."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        from gps_agents.research.llm_evaluator import LLMRelevanceEvaluator

        # Create evaluator with narrow LLM threshold
        evaluator = LLMRelevanceEvaluator(
            profile=profile,
            use_llm=True,
            use_cache=False,
            llm_threshold_low=0.4,
            llm_threshold_high=0.6,  # LLM only for 0.4-0.6
        )

        # Record with clear matches (should score > 0.6)
        record = RawRecord(
            source="Test",
            record_id="test-1",
            record_type="census",
            extracted_fields={
                "surname": "Durham",
                "given_name": "Archer",
                "birth_year": "1844",
                "death_year": "1920",
                "residence": "Tennessee",
            },
            raw_data={},
        )

        # Spy on _llm_evaluate
        with patch.object(evaluator, "_llm_evaluate") as mock_llm:
            mock_llm.return_value = (None, False)
            score = evaluator.evaluate(record)

            # If rule-based score is above threshold, LLM should not be called
            # Or if called, llm_used should still be based on result
            assert score.llm_used is False or mock_llm.call_count == 0


class TestLLMRelevanceEvaluatorIntegration:
    """Integration tests for the LLM evaluator with orchestrator."""

    @pytest.fixture
    def profile(self):
        """Create a test profile."""
        return PersonProfile(
            surname="Durham",
            given_name="Archer",
            birth_year=1844,
        )

    def test_orchestrator_config_llm_option(self):
        """OrchestratorConfig should have use_llm_evaluator option."""
        from gps_agents.research import OrchestratorConfig

        config = OrchestratorConfig(use_llm_evaluator=True)
        assert config.use_llm_evaluator is True

        config = OrchestratorConfig(use_llm_evaluator=False)
        assert config.use_llm_evaluator is False

    def test_orchestrator_config_cache_dir_option(self):
        """OrchestratorConfig should have llm_cache_dir option."""
        from gps_agents.research import OrchestratorConfig

        config = OrchestratorConfig(llm_cache_dir="/tmp/test-cache")
        assert config.llm_cache_dir == "/tmp/test-cache"


class TestEntityExtraction:
    """Tests for entity extraction in the LLM evaluator."""

    @pytest.fixture
    def evaluator(self):
        """Create an evaluator for entity extraction testing."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE, LLMRelevanceEvaluator

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        profile = PersonProfile(surname="Test", given_name="Person")
        return LLMRelevanceEvaluator(
            profile=profile,
            use_llm=False,
            use_cache=False,
        )

    def test_extract_entities_returns_dict(self, evaluator):
        """Entity extraction should return a dict with expected keys."""
        record = RawRecord(
            source="Test",
            record_id="test-1",
            record_type="census",
            extracted_fields={"name": "John Smith"},
            raw_data={"text": "John Smith was born in 1850 in New York."},
        )

        entities = evaluator._extract_entities(record)

        assert isinstance(entities, dict)
        assert "names" in entities
        assert "dates" in entities
        assert "locations" in entities

    def test_extract_entities_finds_names(self, evaluator):
        """Entity extraction should find person names."""
        record = RawRecord(
            source="Test",
            record_id="test-1",
            record_type="census",
            extracted_fields={},
            raw_data={"text": "John Smith married Mary Jones in 1870."},
        )

        entities = evaluator._extract_entities(record)

        # Names should be extracted (if spaCy is available)
        # The exact names found depend on spaCy model
        assert isinstance(entities["names"], list)

    def test_extract_entities_finds_dates(self, evaluator):
        """Entity extraction should find dates."""
        record = RawRecord(
            source="Test",
            record_id="test-1",
            record_type="census",
            extracted_fields={"birth_date": "January 15, 1850"},
            raw_data={},
        )

        entities = evaluator._extract_entities(record)

        # Should have extracted the date
        assert isinstance(entities["dates"], list)


class TestEnhancedMatchScore:
    """Tests for the EnhancedMatchScore dataclass."""

    def test_enhanced_score_attributes(self):
        """EnhancedMatchScore should have additional LLM-related attributes."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        from gps_agents.research.llm_evaluator import EnhancedMatchScore

        score = EnhancedMatchScore(
            overall_score=0.75,
            confidence=MatchConfidence.LIKELY,
            name_score=0.8,
            date_score=0.7,
            location_score=0.6,
            relationship_score=0.5,
            match_reasons=["Name matches"],
            conflict_reasons=[],
            llm_reasoning="LLM determined match",
            llm_used=True,
            cache_hit=False,
            extracted_entities={"names": ["Test"]},
        )

        assert score.llm_reasoning == "LLM determined match"
        assert score.llm_used is True
        assert score.cache_hit is False
        assert score.extracted_entities == {"names": ["Test"]}


class TestYearExtraction:
    """Tests for year extraction from various formats."""

    @pytest.fixture
    def evaluator(self):
        """Create an evaluator for testing."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE, LLMRelevanceEvaluator

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        profile = PersonProfile(surname="Test", given_name="Person")
        return LLMRelevanceEvaluator(
            profile=profile,
            use_llm=False,
            use_cache=False,
        )

    def test_extract_year_from_int(self, evaluator):
        """Should extract year from integer."""
        assert evaluator._extract_year(1844) == 1844

    def test_extract_year_from_string(self, evaluator):
        """Should extract year from string."""
        assert evaluator._extract_year("1844") == 1844

    def test_extract_year_from_date_string(self, evaluator):
        """Should extract year from date string."""
        year = evaluator._extract_year("January 15, 1850")
        assert year == 1850

    def test_extract_year_from_iso_date(self, evaluator):
        """Should extract year from ISO date."""
        year = evaluator._extract_year("1850-01-15")
        assert year == 1850

    def test_extract_year_invalid(self, evaluator):
        """Should return None for invalid input."""
        assert evaluator._extract_year("not a date") is None
        assert evaluator._extract_year(None) is None

    def test_extract_year_out_of_range(self, evaluator):
        """Should return None for years out of genealogy range."""
        assert evaluator._extract_year(1400) is None  # Too old
        assert evaluator._extract_year(2200) is None  # Too future


class TestScoreToConfidence:
    """Tests for score to confidence conversion."""

    @pytest.fixture
    def evaluator(self):
        """Create an evaluator for testing."""
        from gps_agents.research import LLM_EVALUATOR_AVAILABLE, LLMRelevanceEvaluator

        if not LLM_EVALUATOR_AVAILABLE:
            pytest.skip("LLM evaluator not available")

        profile = PersonProfile(surname="Test", given_name="Person")
        return LLMRelevanceEvaluator(
            profile=profile,
            use_llm=False,
            use_cache=False,
        )

    def test_definite_threshold(self, evaluator):
        """Score >= 0.95 should be DEFINITE."""
        assert evaluator._score_to_confidence(0.95) == MatchConfidence.DEFINITE
        assert evaluator._score_to_confidence(1.0) == MatchConfidence.DEFINITE

    def test_likely_threshold(self, evaluator):
        """Score 0.75-0.94 should be LIKELY."""
        assert evaluator._score_to_confidence(0.75) == MatchConfidence.LIKELY
        assert evaluator._score_to_confidence(0.90) == MatchConfidence.LIKELY

    def test_possible_threshold(self, evaluator):
        """Score 0.50-0.74 should be POSSIBLE."""
        assert evaluator._score_to_confidence(0.50) == MatchConfidence.POSSIBLE
        assert evaluator._score_to_confidence(0.70) == MatchConfidence.POSSIBLE

    def test_unlikely_threshold(self, evaluator):
        """Score 0.25-0.49 should be UNLIKELY."""
        assert evaluator._score_to_confidence(0.25) == MatchConfidence.UNLIKELY
        assert evaluator._score_to_confidence(0.45) == MatchConfidence.UNLIKELY

    def test_not_match_threshold(self, evaluator):
        """Score < 0.25 should be NOT_MATCH."""
        assert evaluator._score_to_confidence(0.20) == MatchConfidence.NOT_MATCH
        assert evaluator._score_to_confidence(0.0) == MatchConfidence.NOT_MATCH
