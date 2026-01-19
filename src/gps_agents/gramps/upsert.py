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
from gps_agents.idempotency.config import CONFIG

logger = structlog.get_logger(__name__)


@dataclass
class UpsertResult:
    handle: str
    created: bool


# ---------------------------- Person ----------------------------

def _validate_timeline(person: Person) -> None:
    # death before birth
    by = person.birth.date.year if person.birth and person.birth.date else None
    dy = person.death.date.year if person.death and person.death.date else None
    if by is not None and dy is not None and dy < by:
        raise IdempotencyBlock(
            reason="Timeline impossible: death before birth",
            recommended_action="correct_dates",
        )
    # lifespan > MAX_LIFESPAN
    if by is not None and dy is not None and (dy - by) > CONFIG.max_lifespan:
        raise IdempotencyBlock(
            reason=f"Timeline impossible: lifespan exceeds {CONFIG.max_lifespan} years",
            recommended_action="review_life_events",
        )
    # future extension: event-after-death checks if events carry dates


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
    _validate_timeline(person)

    # matcher path
    matcher = matcher_factory(client) if matcher_factory else PersonMatcher(client)
    matches = matcher.find_matches(person, threshold=50.0, limit=1)
    if matches:
        m = matches[0]
        score = m.match_score / 100.0  # convert to 0-1
        if score >= CONFIG.merge_threshold:
            logger.info("upsert_person.automerge", score=score)
            projection.save_fingerprint("person", fp.value, m.matched_handle)
            projection.set_external_ids(fp.value, gramps_handle=m.matched_handle)
            return UpsertResult(handle=m.matched_handle or "", created=False)
        if CONFIG.review_low <= score < CONFIG.review_high:
            raise IdempotencyBlock(
                reason="Probable duplicate requires review",
                match_score=score,
                existing_summary=m.matched_person.display_name if m.matched_person else None,
                proposed_summary=person.display_name,
                recommended_action="review_and_merge_or_skip",
            )

    # Reservation + claim within a transaction; fallback to lock on busy
    try:
        with projection.transaction() as conn:  # type: ignore[unused-variable]
            projection.ensure_fingerprint_row("person", fp.value)
            existing2 = projection.get_gramps_handle_by_fingerprint(fp.value)
            if existing2:
                return UpsertResult(handle=existing2, created=False)
            handle = client.add_person(person)
            claimed = projection.claim_fingerprint_handle(fp.value, handle)
            if claimed == 0:
                # Lost race; reuse winner
                reuse = projection.get_gramps_handle_by_fingerprint(fp.value)
                return UpsertResult(handle=reuse or handle, created=False)
            projection.set_external_ids(fp.value, gramps_handle=handle, last_synced_at=datetime.now(UTC).isoformat())
            return UpsertResult(handle=handle, created=True)
    except Exception:
        # fallback: lock approach (rare)
        import uuid, time
        owner = str(uuid.uuid4())
        attempts = 20
        while attempts > 0:
            if projection.reserve_fingerprint_lock(fp.value, owner, ttl_seconds=CONFIG.lock_ttl_seconds):
                break
            time.sleep(0.01)
            attempts -= 1
        if attempts == 0:
            raise IdempotencyBlock(reason="Could not obtain idempotency lock", recommended_action="retry")
        try:
            existing2 = projection.get_gramps_handle_by_fingerprint(fp.value)
            if existing2:
                return UpsertResult(handle=existing2, created=False)
            handle = client.add_person(person)
            projection.save_fingerprint("person", fp.value, handle)
            projection.set_external_ids(fp.value, gramps_handle=handle, last_synced_at=datetime.now(UTC).isoformat())
            return UpsertResult(handle=handle, created=True)
        finally:
            projection.release_fingerprint_lock(fp.value, owner)


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


# ---------------------------- Place -----------------------------

def upsert_place(
    client: GrampsClient,
    projection: SQLiteProjection,
    place: "Place",
) -> UpsertResult:
    from gps_agents.idempotency.fingerprint import fingerprint_place
    fp = fingerprint_place(place)
    try:
        place.fingerprint = fp.value
    except Exception:
        pass
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertResult(handle=existing, created=False)
    try:
        with projection.transaction() as _:
            projection.ensure_fingerprint_row("place", fp.value)
            existing2 = projection.get_gramps_handle_by_fingerprint(fp.value)
            if existing2:
                return UpsertResult(handle=existing2, created=False)
            if not client._conn:
                raise RuntimeError("GrampsClient must be connected")
            handle = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")[:20]
            gramps_id = place.gramps_id or f"P{int(datetime.now(UTC).timestamp())}"
            data = {
                "handle": handle,
                "gramps_id": gramps_id,
                "name": place.name,
                "city": place.city,
                "state": place.state,
                "country": place.country,
            }
            blob = client._serialize_blob(data)  # noqa: SLF001
            with client.session():
                client._conn.execute("INSERT INTO place (handle, gramps_id, blob_data) VALUES (?, ?, ?)", (handle, gramps_id, blob))
            claimed = projection.claim_fingerprint_handle(fp.value, handle)
            if claimed == 0:
                reuse = projection.get_gramps_handle_by_fingerprint(fp.value)
                return UpsertResult(handle=reuse or handle, created=False)
            projection.set_external_ids(fp.value, gramps_handle=handle)
            return UpsertResult(handle=handle, created=True)
    except Exception:
        # fallback lock
        import uuid, time
        owner = str(uuid.uuid4())
        attempts = 20
        while attempts > 0:
            if projection.reserve_fingerprint_lock(fp.value, owner, ttl_seconds=CONFIG.lock_ttl_seconds):
                break
            time.sleep(0.01)
            attempts -= 1
        if attempts == 0:
            raise IdempotencyBlock(reason="Could not obtain idempotency lock", recommended_action="retry")
        try:
            existing2 = projection.get_gramps_handle_by_fingerprint(fp.value)
            if existing2:
                return UpsertResult(handle=existing2, created=False)
            handle = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")[:20]
            gramps_id = place.gramps_id or f"P{int(datetime.now(UTC).timestamp())}"
            data = {
                "handle": handle,
                "gramps_id": gramps_id,
                "name": place.name,
                "city": place.city,
                "state": place.state,
                "country": place.country,
            }
            blob = client._serialize_blob(data)  # noqa: SLF001
            with client.session():
                client._conn.execute("INSERT INTO place (handle, gramps_id, blob_data) VALUES (?, ?, ?)", (handle, gramps_id, blob))
            projection.save_fingerprint("place", fp.value, handle)
            projection.set_external_ids(fp.value, gramps_handle=handle)
            return UpsertResult(handle=handle, created=True)
        finally:
            projection.release_fingerprint_lock(fp.value, owner)


# ---------------------------- Relationship -----------------------

def upsert_relationship(
    client: GrampsClient,
    projection: SQLiteProjection,
    kind: str,
    a_handle: str,
    b_handle: str,
    context: str | None = None,
) -> UpsertResult:
    from gps_agents.idempotency.fingerprint import fingerprint_relationship
    fp = fingerprint_relationship(kind, a_handle, b_handle, context)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertResult(handle=existing, created=False)
    import uuid, time
    owner = str(uuid.uuid4())
    attempts = 20
    while attempts > 0:
        if projection.reserve_fingerprint_lock(fp.value, owner, ttl_seconds=CONFIG.lock_ttl_seconds):
            break
        time.sleep(0.01)
        attempts -= 1
    if attempts == 0:
        raise IdempotencyBlock(reason="Could not obtain idempotency lock", recommended_action="retry")
    try:
        existing2 = projection.get_gramps_handle_by_fingerprint(fp.value)
        if existing2:
            return UpsertResult(handle=existing2, created=False)
        # For now just record fingerprint mapping; Gramps stores relationships in family/event tables
        projection.save_fingerprint("relationship", fp.value, None)
        projection.set_external_ids(fp.value, gramps_handle=None)
        return UpsertResult(handle="", created=True)
    finally:
        projection.release_fingerprint_lock(fp.value, owner)


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
