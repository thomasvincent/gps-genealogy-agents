"""JSON-LD Knowledge Graph export for The Ancestry Engine.

Produces schema.org/Person compatible output with genealogical extensions.
Implements the Z specification output format requirements.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from .models import (
    AncestryEngineState,
    EvidenceType,
    LogEntry,
    Person,
    SourceCitation,
    SourceTier,
)


# =============================================================================
# JSON-LD Context
# =============================================================================

GENEALOGY_CONTEXT = {
    "@context": {
        "@vocab": "https://schema.org/",
        "gps": "https://genealogicalproofstandard.org/vocab#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        # Person extensions
        "givenName": "https://schema.org/givenName",
        "familyName": "https://schema.org/familyName",
        "additionalName": "https://schema.org/additionalName",
        "birthDate": {"@id": "https://schema.org/birthDate", "@type": "xsd:date"},
        "deathDate": {"@id": "https://schema.org/deathDate", "@type": "xsd:date"},
        "birthPlace": {"@id": "https://schema.org/birthPlace", "@type": "@id"},
        "deathPlace": {"@id": "https://schema.org/deathPlace", "@type": "@id"},
        "parent": {"@id": "https://schema.org/parent", "@type": "@id"},
        "spouse": {"@id": "https://schema.org/spouse", "@type": "@id"},
        "children": {"@id": "https://schema.org/children", "@type": "@id"},
        # GPS extensions
        "gps:evidenceType": {"@id": "gps:evidenceType", "@type": "@vocab"},
        "gps:sourceTier": {"@id": "gps:sourceTier", "@type": "@vocab"},
        "gps:confidence": {"@id": "gps:confidence", "@type": "xsd:decimal"},
        "gps:citation": {"@id": "gps:citation", "@type": "@id"},
    }
}


# =============================================================================
# JSON-LD Serializers
# =============================================================================


def person_to_jsonld(person: Person, include_sources: bool = True) -> dict[str, Any]:
    """Convert a Person to JSON-LD format.

    Args:
        person: Person to serialize
        include_sources: Whether to include source citations

    Returns:
        JSON-LD compatible dictionary
    """
    result: dict[str, Any] = {
        "@type": "Person",
        "@id": f"urn:uuid:{person.id}",
        "givenName": person.given_name,
        "familyName": person.surname,
        "name": person.full_name,
    }

    if person.middle_name:
        result["additionalName"] = person.middle_name

    # Dates - use first value as canonical, add alternates
    if person.birth_dates:
        result["birthDate"] = person.birth_dates[0]
        if len(person.birth_dates) > 1:
            result["gps:alternateBirthDates"] = person.birth_dates[1:]

    if person.death_dates:
        result["deathDate"] = person.death_dates[0]
        if len(person.death_dates) > 1:
            result["gps:alternateDeathDates"] = person.death_dates[1:]

    # Places
    if person.birth_places:
        result["birthPlace"] = {
            "@type": "Place",
            "name": person.birth_places[0],
        }
        if len(person.birth_places) > 1:
            result["gps:alternateBirthPlaces"] = [
                {"@type": "Place", "name": p} for p in person.birth_places[1:]
            ]

    if person.death_places:
        result["deathPlace"] = {
            "@type": "Place",
            "name": person.death_places[0],
        }
        if len(person.death_places) > 1:
            result["gps:alternateDeathPlaces"] = [
                {"@type": "Place", "name": p} for p in person.death_places[1:]
            ]

    # Relationships
    if person.parents:
        result["parent"] = [f"urn:uuid:{p}" for p in person.parents]

    if person.spouses:
        result["spouse"] = [f"urn:uuid:{s}" for s in person.spouses]

    if person.children:
        result["children"] = [f"urn:uuid:{c}" for c in person.children]

    # GPS metadata
    result["gps:confidence"] = person.confidence
    result["dateCreated"] = person.created_at.isoformat()
    result["dateModified"] = person.updated_at.isoformat()

    # Source citations
    if include_sources and person.sources:
        result["gps:citation"] = [
            citation_to_jsonld(source) for source in person.sources
        ]

    return result


def citation_to_jsonld(citation: SourceCitation) -> dict[str, Any]:
    """Convert a SourceCitation to JSON-LD format.

    Args:
        citation: Citation to serialize

    Returns:
        JSON-LD compatible dictionary
    """
    result: dict[str, Any] = {
        "@type": "CreativeWork",
        "@id": f"urn:uuid:{citation.id}",
        "publisher": citation.repository,
        "gps:evidenceType": citation.evidence_type.value,
        "gps:sourceTier": citation.tier.value,
        "gps:confidence": citation.confidence,
        "dateAccessed": citation.accessed_at.isoformat(),
    }

    if citation.url:
        result["url"] = citation.url

    if citation.original_text:
        result["text"] = citation.original_text

    if citation.record_type:
        result["additionalType"] = citation.record_type

    return result


def log_entry_to_jsonld(entry: LogEntry) -> dict[str, Any]:
    """Convert a LogEntry to JSON-LD format (for provenance).

    Args:
        entry: Log entry to serialize

    Returns:
        JSON-LD compatible dictionary
    """
    return {
        "@type": "Action",
        "@id": f"urn:uuid:{entry.id}",
        "actionStatus": "CompletedActionStatus" if entry.success else "FailedActionStatus",
        "agent": {"@type": "SoftwareApplication", "name": entry.agent.value},
        "startTime": entry.timestamp.isoformat(),
        "description": entry.rationale,
        "object": entry.context,
    }


# =============================================================================
# Full Graph Export
# =============================================================================


def export_knowledge_graph(
    state: AncestryEngineState,
    include_provenance: bool = True,
    include_sources: bool = True,
) -> dict[str, Any]:
    """Export the full knowledge graph as JSON-LD.

    Args:
        state: Engine state containing the knowledge graph
        include_provenance: Include research log as provenance
        include_sources: Include source citations for each person

    Returns:
        Complete JSON-LD document
    """
    # Build the graph
    graph_items: list[dict[str, Any]] = []

    # Add all persons
    for person in state.knowledge_graph.values():
        graph_items.append(person_to_jsonld(person, include_sources))

    # Build result with context
    result: dict[str, Any] = {
        **GENEALOGY_CONTEXT,
        "@type": "Dataset",
        "@id": f"urn:uuid:{state.session_id}",
        "name": f"Genealogy Research: {state.query}",
        "description": f"Autonomous genealogical research for: {state.query}",
        "dateCreated": state.started_at.isoformat(),
        "creator": {
            "@type": "SoftwareApplication",
            "name": "The Ancestry Engine",
            "version": "1.0.0",
        },
        "@graph": graph_items,
    }

    # Add statistics
    result["gps:statistics"] = {
        "totalPersons": len(state.knowledge_graph),
        "totalTasks": len(state.completed_tasks),
        "totalHypotheses": len(state.hypotheses),
        "totalLogEntries": len(state.research_log),
        "terminated": state.terminated,
        "terminationReason": state.termination_reason,
    }

    # Add provenance (research log)
    if include_provenance:
        result["gps:provenance"] = [
            log_entry_to_jsonld(entry) for entry in state.research_log[-100:]  # Limit to last 100
        ]

    # Add seed person reference
    if state.seed_person:
        result["mainEntity"] = f"urn:uuid:{state.seed_person.id}"

    return result


def export_to_file(
    state: AncestryEngineState,
    output_path: str | Path,
    include_provenance: bool = True,
    include_sources: bool = True,
    indent: int = 2,
) -> Path:
    """Export knowledge graph to a JSON-LD file.

    Args:
        state: Engine state to export
        output_path: Path for output file
        include_provenance: Include research log
        include_sources: Include source citations
        indent: JSON indentation level

    Returns:
        Path to created file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    jsonld = export_knowledge_graph(state, include_provenance, include_sources)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(jsonld, f, indent=indent, default=_json_serializer)

    return output_path


def _json_serializer(obj: Any) -> Any:
    """Custom JSON serializer for non-standard types."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# =============================================================================
# Compact Format (minimal output)
# =============================================================================


def export_compact(state: AncestryEngineState) -> dict[str, Any]:
    """Export a minimal version of the knowledge graph.

    Omits provenance and detailed citations for smaller output.

    Args:
        state: Engine state to export

    Returns:
        Compact JSON-LD document
    """
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Genealogy: {state.query}",
        "itemListElement": [
            {
                "@type": "Person",
                "name": person.full_name,
                "birthDate": person.birth_dates[0] if person.birth_dates else None,
                "deathDate": person.death_dates[0] if person.death_dates else None,
                "birthPlace": person.birth_places[0] if person.birth_places else None,
            }
            for person in state.knowledge_graph.values()
        ],
    }


# =============================================================================
# Validation
# =============================================================================


def validate_jsonld(jsonld: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate JSON-LD structure (basic validation).

    Args:
        jsonld: JSON-LD document to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors: list[str] = []

    # Check required fields
    if "@context" not in jsonld:
        errors.append("Missing @context")

    if "@graph" not in jsonld and "@type" not in jsonld:
        errors.append("Missing @graph or @type")

    # Validate persons in graph
    if "@graph" in jsonld:
        for i, item in enumerate(jsonld["@graph"]):
            if item.get("@type") == "Person":
                if "name" not in item and "givenName" not in item:
                    errors.append(f"Person at index {i} missing name")

    return len(errors) == 0, errors
