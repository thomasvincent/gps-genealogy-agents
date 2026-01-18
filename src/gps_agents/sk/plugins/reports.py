"""Proof summary and research report plugins for Semantic Kernel."""

from __future__ import annotations

from typing import Annotated

from semantic_kernel.functions import kernel_function


class ReportsPlugin:
    """
    Research reporting and documentation plugin.

    Generates GPS-compliant proof summaries, research logs,
    and evidence analysis tables.
    """

    @kernel_function(
        name="generate_proof_summary",
        description="Generate a GPS-compliant proof summary report",
    )
    def generate_proof_summary(
        self,
        research_question: Annotated[str, "The research question being answered"],
        conclusion: Annotated[str, "The conclusion reached"],
        evidence: Annotated[str, "Semicolon-separated list of evidence used"],
        confidence: Annotated[int, "Confidence level 1-5"],
        conflicts: Annotated[str | None, "Semicolon-separated conflicts and resolutions"] = None,
        next_steps: Annotated[str | None, "Semicolon-separated next research steps"] = None,
    ) -> str:
        """
        Generate a proof summary report in markdown format.

        This is the standard GPS proof summary format.
        """
        # Parse evidence
        evidence_list = [e.strip() for e in evidence.split(";") if e.strip()]

        # Parse conflicts
        conflict_list = []
        if conflicts:
            conflict_list = [c.strip() for c in conflicts.split(";") if c.strip()]

        # Parse next steps
        steps_list = []
        if next_steps:
            steps_list = [s.strip() for s in next_steps.split(";") if s.strip()]

        # Confidence labels
        confidence_labels = {
            1: "Speculative",
            2: "Weak",
            3: "Reasonable",
            4: "Strong",
            5: "GPS Complete",
        }

        lines = [
            "# Proof Summary",
            "",
            "## Research Question",
            research_question,
            "",
            "## Conclusion",
            conclusion,
            "",
            f"**Confidence Level:** {confidence}/5 ({confidence_labels.get(confidence, 'Unknown')})",
            "",
            "## Evidence",
        ]

        for i, ev in enumerate(evidence_list, 1):
            lines.append(f"{i}. {ev}")

        if conflict_list:
            lines.extend([
                "",
                "## Conflicts and Resolution",
            ])
            for conflict in conflict_list:
                lines.append(f"- {conflict}")

        lines.extend([
            "",
            "## GPS Compliance Checklist",
            f"- [{'x' if confidence >= 4 else ' '}] Reasonably exhaustive research",
            "- [ ] Complete and accurate source citations",
            f"- [{'x' if len(evidence_list) >= 2 else ' '}] Analysis and correlation of evidence",
            f"- [{'x' if conflict_list else ' '}] Resolution of conflicting evidence",
            "- [x] Written conclusion",
        ])

        if steps_list:
            lines.extend([
                "",
                "## Recommended Next Steps",
            ])
            for step in steps_list:
                lines.append(f"- {step}")

        lines.extend([
            "",
            "---",
            "*AI-assisted analysis. Conclusions rely solely on documented sources.*",
        ])

        return "\n".join(lines)

    @kernel_function(
        name="format_research_log_entry",
        description="Format a research log entry for documentation",
    )
    def format_research_log_entry(
        self,
        repository: Annotated[str, "Repository or database searched"],
        search_description: Annotated[str, "What was searched for"],
        result: Annotated[str, "Result: 'positive', 'negative', or 'inconclusive'"],
        result_description: Annotated[str, "Description of what was found or not found"],
        source_level: Annotated[str, "Source level: 'original', 'derivative', or 'authored'"],
    ) -> str:
        """
        Format a single research log entry.

        All searches should be logged, including negative results
        per GPS Pillar 1 requirements.
        """
        result_emoji = {
            "positive": "✓",
            "negative": "✗",
            "inconclusive": "?",
        }

        lines = [
            f"### {repository}",
            f"**Search:** {search_description}",
            f"**Result:** {result_emoji.get(result, '?')} {result.upper()}",
            f"**Details:** {result_description}",
            f"**Source Level:** {source_level.upper()}",
            "",
        ]

        if result == "negative":
            lines.append("*Note: Negative result documented per GPS Pillar 1 requirements.*")

        return "\n".join(lines)

    @kernel_function(
        name="generate_evidence_table",
        description="Generate a formatted evidence analysis table",
    )
    def generate_evidence_table(
        self,
        evidence_rows: Annotated[str, "Pipe-separated rows: 'source|information|classification|quality'"],
    ) -> str:
        """
        Generate an evidence analysis table in markdown format.

        Input format: source|information|classification|quality
        Separate rows with semicolons.

        Classification should be: direct, indirect, or negative
        Quality should be: original, derivative, or authored
        """
        rows = [r.strip() for r in evidence_rows.split(";") if r.strip()]

        lines = [
            "## Evidence Analysis",
            "",
            "| Source | Information | Classification | Quality |",
            "|--------|-------------|----------------|---------|",
        ]

        for row in rows:
            parts = [p.strip() for p in row.split("|")]
            if len(parts) >= 4:
                lines.append(f"| {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} |")
            elif len(parts) == 3:
                lines.append(f"| {parts[0]} | {parts[1]} | {parts[2]} | - |")

        return "\n".join(lines)

    @kernel_function(
        name="generate_source_summary",
        description="Generate a summary of sources consulted for GPS Pillar 1",
    )
    def generate_source_summary(
        self,
        sources_searched: Annotated[str, "Semicolon-separated list of sources searched"],
        sources_with_results: Annotated[str, "Semicolon-separated list of sources with positive results"],
        time_period: Annotated[str, "Time period covered (e.g., '1850-1920')"],
        location: Annotated[str, "Geographic area searched"],
    ) -> str:
        """
        Generate a source summary showing search coverage.

        This demonstrates reasonably exhaustive search per GPS Pillar 1.
        """
        searched = [s.strip() for s in sources_searched.split(";") if s.strip()]
        with_results = [s.strip() for s in sources_with_results.split(";") if s.strip()]
        negative = [s for s in searched if s not in with_results]

        lines = [
            "## Source Summary",
            "",
            f"**Time Period:** {time_period}",
            f"**Location:** {location}",
            f"**Total Sources Searched:** {len(searched)}",
            "",
            "### Sources with Positive Results",
        ]

        for source in with_results:
            lines.append(f"- ✓ {source}")

        if negative:
            lines.extend([
                "",
                "### Sources with Negative Results",
            ])
            for source in negative:
                lines.append(f"- ✗ {source}")

        lines.extend([
            "",
            "*Negative results documented per GPS requirements.*",
        ])

        return "\n".join(lines)

    @kernel_function(
        name="format_proof_argument",
        description="Format a structured proof argument narrative",
    )
    def format_proof_argument(
        self,
        claim: Annotated[str, "The genealogical claim being proven"],
        background: Annotated[str, "Background context for the claim"],
        evidence_summary: Annotated[str, "Summary of evidence supporting the claim"],
        analysis: Annotated[str, "Analysis connecting evidence to conclusion"],
        conclusion: Annotated[str, "Final conclusion with confidence statement"],
    ) -> str:
        """
        Format a formal proof argument for GPS Pillar 5.

        This creates a coherently written, soundly reasoned conclusion.
        """
        lines = [
            "# Proof Argument",
            "",
            "## Claim",
            claim,
            "",
            "## Background",
            background,
            "",
            "## Evidence Summary",
            evidence_summary,
            "",
            "## Analysis",
            analysis,
            "",
            "## Conclusion",
            conclusion,
            "",
            "---",
            "*This proof argument follows the Genealogical Proof Standard (GPS).*",
        ]

        return "\n".join(lines)
