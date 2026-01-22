"""Content fingerprinting and caching for idempotent LLM calls.

Prevents duplicate API calls by fingerprinting input content and caching results.
Integrates with the system-wide fingerprinting from gps_agents.idempotency.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True)
class ContentFingerprint:
    """SHA-256 fingerprint of content for deduplication."""
    kind: str
    value: str  # hex sha256

    def __str__(self) -> str:
        return f"{self.kind}:{self.value[:16]}"


@dataclass
class CachedResult(Generic[OutputT]):
    """Cached LLM result with metadata."""
    fingerprint: ContentFingerprint
    output_json: str  # JSON-serialized output
    created_at: datetime
    role: str
    input_hash: str

    def is_expired(self, max_age: timedelta) -> bool:
        """Check if cache entry is expired."""
        return datetime.now(UTC) - self.created_at > max_age


@dataclass
class IdempotencyCache:
    """In-memory cache for LLM results keyed by content fingerprint.

    This provides deduplication at the LLM call level to prevent
    re-processing the same content multiple times.
    """
    cache: dict[str, CachedResult] = field(default_factory=dict)
    max_age: timedelta = field(default_factory=lambda: timedelta(hours=24))
    max_size: int = 10000
    hits: int = 0
    misses: int = 0

    def get(self, fingerprint: ContentFingerprint) -> CachedResult | None:
        """Get cached result by fingerprint."""
        key = str(fingerprint)
        result = self.cache.get(key)

        if result is None:
            self.misses += 1
            return None

        if result.is_expired(self.max_age):
            del self.cache[key]
            self.misses += 1
            return None

        self.hits += 1
        return result

    def put(
        self,
        fingerprint: ContentFingerprint,
        output: BaseModel,
        role: str,
        input_hash: str,
    ) -> None:
        """Store result in cache."""
        # Evict oldest entries if at capacity
        if len(self.cache) >= self.max_size:
            self._evict_oldest()

        key = str(fingerprint)
        self.cache[key] = CachedResult(
            fingerprint=fingerprint,
            output_json=output.model_dump_json(),
            created_at=datetime.now(UTC),
            role=role,
            input_hash=input_hash,
        )

    def _evict_oldest(self) -> None:
        """Evict oldest 10% of entries."""
        if not self.cache:
            return
        entries = sorted(self.cache.items(), key=lambda x: x[1].created_at)
        evict_count = max(1, len(entries) // 10)
        for key, _ in entries[:evict_count]:
            del self.cache[key]

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0


def fingerprint_input(input_data: BaseModel, role: str) -> ContentFingerprint:
    """Create a fingerprint from LLM input data.

    Args:
        input_data: Pydantic model containing input
        role: The LLM role being invoked

    Returns:
        ContentFingerprint for deduplication
    """
    # Serialize to JSON with sorted keys for determinism
    json_str = input_data.model_dump_json(exclude_none=True)
    # Parse and re-serialize with sorted keys
    data = json.loads(json_str)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))

    # Hash the canonical representation
    hash_value = hashlib.sha256(f"{role}:{canonical}".encode()).hexdigest()

    return ContentFingerprint(kind=f"llm_{role}", value=hash_value)


def fingerprint_raw_text(text: str, context: str = "raw") -> ContentFingerprint:
    """Create a fingerprint from raw text content.

    Useful for fingerprinting source text before extraction.

    Args:
        text: Raw text content
        context: Context label for the fingerprint

    Returns:
        ContentFingerprint for deduplication
    """
    # Normalize whitespace
    normalized = " ".join(text.split())
    hash_value = hashlib.sha256(normalized.encode()).hexdigest()
    return ContentFingerprint(kind=context, value=hash_value)


class PersistentIdempotencyCache(IdempotencyCache):
    """File-backed idempotency cache for persistence across sessions.

    Stores cache entries in a JSONL file for durability.
    """

    def __init__(
        self,
        cache_path: Path | str,
        max_age: timedelta | None = None,
        max_size: int = 10000,
    ):
        """Initialize with persistence path.

        Args:
            cache_path: Path to cache file
            max_age: Maximum age for cache entries
            max_size: Maximum cache size
        """
        super().__init__(
            max_age=max_age or timedelta(hours=24),
            max_size=max_size,
        )
        self.cache_path = Path(cache_path)
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if not self.cache_path.exists():
            return

        try:
            with open(self.cache_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        fingerprint = ContentFingerprint(
                            kind=entry["kind"],
                            value=entry["value"],
                        )
                        result = CachedResult(
                            fingerprint=fingerprint,
                            output_json=entry["output_json"],
                            created_at=datetime.fromisoformat(entry["created_at"]),
                            role=entry["role"],
                            input_hash=entry["input_hash"],
                        )
                        if not result.is_expired(self.max_age):
                            self.cache[str(fingerprint)] = result
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            logger.warning(f"Could not load cache from {self.cache_path}")

    def _save(self) -> None:
        """Save cache to disk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w") as f:
            for result in self.cache.values():
                entry = {
                    "kind": result.fingerprint.kind,
                    "value": result.fingerprint.value,
                    "output_json": result.output_json,
                    "created_at": result.created_at.isoformat(),
                    "role": result.role,
                    "input_hash": result.input_hash,
                }
                f.write(json.dumps(entry) + "\n")

    def put(
        self,
        fingerprint: ContentFingerprint,
        output: BaseModel,
        role: str,
        input_hash: str,
    ) -> None:
        """Store result and persist to disk."""
        super().put(fingerprint, output, role, input_hash)
        # Persist every 100 entries or on cache miss
        if len(self.cache) % 100 == 0:
            self._save()

    def close(self) -> None:
        """Save and close the cache."""
        self._save()


# Global in-memory cache instance (can be replaced with persistent)
_global_cache: IdempotencyCache | None = None


def get_global_cache() -> IdempotencyCache:
    """Get or create the global idempotency cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = IdempotencyCache()
    return _global_cache


def set_global_cache(cache: IdempotencyCache) -> None:
    """Set the global idempotency cache."""
    global _global_cache
    _global_cache = cache
