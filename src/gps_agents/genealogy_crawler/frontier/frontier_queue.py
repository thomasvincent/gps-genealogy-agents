"""RocksDB-backed Frontier Queue implementation.

Uses RocksDB's lexicographic key ordering to implement a priority queue
with deduplication and persistence.
"""
from __future__ import annotations

import hashlib
import json
import struct
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

try:
    import rocksdb
except ImportError:
    rocksdb = None  # type: ignore

if TYPE_CHECKING:
    from collections.abc import Iterator


class CrawlPriority(IntEnum):
    """Priority levels for crawl items.

    Lower values = higher priority (processed first).
    Uses IntEnum for easy key encoding.
    """
    CRITICAL = 0      # Immediate verification needed
    HIGH = 10         # Primary source, high confidence match
    NORMAL = 50       # Standard crawl item
    LOW = 80          # Speculative/low confidence
    BACKGROUND = 100  # Fill items when queue is empty


@dataclass
class CrawlItem:
    """A single item in the crawl frontier.

    Represents a URL or query to be processed by the crawler,
    with metadata for prioritization and deduplication.
    """
    item_id: UUID = field(default_factory=uuid4)
    url: str | None = None
    query: dict[str, Any] = field(default_factory=dict)
    adapter_id: str = ""  # Which adapter should process this
    priority: CrawlPriority = CrawlPriority.NORMAL

    # Context for the crawl
    subject_id: UUID | None = None  # Person being researched
    hypothesis: str | None = None   # Why we're crawling this
    parent_item_id: UUID | None = None  # Item that generated this

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scheduled_at: datetime | None = None  # For delayed processing
    retry_count: int = 0
    max_retries: int = 3

    @property
    def content_hash(self) -> str:
        """Hash for deduplication based on URL/query content."""
        content = json.dumps({
            "url": self.url,
            "query": self.query,
            "adapter_id": self.adapter_id,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "item_id": str(self.item_id),
            "url": self.url,
            "query": self.query,
            "adapter_id": self.adapter_id,
            "priority": int(self.priority),
            "subject_id": str(self.subject_id) if self.subject_id else None,
            "hypothesis": self.hypothesis,
            "parent_item_id": str(self.parent_item_id) if self.parent_item_id else None,
            "created_at": self.created_at.isoformat(),
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrawlItem:
        """Deserialize from dictionary."""
        return cls(
            item_id=UUID(data["item_id"]),
            url=data.get("url"),
            query=data.get("query", {}),
            adapter_id=data.get("adapter_id", ""),
            priority=CrawlPriority(data.get("priority", CrawlPriority.NORMAL)),
            subject_id=UUID(data["subject_id"]) if data.get("subject_id") else None,
            hypothesis=data.get("hypothesis"),
            parent_item_id=UUID(data["parent_item_id"]) if data.get("parent_item_id") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC),
            scheduled_at=datetime.fromisoformat(data["scheduled_at"]) if data.get("scheduled_at") else None,
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )


@dataclass
class FrontierStats:
    """Statistics about the frontier queue."""
    total_items: int = 0
    pending_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    unique_urls: int = 0
    items_by_priority: dict[str, int] = field(default_factory=dict)
    items_by_adapter: dict[str, int] = field(default_factory=dict)


class FrontierQueue:
    """RocksDB-backed priority queue for crawl frontier.

    Uses RocksDB's lexicographic key ordering to implement priority:
    - Queue keys: "q:{priority:02d}:{timestamp}:{item_id}"
    - Seen keys: "seen:{content_hash}"
    - Item keys: "item:{item_id}"

    Lower priority numbers are processed first due to lexicographic ordering.
    """

    # Key prefixes for different data types
    QUEUE_PREFIX = b"q:"
    SEEN_PREFIX = b"seen:"
    ITEM_PREFIX = b"item:"
    PROCESSING_PREFIX = b"proc:"
    COMPLETED_PREFIX = b"done:"
    FAILED_PREFIX = b"fail:"

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the frontier queue.

        Args:
            db_path: Path to RocksDB database directory
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        if rocksdb is None:
            # Fallback to in-memory + file-based storage
            self._use_fallback = True
            self._fallback_path = self.db_path / "frontier.jsonl"
            self._queue: list[tuple[bytes, CrawlItem]] = []
            self._seen: set[str] = set()
            self._items: dict[str, CrawlItem] = {}
            self._processing: dict[str, CrawlItem] = {}
            self._completed: dict[str, CrawlItem] = {}
            self._failed: dict[str, CrawlItem] = {}
            self._load_fallback()
        else:
            self._use_fallback = False
            opts = rocksdb.Options()
            opts.create_if_missing = True
            opts.max_open_files = 300
            self.db = rocksdb.DB(str(self.db_path / "frontier.db"), opts)

    def _load_fallback(self) -> None:
        """Load state from fallback file storage."""
        if not self._fallback_path.exists():
            return

        try:
            with open(self._fallback_path) as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        item = CrawlItem.from_dict(entry["item"])
                        status = entry.get("status", "pending")

                        if status == "pending":
                            key = self._make_queue_key(item)
                            self._queue.append((key, item))
                            self._items[str(item.item_id)] = item
                        elif status == "processing":
                            self._processing[str(item.item_id)] = item
                        elif status == "completed":
                            self._completed[str(item.item_id)] = item
                        elif status == "failed":
                            self._failed[str(item.item_id)] = item

                        self._seen.add(item.content_hash)
                    except (json.JSONDecodeError, KeyError):
                        continue

            # Sort queue by key for priority ordering
            self._queue.sort(key=lambda x: x[0])
        except OSError:
            pass

    def _save_fallback(self) -> None:
        """Save state to fallback file storage."""
        with open(self._fallback_path, "w") as f:
            for _, item in self._queue:
                f.write(json.dumps({"item": item.to_dict(), "status": "pending"}) + "\n")
            for item in self._processing.values():
                f.write(json.dumps({"item": item.to_dict(), "status": "processing"}) + "\n")
            for item in self._completed.values():
                f.write(json.dumps({"item": item.to_dict(), "status": "completed"}) + "\n")
            for item in self._failed.values():
                f.write(json.dumps({"item": item.to_dict(), "status": "failed"}) + "\n")

    def _make_queue_key(self, item: CrawlItem) -> bytes:
        """Create a queue key for lexicographic ordering.

        Format: "q:{priority:02d}:{timestamp_us:016d}:{item_id}"

        This ensures:
        1. Lower priority numbers sort first
        2. Within same priority, earlier items sort first
        3. Item ID ensures uniqueness
        """
        # Use microseconds for high precision ordering
        timestamp_us = int(item.created_at.timestamp() * 1_000_000)

        return f"q:{item.priority:02d}:{timestamp_us:016d}:{item.item_id}".encode()

    def push(self, item: CrawlItem, check_duplicate: bool = True) -> bool:
        """Add an item to the frontier queue.

        Args:
            item: The crawl item to add
            check_duplicate: Whether to skip if URL/query already seen

        Returns:
            True if item was added, False if duplicate
        """
        # Check for duplicates
        if check_duplicate:
            content_hash = item.content_hash
            if self._is_seen(content_hash):
                return False
            self._mark_seen(content_hash)

        queue_key = self._make_queue_key(item)
        item_data = json.dumps(item.to_dict()).encode()

        if self._use_fallback:
            self._queue.append((queue_key, item))
            self._queue.sort(key=lambda x: x[0])
            self._items[str(item.item_id)] = item
            self._save_fallback()
        else:
            # Store item data
            self.db.put(self.ITEM_PREFIX + str(item.item_id).encode(), item_data)
            # Add to queue
            self.db.put(queue_key, str(item.item_id).encode())

        return True

    def push_many(self, items: list[CrawlItem], check_duplicate: bool = True) -> int:
        """Add multiple items to the queue efficiently.

        Args:
            items: List of crawl items to add
            check_duplicate: Whether to skip duplicates

        Returns:
            Number of items actually added
        """
        added = 0

        if self._use_fallback:
            for item in items:
                if self.push(item, check_duplicate):
                    added += 1
        else:
            # Use write batch for efficiency
            batch = rocksdb.WriteBatch()

            for item in items:
                if check_duplicate:
                    content_hash = item.content_hash
                    if self._is_seen(content_hash):
                        continue
                    # Mark seen in batch
                    batch.put(self.SEEN_PREFIX + content_hash.encode(), b"1")

                queue_key = self._make_queue_key(item)
                item_data = json.dumps(item.to_dict()).encode()

                batch.put(self.ITEM_PREFIX + str(item.item_id).encode(), item_data)
                batch.put(queue_key, str(item.item_id).encode())
                added += 1

            self.db.write(batch)

        return added

    def pop(self) -> CrawlItem | None:
        """Pop the highest priority item from the queue.

        Moves item to processing state until marked complete/failed.

        Returns:
            The next item to process, or None if queue is empty
        """
        if self._use_fallback:
            if not self._queue:
                return None

            queue_key, item = self._queue.pop(0)
            del self._items[str(item.item_id)]
            self._processing[str(item.item_id)] = item
            self._save_fallback()
            return item

        # Find first queue key
        it = self.db.iteritems()
        it.seek(self.QUEUE_PREFIX)

        for key, item_id_bytes in it:
            if not key.startswith(self.QUEUE_PREFIX):
                break

            item_id = item_id_bytes.decode()

            # Get item data
            item_data = self.db.get(self.ITEM_PREFIX + item_id.encode())
            if item_data is None:
                # Orphaned queue entry, remove it
                self.db.delete(key)
                continue

            item = CrawlItem.from_dict(json.loads(item_data.decode()))

            # Atomic move to processing
            batch = rocksdb.WriteBatch()
            batch.delete(key)
            batch.put(self.PROCESSING_PREFIX + item_id.encode(), item_data)
            self.db.write(batch)

            return item

        return None

    def peek(self, count: int = 1) -> list[CrawlItem]:
        """Peek at the next items without removing them.

        Args:
            count: Number of items to peek

        Returns:
            List of upcoming items
        """
        items = []

        if self._use_fallback:
            for _, item in self._queue[:count]:
                items.append(item)
        else:
            it = self.db.iteritems()
            it.seek(self.QUEUE_PREFIX)

            for key, item_id_bytes in it:
                if not key.startswith(self.QUEUE_PREFIX):
                    break
                if len(items) >= count:
                    break

                item_id = item_id_bytes.decode()
                item_data = self.db.get(self.ITEM_PREFIX + item_id.encode())
                if item_data:
                    items.append(CrawlItem.from_dict(json.loads(item_data.decode())))

        return items

    def complete(self, item_id: UUID) -> bool:
        """Mark an item as successfully completed.

        Args:
            item_id: The item's UUID

        Returns:
            True if item was in processing state
        """
        item_id_str = str(item_id)

        if self._use_fallback:
            if item_id_str not in self._processing:
                return False
            item = self._processing.pop(item_id_str)
            self._completed[item_id_str] = item
            self._save_fallback()
            return True

        # Move from processing to completed
        item_data = self.db.get(self.PROCESSING_PREFIX + item_id_str.encode())
        if item_data is None:
            return False

        batch = rocksdb.WriteBatch()
        batch.delete(self.PROCESSING_PREFIX + item_id_str.encode())
        batch.put(self.COMPLETED_PREFIX + item_id_str.encode(), item_data)
        self.db.write(batch)

        return True

    def fail(self, item_id: UUID, requeue: bool = True) -> bool:
        """Mark an item as failed.

        Args:
            item_id: The item's UUID
            requeue: Whether to requeue if retries remaining

        Returns:
            True if item was in processing state
        """
        item_id_str = str(item_id)

        if self._use_fallback:
            if item_id_str not in self._processing:
                return False

            item = self._processing.pop(item_id_str)
            item.retry_count += 1

            if requeue and item.retry_count < item.max_retries:
                # Requeue with lower priority (move to next priority level)
                item.priority = self._demote_priority(item.priority)
                queue_key = self._make_queue_key(item)
                self._queue.append((queue_key, item))
                self._queue.sort(key=lambda x: x[0])
                self._items[item_id_str] = item
            else:
                self._failed[item_id_str] = item

            self._save_fallback()
            return True

        # Get item from processing
        item_data = self.db.get(self.PROCESSING_PREFIX + item_id_str.encode())
        if item_data is None:
            return False

        item = CrawlItem.from_dict(json.loads(item_data.decode()))
        item.retry_count += 1

        batch = rocksdb.WriteBatch()
        batch.delete(self.PROCESSING_PREFIX + item_id_str.encode())

        if requeue and item.retry_count < item.max_retries:
            # Requeue with lower priority (move to next priority level)
            item.priority = self._demote_priority(item.priority)
            new_item_data = json.dumps(item.to_dict()).encode()
            queue_key = self._make_queue_key(item)
            batch.put(self.ITEM_PREFIX + item_id_str.encode(), new_item_data)
            batch.put(queue_key, item_id_str.encode())
        else:
            batch.put(self.FAILED_PREFIX + item_id_str.encode(), item_data)

        self.db.write(batch)
        return True

    def _is_seen(self, content_hash: str) -> bool:
        """Check if a content hash has been seen."""
        if self._use_fallback:
            return content_hash in self._seen

        return self.db.get(self.SEEN_PREFIX + content_hash.encode()) is not None

    def _mark_seen(self, content_hash: str) -> None:
        """Mark a content hash as seen."""
        if self._use_fallback:
            self._seen.add(content_hash)
        else:
            self.db.put(self.SEEN_PREFIX + content_hash.encode(), b"1")

    def _demote_priority(self, current: CrawlPriority) -> CrawlPriority:
        """Demote priority to the next lower level.

        Used when requeuing failed items to give them lower priority.
        """
        priority_order = [
            CrawlPriority.CRITICAL,
            CrawlPriority.HIGH,
            CrawlPriority.NORMAL,
            CrawlPriority.LOW,
            CrawlPriority.BACKGROUND,
        ]
        try:
            idx = priority_order.index(current)
            return priority_order[min(idx + 1, len(priority_order) - 1)]
        except ValueError:
            return CrawlPriority.BACKGROUND

    def is_duplicate(self, item: CrawlItem) -> bool:
        """Check if an item's URL/query has already been seen.

        Args:
            item: The crawl item to check

        Returns:
            True if duplicate
        """
        return self._is_seen(item.content_hash)

    def __len__(self) -> int:
        """Get the number of pending items in the queue."""
        if self._use_fallback:
            return len(self._queue)

        count = 0
        it = self.db.iterkeys()
        it.seek(self.QUEUE_PREFIX)

        for key in it:
            if not key.startswith(self.QUEUE_PREFIX):
                break
            count += 1

        return count

    def __bool__(self) -> bool:
        """Check if queue has pending items."""
        return len(self) > 0

    def stats(self) -> FrontierStats:
        """Get statistics about the frontier queue."""
        stats = FrontierStats()

        if self._use_fallback:
            stats.pending_items = len(self._queue)
            stats.completed_items = len(self._completed)
            stats.failed_items = len(self._failed)
            stats.total_items = stats.pending_items + len(self._processing) + stats.completed_items + stats.failed_items
            stats.unique_urls = len(self._seen)

            # Count by priority
            for _, item in self._queue:
                priority_name = item.priority.name
                stats.items_by_priority[priority_name] = stats.items_by_priority.get(priority_name, 0) + 1

                adapter_id = item.adapter_id or "unknown"
                stats.items_by_adapter[adapter_id] = stats.items_by_adapter.get(adapter_id, 0) + 1
        else:
            # Count different key prefixes
            for prefix, attr in [
                (self.QUEUE_PREFIX, "pending_items"),
                (self.PROCESSING_PREFIX, None),
                (self.COMPLETED_PREFIX, "completed_items"),
                (self.FAILED_PREFIX, "failed_items"),
                (self.SEEN_PREFIX, "unique_urls"),
            ]:
                it = self.db.iterkeys()
                it.seek(prefix)
                count = 0
                for key in it:
                    if not key.startswith(prefix):
                        break
                    count += 1

                if attr:
                    setattr(stats, attr, count)
                elif prefix == self.PROCESSING_PREFIX:
                    processing_count = count

            stats.total_items = stats.pending_items + processing_count + stats.completed_items + stats.failed_items

            # Get priority/adapter breakdown from pending items
            it = self.db.iteritems()
            it.seek(self.QUEUE_PREFIX)

            for key, item_id_bytes in it:
                if not key.startswith(self.QUEUE_PREFIX):
                    break

                item_data = self.db.get(self.ITEM_PREFIX + item_id_bytes)
                if item_data:
                    item = CrawlItem.from_dict(json.loads(item_data.decode()))
                    priority_name = item.priority.name
                    stats.items_by_priority[priority_name] = stats.items_by_priority.get(priority_name, 0) + 1

                    adapter_id = item.adapter_id or "unknown"
                    stats.items_by_adapter[adapter_id] = stats.items_by_adapter.get(adapter_id, 0) + 1

        return stats

    def recover_stalled(self, timeout_seconds: float = 300) -> int:
        """Recover items that have been processing too long.

        Items in processing state for longer than timeout are requeued.

        Args:
            timeout_seconds: How long before an item is considered stalled

        Returns:
            Number of items recovered
        """
        now = datetime.now(UTC)
        recovered = 0

        if self._use_fallback:
            stalled = []
            for item_id, item in list(self._processing.items()):
                age = (now - item.created_at).total_seconds()
                if age > timeout_seconds:
                    stalled.append(item_id)

            for item_id in stalled:
                item = self._processing.pop(item_id)
                item.retry_count += 1
                if item.retry_count < item.max_retries:
                    queue_key = self._make_queue_key(item)
                    self._queue.append((queue_key, item))
                    self._items[item_id] = item
                    recovered += 1
                else:
                    self._failed[item_id] = item

            if stalled:
                self._queue.sort(key=lambda x: x[0])
                self._save_fallback()
        else:
            batch = rocksdb.WriteBatch()
            stalled_items = []

            it = self.db.iteritems()
            it.seek(self.PROCESSING_PREFIX)

            for key, item_data in it:
                if not key.startswith(self.PROCESSING_PREFIX):
                    break

                item = CrawlItem.from_dict(json.loads(item_data.decode()))
                age = (now - item.created_at).total_seconds()

                if age > timeout_seconds:
                    stalled_items.append((key, item_data, item))

            for key, item_data, item in stalled_items:
                item.retry_count += 1
                batch.delete(key)

                item_id_str = str(item.item_id)
                if item.retry_count < item.max_retries:
                    new_item_data = json.dumps(item.to_dict()).encode()
                    queue_key = self._make_queue_key(item)
                    batch.put(self.ITEM_PREFIX + item_id_str.encode(), new_item_data)
                    batch.put(queue_key, item_id_str.encode())
                    recovered += 1
                else:
                    batch.put(self.FAILED_PREFIX + item_id_str.encode(), item_data)

            if stalled_items:
                self.db.write(batch)

        return recovered

    def clear(self) -> None:
        """Clear all data from the queue (use with caution)."""
        if self._use_fallback:
            self._queue.clear()
            self._seen.clear()
            self._items.clear()
            self._processing.clear()
            self._completed.clear()
            self._failed.clear()
            if self._fallback_path.exists():
                self._fallback_path.unlink()
        else:
            # Delete all keys
            batch = rocksdb.WriteBatch()
            it = self.db.iterkeys()
            it.seek_to_first()

            for key in it:
                batch.delete(key)

            self.db.write(batch)

    def close(self) -> None:
        """Close the database connection."""
        if self._use_fallback:
            self._save_fallback()
        else:
            del self.db
