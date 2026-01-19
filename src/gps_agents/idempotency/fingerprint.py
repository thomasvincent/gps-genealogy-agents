"""Deterministic fingerprinting for idempotency across entities.

Rules:
- Normalization:
  - Unicode NFKD normalize then strip diacritics (ASCII transliteration)
  - casefold() for case-insensitivity
  - collapse internal whitespace to single spaces; trim leading/trailing
  - strip punctuation that is generally non-semantic for names/places (,.()[]{}:;"'`)
- Dates:
  - Represent dates at the coarsest reliable precision
  - If approximate/before/after flags present, reduce precision to year only
  - If only year present => use year; if year+month => YYYY-MM; if full => YYYY-MM-DD
- Exclude volatile fields like timestamps (e.g., accessed_at)

Fingerprints are SHA-256 of a canonical tuple joined with "\n" to keep readable diffs.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from gps_agents.gramps.models import Event, EventType, Name, Person, Place, Source, Citation


_PUNCT_RE = re.compile(r"[\,\.\(\)\[\]\{\}:;\'\"`]")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Fingerprint:
    kind: str
    value: str  # hex sha256

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"{self.kind}:{self.value}"


def _strip_diacritics(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _normalize_text(s: str) -> str:
    s = s or ""
    s = _strip_diacritics(s)
    s = s.casefold()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def _norm_date(d) -> str:
    # d is GrampsDate | None; represent at coarsest safe precision
    if d is None:
        return ""
    year = getattr(d, "year", None)
    month = getattr(d, "month", None)
    day = getattr(d, "day", None)
    approx = getattr(d, "approximate", False) or getattr(d, "before", False) or getattr(d, "after", False)
    if year is None:
        return ""
    if approx:
        return f"{year:04d}"
    if year and month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if year and month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def _sha256(parts: Iterable[str]) -> str:
    canonical = "\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ------------------------ Entity Fingerprints ------------------------


def fingerprint_person(p: Person) -> Fingerprint:
    name = p.primary_name or Name()
    given = _normalize_text(name.given)
    surname = _normalize_text(name.surname)
    sex = (p.sex or "U").upper()
    byear = _norm_date(p.birth.date) if p.birth else ""
    bplace = _normalize_text(str(p.birth.place)) if p.birth and p.birth.place else ""
    parts = ["person", given, surname, sex, byear, bplace]
    return Fingerprint("person", _sha256(parts))


def fingerprint_event(e: Event) -> Fingerprint:
    et = e.event_type.value if isinstance(e.event_type, EventType) else str(e.event_type)
    d = _norm_date(e.date)
    place = _normalize_text(str(e.place)) if e.place else ""
    desc = _normalize_text(e.description or "")
    parts = ["event", et, d, place, desc]
    return Fingerprint("event", _sha256(parts))


def fingerprint_source(s: Source) -> Fingerprint:
    title = _normalize_text(s.title)
    author = _normalize_text(s.author or "")
    publisher = _normalize_text(s.publisher or "")
    pubinfo = _normalize_text(s.publication_info or "")
    url = _normalize_text(s.url or "")
    parts = ["source", title, author, publisher, pubinfo, url]
    return Fingerprint("source", _sha256(parts))


def fingerprint_citation(c: Citation) -> Fingerprint:
    # Exclude accessed_at (volatile)
    repo = _normalize_text(c.source_id or "") if hasattr(c, "source_id") else _normalize_text(c.repository)
    page = _normalize_text(getattr(c, "page", None) or getattr(c, "record_id", None) or "")
    date = _norm_date(getattr(c, "date", None))
    parts = ["citation", repo, page, date]
    return Fingerprint("citation", _sha256(parts))


def fingerprint_place(pl: Place) -> Fingerprint:
    parts = [
        "place",
        _normalize_text(pl.name),
        _normalize_text(pl.city or ""),
        _normalize_text(pl.county or ""),
        _normalize_text(pl.state or ""),
        _normalize_text(pl.country or ""),
    ]
    return Fingerprint("place", _sha256(parts))


def fingerprint_media_bytes(content: bytes) -> Fingerprint:
    return Fingerprint("media", hashlib.sha256(content).hexdigest())


def fingerprint_relationship(kind: str, a_id: str, b_id: str, context: str | None = None) -> Fingerprint:
    # sort ids to make symmetric relationships stable unless order matters (e.g., parent-child)
    kind_norm = _normalize_text(kind)
    context_norm = _normalize_text(context or "")
    if kind_norm in {"spouse", "marriage", "partner"}:
        a, b = sorted([a_id, b_id])
    else:
        a, b = a_id, b_id
    parts = ["relationship", kind_norm, a, b, context_norm]
    return Fingerprint("relationship", _sha256(parts))
