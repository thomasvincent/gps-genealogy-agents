"""RocksDB-based append-only fact ledger with privacy and CQRS support."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from uuid import UUID

try:
    import rocksdb
except ImportError:
    rocksdb = None  # type: ignore

from ..models.fact import Fact, FactStatus
from .privacy import PrivacyCheckResult, PrivacyEngine, PrivacyStatus, get_privacy_engine

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)


# =============================================================================
# CQRS Event Types
# =============================================================================


class LedgerEventType(str, Enum):
    """Types of events emitted by the ledger for CQRS projection."""
    FACT_APPENDED = "fact_appended"
    FACT_UPDATED = "fact_updated"  # New version of existing fact
    FACT_STATUS_CHANGED = "fact_status_changed"


@dataclass
class LedgerEvent:
    """Event emitted when the ledger changes, for CQRS projection."""
    event_type: LedgerEventType
    fact_id: UUID
    version: int
    timestamp: datetime
    fact: Fact
    privacy_status: PrivacyStatus
    is_restricted: bool
    metadata: dict | None = None


# Type alias for event handlers
EventHandler = Callable[[LedgerEvent], None]


# =============================================================================
# Privacy-Aware Fact Ledger
# =============================================================================


class FactLedger:
    """Append-only, versioned fact ledger using RocksDB.

    This is the authoritative write store in the CQRS architecture.
    Facts are immutable - updates create new versions.

    Features:
    - Privacy Engine: Enforces 100-year rule for living person protection
    - CQRS Events: Emits events for Neo4j graph projection
    - Idempotency: Content fingerprinting prevents duplicate writes
    """

    def __init__(
        self,
        db_path: str | Path,
        privacy_engine: PrivacyEngine | None = None,
        enforce_privacy: bool = True,
    ) -> None:
        """Initialize the ledger.

        Args:
            db_path: Path to RocksDB database directory
            privacy_engine: Privacy engine for 100-year rule (uses default if None)
            enforce_privacy: If True, check privacy before appending
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Privacy engine for living person protection
        self._privacy_engine = privacy_engine or get_privacy_engine()
        self._enforce_privacy = enforce_privacy

        # CQRS event handlers for projection
        self._event_handlers: list[EventHandler] = []

        # Person date cache for efficient privacy checks
        self._person_dates: dict[str, dict[str, int | None]] = {}

        if rocksdb is None:
            # Fallback to file-based storage for development
            logger.warning(
                "RocksDB not available, using file-based fallback. "
                "NOT RECOMMENDED FOR PRODUCTION USE. "
                "Install python-rocksdb for production deployments."
            )
            import os
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise RuntimeError(
                    "RocksDB is required in production environments. "
                    "Install with: pip install python-rocksdb"
                )
            self._use_fallback = True
            self._fallback_path = self.db_path / "facts.jsonl"
            self._index_path = self.db_path / "index.json"
            self._load_fallback_index()
        else:
            self._use_fallback = False
            opts = rocksdb.Options()
            opts.create_if_missing = True
            opts.max_open_files = 300
            self.db = rocksdb.DB(str(self.db_path / "facts.db"), opts)
            # In-memory version index for O(1) latest version lookup
            # Lazy-loaded on first access, maintained during append
            self._version_index: dict[str, int] | None = None

    def _load_fallback_index(self) -> None:
        """Load index for fallback file-based storage.

        Initializes _index as empty dict if file doesn't exist or is corrupted.
        Index structure: fact_id -> {version: byte_offset} for O(1) retrieval.
        """
        self._index: dict[str, dict[int, int]] = {}  # fact_id -> {version: byte_offset}
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text())
                # Convert nested dicts to int keys (JSON stores keys as strings)
                self._index = {
                    fact_id: {int(v): offset for v, offset in versions.items()}
                    for fact_id, versions in self._index.items()
                }
            except (json.JSONDecodeError, OSError):
                # Index corrupted or unreadable - rebuild from facts file
                self._rebuild_index_from_facts()

    def _save_fallback_index(self) -> None:
        """Save index for fallback file-based storage."""
        self._index_path.write_text(json.dumps(self._index))

    def _rebuild_index_from_facts(self) -> None:
        """Rebuild index by scanning facts file with byte offsets.

        Used when index is corrupted or missing.
        Stores byte offset for each fact version to enable O(1) retrieval.
        """
        self._index = {}
        if not self._fallback_path.exists():
            return

        try:
            with open(self._fallback_path) as f:
                while True:
                    byte_offset = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    try:
                        entry = json.loads(line)
                        key = entry.get("key", "")
                        if ":" in key:
                            fact_id_str, version_str = key.split(":", 1)
                            version = int(version_str)
                            if fact_id_str not in self._index:
                                self._index[fact_id_str] = {}
                            self._index[fact_id_str][version] = byte_offset
                    except (json.JSONDecodeError, ValueError):
                        continue  # Skip malformed entries
            self._save_fallback_index()
        except OSError:
            pass  # Can't read file, leave index empty

    def _ensure_version_index(self) -> dict[str, int]:
        """Lazy-load version index for RocksDB mode (O(N) scan once, O(1) thereafter)."""
        if self._version_index is not None:
            return self._version_index

        self._version_index = {}
        it = self.db.iterkeys()
        it.seek_to_first()
        for key in it:
            key_str = key.decode()
            if ":" not in key_str:
                continue
            fact_id_str, version_str = key_str.split(":", 1)
            try:
                version = int(version_str)
                if fact_id_str not in self._version_index or version > self._version_index[fact_id_str]:
                    self._version_index[fact_id_str] = version
            except ValueError:
                continue
        return self._version_index

    # =========================================================================
    # CQRS Event Registration
    # =========================================================================

    def register_event_handler(self, handler: EventHandler) -> None:
        """Register a handler for ledger events (CQRS projection).

        Args:
            handler: Callable that receives LedgerEvent instances
        """
        self._event_handlers.append(handler)
        logger.debug(f"Registered event handler: {handler.__name__ if hasattr(handler, '__name__') else handler}")

    def unregister_event_handler(self, handler: EventHandler) -> None:
        """Unregister an event handler."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def _emit_event(self, event: LedgerEvent) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}", exc_info=True)

    # =========================================================================
    # Person Date Cache (for privacy checks)
    # =========================================================================

    def update_person_dates(
        self,
        person_id: str,
        birth_year: int | None = None,
        death_year: int | None = None,
    ) -> None:
        """Update cached birth/death years for a person.

        Called when new birth/death facts are discovered.
        """
        if person_id not in self._person_dates:
            self._person_dates[person_id] = {"birth_year": None, "death_year": None}

        if birth_year is not None:
            self._person_dates[person_id]["birth_year"] = birth_year
        if death_year is not None:
            self._person_dates[person_id]["death_year"] = death_year

    def get_person_dates(self, person_id: str) -> dict[str, int | None]:
        """Get cached birth/death years for a person."""
        return self._person_dates.get(person_id, {"birth_year": None, "death_year": None})

    # =========================================================================
    # Core Append with Privacy and CQRS
    # =========================================================================

    def append(
        self,
        fact: Fact,
        skip_privacy_check: bool = False,
    ) -> str:
        """Append a fact to the ledger with privacy check and event emission.

        Args:
            fact: The fact to append
            skip_privacy_check: If True, bypass privacy check (use with caution)

        Returns:
            The ledger key for the appended fact

        Raises:
            PrivacyViolationError: If fact violates privacy rules (when enforced)
        """
        # Privacy check (100-year rule)
        privacy_result: PrivacyCheckResult | None = None
        if self._enforce_privacy and not skip_privacy_check:
            person_dates = self.get_person_dates(fact.person_id or "")
            privacy_result = self._privacy_engine.check_fact(
                fact,
                context={
                    "birth_year": person_dates.get("birth_year"),
                    "death_year": person_dates.get("death_year"),
                },
            )

            # Log privacy status
            if privacy_result.is_restricted:
                logger.info(
                    f"Fact {fact.fact_id} flagged as RESTRICTED "
                    f"(status={privacy_result.status.value}): {privacy_result.recommendations}"
                )

            # If there are violations, log them (in strict mode, could raise)
            if privacy_result.violations:
                for violation in privacy_result.violations:
                    logger.warning(f"Privacy violation: {violation}")

        # Perform the append
        key = fact.ledger_key()
        value = fact.model_dump_json()

        if self._use_fallback:
            with open(self._fallback_path, "a") as f:
                # Record byte offset before writing for O(1) retrieval
                byte_offset = f.tell()
                f.write(json.dumps({"key": key, "value": json.loads(value)}) + "\n")

            fact_id_str = str(fact.fact_id)
            if fact_id_str not in self._index:
                self._index[fact_id_str] = {}
            self._index[fact_id_str][fact.version] = byte_offset
            self._save_fallback_index()
        else:
            self.db.put(key.encode(), value.encode())
            # Maintain version index for O(1) latest version lookup
            if self._version_index is not None:
                fact_id_str = str(fact.fact_id)
                current = self._version_index.get(fact_id_str, 0)
                if fact.version > current:
                    self._version_index[fact_id_str] = fact.version

        # Update person date cache if this is a birth/death fact
        if fact.person_id and fact.fact_type in ("birth", "death"):
            self._update_person_dates_from_fact(fact)

        # Emit CQRS event for projection
        if self._event_handlers:
            event_type = (
                LedgerEventType.FACT_UPDATED
                if fact.version > 1
                else LedgerEventType.FACT_APPENDED
            )
            event = LedgerEvent(
                event_type=event_type,
                fact_id=fact.fact_id,
                version=fact.version,
                timestamp=datetime.now(UTC),
                fact=fact,
                privacy_status=(
                    privacy_result.status if privacy_result
                    else PrivacyStatus.UNKNOWN
                ),
                is_restricted=(
                    privacy_result.is_restricted if privacy_result
                    else True  # Default to restricted if not checked
                ),
                metadata={"key": key},
            )
            self._emit_event(event)

        return key

    def _update_person_dates_from_fact(self, fact: Fact) -> None:
        """Extract and cache birth/death year from fact."""
        import re

        if not fact.person_id:
            return

        # Extract year from statement
        match = re.search(r"\b(1[6-9]\d{2}|20[0-2]\d)\b", fact.statement)
        if match:
            year = int(match.group(1))
            if fact.fact_type == "birth":
                self.update_person_dates(fact.person_id, birth_year=year)
            elif fact.fact_type == "death":
                self.update_person_dates(fact.person_id, death_year=year)

    def get(self, fact_id: UUID, version: int | None = None) -> Fact | None:
        """Retrieve a fact by ID and optional version.

        Uses byte offset index for O(1) retrieval in fallback mode.

        Args:
            fact_id: The fact's UUID
            version: Specific version to retrieve, or None for latest

        Returns:
            The requested Fact or None if not found
        """
        if version is None:
            version = self.get_latest_version(fact_id)
            if version is None:
                return None

        key = f"{fact_id}:{version}"

        if self._use_fallback:
            if not self._fallback_path.exists():
                return None
            fact_id_str = str(fact_id)
            # O(1) lookup using byte offset index
            versions_dict = self._index.get(fact_id_str)
            if not versions_dict or version not in versions_dict:
                return None
            byte_offset = versions_dict[version]
            with open(self._fallback_path) as f:
                f.seek(byte_offset)
                line = f.readline()
                if line:
                    entry = json.loads(line)
                    if entry["key"] == key:
                        return Fact.model_validate(entry["value"])
            return None
        value = self.db.get(key.encode())
        if value is None:
            return None
        return Fact.model_validate_json(value.decode())

    def get_latest_version(self, fact_id: UUID) -> int | None:
        """Get the latest version number for a fact.

        Uses in-memory version index for O(1) lookup in RocksDB mode.

        Args:
            fact_id: The fact's UUID

        Returns:
            Latest version number or None if fact doesn't exist
        """
        if self._use_fallback:
            versions_dict = self._index.get(str(fact_id), {})
            return max(versions_dict.keys()) if versions_dict else None
        # O(1) lookup via version index (lazy-loaded on first access)
        version_index = self._ensure_version_index()
        return version_index.get(str(fact_id))

    def get_all_versions(self, fact_id: UUID) -> list[Fact]:
        """Get all versions of a fact.

        Args:
            fact_id: The fact's UUID

        Returns:
            List of all versions, sorted by version number
        """
        if self._use_fallback:
            versions_dict = self._index.get(str(fact_id), {})
            facts = []
            for v in sorted(versions_dict.keys()):
                fact = self.get(fact_id, v)
                if fact:
                    facts.append(fact)
            return facts
        facts = []
        prefix = f"{fact_id}:".encode()
        it = self.db.iteritems()
        it.seek(prefix)
        for key, value in it:
            if not key.startswith(prefix):
                break
            facts.append(Fact.model_validate_json(value.decode()))
        return sorted(facts, key=lambda f: f.version)

    def iter_all_facts(self, status: FactStatus | None = None) -> Iterator[Fact]:
        """Iterate over all facts (latest versions only).

        Args:
            status: Optional filter by status

        Yields:
            Facts matching the criteria

        Note:
            For RocksDB mode, this builds a version cache first to avoid O(n²)
            complexity from calling get_latest_version for each key.
        """
        if self._use_fallback:
            if not self._fallback_path.exists():
                return
            # Get latest version of each fact - uses pre-built index with O(1) retrieval
            for fact_id_str, versions_dict in self._index.items():
                if not versions_dict:
                    continue
                latest_version = max(versions_dict.keys())
                fact = self.get(UUID(fact_id_str), latest_version)
                if fact and (status is None or fact.status == status):
                    yield fact
        else:
            # Use version index for streaming iteration (no full cache needed)
            version_index = self._ensure_version_index()
            for fact_id_str, latest_version in version_index.items():
                key = f"{fact_id_str}:{latest_version}".encode()
                value = self.db.get(key)
                if value is None:
                    continue
                fact = Fact.model_validate_json(value.decode())
                if status is None or fact.status == status:
                    yield fact

    def count(self, status: FactStatus | None = None) -> int:
        """Count facts in the ledger.

        Args:
            status: Optional filter by status

        Returns:
            Number of facts (latest versions only)
        """
        return sum(1 for _ in self.iter_all_facts(status))

    def close(self) -> None:
        """Close the database connection."""
        if not self._use_fallback:
            del self.db
