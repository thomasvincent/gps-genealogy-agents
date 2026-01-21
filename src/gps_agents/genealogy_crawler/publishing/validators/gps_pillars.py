"""GPS Pillar validation for publishing.

Provides heuristic-based validation of research against GPS pillars
as a complement to LLM-based grading.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import GPSPillar


@dataclass
class PillarValidationResult:
    """Result of validating a single GPS pillar."""

    pillar: GPSPillar
    score: float
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class GPSValidationSummary:
    """Summary of GPS validation across all pillars."""

    pillar_results: dict[GPSPillar, PillarValidationResult]
    overall_score: float
    passes_threshold: bool
    threshold: float = 7.0

    @property
    def lowest_pillar(self) -> PillarValidationResult | None:
        """Get the pillar with the lowest score."""
        if not self.pillar_results:
            return None
        return min(self.pillar_results.values(), key=lambda r: r.score)


class GPSPillarValidator:
    """Heuristic validator for GPS pillars.

    Provides quick validation checks that can be run before or alongside
    LLM-based GPS grading. Useful for fast feedback and sanity checks.
    """

    def __init__(self, strict: bool = False):
        """Initialize validator.

        Args:
            strict: If True, apply stricter thresholds
        """
        self._strict = strict

    def validate_exhaustive_search(
        self,
        source_count: int,
        source_tiers: dict[str, int],
        years_covered: int = 0,
    ) -> PillarValidationResult:
        """Validate Pillar 1: Reasonably Exhaustive Search.

        Args:
            source_count: Total number of sources consulted
            source_tiers: Counts by tier (tier_0, tier_1, tier_2)
            years_covered: Number of years in research scope

        Returns:
            Validation result with score and feedback
        """
        issues = []
        suggestions = []

        # Base score from source count
        if source_count >= 15:
            score = 9.0
        elif source_count >= 10:
            score = 8.0
        elif source_count >= 5:
            score = 7.0
        elif source_count >= 3:
            score = 6.0
        else:
            score = 4.0
            issues.append(f"Only {source_count} sources consulted")
            suggestions.append("Consult additional repositories")

        # Check tier diversity
        tier_0 = source_tiers.get("tier_0", 0)
        tier_1 = source_tiers.get("tier_1", 0)
        tier_2 = source_tiers.get("tier_2", 0)

        if tier_0 == 0:
            score -= 1.0
            issues.append("No Tier 0 (freely accessible) sources")
            suggestions.append("Add Wikipedia, Find-a-Grave, or similar sources")

        if tier_1 + tier_2 > 0 and tier_0 < 2:
            score -= 0.5
            suggestions.append("Verify Tier 0 sources before relying on credentialed sources")

        # Bonus for source diversity
        tier_count = sum(1 for t in [tier_0, tier_1, tier_2] if t > 0)
        if tier_count >= 2:
            score += 0.5

        return PillarValidationResult(
            pillar=GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH,
            score=min(10.0, max(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_complete_citations(
        self,
        citation_count: int,
        total_claims: int,
    ) -> PillarValidationResult:
        """Validate Pillar 2: Complete Citations.

        Args:
            citation_count: Number of properly cited claims
            total_claims: Total number of claims

        Returns:
            Validation result with score and feedback
        """
        issues = []
        suggestions = []

        if total_claims == 0:
            return PillarValidationResult(
                pillar=GPSPillar.COMPLETE_CITATIONS,
                score=1.0,
                issues=["No claims to cite"],
                suggestions=["Add claims with citations"],
            )

        citation_rate = citation_count / total_claims

        if citation_rate >= 0.95:
            score = 9.5
        elif citation_rate >= 0.90:
            score = 9.0
        elif citation_rate >= 0.80:
            score = 8.0
        elif citation_rate >= 0.70:
            score = 7.0
        elif citation_rate >= 0.50:
            score = 5.0
            issues.append(f"Only {citation_rate:.0%} of claims are cited")
            suggestions.append("Add citations for remaining claims")
        else:
            score = 3.0
            issues.append(f"Low citation rate: {citation_rate:.0%}")
            suggestions.append("Most claims lack citations - add sources")

        uncited = total_claims - citation_count
        if uncited > 0:
            issues.append(f"{uncited} claims without citations")

        return PillarValidationResult(
            pillar=GPSPillar.COMPLETE_CITATIONS,
            score=min(10.0, max(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_analysis_and_correlation(
        self,
        source_count: int,
        conflicts_found: int,
        research_notes_count: int = 0,
    ) -> PillarValidationResult:
        """Validate Pillar 3: Analysis and Correlation.

        Args:
            source_count: Total number of sources
            conflicts_found: Number of conflicts identified
            research_notes_count: Number of research notes

        Returns:
            Validation result with score and feedback
        """
        issues = []
        suggestions = []

        # Base score - analysis is harder to validate heuristically
        score = 7.0

        # Multiple sources without conflicts is suspicious (either no analysis or very clean data)
        if source_count > 5 and conflicts_found == 0:
            score -= 0.5
            suggestions.append(
                "No conflicts found - verify sources were compared"
            )

        # Research notes indicate analysis effort
        if research_notes_count >= 3:
            score += 1.0
        elif research_notes_count == 0:
            score -= 0.5
            suggestions.append("Add research notes documenting methodology")

        # Some conflicts indicate analysis is happening
        if conflicts_found > 0:
            score += 0.5

        return PillarValidationResult(
            pillar=GPSPillar.ANALYSIS_AND_CORRELATION,
            score=min(10.0, max(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_conflict_resolution(
        self,
        conflicts_found: int,
        conflicts_resolved: int,
        unresolved_documented: int = 0,
    ) -> PillarValidationResult:
        """Validate Pillar 4: Conflict Resolution.

        Args:
            conflicts_found: Number of conflicts identified
            conflicts_resolved: Number of conflicts resolved
            unresolved_documented: Number of unresolved conflicts in Paper Trail

        Returns:
            Validation result with score and feedback
        """
        issues = []
        suggestions = []

        if conflicts_found == 0:
            # No conflicts might be fine or might indicate missing analysis
            return PillarValidationResult(
                pillar=GPSPillar.CONFLICT_RESOLUTION,
                score=8.0,
                issues=[],
                suggestions=["Verify all sources were compared for potential conflicts"],
            )

        # Calculate resolution rate
        total_handled = conflicts_resolved + unresolved_documented
        resolution_rate = total_handled / conflicts_found if conflicts_found > 0 else 1.0

        if resolution_rate >= 1.0 and conflicts_resolved > 0:
            score = 9.0
        elif resolution_rate >= 0.90:
            score = 8.5
        elif resolution_rate >= 0.75:
            score = 7.5
        elif resolution_rate >= 0.50:
            score = 6.0
            issues.append(f"Only {resolution_rate:.0%} of conflicts addressed")
        else:
            score = 4.0
            issues.append(f"Many conflicts unaddressed: {resolution_rate:.0%}")
            suggestions.append("Address remaining conflicts or document as unresolvable")

        # Bonus for documenting unresolved conflicts (honest uncertainty)
        if unresolved_documented > 0:
            score += 0.5

        unaddressed = conflicts_found - total_handled
        if unaddressed > 0:
            issues.append(f"{unaddressed} conflicts neither resolved nor documented")

        return PillarValidationResult(
            pillar=GPSPillar.CONFLICT_RESOLUTION,
            score=min(10.0, max(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_written_conclusion(
        self,
        has_written_conclusion: bool,
        conclusion_length: int = 0,
    ) -> PillarValidationResult:
        """Validate Pillar 5: Written Conclusion.

        Args:
            has_written_conclusion: Whether a conclusion exists
            conclusion_length: Character length of conclusion

        Returns:
            Validation result with score and feedback
        """
        issues = []
        suggestions = []

        if not has_written_conclusion:
            return PillarValidationResult(
                pillar=GPSPillar.WRITTEN_CONCLUSION,
                score=3.0,
                issues=["No written conclusion/proof argument"],
                suggestions=["Write a coherent proof argument connecting evidence"],
            )

        # Score based on conclusion length (proxy for thoroughness)
        if conclusion_length >= 1000:
            score = 9.0
        elif conclusion_length >= 500:
            score = 8.0
        elif conclusion_length >= 200:
            score = 7.0
        elif conclusion_length >= 50:
            score = 6.0
            suggestions.append("Expand conclusion to fully address evidence")
        else:
            score = 5.0
            issues.append("Conclusion is very brief")
            suggestions.append("Write a more thorough proof argument")

        return PillarValidationResult(
            pillar=GPSPillar.WRITTEN_CONCLUSION,
            score=min(10.0, max(1.0, score)),
            issues=issues,
            suggestions=suggestions,
        )

    def validate_all(
        self,
        source_count: int,
        source_tiers: dict[str, int],
        citation_count: int,
        total_claims: int,
        conflicts_found: int,
        conflicts_resolved: int,
        unresolved_documented: int,
        has_written_conclusion: bool,
        conclusion_length: int = 0,
        research_notes_count: int = 0,
        threshold: float = 7.0,
    ) -> GPSValidationSummary:
        """Validate all GPS pillars.

        Args:
            source_count: Total sources consulted
            source_tiers: Counts by tier
            citation_count: Cited claims
            total_claims: Total claims
            conflicts_found: Conflicts identified
            conflicts_resolved: Conflicts resolved
            unresolved_documented: Documented unresolved conflicts
            has_written_conclusion: Whether conclusion exists
            conclusion_length: Length of conclusion
            research_notes_count: Number of research notes
            threshold: Minimum passing score

        Returns:
            GPSValidationSummary with all pillar results
        """
        results = {}

        # Validate each pillar
        results[GPSPillar.REASONABLY_EXHAUSTIVE_SEARCH] = self.validate_exhaustive_search(
            source_count=source_count,
            source_tiers=source_tiers,
        )

        results[GPSPillar.COMPLETE_CITATIONS] = self.validate_complete_citations(
            citation_count=citation_count,
            total_claims=total_claims,
        )

        results[GPSPillar.ANALYSIS_AND_CORRELATION] = self.validate_analysis_and_correlation(
            source_count=source_count,
            conflicts_found=conflicts_found,
            research_notes_count=research_notes_count,
        )

        results[GPSPillar.CONFLICT_RESOLUTION] = self.validate_conflict_resolution(
            conflicts_found=conflicts_found,
            conflicts_resolved=conflicts_resolved,
            unresolved_documented=unresolved_documented,
        )

        results[GPSPillar.WRITTEN_CONCLUSION] = self.validate_written_conclusion(
            has_written_conclusion=has_written_conclusion,
            conclusion_length=conclusion_length,
        )

        # Calculate overall score
        overall = sum(r.score for r in results.values()) / len(results)

        return GPSValidationSummary(
            pillar_results=results,
            overall_score=overall,
            passes_threshold=overall >= threshold,
            threshold=threshold,
        )
