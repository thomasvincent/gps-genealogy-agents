from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _statement_fingerprint(property_id: str, value: Any, qualifiers: dict | None, references: list | None) -> str:
    canon = {
        "property": property_id,
        "value": value,
        "qualifiers": qualifiers or {},
        "references": references or [],
    }
    b = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _normalize_time(value: dict) -> dict:
    # Normalize time strings to the granularity of precision
    if not isinstance(value, dict):
        return value
    t = value.copy()
    time = t.get("time")
    precision = t.get("precision")
    if isinstance(time, str) and isinstance(precision, int):
        # If year precision (9), keep +YYYY; month (10) keep +YYYY-MM; day (11) keep +YYYY-MM-DD
        try:
            core = time.lstrip("+")
            parts = core.split("T")[0].split("-")
            if precision == 9 and len(parts) >= 1:
                t["time"] = "+" + parts[0]
            elif precision == 10 and len(parts) >= 2:
                t["time"] = "+" + parts[0] + "-" + parts[1]
            elif precision == 11 and len(parts) >= 3:
                t["time"] = "+" + parts[0] + "-" + parts[1] + "-" + parts[2]
        except Exception:
            pass
    return t


def _canon_claim(property_id: str, value, qualifiers: dict | None, references: list | None) -> dict:
    # Normalize property/value and deep-sort order-independent structures
    pid = property_id.upper()
    val = _normalize_time(value)
    def sort_dict(d: dict) -> dict:
        return json.loads(json.dumps(d, sort_keys=True))
    def canon_refs(refs: list | None) -> list:
        if not refs:
            return []
        # Each reference is a dict; sort items within, then sort list
        items = [sort_dict(r) for r in refs]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True))
    def canon_qual(q: dict | None) -> dict:
        return sort_dict(q or {})
    return {
        "property": pid,
        "value": val,
        "qualifiers": canon_qual(qualifiers),
        "references": canon_refs(references),
    }


def _equivalent(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def ensure_statement(
    client,
    entity_id: str,
    property_id: str,
    value: Any,
    *,
    qualifiers: dict | None = None,
    references: list[dict] | None = None,
    cache: dict | None = None,
    projection=None,
) -> str | None:
    """Ensure a statement exists; add only if missing.

    Returns statement GUID when present/created. Uses optional cache keyed by
    statement fingerprint for future runs.

    The `client` is expected to expose:
      - get_claims(entity_id, property_id) -> list[dict]
      - add_claim(entity_id, property_id, value, qualifiers, references) -> str (GUID)
    """
    fp = _statement_fingerprint(property_id, value, qualifiers, references)
    # Prefer durable cache
    if projection is not None:
        guid = getattr(projection, "get_statement_guid")(fp)
        if guid:
            logger.info("ensure_statement.cache_hit", fingerprint=fp)
            return guid
    if cache is not None and fp in cache:
        logger.info("ensure_statement.cache_hit", fingerprint=fp)
        return cache[fp]

    existing = client.get_claims(entity_id, property_id)  # mocked in tests
    target = _canon_claim(property_id, value, qualifiers, references)
    for claim in existing:
        cand = _canon_claim(claim.get("property"), claim.get("value"), claim.get("qualifiers"), claim.get("references"))
        if _equivalent(cand, target):
            guid = claim.get("id") or claim.get("guid")
            if projection is not None:
                getattr(projection, "set_statement_guid")(fp, guid, entity_id=entity_id, property_id=property_id)
            elif cache is not None:
                cache[fp] = guid
            logger.info("ensure_statement.exists", property=property_id, guid=guid)
            return guid

    guid = client.add_claim(entity_id, property_id, value, qualifiers or {}, references or [])
    if projection is not None:
        getattr(projection, "set_statement_guid")(fp, guid, entity_id=entity_id, property_id=property_id)
    elif cache is not None:
        cache[fp] = guid
    logger.info("ensure_statement.created", property=property_id, guid=guid)
    return guid
