"""RocksDB-based append-only fact ledger."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

try:
    import rocksdb
except ImportError:
    rocksdb = None  # type: ignore

from typing import TYPE_CHECKING

from ..models.fact import Fact, FactStatus

if TYPE_CHECKING:
    from collections.abc import Iterator


class FactLedger:
    """Append-only, versioned fact ledger using RocksDB.

    This is the authoritative write store in the CQRS architecture.
    Facts are immutable - updates create new versions.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the ledger.

        Args:
            db_path: Path to RocksDB database directory
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        if rocksdb is None:
            # Fallback to file-based storage for development
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

    def _load_fallback_index(self) -> None:
        """Load index for fallback file-based storage.

        Initializes _index as empty dict if file doesn't exist or is corrupted.
        """
        self._index: dict[str, list[int]] = {}  # fact_id -> [versions]
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text())
            except (json.JSONDecodeError, OSError):
                # Index corrupted or unreadable - rebuild from facts file
                self._rebuild_index_from_facts()

    def _save_fallback_index(self) -> None:
        """Save index for fallback file-based storage."""
        self._index_path.write_text(json.dumps(self._index))

    def _rebuild_index_from_facts(self) -> None:
        """Rebuild index by scanning facts file.

        Used when index is corrupted or missing.
        """
        self._index = {}
        if not self._fallback_path.exists():
            return

        try:
            with open(self._fallback_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        key = entry.get("key", "")
                        if ":" in key:
                            fact_id_str, version_str = key.split(":", 1)
                            version = int(version_str)
                            if fact_id_str not in self._index:
                                self._index[fact_id_str] = []
                            self._index[fact_id_str].append(version)
                    except (json.JSONDecodeError, ValueError):
                        continue  # Skip malformed entries
            self._save_fallback_index()
        except OSError:
            pass  # Can't read file, leave index empty

    def append(self, fact: Fact) -> str:
        """Append a fact to the ledger.

        Args:
            fact: The fact to append

        Returns:
            The ledger key for the appended fact
        """
        key = fact.ledger_key()
        value = fact.model_dump_json()

        if self._use_fallback:
            with open(self._fallback_path, "a") as f:
                f.write(json.dumps({"key": key, "value": json.loads(value)}) + "\n")

            fact_id_str = str(fact.fact_id)
            if fact_id_str not in self._index:
                self._index[fact_id_str] = []
            self._index[fact_id_str].append(fact.version)
            self._save_fallback_index()
        else:
            self.db.put(key.encode(), value.encode())

        return key

    def get(self, fact_id: UUID, version: int | None = None) -> Fact | None:
        """Retrieve a fact by ID and optional version.

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
            with open(self._fallback_path) as f:
                for line in f:
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

        Args:
            fact_id: The fact's UUID

        Returns:
            Latest version number or None if fact doesn't exist
        """
        if self._use_fallback:
            versions = self._index.get(str(fact_id), [])
            return max(versions) if versions else None
        # Scan for highest version (could optimize with secondary index)
        latest = None
        prefix = f"{fact_id}:".encode()
        it = self.db.iterkeys()
        it.seek(prefix)
        for key in it:
            if not key.startswith(prefix):
                break
            version = int(key.decode().split(":")[1])
            if latest is None or version > latest:
                latest = version
        return latest

    def get_all_versions(self, fact_id: UUID) -> list[Fact]:
        """Get all versions of a fact.

        Args:
            fact_id: The fact's UUID

        Returns:
            List of all versions, sorted by version number
        """
        if self._use_fallback:
            versions = self._index.get(str(fact_id), [])
            facts = []
            for v in sorted(versions):
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
            # Get latest version of each fact - uses pre-built index
            for fact_id_str, versions in self._index.items():
                fact = self.get(UUID(fact_id_str), max(versions))
                if fact and (status is None or fact.status == status):
                    yield fact
        else:
            # First pass: build version cache (O(n) instead of O(n²))
            latest_versions: dict[str, tuple[int, bytes]] = {}
            it = self.db.iteritems()
            it.seek_to_first()

            for key, value in it:
                key_str = key.decode()
                parts = key_str.split(":", 1)
                if len(parts) != 2:
                    continue
                fact_id_str, version_str = parts
                try:
                    version = int(version_str)
                except ValueError:
                    continue

                if fact_id_str not in latest_versions or version > latest_versions[fact_id_str][0]:
                    latest_versions[fact_id_str] = (version, value)

            # Second pass: yield latest versions
            for _, value in latest_versions.values():
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
