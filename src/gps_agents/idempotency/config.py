from __future__ import annotations

import os
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default


@dataclass(frozen=True)
class IdempotencyConfig:
    merge_threshold: float = _f("IDEMPOTENCY_MERGE_THRESHOLD", 0.95)
    review_low: float = _f("IDEMPOTENCY_REVIEW_LOW", 0.80)
    review_high: float = _f("IDEMPOTENCY_REVIEW_HIGH", 0.95)

    # Timeline limits
    min_parent_age: int = _i("IDEMPOTENCY_MIN_PARENT_AGE", 12)
    max_parent_age: int = _i("IDEMPOTENCY_MAX_PARENT_AGE", 60)
    max_lifespan: int = _i("IDEMPOTENCY_MAX_LIFESPAN", 120)

    # Lock TTL seconds (for recovering abandoned locks)
    lock_ttl_seconds: int = _i("IDEMPOTENCY_LOCK_TTL", 300)


CONFIG = IdempotencyConfig()
