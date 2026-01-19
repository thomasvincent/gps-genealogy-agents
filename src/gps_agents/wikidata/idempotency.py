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


def _equivalent(a: dict, b: dict) -> bool:
    # Compare property, value, qualifiers, references canonicalized
    def canon(x: dict) -> dict:
        return json.loads(json.dumps(x, sort_keys=True))

    return canon(a) == canon(b)


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
    target = {
        "property": property_id,
        "value": value,
        "qualifiers": qualifiers or {},
        "references": references or [],
    }
    for claim in existing:
        if _equivalent(
            {k: claim.get(k) for k in ("property", "value", "qualifiers", "references")},
            target,
        ):
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
