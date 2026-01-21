"""Tests for the Publishing Manager module."""
from datetime import datetime

import pytest

from gps_agents.genealogy_crawler.publishing import (
    GPSGradeCard,
    GPSPillar,
    GPSPillarScore,
    GPSPillarValidator,
    GPSValidationSummary,
    IntegrityCheckResult,
    IntegrityValidator,
    PublishingManager,
    PublishingPipeline,
    PublishingPlatform,
    PublishingStatus,
    QuorumDecision,
    ResearchNote,
    ReviewerType,
    ReviewIssue,
    ReviewVerdict,
    Severity,
    Uncertainty,
    UnresolvedConflict,
    Verdict,
)


# =============================================================================
# GPS Grade Card Tests
# =============================================================================


class TestGPSPillarScore:
    """Tests for GPSPillarScore model."""

    def test_create_pillar_score(self):
        """Test creating a pillar score."""
        score = GPSPillarScore(
            pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH,
            score=8.5,
            rationale="Good source coverage",
            improvements_needed=["Check parish records"],
        )

        assert score.pillar == GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH
        assert score.score == 8.5
        assert score.rationale == "Good source coverage"
        assert "Check parish records" in score.improvements_needed

    def test_score_bounds(self):
        """Test that score is bounded 1-10."""
        with pytest.raises(ValueError):
            GPSPillarScore(
                pillar=GPSPillar.COMPLETE_CITATIONS,
                score=11.0,
                rationale="Invalid",
            )

        with pytest.raises(ValueError):
            GPSPillarScore(
                pillar=GPSPillar.COMPLETE_CITATIONS,
                score=0.5,
                rationale="Invalid",
            )


class TestGPSGradeCard:
    """Tests for GPSGradeCard model."""

    @pytest.fixture
    def grade_a_card(self) -> GPSGradeCard:
        """Create a Grade A card."""
        return GPSGradeCard(
            subject_id="person_123",
            pillar_scores=[
                GPSPillarScore(pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH, score=9.5, rationale="Excellent"),
                GPSPillarScore(pillar=GPSPillar.COMPLETE_CITATIONS, score=9.2, rationale="Excellent"),
                GPSPillarScore(pillar=GPSPillar.ANALYSIS_AND_CORRELATION, score=9.0, rationale="Excellent"),
                GPSPillarScore(pillar=GPSPillar.CONFLICT_RESOLUTION, score=9.3, rationale="Excellent"),
                GPSPillarScore(pillar=GPSPillar.WRITTEN_CONCLUSION, score=9.0, rationale="Excellent"),
            ],
        )

    @pytest.fixture
    def grade_b_card(self) -> GPSGradeCard:
        """Create a Grade B card."""
        return GPSGradeCard(
            subject_id="person_456",
            pillar_scores=[
                GPSPillarScore(pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH, score=8.5, rationale="Good"),
                GPSPillarScore(pillar=GPSPillar.COMPLETE_CITATIONS, score=8.2, rationale="Good"),
                GPSPillarScore(pillar=GPSPillar.ANALYSIS_AND_CORRELATION, score=8.0, rationale="Good"),
                GPSPillarScore(pillar=GPSPillar.CONFLICT_RESOLUTION, score=8.3, rationale="Good"),
                GPSPillarScore(pillar=GPSPillar.WRITTEN_CONCLUSION, score=8.0, rationale="Good"),
            ],
        )

    @pytest.fixture
    def grade_c_card(self) -> GPSGradeCard:
        """Create a Grade C card."""
        return GPSGradeCard(
            subject_id="person_789",
            pillar_scores=[
                GPSPillarScore(pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH, score=7.5, rationale="Adequate"),
                GPSPillarScore(pillar=GPSPillar.COMPLETE_CITATIONS, score=7.2, rationale="Adequate"),
                GPSPillarScore(pillar=GPSPillar.ANALYSIS_AND_CORRELATION, score=7.0, rationale="Adequate"),
                GPSPillarScore(pillar=GPSPillar.CONFLICT_RESOLUTION, score=7.3, rationale="Adequate"),
                GPSPillarScore(pillar=GPSPillar.WRITTEN_CONCLUSION, score=7.0, rationale="Adequate"),
            ],
        )

    def test_overall_score_calculation(self, grade_a_card):
        """Test overall score is average of pillar scores."""
        expected = (9.5 + 9.2 + 9.0 + 9.3 + 9.0) / 5
        assert abs(grade_a_card.overall_score - expected) < 0.01

    def test_letter_grade_a(self, grade_a_card):
        """Test Grade A classification."""
        assert grade_a_card.letter_grade == "A"
        assert grade_a_card.is_publication_ready is True

    def test_letter_grade_b(self, grade_b_card):
        """Test Grade B classification."""
        assert grade_b_card.letter_grade == "B"
        assert grade_b_card.is_publication_ready is True

    def test_letter_grade_c(self, grade_c_card):
        """Test Grade C classification."""
        assert grade_c_card.letter_grade == "C"
        assert grade_c_card.is_publication_ready is True

    def test_allowed_platforms_grade_a(self, grade_a_card):
        """Test Grade A allows all platforms."""
        allowed = grade_a_card.allowed_platforms
        assert PublishingPlatform.WIKIPEDIA in allowed
        assert PublishingPlatform.WIKIDATA in allowed
        assert PublishingPlatform.WIKITREE in allowed
        assert PublishingPlatform.GITHUB in allowed

    def test_allowed_platforms_grade_b(self, grade_b_card):
        """Test Grade B allows WikiTree and GitHub."""
        allowed = grade_b_card.allowed_platforms
        assert PublishingPlatform.WIKIPEDIA not in allowed
        assert PublishingPlatform.WIKIDATA not in allowed
        assert PublishingPlatform.WIKITREE in allowed
        assert PublishingPlatform.GITHUB in allowed

    def test_allowed_platforms_grade_c(self, grade_c_card):
        """Test Grade C allows only GitHub."""
        allowed = grade_c_card.allowed_platforms
        assert PublishingPlatform.WIKIPEDIA not in allowed
        assert PublishingPlatform.WIKIDATA not in allowed
        assert PublishingPlatform.WIKITREE not in allowed
        assert PublishingPlatform.GITHUB in allowed

    def test_get_pillar_score(self, grade_a_card):
        """Test getting a specific pillar score."""
        score = grade_a_card.get_pillar_score(GPSPillar.COMPLETE_CITATIONS)
        assert score is not None
        assert score.score == 9.2

    def test_get_lowest_pillar(self, grade_a_card):
        """Test finding the lowest scoring pillar."""
        lowest = grade_a_card.get_lowest_pillar()
        assert lowest is not None
        assert lowest.score == 9.0  # Both analysis and conclusion are 9.0


# =============================================================================
# Quorum Decision Tests
# =============================================================================


class TestQuorumDecision:
    """Tests for QuorumDecision model."""

    @pytest.fixture
    def passing_quorum(self) -> QuorumDecision:
        """Create a passing quorum decision."""
        return QuorumDecision(
            logic_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.LOGIC_REVIEWER,
                verdict=Verdict.PASS,
                issues=[],
                rationale="Timeline is consistent",
                reviewer_model="test",
            ),
            source_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.SOURCE_REVIEWER,
                verdict=Verdict.PASS,
                issues=[],
                rationale="Citations are valid",
                reviewer_model="test",
            ),
        )

    @pytest.fixture
    def failing_quorum(self) -> QuorumDecision:
        """Create a failing quorum decision."""
        return QuorumDecision(
            logic_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.LOGIC_REVIEWER,
                verdict=Verdict.FAIL,
                issues=[
                    ReviewIssue(
                        severity=Severity.CRITICAL,
                        description="Death before birth",
                    )
                ],
                rationale="Impossible timeline",
                reviewer_model="test",
            ),
            source_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.SOURCE_REVIEWER,
                verdict=Verdict.PASS,
                issues=[],
                rationale="Citations are valid",
                reviewer_model="test",
            ),
        )

    def test_quorum_reached(self, passing_quorum):
        """Test quorum is reached when both verdicts exist."""
        assert passing_quorum.quorum_reached is True

    def test_quorum_approved_when_both_pass(self, passing_quorum):
        """Test quorum is approved when both reviewers pass."""
        assert passing_quorum.approved is True

    def test_quorum_not_approved_when_one_fails(self, failing_quorum):
        """Test quorum is not approved when one reviewer fails."""
        assert failing_quorum.approved is False

    def test_blocking_issues_collected(self, failing_quorum):
        """Test blocking issues are collected from both reviewers."""
        blocking = failing_quorum.blocking_issues
        assert len(blocking) == 1
        assert blocking[0].severity == Severity.CRITICAL

    def test_all_issues_combined(self, failing_quorum):
        """Test all issues are combined from both reviewers."""
        all_issues = failing_quorum.all_issues
        assert len(all_issues) == 1


# =============================================================================
# GPS Pillar Validator Tests
# =============================================================================


class TestGPSPillarValidator:
    """Tests for GPSPillarValidator."""

    @pytest.fixture
    def validator(self) -> GPSPillarValidator:
        """Create a validator."""
        return GPSPillarValidator()

    def test_validate_exhaustive_search_excellent(self, validator):
        """Test excellent exhaustive search score."""
        result = validator.validate_exhaustive_search(
            source_count=20,
            source_tiers={"tier_0": 10, "tier_1": 7, "tier_2": 3},
        )
        assert result.score >= 9.0
        assert len(result.issues) == 0

    def test_validate_exhaustive_search_poor(self, validator):
        """Test poor exhaustive search score."""
        result = validator.validate_exhaustive_search(
            source_count=2,
            source_tiers={"tier_0": 0, "tier_1": 2, "tier_2": 0},
        )
        assert result.score < 7.0
        assert len(result.issues) > 0

    def test_validate_citations_excellent(self, validator):
        """Test excellent citation score."""
        result = validator.validate_complete_citations(
            citation_count=95,
            total_claims=100,
        )
        assert result.score >= 9.0

    def test_validate_citations_poor(self, validator):
        """Test poor citation score."""
        result = validator.validate_complete_citations(
            citation_count=30,
            total_claims=100,
        )
        assert result.score < 7.0
        assert len(result.issues) > 0

    def test_validate_conflict_resolution_all_resolved(self, validator):
        """Test all conflicts resolved."""
        result = validator.validate_conflict_resolution(
            conflicts_found=5,
            conflicts_resolved=5,
            unresolved_documented=0,
        )
        assert result.score >= 9.0

    def test_validate_conflict_resolution_none_handled(self, validator):
        """Test no conflicts handled."""
        result = validator.validate_conflict_resolution(
            conflicts_found=5,
            conflicts_resolved=0,
            unresolved_documented=0,
        )
        assert result.score < 7.0

    def test_validate_all_passing(self, validator):
        """Test validating all pillars with passing scores."""
        summary = validator.validate_all(
            source_count=15,
            source_tiers={"tier_0": 8, "tier_1": 5, "tier_2": 2},
            citation_count=90,
            total_claims=100,
            conflicts_found=3,
            conflicts_resolved=3,
            unresolved_documented=0,
            has_written_conclusion=True,
            conclusion_length=500,
        )

        assert summary.passes_threshold is True
        assert summary.overall_score >= 7.0


# =============================================================================
# Integrity Validator Tests
# =============================================================================


class TestIntegrityValidator:
    """Tests for IntegrityValidator."""

    @pytest.fixture
    def validator(self) -> IntegrityValidator:
        """Create a validator."""
        return IntegrityValidator()

    @pytest.fixture
    def grade_a_pipeline(self) -> PublishingPipeline:
        """Create a Grade A pipeline."""
        return PublishingPipeline(
            pipeline_id="test_1",
            subject_id="person_123",
            grade_card=GPSGradeCard(
                subject_id="person_123",
                pillar_scores=[
                    GPSPillarScore(pillar=p, score=9.2, rationale="Test")
                    for p in GPSPillar
                ],
            ),
        )

    def test_check_grade_requirements(self, validator, grade_a_pipeline):
        """Test grade requirements checking."""
        allowed, warnings = validator.check_grade_requirements(
            grade_a_pipeline.grade_card
        )
        assert PublishingPlatform.WIKIPEDIA in allowed
        assert PublishingPlatform.WIKIDATA in allowed
        assert len(warnings) == 0

    def test_validate_pipeline_without_grade(self, validator):
        """Test validation fails without grade card."""
        pipeline = PublishingPipeline(
            pipeline_id="test_2",
            subject_id="person_456",
        )
        result = validator.validate_pipeline(pipeline)
        assert result.can_publish is False
        assert len(result.warnings) > 0

    def test_validate_pipeline_with_blocking_issues(self, validator, grade_a_pipeline):
        """Test pipeline with critical issues is blocked."""
        grade_a_pipeline.quorum_decision = QuorumDecision(
            logic_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.LOGIC_REVIEWER,
                verdict=Verdict.FAIL,
                issues=[
                    ReviewIssue(
                        severity=Severity.CRITICAL,
                        description="Fatal error",
                    )
                ],
                rationale="Critical issue",
                reviewer_model="test",
            ),
            source_verdict=ReviewVerdict(
                reviewer_type=ReviewerType.SOURCE_REVIEWER,
                verdict=Verdict.PASS,
                issues=[],
                rationale="OK",
                reviewer_model="test",
            ),
        )

        result = validator.validate_pipeline(grade_a_pipeline)
        assert result.can_publish is False
        assert len(result.blocking_issues) > 0


# =============================================================================
# Publishing Pipeline Tests
# =============================================================================


class TestPublishingPipeline:
    """Tests for PublishingPipeline model."""

    def test_create_pipeline(self):
        """Test creating a basic pipeline."""
        pipeline = PublishingPipeline(
            pipeline_id="test_1",
            subject_id="person_123",
        )
        assert pipeline.status == PublishingStatus.DRAFT
        assert pipeline.is_blocked is True  # No grade card

    def test_pipeline_with_grade_card(self):
        """Test pipeline with grade card."""
        pipeline = PublishingPipeline(
            pipeline_id="test_2",
            subject_id="person_456",
            grade_card=GPSGradeCard(
                subject_id="person_456",
                pillar_scores=[
                    GPSPillarScore(pillar=p, score=9.0, rationale="Test")
                    for p in GPSPillar
                ],
            ),
        )
        assert pipeline.is_blocked is False
        assert len(pipeline.effective_platforms) > 0

    def test_has_paper_trail(self):
        """Test paper trail detection."""
        pipeline = PublishingPipeline(
            pipeline_id="test_3",
            subject_id="person_789",
        )
        assert pipeline.has_paper_trail() is False

        pipeline.research_notes.append(
            ResearchNote(
                note_id="note_1",
                subject_id="person_789",
                content="Test note",
            )
        )
        assert pipeline.has_paper_trail() is True


# =============================================================================
# Paper Trail of Doubt Tests
# =============================================================================


class TestPaperTrail:
    """Tests for Paper Trail of Doubt models."""

    def test_create_research_note(self):
        """Test creating a research note."""
        note = ResearchNote(
            note_id="note_1",
            subject_id="person_123",
            content="Checked parish records",
            source_refs=["source_1", "source_2"],
        )
        assert note.content == "Checked parish records"
        assert len(note.source_refs) == 2

    def test_create_uncertainty(self):
        """Test creating an uncertainty record."""
        uncertainty = Uncertainty(
            uncertainty_id="unc_1",
            subject_id="person_123",
            field="birth_date",
            description="Two sources disagree",
            confidence_level=0.75,
            alternative_interpretations=["1845", "1847"],
        )
        assert uncertainty.confidence_level == 0.75
        assert len(uncertainty.alternative_interpretations) == 2

    def test_create_unresolved_conflict(self):
        """Test creating an unresolved conflict."""
        conflict = UnresolvedConflict(
            conflict_id="conf_1",
            subject_id="person_123",
            field="death_location",
            competing_claims=[
                {"value": "Chicago", "source": "death cert"},
                {"value": "Springfield", "source": "obituary"},
            ],
            analysis_summary="Both primary sources",
            remaining_doubt="Cannot determine",
        )
        assert len(conflict.competing_claims) == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestPublishingManagerIntegration:
    """Integration tests for PublishingManager."""

    def test_import_publishing_manager(self):
        """Test that PublishingManager can be imported from main module."""
        from gps_agents.genealogy_crawler import (
            PublishingManager,
            GPSGradeCard,
            QuorumDecision,
        )

        assert PublishingManager is not None
        assert GPSGradeCard is not None
        assert QuorumDecision is not None

    def test_all_publishing_types_exported(self):
        """Test that all publishing types are exported."""
        from gps_agents.genealogy_crawler import (
            GPSPillar,
            GPSPillarScore,
            GPSGradeCard,
            PublishingPipeline,
            PublishingStatus,
            PublishingPlatform,
            ReviewerType,
            Verdict,
            Severity,
            ReviewIssue,
            ReviewVerdict,
            QuorumDecision,
            ResearchNote,
            Uncertainty,
            UnresolvedConflict,
            GPSPillarValidator,
            IntegrityValidator,
        )

        # All imports succeeded
        assert GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH is not None
        assert Verdict.PASS is not None
        assert Severity.CRITICAL is not None

    def test_linguist_types_exported(self):
        """Test that Linguist Agent types are exported."""
        from gps_agents.genealogy_crawler import (
            LinguistLLM,
            LinguistInput,
            LinguistOutput,
            AcceptedFact,
            WikipediaDraft,
            WikiTreeBio,
            GPSPillar5Grade,
        )

        assert LinguistLLM is not None
        assert LinguistInput is not None
        assert LinguistOutput is not None
        assert AcceptedFact is not None
        assert WikipediaDraft is not None
        assert WikiTreeBio is not None
        assert GPSPillar5Grade is not None


# =============================================================================
# Linguist Agent Tests
# =============================================================================


class TestAcceptedFact:
    """Tests for AcceptedFact model."""

    def test_create_accepted_fact(self):
        """Test creating an accepted fact."""
        from gps_agents.genealogy_crawler.publishing import AcceptedFact

        fact = AcceptedFact(
            field="birth_date",
            value="1850-03-15",
            confidence=0.95,
            source_refs=["source_1", "source_2"],
            source_tier="tier_0",
        )

        assert fact.field == "birth_date"
        assert fact.value == "1850-03-15"
        assert fact.confidence == 0.95
        assert len(fact.source_refs) == 2
        assert fact.source_tier == "tier_0"

    def test_confidence_bounds(self):
        """Test that confidence is bounded 0-1."""
        from gps_agents.genealogy_crawler.publishing import AcceptedFact

        with pytest.raises(ValueError):
            AcceptedFact(
                field="test",
                value="test",
                confidence=1.5,
            )

        with pytest.raises(ValueError):
            AcceptedFact(
                field="test",
                value="test",
                confidence=-0.1,
            )


class TestLinguistInput:
    """Tests for LinguistInput model."""

    def test_create_linguist_input(self):
        """Test creating linguist input."""
        from gps_agents.genealogy_crawler.publishing import (
            AcceptedFact,
            LinguistInput,
        )

        facts = [
            AcceptedFact(field="birth_date", value="1850-03-15", confidence=0.95),
            AcceptedFact(field="birth_place", value="Boston, MA", confidence=0.92),
        ]

        input_data = LinguistInput(
            subject_id="person_123",
            subject_name="John Smith",
            accepted_facts=facts,
            wikidata_qid="Q12345",
            generate_wikipedia=True,
            generate_wikitree=True,
            generate_diff=False,
        )

        assert input_data.subject_id == "person_123"
        assert input_data.subject_name == "John Smith"
        assert len(input_data.accepted_facts) == 2
        assert input_data.wikidata_qid == "Q12345"
        assert input_data.generate_wikipedia is True
        assert input_data.generate_wikitree is True
        assert input_data.generate_diff is False


class TestLinguistFilterAcceptedFacts:
    """Tests for fact filtering logic."""

    def test_filter_accepted_facts(self):
        """Test filtering facts by status and confidence."""
        from gps_agents.genealogy_crawler.publishing import LinguistLLM

        facts = [
            # Should be included
            {"field": "birth_date", "value": "1850", "status": "ACCEPTED", "confidence": 0.95},
            {"field": "birth_place", "value": "Boston", "status": "ACCEPTED", "confidence": 0.90},
            # Should be excluded - low confidence
            {"field": "death_date", "value": "1920", "status": "ACCEPTED", "confidence": 0.85},
            # Should be excluded - wrong status
            {"field": "occupation", "value": "farmer", "status": "PENDING", "confidence": 0.95},
            {"field": "spouse", "value": "Jane Doe", "status": "REJECTED", "confidence": 0.99},
        ]

        accepted = LinguistLLM.filter_accepted_facts(facts, min_confidence=0.9)

        assert len(accepted) == 2
        assert accepted[0].field == "birth_date"
        assert accepted[1].field == "birth_place"

    def test_filter_with_custom_threshold(self):
        """Test filtering with custom confidence threshold."""
        from gps_agents.genealogy_crawler.publishing import LinguistLLM

        facts = [
            {"field": "birth_date", "value": "1850", "status": "ACCEPTED", "confidence": 0.80},
            {"field": "death_date", "value": "1920", "status": "ACCEPTED", "confidence": 0.75},
        ]

        # Default threshold (0.9) - none pass
        accepted = LinguistLLM.filter_accepted_facts(facts)
        assert len(accepted) == 0

        # Custom threshold (0.7) - both pass
        accepted = LinguistLLM.filter_accepted_facts(facts, min_confidence=0.7)
        assert len(accepted) == 2


class TestGPSPillar5Grade:
    """Tests for GPSPillar5Grade model."""

    def test_create_pillar5_grade(self):
        """Test creating GPS Pillar 5 grade."""
        from gps_agents.genealogy_crawler.publishing import GPSPillar5Grade

        grade = GPSPillar5Grade(
            score=8.5,
            rationale="Good written conclusion with clear evidence",
            improvements_needed=["Add more specific dates"],
        )

        assert grade.score == 8.5
        assert "clear evidence" in grade.rationale
        assert len(grade.improvements_needed) == 1

    def test_pillar5_score_bounds(self):
        """Test that Pillar 5 score is bounded 1-10."""
        from gps_agents.genealogy_crawler.publishing import GPSPillar5Grade

        with pytest.raises(ValueError):
            GPSPillar5Grade(score=11.0, rationale="Invalid")

        with pytest.raises(ValueError):
            GPSPillar5Grade(score=0.5, rationale="Invalid")


class TestWikipediaDraft:
    """Tests for WikipediaDraft model."""

    def test_create_wikipedia_draft(self):
        """Test creating Wikipedia draft."""
        from gps_agents.genealogy_crawler.publishing import WikipediaDraft

        draft = WikipediaDraft(
            lead_paragraph="John Smith (1850-1920) was an American farmer...",
            infobox_wikitext="{{Infobox person|name=John Smith|birth_date=1850}}",
            categories=["1850 births", "1920 deaths", "American farmers"],
        )

        assert "John Smith" in draft.lead_paragraph
        assert "Infobox person" in draft.infobox_wikitext
        assert len(draft.categories) == 3


class TestWikiTreeBio:
    """Tests for WikiTreeBio model."""

    def test_create_wikitree_bio(self):
        """Test creating WikiTree biography."""
        from gps_agents.genealogy_crawler.publishing import WikiTreeBio

        bio = WikiTreeBio(
            narrative="Our research shows that John Smith was born in Boston...",
            research_notes="Further research needed on death location.",
            templates_used=["{{Birth Date and Age}}", "{{Death Date and Age}}"],
        )

        assert "Our research shows" in bio.narrative
        assert "research needed" in bio.research_notes
        assert len(bio.templates_used) == 2


class TestLinguistOutput:
    """Tests for LinguistOutput model."""

    def test_create_linguist_output(self):
        """Test creating complete linguist output."""
        from gps_agents.genealogy_crawler.publishing import (
            GPSPillar5Grade,
            LinguistOutput,
            WikipediaDraft,
            WikiTreeBio,
        )

        output = LinguistOutput(
            gps_pillar_5_grade=GPSPillar5Grade(
                score=9.0,
                rationale="Excellent written conclusion",
            ),
            wikipedia_draft=WikipediaDraft(
                lead_paragraph="John Smith was...",
                infobox_wikitext="{{Infobox person}}",
            ),
            wikitree_bio=WikiTreeBio(
                narrative="Our research shows...",
                research_notes="No major uncertainties.",
            ),
            markdown_diff="--- a/article.md\n+++ b/article.md",
            research_notes="### RESEARCH_NOTES\nNo open questions.",
            is_publication_ready=True,
            blocking_issues=[],
        )

        assert output.gps_pillar_5_grade.score == 9.0
        assert output.wikipedia_draft is not None
        assert output.wikitree_bio is not None
        assert output.is_publication_ready is True
        assert len(output.blocking_issues) == 0


# =============================================================================
# Media & Photo Agent Tests
# =============================================================================


class TestPhotoSource:
    """Tests for PhotoSource enum."""

    def test_photo_source_values(self):
        """Test PhotoSource enum values."""
        from gps_agents.genealogy_crawler.publishing import PhotoSource

        assert PhotoSource.FIND_A_GRAVE == "find_a_grave"
        assert PhotoSource.WIKITREE == "wikitree"
        assert PhotoSource.WIKIMEDIA_COMMONS == "wikimedia_commons"
        assert PhotoSource.FAMILYSEARCH == "familysearch"


class TestMediaLicense:
    """Tests for MediaLicense enum."""

    def test_license_values(self):
        """Test MediaLicense enum values."""
        from gps_agents.genealogy_crawler.publishing import MediaLicense

        assert MediaLicense.CC0 == "CC0"
        assert MediaLicense.CC_BY == "CC-BY"
        assert MediaLicense.PUBLIC_DOMAIN == "Public Domain"
        assert MediaLicense.UNKNOWN == "Unknown"


class TestMediaType:
    """Tests for MediaType enum."""

    def test_media_type_values(self):
        """Test MediaType enum values."""
        from gps_agents.genealogy_crawler.publishing import MediaType

        assert MediaType.HEADSTONE == "headstone"
        assert MediaType.PORTRAIT == "portrait"
        assert MediaType.CERTIFICATE == "certificate"
        assert MediaType.DOCUMENT == "document"


class TestPhotoTarget:
    """Tests for PhotoTarget model."""

    def test_create_photo_target(self):
        """Test creating a photo target."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaType,
            PhotoSource,
            PhotoTarget,
        )

        target = PhotoTarget(
            url="https://findagrave.com/memorial/12345/photo",
            source=PhotoSource.FIND_A_GRAVE,
            media_type=MediaType.HEADSTONE,
            subject_id="person_123",
            subject_name="John Smith",
            caption="Headstone of John Smith",
            license_detected=MediaLicense.CC_BY,
            source_page_url="https://findagrave.com/memorial/12345",
            date_photographed="2020-05-15",
            photographer="Jane Doe",
        )

        assert target.url == "https://findagrave.com/memorial/12345/photo"
        assert target.source == PhotoSource.FIND_A_GRAVE
        assert target.media_type == MediaType.HEADSTONE
        assert target.subject_id == "person_123"
        assert target.license_detected == MediaLicense.CC_BY

    def test_photo_target_defaults(self):
        """Test PhotoTarget default values."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaType,
            PhotoSource,
            PhotoTarget,
        )

        target = PhotoTarget(
            url="https://example.com/photo.jpg",
            source=PhotoSource.OTHER,
            media_type=MediaType.OTHER,
            subject_id="person_123",
            subject_name="John Smith",
        )

        assert target.caption == ""
        assert target.license_detected == MediaLicense.UNKNOWN
        assert target.date_photographed is None
        assert target.photographer is None


class TestMediaMetadata:
    """Tests for MediaMetadata model."""

    def test_create_media_metadata(self):
        """Test creating media metadata."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaMetadata,
            MediaType,
            PhotoSource,
            SubjectConfidence,
        )

        metadata = MediaMetadata(
            subject_id="person_123",
            subject_name="John Smith",
            surname="Smith",
            caption="Headstone of John Smith",
            license=MediaLicense.CC0,
            repository_url="https://findagrave.com/memorial/12345/photo",
            source=PhotoSource.FIND_A_GRAVE,
            media_type=MediaType.HEADSTONE,
            date_downloaded="2024-01-20T12:00:00",
            local_filename="headstone_person_123_abc12345.jpg",
            local_directory="research/persons/smith-john-1850/media/",
            ledger_uuid="abc12345-1234-5678-9abc-def012345678",
            original_filename="headstone_person_123.jpg",
            subject_confidence=SubjectConfidence.HIGH,
            sync_targets=["wikipedia", "github", "wikitree"],
        )

        assert metadata.subject_id == "person_123"
        assert metadata.surname == "Smith"
        assert metadata.license == MediaLicense.CC0
        assert len(metadata.sync_targets) == 3
        assert metadata.ledger_uuid == "abc12345-1234-5678-9abc-def012345678"
        assert metadata.subject_confidence == SubjectConfidence.HIGH


class TestDownloadQueueItem:
    """Tests for DownloadQueueItem model."""

    def test_create_download_queue_item(self):
        """Test creating a download queue item."""
        from gps_agents.genealogy_crawler.publishing import (
            DownloadQueueItem,
            MediaType,
            PhotoSource,
            PhotoTarget,
        )

        target = PhotoTarget(
            url="https://example.com/photo.jpg",
            source=PhotoSource.FIND_A_GRAVE,
            media_type=MediaType.HEADSTONE,
            subject_id="person_123",
            subject_name="John Smith",
            evidence_claim_id="claim_456",  # Required for compliance
        )

        item = DownloadQueueItem(
            photo_target=target,
            priority=1,
            local_path="research/persons/smith-john-1850/media/headstone_person_123_abc12345.jpg",
            sidecar_path="research/persons/smith-john-1850/media/headstone_person_123_abc12345.json",
            ledger_uuid="abc12345-1234-5678-9abc-def012345678",
            status="pending",
        )

        assert item.priority == 1
        assert item.status == "pending"
        assert "headstone" in item.local_path
        assert item.ledger_uuid == "abc12345-1234-5678-9abc-def012345678"

    def test_priority_bounds(self):
        """Test that priority is bounded 1-5."""
        from gps_agents.genealogy_crawler.publishing import (
            DownloadQueueItem,
            MediaType,
            PhotoSource,
            PhotoTarget,
        )

        target = PhotoTarget(
            url="https://example.com/photo.jpg",
            source=PhotoSource.OTHER,
            media_type=MediaType.OTHER,
            subject_id="person_123",
            subject_name="John Smith",
        )

        with pytest.raises(ValueError):
            DownloadQueueItem(
                photo_target=target,
                priority=0,
                local_path="test.jpg",
                sidecar_path="test.json",
            )

        with pytest.raises(ValueError):
            DownloadQueueItem(
                photo_target=target,
                priority=6,
                local_path="test.jpg",
                sidecar_path="test.json",
            )


class TestMediaPhotoAgentInput:
    """Tests for MediaPhotoAgentInput model."""

    def test_create_media_agent_input(self):
        """Test creating media agent input."""
        from gps_agents.genealogy_crawler.publishing import MediaPhotoAgentInput

        input_data = MediaPhotoAgentInput(
            subject_id="person_123",
            subject_name="John Smith",
            surname="Smith",
            research_sources=[
                {"url": "https://findagrave.com/memorial/12345", "type": "find_a_grave"},
                {"url": "https://wikitree.com/wiki/Smith-1234", "type": "wikitree"},
            ],
            discovered_urls=[
                "https://findagrave.com/memorial/12345/photo",
                "https://commons.wikimedia.org/wiki/File:JohnSmith.jpg",
            ],
            target_wikipedia=True,
            target_github=True,
            target_wikitree=False,
            base_output_directory="media",
        )

        assert input_data.subject_id == "person_123"
        assert input_data.surname == "Smith"
        assert len(input_data.research_sources) == 2
        assert len(input_data.discovered_urls) == 2
        assert input_data.target_wikitree is False


class TestMediaPhotoAgentOutput:
    """Tests for MediaPhotoAgentOutput model."""

    def test_create_media_agent_output(self):
        """Test creating media agent output."""
        from gps_agents.genealogy_crawler.publishing import MediaPhotoAgentOutput

        output = MediaPhotoAgentOutput(
            photo_targets=[],
            download_queue=[],
            sidecar_files=[],
            license_issues=[{"url": "test.jpg", "issue": "Unknown license"}],
            total_photos_found=5,
            photos_allowed_wikipedia=3,
            photos_allowed_github=5,
            photos_allowed_wikitree=3,
            directory_structure={"media/smith/smith_123/": ["headstone.jpg", "portrait.jpg"]},
        )

        assert output.total_photos_found == 5
        assert output.photos_allowed_wikipedia == 3
        assert len(output.license_issues) == 1
        assert len(output.directory_structure) == 1


class TestMediaPhotoAgentLLM:
    """Tests for MediaPhotoAgentLLM helper methods."""

    def test_get_allowed_sync_targets_cc0(self):
        """Test sync targets for CC0 license."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaPhotoAgentLLM,
        )

        targets = MediaPhotoAgentLLM.get_allowed_sync_targets(MediaLicense.CC0)
        assert "wikipedia" in targets
        assert "github" in targets
        assert "wikitree" in targets

    def test_get_allowed_sync_targets_fair_use(self):
        """Test sync targets for Fair Use license."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaPhotoAgentLLM,
        )

        targets = MediaPhotoAgentLLM.get_allowed_sync_targets(MediaLicense.FAIR_USE)
        assert "github" in targets
        assert "wikipedia" not in targets
        assert "wikitree" not in targets

    def test_get_allowed_sync_targets_unknown(self):
        """Test sync targets for Unknown license."""
        from gps_agents.genealogy_crawler.publishing import (
            MediaLicense,
            MediaPhotoAgentLLM,
        )

        targets = MediaPhotoAgentLLM.get_allowed_sync_targets(MediaLicense.UNKNOWN)
        assert len(targets) == 0

    def test_generate_directory_path(self):
        """Test surname-centric directory path generation per DevOps standard."""
        from gps_agents.genealogy_crawler.publishing import MediaPhotoAgentLLM

        # New format: research/persons/{surname-firstname-birthyear}/media/
        path = MediaPhotoAgentLLM.generate_directory_path(
            base_directory="research/persons",
            surname="Smith",
            firstname="John",
            birth_year="1850",
        )

        assert path == "research/persons/smith-john-1850/media/"

    def test_generate_directory_path_with_spaces(self):
        """Test directory path with surname containing spaces."""
        from gps_agents.genealogy_crawler.publishing import MediaPhotoAgentLLM

        # Spaces converted to hyphens per DevOps standard
        path = MediaPhotoAgentLLM.generate_directory_path(
            base_directory="research/persons",
            surname="Van Der Berg",
            firstname="Maria",
            birth_year="1920",
        )

        assert path == "research/persons/van-der-berg-maria-1920/media/"

    def test_generate_sidecar_filename(self):
        """Test sidecar filename generation."""
        from gps_agents.genealogy_crawler.publishing import MediaPhotoAgentLLM

        sidecar = MediaPhotoAgentLLM.generate_sidecar_filename("headstone_001.jpg")
        assert sidecar == "headstone_001.json"

        sidecar = MediaPhotoAgentLLM.generate_sidecar_filename("portrait.png")
        assert sidecar == "portrait.json"


class TestMediaAgentExports:
    """Tests for Media & Photo Agent exports."""

    def test_media_agent_types_exported(self):
        """Test that Media & Photo Agent types are exported from main module."""
        from gps_agents.genealogy_crawler import (
            DownloadQueueItem,
            MediaLicense,
            MediaMetadata,
            MediaPhotoAgentInput,
            MediaPhotoAgentLLM,
            MediaPhotoAgentOutput,
            MediaType,
            PhotoSource,
            PhotoTarget,
        )

        # Verify types are accessible
        assert PhotoSource.FIND_A_GRAVE == "find_a_grave"
        assert MediaLicense.CC0 == "CC0"
        assert MediaType.HEADSTONE == "headstone"
        assert MediaPhotoAgentLLM is not None
        assert PhotoTarget is not None
        assert MediaMetadata is not None
        assert DownloadQueueItem is not None
        assert MediaPhotoAgentInput is not None
        assert MediaPhotoAgentOutput is not None


# =============================================================================
# Search Revision Agent Tests
# =============================================================================


class TestSearchStrategy:
    """Tests for SearchStrategy enum."""

    def test_strategy_values(self):
        """Test that all strategies are defined."""
        from gps_agents.genealogy_crawler.publishing import SearchStrategy

        assert SearchStrategy.PHONETIC_EXPANSION == "phonetic_expansion"
        assert SearchStrategy.DATE_PAD == "date_pad"
        assert SearchStrategy.REGIONAL_ROUTING == "regional_routing"
        assert SearchStrategy.NEGATIVE_SEARCH == "negative_search"


class TestMissingSourceClass:
    """Tests for MissingSourceClass model."""

    def test_create_missing_source_class(self):
        """Test creating a missing source class."""
        from gps_agents.genealogy_crawler.publishing import MissingSourceClass

        missing = MissingSourceClass(
            category="vital_records",
            description="No birth certificate found",
            priority=1,
            suggested_repositories=["FamilySearch", "Ancestry"],
        )

        assert missing.category == "vital_records"
        assert missing.priority == 1
        assert len(missing.suggested_repositories) == 2


class TestNameVariant:
    """Tests for NameVariant model."""

    def test_create_name_variant(self):
        """Test creating a name variant."""
        from gps_agents.genealogy_crawler.publishing import NameVariant

        variant = NameVariant(
            original="Janvrin",
            variant="Janvren",
            variant_type="historical",
            confidence=0.7,
        )

        assert variant.original == "Janvrin"
        assert variant.variant == "Janvren"
        assert variant.variant_type == "historical"
        assert variant.confidence == 0.7


class TestSearchRevisionAgentLLM:
    """Tests for SearchRevisionAgentLLM class."""

    def test_generate_soundex(self):
        """Test Soundex generation."""
        from gps_agents.genealogy_crawler.publishing import SearchRevisionAgentLLM

        # Standard Soundex tests
        assert SearchRevisionAgentLLM.generate_soundex("Smith") == "S530"
        assert SearchRevisionAgentLLM.generate_soundex("Smyth") == "S530"
        assert SearchRevisionAgentLLM.generate_soundex("Robert") == "R163"
        assert SearchRevisionAgentLLM.generate_soundex("Rupert") == "R163"

    def test_generate_soundex_empty(self):
        """Test Soundex with empty string."""
        from gps_agents.genealogy_crawler.publishing import SearchRevisionAgentLLM

        assert SearchRevisionAgentLLM.generate_soundex("") == ""


class TestSearchRevisionInput:
    """Tests for SearchRevisionInput model."""

    def test_create_search_revision_input(self):
        """Test creating search revision input."""
        from gps_agents.genealogy_crawler.publishing import (
            MissingSourceClass,
            SearchRevisionInput,
        )

        input_data = SearchRevisionInput(
            subject_id="person_123",
            subject_name="John Janvrin",
            given_name="John",
            surname="Janvrin",
            birth_year=1850,
            death_year=1920,
            known_locations=["Jersey", "Belgium"],
            country_of_origin="France",
            missing_source_classes=[
                MissingSourceClass(
                    category="vital_records",
                    description="No birth certificate",
                )
            ],
            pillar1_score=5.5,
        )

        assert input_data.subject_name == "John Janvrin"
        assert input_data.birth_year == 1850
        assert len(input_data.missing_source_classes) == 1
        assert input_data.pillar1_score == 5.5


class TestSearchRevisionExports:
    """Tests for Search Revision Agent exports."""

    def test_search_revision_types_exported(self):
        """Test that Search Revision Agent types are exported from main module."""
        from gps_agents.genealogy_crawler import (
            DateRange,
            MissingSourceClass,
            NameVariant,
            NegativeSearchTarget,
            RegionalArchive,
            SearchRevisionAgentLLM,
            SearchRevisionInput,
            SearchRevisionOutput,
            SearchStrategy,
            TiebreakerSearchQuery,
        )

        # Verify types are accessible
        assert SearchStrategy.PHONETIC_EXPANSION is not None
        assert MissingSourceClass is not None
        assert NameVariant is not None
        assert DateRange is not None
        assert RegionalArchive is not None
        assert NegativeSearchTarget is not None
        assert TiebreakerSearchQuery is not None
        assert SearchRevisionInput is not None
        assert SearchRevisionOutput is not None
        assert SearchRevisionAgentLLM is not None


# =============================================================================
# DevOps Specialist Tests
# =============================================================================


class TestCommitType:
    """Tests for CommitType enum."""

    def test_commit_type_values(self):
        """Test that all commit types are defined."""
        from gps_agents.genealogy_crawler.publishing import CommitType

        assert CommitType.FEAT == "feat"
        assert CommitType.FIX == "fix"
        assert CommitType.DATA == "data"
        assert CommitType.DOCS == "docs"


class TestPublishingBundle:
    """Tests for PublishingBundle model."""

    def test_create_publishing_bundle(self):
        """Test creating a publishing bundle."""
        from gps_agents.genealogy_crawler.publishing import PublishingBundle

        bundle = PublishingBundle(
            bundle_id="bundle_001",
            subject_id="person_123",
            subject_name="John Smith",
            surname="Smith",
            firstname="John",
            birth_year="1850",
            wikipedia_draft="# John Smith\n\nJohn Smith was...",
            gps_grade="A",
            source_count=15,
        )

        assert bundle.bundle_id == "bundle_001"
        assert bundle.subject_name == "John Smith"
        assert bundle.gps_grade == "A"
        assert bundle.wikipedia_draft is not None


class TestDevOpsSpecialistLLM:
    """Tests for DevOpsSpecialistLLM class."""

    def test_generate_person_directory(self):
        """Test person directory generation."""
        from gps_agents.genealogy_crawler.publishing import DevOpsSpecialistLLM

        path = DevOpsSpecialistLLM.generate_person_directory(
            base_directory="research/persons",
            surname="Smith",
            firstname="John",
            birth_year="1850",
        )

        assert path == "research/persons/smith-john-1850/"

    def test_generate_person_directory_with_spaces(self):
        """Test person directory with spaces in name."""
        from gps_agents.genealogy_crawler.publishing import DevOpsSpecialistLLM

        path = DevOpsSpecialistLLM.generate_person_directory(
            base_directory="research/persons",
            surname="Van Der Berg",
            firstname="Maria Anna",
            birth_year="1920",
        )

        assert path == "research/persons/van-der-berg-maria-anna-1920/"


class TestDevOpsWorkflowInput:
    """Tests for DevOpsWorkflowInput model."""

    def test_create_workflow_input(self):
        """Test creating workflow input."""
        from gps_agents.genealogy_crawler.publishing import (
            DevOpsWorkflowInput,
            PublishingBundle,
        )

        input_data = DevOpsWorkflowInput(
            bundles=[
                PublishingBundle(
                    bundle_id="bundle_001",
                    subject_id="person_123",
                    subject_name="John Smith",
                    surname="Smith",
                    firstname="John",
                    birth_year="1850",
                )
            ],
            base_directory="research/persons",
            create_branch=True,
        )

        assert len(input_data.bundles) == 1
        assert input_data.create_branch is True


class TestDevOpsSpecialistExports:
    """Tests for DevOps Specialist exports."""

    def test_devops_types_exported(self):
        """Test that DevOps Specialist types are exported from main module."""
        from gps_agents.genealogy_crawler import (
            CommitType,
            DevOpsSpecialistLLM,
            DevOpsWorkflowInput,
            DevOpsWorkflowOutput,
            GitCommitSpec,
            GitFileOperation,
            PublishingBundle,
        )

        # Verify types are accessible
        assert CommitType.FEAT is not None
        assert PublishingBundle is not None
        assert GitFileOperation is not None
        assert GitCommitSpec is not None
        assert DevOpsWorkflowInput is not None
        assert DevOpsWorkflowOutput is not None
        assert DevOpsSpecialistLLM is not None
