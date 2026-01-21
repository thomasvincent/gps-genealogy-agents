"""Integrity validation for publishing.

Validates publishing pipelines for blocking issues and determines
which platforms are allowed based on grade and issue severity.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (
    GPSGradeCard,
    PublishingPipeline,
    PublishingPlatform,
    QuorumDecision,
    ReviewIssue,
    Severity,
)


@dataclass
class IntegrityCheckResult:
    """Result of integrity validation."""

    can_publish: bool
    allowed_platforms: list[PublishingPlatform]
    blocked_platforms: list[PublishingPlatform]
    blocking_issues: list[ReviewIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class IntegrityValidator:
    """Validates publishing pipeline integrity.

    The integrity guard enforces publishing rules:
    - CRITICAL issues block ALL publishing
    - HIGH issues block Wikipedia/Wikidata
    - Grade requirements determine platform eligibility
    """

    # Platform requirements
    PLATFORM_MIN_GRADES = {
        PublishingPlatform.WIKIPEDIA: "A",
        PublishingPlatform.WIKIDATA: "A",
        PublishingPlatform.WIKITREE: "B",
        PublishingPlatform.GITHUB: "C",
    }

    GRADE_ORDER = ["F", "D", "C", "B", "A"]

    def __init__(self, strict: bool = True):
        """Initialize validator.

        Args:
            strict: If True, apply stricter blocking rules
        """
        self._strict = strict

    def _grade_meets_requirement(self, actual: str, required: str) -> bool:
        """Check if actual grade meets or exceeds requirement."""
        if actual not in self.GRADE_ORDER or required not in self.GRADE_ORDER:
            return False
        return self.GRADE_ORDER.index(actual) >= self.GRADE_ORDER.index(required)

    def check_grade_requirements(
        self,
        grade_card: GPSGradeCard,
    ) -> tuple[list[PublishingPlatform], list[str]]:
        """Check which platforms the grade qualifies for.

        Args:
            grade_card: GPS grade card to check

        Returns:
            Tuple of (allowed_platforms, warning_messages)
        """
        allowed = []
        warnings = []

        letter_grade = grade_card.letter_grade

        for platform, min_grade in self.PLATFORM_MIN_GRADES.items():
            if self._grade_meets_requirement(letter_grade, min_grade):
                allowed.append(platform)
            else:
                warnings.append(
                    f"{platform.value} requires Grade {min_grade}+, "
                    f"current grade is {letter_grade}"
                )

        return allowed, warnings

    def check_quorum_issues(
        self,
        quorum: QuorumDecision,
    ) -> tuple[list[ReviewIssue], set[PublishingPlatform]]:
        """Check quorum issues and determine blocked platforms.

        Args:
            quorum: Quorum decision to check

        Returns:
            Tuple of (blocking_issues, platforms_to_block)
        """
        blocking_issues = []
        platforms_to_block: set[PublishingPlatform] = set()

        for issue in quorum.all_issues:
            if issue.severity == Severity.CRITICAL:
                # Block everything
                blocking_issues.append(issue)
                platforms_to_block = set(PublishingPlatform)
            elif issue.severity == Severity.HIGH:
                # Block Wikipedia/Wikidata
                blocking_issues.append(issue)
                platforms_to_block.add(PublishingPlatform.WIKIPEDIA)
                platforms_to_block.add(PublishingPlatform.WIKIDATA)
            elif issue.severity == Severity.MEDIUM and self._strict:
                # In strict mode, MEDIUM issues also block Wikipedia
                platforms_to_block.add(PublishingPlatform.WIKIPEDIA)

        return blocking_issues, platforms_to_block

    def validate_pipeline(
        self,
        pipeline: PublishingPipeline,
    ) -> IntegrityCheckResult:
        """Validate a publishing pipeline.

        Args:
            pipeline: Pipeline to validate

        Returns:
            IntegrityCheckResult with validation details
        """
        all_platforms = set(PublishingPlatform)
        allowed_platforms = set()
        blocked_platforms = set()
        blocking_issues = []
        warnings = []

        # Check 1: Must have grade card
        if not pipeline.grade_card:
            return IntegrityCheckResult(
                can_publish=False,
                allowed_platforms=[],
                blocked_platforms=list(all_platforms),
                blocking_issues=[],
                warnings=["No GPS grade card - run grading first"],
            )

        # Check 2: Grade requirements
        grade_allowed, grade_warnings = self.check_grade_requirements(
            pipeline.grade_card
        )
        allowed_platforms = set(grade_allowed)
        warnings.extend(grade_warnings)

        # Check 3: Quorum issues (if quorum exists)
        if pipeline.quorum_decision:
            issues, to_block = self.check_quorum_issues(pipeline.quorum_decision)
            blocking_issues.extend(issues)
            allowed_platforms -= to_block
            blocked_platforms |= to_block

        # Check 4: Quorum must be approved for Wikipedia/Wikidata
        if pipeline.quorum_decision and not pipeline.quorum_decision.approved:
            allowed_platforms.discard(PublishingPlatform.WIKIPEDIA)
            allowed_platforms.discard(PublishingPlatform.WIKIDATA)
            blocked_platforms.add(PublishingPlatform.WIKIPEDIA)
            blocked_platforms.add(PublishingPlatform.WIKIDATA)
            warnings.append("Quorum not approved - Wikipedia/Wikidata blocked")

        # Check 5: Must have passed quorum for Wikipedia/Wikidata
        if not pipeline.quorum_decision:
            if PublishingPlatform.WIKIPEDIA in allowed_platforms:
                allowed_platforms.discard(PublishingPlatform.WIKIPEDIA)
                warnings.append("No quorum review - Wikipedia blocked")
            if PublishingPlatform.WIKIDATA in allowed_platforms:
                allowed_platforms.discard(PublishingPlatform.WIKIDATA)
                warnings.append("No quorum review - Wikidata blocked")

        # Calculate final blocked platforms
        blocked_platforms = all_platforms - allowed_platforms

        return IntegrityCheckResult(
            can_publish=len(allowed_platforms) > 0,
            allowed_platforms=list(allowed_platforms),
            blocked_platforms=list(blocked_platforms),
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    def validate_for_platform(
        self,
        pipeline: PublishingPipeline,
        platform: PublishingPlatform,
    ) -> tuple[bool, list[str]]:
        """Check if pipeline can publish to a specific platform.

        Args:
            pipeline: Pipeline to validate
            platform: Target platform

        Returns:
            Tuple of (can_publish, reason_messages)
        """
        result = self.validate_pipeline(pipeline)

        if platform in result.allowed_platforms:
            return True, []

        reasons = []

        # Check grade requirement
        if pipeline.grade_card:
            required = self.PLATFORM_MIN_GRADES.get(platform, "A")
            if not self._grade_meets_requirement(
                pipeline.grade_card.letter_grade, required
            ):
                reasons.append(
                    f"Grade {pipeline.grade_card.letter_grade} below "
                    f"required {required} for {platform.value}"
                )

        # Check blocking issues
        for issue in result.blocking_issues:
            reasons.append(f"{issue.severity.value}: {issue.description}")

        # Check quorum
        if platform in (PublishingPlatform.WIKIPEDIA, PublishingPlatform.WIKIDATA):
            if not pipeline.quorum_decision:
                reasons.append("Quorum review required")
            elif not pipeline.quorum_decision.approved:
                reasons.append("Quorum not approved")

        return False, reasons
