"""Semantic Kernel plugin for citation formatting (Evidence Explained style)."""
from __future__ import annotations

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from gps_agents.models.source import EvidenceType, SourceCitation


class CitationPlugin:
    """Plugin for creating and formatting citations.

    Follows Evidence Explained (Mills) citation format for genealogical sources.
    """

    @kernel_function(
        name="format_citation",
        description="Format a source citation in Evidence Explained style.",
    )
    def format_citation(
        self,
        source_json: Annotated[str, "JSON SourceCitation object"],
    ) -> Annotated[str, "Formatted citation string"]:
        """Format a citation in Evidence Explained style."""
        source = SourceCitation.model_validate_json(source_json)
        return source.to_evidence_explained()

    @kernel_function(
        name="create_citation",
        description="Create a properly structured SourceCitation.",
    )
    def create_citation(
        self,
        repository: Annotated[str, "Repository name (e.g., FamilySearch, WikiTree)"],
        record_id: Annotated[str, "Unique record identifier"],
        evidence_type: Annotated[str, "Evidence type: direct, indirect, or negative"],
        url: Annotated[str | None, "URL to the record"] = None,
        record_type: Annotated[str | None, "Type of record (e.g., Birth Certificate)"] = None,
    ) -> Annotated[str, "JSON SourceCitation object"]:
        """Create a new source citation."""
        try:
            evidence = EvidenceType(evidence_type.lower())
        except ValueError:
            return json.dumps({"error": f"Invalid evidence type: {evidence_type}"})

        # Build kwargs, excluding None values to use model defaults
        kwargs = {
            "repository": repository,
            "record_id": record_id,
            "evidence_type": evidence,
        }
        if url is not None:
            kwargs["url"] = url
        if record_type is not None:
            kwargs["record_type"] = record_type

        citation = SourceCitation(**kwargs)
        return citation.model_dump_json()

    @kernel_function(
        name="classify_evidence",
        description="Determine the evidence type (direct, indirect, negative) for a source.",
    )
    def classify_evidence(
        self,
        source_description: Annotated[str, "Description of what the source says"],
        claim: Annotated[str, "The claim being supported"],
    ) -> Annotated[str, "JSON with evidence classification and reasoning"]:
        """Classify evidence type based on source content and claim."""
        source_lower = source_description.lower()
        _ = claim.lower()  # Reserved for future claim-based classification

        # Direct: Source explicitly states the fact
        direct_indicators = [
            "states that",
            "records that",
            "birth certificate",
            "death certificate",
            "marriage certificate",
            "baptism record",
            "burial record",
            "census lists",
            "explicitly",
            "named as",
        ]

        # Indirect: Source implies the fact through inference
        indirect_indicators = [
            "suggests",
            "implies",
            "based on age",
            "calculated from",
            "estimated",
            "approximately",
            "inferred",
            "consistent with",
        ]

        # Negative: Absence of expected record
        negative_indicators = [
            "no record found",
            "not listed",
            "absent from",
            "no mention",
            "searched but not found",
            "missing from",
        ]

        if any(ind in source_lower for ind in negative_indicators):
            evidence_type = "negative"
            reasoning = "Source indicates absence of expected record"
        elif any(ind in source_lower for ind in direct_indicators):
            evidence_type = "direct"
            reasoning = "Source directly states the claimed fact"
        elif any(ind in source_lower for ind in indirect_indicators):
            evidence_type = "indirect"
            reasoning = "Fact must be inferred from source information"
        else:
            evidence_type = "indirect"
            reasoning = "Default classification - requires inference to support claim"

        return json.dumps({
            "evidence_type": evidence_type,
            "reasoning": reasoning,
            "source_excerpt": source_description[:200],
            "claim": claim,
        })

    @kernel_function(
        name="format_bibliography_entry",
        description="Format a citation as a bibliography entry.",
    )
    def format_bibliography_entry(
        self,
        source_json: Annotated[str, "JSON SourceCitation object"],
    ) -> Annotated[str, "Bibliography-style citation"]:
        """Format citation for a bibliography/source list."""
        source = SourceCitation.model_validate_json(source_json)

        parts = []

        # Use informant as creator if available
        if source.informant:
            parts.append(source.informant)

        # Use record_type as title
        if source.record_type:
            parts.append(f'"{source.record_type}"')

        parts.append(source.repository)

        # Use record_id as location
        if source.record_id:
            parts.append(f"record {source.record_id}")

        if source.url:
            parts.append(f"({source.url})")

        if source.accessed_at:
            parts.append(f"accessed {source.accessed_at}")

        return ", ".join(parts) + "."

    @kernel_function(
        name="validate_citation",
        description="Check if a citation meets minimum quality standards.",
    )
    def validate_citation(
        self,
        source_json: Annotated[str, "JSON SourceCitation object"],
    ) -> Annotated[str, "JSON validation result with issues"]:
        """Validate citation completeness."""
        source = SourceCitation.model_validate_json(source_json)
        issues = []
        warnings = []

        # Required fields
        if not source.repository:
            issues.append("Missing repository name")
        if not source.record_id:
            issues.append("Missing record identifier")
        if not source.evidence_type:
            issues.append("Missing evidence type classification")

        # Recommended fields
        if not source.url:
            warnings.append("No URL provided - makes verification difficult")
        if not source.accessed_at:
            warnings.append("No access date - important for changing online sources")
        if not source.record_type:
            warnings.append("No record type specified")

        is_valid = len(issues) == 0

        return json.dumps({
            "is_valid": is_valid,
            "issues": issues,
            "warnings": warnings,
            "completeness_score": 1.0 - (len(issues) * 0.2 + len(warnings) * 0.1),
        })

    @kernel_function(
        name="merge_duplicate_citations",
        description="Check if two citations refer to the same source.",
    )
    def check_duplicate(
        self,
        citation1_json: Annotated[str, "First citation JSON"],
        citation2_json: Annotated[str, "Second citation JSON"],
    ) -> Annotated[str, "JSON with duplicate analysis"]:
        """Check if citations are duplicates."""
        c1 = SourceCitation.model_validate_json(citation1_json)
        c2 = SourceCitation.model_validate_json(citation2_json)

        same_repo = c1.repository.lower() == c2.repository.lower()
        same_id = c1.record_id == c2.record_id
        same_url = c1.url == c2.url if (c1.url and c2.url) else False

        is_duplicate = same_repo and (same_id or same_url)
        is_likely_duplicate = same_repo and (
            c1.record_type and c2.record_type and c1.record_type == c2.record_type
        )

        return json.dumps({
            "is_duplicate": is_duplicate,
            "is_likely_duplicate": is_likely_duplicate,
            "same_repository": same_repo,
            "same_record_id": same_id,
            "same_url": same_url,
        })
