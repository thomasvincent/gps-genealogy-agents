from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from gps_agents.gramps.merge import PersonMatcher
from gps_agents.gramps.models import Person, Event, Source, Place, Citation
from gps_agents.idempotency.config import CONFIG
from gps_agents.idempotency.fingerprint import (
    fingerprint_person,
    fingerprint_event,
    fingerprint_source,
    fingerprint_place,
)


@dataclass
class UpsertDecision:
    action: str  # reuse|merge|review|create|block
    score: float
    fingerprint: str
    existing_handle: Optional[str] = None
    reason: Optional[str] = None


def decide_upsert_person(client, projection, person: Person) -> UpsertDecision:
    """Pure decision (no writes) for person upsert based on fingerprint + matcher.

    Returns a structured UpsertDecision with action and score.
    """
    fp = fingerprint_person(person)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)

    matcher = PersonMatcher(client)
    matches = matcher.find_matches(person, threshold=50.0, limit=1)
    if not matches:
        return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)

    m = matches[0]
    score = m.match_score / 100.0

    # Weak evidence handling similar to upsert_person
    def _year_only(ev):
        return bool(ev and ev.date and ev.date.year and not ev.date.month and not ev.date.day)

    weak = CONFIG.weak_evidence_downgrade and (_year_only(person.birth) or _year_only(person.death))
    threshold = CONFIG.merge_threshold + (CONFIG.weak_evidence_margin if weak else 0.0)

    if score >= threshold:
        return UpsertDecision(action="merge", score=score, fingerprint=fp.value, existing_handle=m.matched_handle)
    if CONFIG.review_low <= score < CONFIG.review_high:
        return UpsertDecision(action="review", score=score, fingerprint=fp.value, existing_handle=m.matched_handle, reason="Probable duplicate")
    return UpsertDecision(action="create", score=score, fingerprint=fp.value)


def decide_upsert_event(client, projection, event: Event) -> UpsertDecision:
    fp = fingerprint_event(event)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)
    return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)


def decide_upsert_citation(client, projection, citation: Citation) -> UpsertDecision:
    from gps_agents.idempotency.fingerprint import fingerprint_citation
    fp = fingerprint_citation(citation)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)
    return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)


def decide_upsert_relationship(client, projection, kind: str, a_handle: str, b_handle: str, context: str | None = None) -> UpsertDecision:
    from gps_agents.idempotency.fingerprint import fingerprint_relationship
    fp = fingerprint_relationship(kind, a_handle, b_handle, context)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)
    return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)


def decide_upsert_source(client, projection, source: Source) -> UpsertDecision:
    fp = fingerprint_source(source)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)
    return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)


def decide_upsert_place(client, projection, place: Place) -> UpsertDecision:
    fp = fingerprint_place(place)
    existing = projection.get_gramps_handle_by_fingerprint(fp.value)
    if existing:
        return UpsertDecision(action="reuse", score=1.0, fingerprint=fp.value, existing_handle=existing)
    return UpsertDecision(action="create", score=0.0, fingerprint=fp.value)
