"""JSON export for family tree data.

Exports facts and relationships to a structured JSON format that can be:
- Imported into other genealogy tools
- Used for data analysis
- Consumed by visualization libraries (D3.js, etc.)
- Stored in document databases
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus


@dataclass
class PersonExport:
    """Exported person data."""

    id: str
    name: str
    given_name: str | None = None
    surname: str | None = None
    birth_date: str | None = None
    birth_place: str | None = None
    death_date: str | None = None
    death_place: str | None = None
    occupation: str | None = None
    notes: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RelationshipExport:
    """Exported relationship data."""

    type: str  # parent_of, child_of, spouse_of, sibling_of
    subject_id: str
    object_id: str
    date: str | None = None
    place: str | None = None
    confidence: float = 1.0
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FamilyTreeExport:
    """Complete family tree export."""

    metadata: dict[str, Any]
    persons: list[PersonExport]
    relationships: list[RelationshipExport]
    unlinked_facts: list[dict[str, Any]]


def _parse_person_key(person_key: str) -> tuple[str, str | None, str | None]:
    """Parse person_id key into name components.

    Format: "Given Surname|YEAR|PLACE"

    Returns:
        Tuple of (full_name, given_name, surname)
    """
    parts = person_key.split("|")
    name_part = parts[0].strip() if parts else ""

    if not name_part:
        return "Unknown", None, None

    name_parts = name_part.split()
    if len(name_parts) == 1:
        return name_part, name_part, None
    else:
        given = " ".join(name_parts[:-1])
        surname = name_parts[-1]
        return name_part, given, surname


def _fact_to_dict(fact: Fact) -> dict[str, Any]:
    """Convert a Fact to a dictionary."""
    return {
        "id": fact.fact_id,
        "type": fact.fact_type,
        "statement": fact.statement,
        "person_id": fact.person_id,
        "relation_subject": fact.relation_subject,
        "relation_object": fact.relation_object,
        "relation_kind": fact.relation_kind,
        "confidence": fact.confidence,
        "sources": [
            {"id": s.source_id, "url": s.url, "title": s.title}
            for s in (fact.sources or [])
        ],
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
    }


def export_json(
    ledger_dir: Path,
    out_file: Path,
    include_sources: bool = True,
    include_rejected: bool = False,
    pretty: bool = True,
) -> Path:
    """Export facts and relationships to JSON format.

    Args:
        ledger_dir: Path to the fact ledger directory
        out_file: Output file path for the JSON file
        include_sources: Include source citations in export
        include_rejected: Include rejected facts (default: False)
        pretty: Pretty-print the JSON (default: True)

    Returns:
        Path to the created JSON file
    """
    ledger = FactLedger(str(ledger_dir))

    persons: dict[str, PersonExport] = {}
    relationships: list[RelationshipExport] = []
    unlinked_facts: list[dict[str, Any]] = []

    def _ensure_person(person_key: str) -> str:
        """Ensure person exists in export and return ID."""
        if person_key not in persons:
            full_name, given, surname = _parse_person_key(person_key)
            person_id = f"P{len(persons) + 1}"
            persons[person_key] = PersonExport(
                id=person_id,
                name=full_name,
                given_name=given,
                surname=surname,
            )
        return persons[person_key].id

    # Process all accepted facts
    statuses = [FactStatus.ACCEPTED]
    if include_rejected:
        statuses.append(FactStatus.REJECTED)

    for status in statuses:
        for fact in ledger.iter_all_facts(status):
            fact_type = (fact.fact_type or "").lower()

            if fact_type == "relationship":
                # Process relationship
                subject = (fact.relation_subject or "").strip()
                obj = (fact.relation_object or "").strip()
                kind = (fact.relation_kind or "").lower()

                if subject and obj:
                    subject_id = _ensure_person(subject)
                    object_id = _ensure_person(obj)

                    rel = RelationshipExport(
                        type=kind,
                        subject_id=subject_id,
                        object_id=object_id,
                        confidence=fact.confidence or 1.0,
                    )
                    if include_sources and fact.sources:
                        rel.sources = [
                            {"id": s.source_id, "url": s.url, "title": s.title}
                            for s in fact.sources
                        ]
                    relationships.append(rel)

            elif fact.person_id:
                # Person fact
                person_key = fact.person_id
                _ensure_person(person_key)
                person = persons[person_key]

                # Add fact data
                person.facts.append(_fact_to_dict(fact))

                # Extract specific fact types
                if fact_type == "birth":
                    person.birth_date = _extract_date(fact.statement)
                    person.birth_place = _extract_place(fact.statement)
                elif fact_type == "death":
                    person.death_date = _extract_date(fact.statement)
                    person.death_place = _extract_place(fact.statement)
                elif fact_type == "occupation":
                    person.occupation = fact.statement

                if include_sources and fact.sources:
                    for src in fact.sources:
                        person.sources.append({
                            "id": src.source_id,
                            "url": src.url,
                            "title": src.title,
                        })

            else:
                # Unlinked fact
                unlinked_facts.append(_fact_to_dict(fact))

    # Build export structure
    export = FamilyTreeExport(
        metadata={
            "generator": "gps-genealogy-agents",
            "version": "0.2.0",
            "export_date": datetime.now(UTC).isoformat(),
            "total_persons": len(persons),
            "total_relationships": len(relationships),
            "include_rejected": include_rejected,
        },
        persons=list(persons.values()),
        relationships=relationships,
        unlinked_facts=unlinked_facts,
    )

    # Convert to JSON
    export_dict = {
        "metadata": export.metadata,
        "persons": [asdict(p) for p in export.persons],
        "relationships": [asdict(r) for r in export.relationships],
        "unlinked_facts": export.unlinked_facts,
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(export_dict, f, indent=2, ensure_ascii=False)
        else:
            json.dump(export_dict, f, ensure_ascii=False)

    return out_file


def _extract_date(statement: str) -> str | None:
    """Extract date from statement like 'Birth on 12 Jan 1900'."""
    import re

    # Look for date patterns
    patterns = [
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, statement, re.I)
        if match:
            return match.group(1)

    return None


def _extract_place(statement: str) -> str | None:
    """Extract place from statement."""
    import re

    # Look for place patterns like "in City, State" or "at Place"
    patterns = [
        r"\b(?:in|at)\s+([A-Z][a-z]+(?:,?\s+[A-Z][a-z]+)*)",
        r"\b(?:born|died)\s+(?:in|at)\s+([A-Z][a-z]+(?:,?\s+[A-Z][a-z]+)*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, statement)
        if match:
            return match.group(1)

    return None


def export_json_simple(
    persons: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    out_file: Path,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Export pre-structured data to JSON.

    Args:
        persons: List of person dictionaries
        relationships: List of relationship dictionaries
        out_file: Output file path
        metadata: Optional metadata dictionary

    Returns:
        Path to the created JSON file
    """
    export = {
        "metadata": metadata or {
            "generator": "gps-genealogy-agents",
            "version": "0.2.0",
            "export_date": datetime.now(UTC).isoformat(),
        },
        "persons": persons,
        "relationships": relationships,
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    return out_file
