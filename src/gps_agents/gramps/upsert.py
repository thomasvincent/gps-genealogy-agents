from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

import structlog

from gps_agents.gramps.client import GrampsClient
from gps_agents.gramps.merge import MatchConfidence, PersonMatcher
from gps_agents.gramps.models import Event, EventType, Person, Source, Citation
from gps_agents.idempotency.exceptions import IdempotencyBlock
from gps_agents.idempotency.fingerprint import (
    fingerprint_citation,
    fingerprint_event,
    fingerprint_person,
    fingerprint_place,
    fingerprint_relationship,
    fingerprint_source,
)
from gps_agents.projections.sqlite_projection import SQLiteProjection

logger = structlog.get_logger(__name__)


@dataclass
class UpsertResult:
    handle: str
    created: bool


# ---------------------------- Person ----------------------------

def upsert_person(
    client: GrampsClient,
    projection: SQLiteProjection,
    person: Person,
    *,
    matcher_factory: Callable[[GrampsClient], PersonMatcher] | None = None,
) -> UpsertResult:
    """Idempotent person upsert with fingerprint and matcher fallback.

    Flow:
    A) Check fingerprint_index → return existing handle if present
    B) Fallback to PersonMatcher if no fingerprint match
       - Auto-merge only when confidence >= 0.95
       - Raise IdempotencyBlock when 0.80–0.95
    C) Otherwise create new person
    """
    fp = fingerprint_person(person)
    # store on model when available
    try:
        person.fingerprint = fp.value  # pydantic field
    except Exception:
        pass
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        logger.info("upsert_person.reuse", fingerprint=fp.value, handle=existing)
        return UpsertResult(handle=existing, created=False)

    # timeline sanity
    by = person.birth.date.year if person.birth and person.birth.date else None
    dy = person.death.date.year if person.death and person.death.date else None
    if by is not None and dy is not None and dy < by:
        raise IdempotencyBlock(
            reason="Timeline impossible: death before birth",
            match_score=None,
            existing_summary=None,
            proposed_summary=f"{person.display_name} birth={by} death={dy}",
            recommended_action="correct_dates",
        )

    # matcher path
    matcher = matcher_factory(client) if matcher_factory else PersonMatcher(client)
    matches = matcher.find_matches(person, threshold=50.0, limit=1)
    if matches:
        m = matches[0]
        score = m.match_score / 100.0  # convert to 0-1
        if score >= 0.95:
            # auto-merge (no destructive writes here; return existing handle)
            logger.info("upsert_person.automerge", score=score)
            projection.save_fingerprint("person", fp.value, m.matched_handle)
            projection.set_external_ids(fp.value, gramps_handle=m.matched_handle)
            return UpsertResult(handle=m.matched_handle or "", created=False)
        if 0.80 <= score < 0.95:
            raise IdempotencyBlock(
                reason="Probable duplicate requires review",
                match_score=score,
                existing_summary=m.matched_person.display_name if m.matched_person else None,
                proposed_summary=person.display_name,
                recommended_action="review_and_merge_or_skip",
            )

    # Create new person
    handle = client.add_person(person)
    projection.save_fingerprint("person", fp.value, handle)
    projection.set_external_ids(fp.value, gramps_handle=handle, last_synced_at=datetime.now(UTC).isoformat())
    logger.info("upsert_person.created", fingerprint=fp.value, handle=handle)
    return UpsertResult(handle=handle, created=True)


# ---------------------------- Citation ----------------------------

def upsert_citation(
    client: GrampsClient,
    projection: SQLiteProjection,
    citation: Citation,
) -> UpsertResult:
    fp = fingerprint_citation(citation)
    try:
        citation.fingerprint = fp.value
    except Exception:
        pass
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        logger.info("upsert_citation.reuse", fingerprint=fp.value, handle=existing)
        return UpsertResult(handle=existing, created=False)

    if not client._conn:  # noqa: SLF001
        raise RuntimeError("GrampsClient must be connected")
    handle = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")[:20]
    gramps_id = citation.gramps_id or f"C{int(datetime.now(UTC).timestamp())}"
    data = {
        "handle": handle,
        "gramps_id": gramps_id,
        "source_id": citation.source_id,
        "page": citation.page or "",
        "date": citation.date.model_dump() if citation.date else None,
        "confidence": citation.confidence,
        "note": citation.note or "",
    }
    blob = client._serialize_blob(data)  # noqa: SLF001
    with client.session():
        client._conn.execute(  # noqa: SLF001
            "INSERT INTO citation (handle, gramps_id, blob_data) VALUES (?, ?, ?)",
            (handle, gramps_id, blob),
        )
    projection.save_fingerprint("citation", fp.value, handle)
    projection.set_external_ids(fp.value, gramps_handle=handle)
    logger.info("upsert_citation.created", fingerprint=fp.value, handle=handle)
    return UpsertResult(handle=handle, created=True)


# ---------------------------- Event -----------------------------

def upsert_event(
    client: GrampsClient,
    projection: SQLiteProjection,
    event: Event,
) -> UpsertResult:
    fp = fingerprint_event(event)
    try:
        event.fingerprint = fp.value
    except Exception:
        pass
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        logger.info("upsert_event.reuse", fingerprint=fp.value, handle=existing)
        return UpsertResult(handle=existing, created=False)

    # Minimal insert into Gramps 'event' table, matching client.add_person style
    if not client._conn:  # noqa: SLF001 - internal OK in integration layer
        raise RuntimeError("GrampsClient must be connected")
    handle = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")[:20]
    gramps_id = event.gramps_id or f"E{int(datetime.now(UTC).timestamp())}"
    data = {
        "handle": handle,
        "gramps_id": gramps_id,
        "type": (event.event_type.value if isinstance(event.event_type, EventType) else str(event.event_type)),
        "date": event.date.model_dump() if event.date else None,
        "place": event.place.model_dump() if event.place else None,
        "description": event.description or "",
    }
    blob = client._serialize_blob(data)  # noqa: SLF001
    with client.session():
        client._conn.execute(  # noqa: SLF001
            "INSERT INTO event (handle, gramps_id, blob_data) VALUES (?, ?, ?)",
            (handle, gramps_id, blob),
        )
    projection.save_fingerprint("event", fp.value, handle)
    projection.set_external_ids(fp.value, gramps_handle=handle)
    logger.info("upsert_event.created", fingerprint=fp.value, handle=handle)
    return UpsertResult(handle=handle, created=True)


# ---------------------------- Source ----------------------------

def upsert_source(
    client: GrampsClient,
    projection: SQLiteProjection,
    source: Source,
) -> UpsertResult:
    fp = fingerprint_source(source)
    try:
        source.fingerprint = fp.value
    except Exception:
        pass
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        logger.info("upsert_source.reuse", fingerprint=fp.value, handle=existing)
        return UpsertResult(handle=existing, created=False)

    handle = client.add_source(source)
    projection.save_fingerprint("source", fp.value, handle)
    projection.set_external_ids(fp.value, gramps_handle=handle)
    logger.info("upsert_source.created", fingerprint=fp.value, handle=handle)
    return UpsertResult(handle=handle, created=True)
