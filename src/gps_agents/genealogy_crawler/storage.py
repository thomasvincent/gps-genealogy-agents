"""SQLite storage for the genealogy crawler.

Provides persistence for the knowledge graph, provenance data, and audit logs.
Implements the data model from models.py with SQLite-specific serialization.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generator
from uuid import UUID

from .models import (
    Assertion,
    AssertionStatus,
    AuditActionType,
    AuditLog,
    ClueItem,
    CrawlerState,
    EvidenceClaim,
    EvidenceType,
    Event,
    EventType,
    FrontierItem,
    HypothesisType,
    MergeCluster,
    NoveltyGuard,
    Person,
    QueryRecord,
    QueueItemStatus,
    Relationship,
    RelationshipType,
    RevisitItem,
    SourceRecord,
    SourceTier,
)


# =============================================================================
# Schema Definitions
# =============================================================================


SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Persons table
CREATE TABLE IF NOT EXISTS persons (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    given_name TEXT,
    surname TEXT,
    name_variants TEXT,  -- JSON array
    birth_date_earliest TEXT,
    birth_date_latest TEXT,
    birth_date_display TEXT,
    death_date_earliest TEXT,
    death_date_latest TEXT,
    death_date_display TEXT,
    birth_place TEXT,
    birth_place_normalized TEXT,
    death_place TEXT,
    death_place_normalized TEXT,
    is_living INTEGER DEFAULT 0,
    privacy_redacted INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.5,
    merge_cluster_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(canonical_name);
CREATE INDEX IF NOT EXISTS idx_persons_merge_cluster ON persons(merge_cluster_id);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    date_earliest TEXT,
    date_latest TEXT,
    date_display TEXT,
    place TEXT,
    place_normalized TEXT,
    participants TEXT,  -- JSON array of UUIDs
    participant_roles TEXT,  -- JSON object
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- Relationships table
CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    person1_id TEXT NOT NULL,
    person2_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    person1_role TEXT,
    person2_role TEXT,
    start_date TEXT,
    end_date TEXT,
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    FOREIGN KEY (person1_id) REFERENCES persons(id),
    FOREIGN KEY (person2_id) REFERENCES persons(id)
);
CREATE INDEX IF NOT EXISTS idx_relationships_person1 ON relationships(person1_id);
CREATE INDEX IF NOT EXISTS idx_relationships_person2 ON relationships(person2_id);

-- Assertions table
CREATE TABLE IF NOT EXISTS assertions (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_value TEXT,  -- JSON serialized
    field_value_normalized TEXT,  -- JSON serialized
    confidence REAL DEFAULT 0.5,
    status TEXT DEFAULT 'unverified',
    asserted_at TEXT NOT NULL,
    asserted_by TEXT DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_assertions_entity ON assertions(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_assertions_field ON assertions(field_name);

-- Evidence claims table
CREATE TABLE IF NOT EXISTS evidence_claims (
    id TEXT PRIMARY KEY,
    source_record_id TEXT NOT NULL,
    assertion_id TEXT,
    citation_snippet TEXT NOT NULL,
    snippet_context TEXT,
    extraction_method TEXT NOT NULL,
    extractor_version TEXT,
    source_reliability REAL DEFAULT 0.5,
    evidence_type TEXT DEFAULT 'secondary',
    llm_rationale TEXT,
    llm_confidence REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_record_id) REFERENCES source_records(id),
    FOREIGN KEY (assertion_id) REFERENCES assertions(id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_source ON evidence_claims(source_record_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_assertion ON evidence_claims(assertion_id);

-- Source records table
CREATE TABLE IF NOT EXISTS source_records (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_tier INTEGER NOT NULL,
    accessed_at TEXT NOT NULL,
    content_hash TEXT,
    raw_text TEXT,
    raw_extracted TEXT,  -- JSON
    metadata TEXT,  -- JSON
    robots_respected INTEGER DEFAULT 1,
    cache_hit INTEGER DEFAULT 0,
    rate_limited INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_source_records_url ON source_records(url);
CREATE INDEX IF NOT EXISTS idx_source_records_hash ON source_records(content_hash);

-- Merge clusters table
CREATE TABLE IF NOT EXISTS merge_clusters (
    id TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    member_ids TEXT NOT NULL,  -- JSON array
    merge_rationale TEXT NOT NULL,
    why_not_split TEXT,
    similarity_score REAL DEFAULT 0.0,
    feature_scores TEXT,  -- JSON
    is_reversible INTEGER DEFAULT 1,
    original_states TEXT,  -- JSON
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT 'entity_resolver',
    FOREIGN KEY (canonical_id) REFERENCES persons(id)
);
CREATE INDEX IF NOT EXISTS idx_merge_clusters_canonical ON merge_clusters(canonical_id);

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    before_state TEXT,  -- JSON
    after_state TEXT,  -- JSON
    agent_name TEXT NOT NULL,
    rationale TEXT,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);

-- Queue tables
CREATE TABLE IF NOT EXISTS frontier_queue (
    id TEXT PRIMARY KEY,
    priority REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    target_entity_id TEXT,
    target_entity_type TEXT,
    query_string TEXT NOT NULL,
    query_hash TEXT,
    source_tiers TEXT,  -- JSON array
    context TEXT,  -- JSON
    discovered_from TEXT
);
CREATE INDEX IF NOT EXISTS idx_frontier_queue_status ON frontier_queue(status, priority DESC);

CREATE TABLE IF NOT EXISTS clue_queue (
    id TEXT PRIMARY KEY,
    priority REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    hypothesis_type TEXT NOT NULL,
    hypothesis_text TEXT NOT NULL,
    is_fact INTEGER DEFAULT 0,
    related_person_id TEXT,
    related_source_id TEXT,
    suggested_queries TEXT,  -- JSON array
    suggested_sources TEXT,  -- JSON array
    evidence_hint TEXT,
    triggering_snippet TEXT
);
CREATE INDEX IF NOT EXISTS idx_clue_queue_status ON clue_queue(status, priority DESC);

CREATE TABLE IF NOT EXISTS revisit_queue (
    id TEXT PRIMARY KEY,
    priority REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    original_source_id TEXT NOT NULL,
    original_query TEXT NOT NULL,
    improved_query TEXT NOT NULL,
    query_improvements TEXT,  -- JSON array
    revisit_reason TEXT NOT NULL,
    triggering_clue_id TEXT,
    triggering_discovery TEXT,
    last_visited_at TEXT,
    previous_results_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_revisit_queue_status ON revisit_queue(status, priority DESC);

-- Novelty guard (query history)
CREATE TABLE IF NOT EXISTS query_history (
    query_hash TEXT NOT NULL,
    source_tier INTEGER NOT NULL,
    query_string TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    result_hash TEXT,
    PRIMARY KEY (query_hash, source_tier)
);
CREATE INDEX IF NOT EXISTS idx_query_history_hash ON query_history(query_hash);

-- Crawler sessions table
CREATE TABLE IF NOT EXISTS crawler_sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    seed_person_id TEXT,
    target_generations INTEGER DEFAULT 4,
    budget_limit REAL DEFAULT 1000.0,
    budget_used REAL DEFAULT 0.0,
    max_iterations INTEGER DEFAULT 500,
    iteration_count INTEGER DEFAULT 0,
    queries_since_last_discovery INTEGER DEFAULT 0,
    recent_discovery_rate REAL DEFAULT 1.0,
    is_running INTEGER DEFAULT 0,
    is_terminated INTEGER DEFAULT 0,
    termination_reason TEXT
);
"""


# =============================================================================
# Storage Class
# =============================================================================


class CrawlerStorage:
    """SQLite storage for the genealogy crawler."""

    def __init__(self, db_path: Path | str = ":memory:"):
        """Initialize storage.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory
        """
        self.db_path = str(db_path)
        self._connection: sqlite3.Connection | None = None
        self._initialize_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _initialize_schema(self) -> None:
        """Initialize database schema."""
        with self.transaction() as cursor:
            cursor.executescript(SCHEMA_SQL)
            # Check if we need to record schema version
            cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
                )

    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # =========================================================================
    # Serialization Helpers
    # =========================================================================

    @staticmethod
    def _serialize_datetime(dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return dt.isoformat() if dt else None

    @staticmethod
    def _deserialize_datetime(s: str | None) -> datetime | None:
        """Deserialize ISO format to datetime."""
        if not s:
            return None
        return datetime.fromisoformat(s)

    @staticmethod
    def _serialize_json(obj: Any) -> str | None:
        """Serialize object to JSON string."""
        if obj is None:
            return None
        return json.dumps(obj, default=str)

    @staticmethod
    def _deserialize_json(s: str | None) -> Any:
        """Deserialize JSON string to object."""
        if not s:
            return None
        return json.loads(s)

    # =========================================================================
    # Person CRUD
    # =========================================================================

    def save_person(self, person: Person) -> None:
        """Save a person to the database."""
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO persons (
                    id, canonical_name, given_name, surname, name_variants,
                    birth_date_earliest, birth_date_latest, birth_date_display,
                    death_date_earliest, death_date_latest, death_date_display,
                    birth_place, birth_place_normalized, death_place, death_place_normalized,
                    is_living, privacy_redacted, confidence, merge_cluster_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(person.id),
                    person.canonical_name,
                    person.given_name,
                    person.surname,
                    self._serialize_json(person.name_variants),
                    self._serialize_datetime(person.birth_date_earliest),
                    self._serialize_datetime(person.birth_date_latest),
                    person.birth_date_display,
                    self._serialize_datetime(person.death_date_earliest),
                    self._serialize_datetime(person.death_date_latest),
                    person.death_date_display,
                    person.birth_place,
                    person.birth_place_normalized,
                    person.death_place,
                    person.death_place_normalized,
                    int(person.is_living),
                    int(person.privacy_redacted),
                    person.confidence,
                    str(person.merge_cluster_id) if person.merge_cluster_id else None,
                    self._serialize_datetime(person.created_at),
                    self._serialize_datetime(person.updated_at),
                ),
            )

    def get_person(self, person_id: UUID | str) -> Person | None:
        """Get a person by ID."""
        with self.transaction() as cursor:
            cursor.execute("SELECT * FROM persons WHERE id = ?", (str(person_id),))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_person(row)

    def _row_to_person(self, row: sqlite3.Row) -> Person:
        """Convert database row to Person model."""
        return Person(
            id=UUID(row["id"]),
            canonical_name=row["canonical_name"],
            given_name=row["given_name"],
            surname=row["surname"],
            name_variants=self._deserialize_json(row["name_variants"]) or [],
            birth_date_earliest=self._deserialize_datetime(row["birth_date_earliest"]),
            birth_date_latest=self._deserialize_datetime(row["birth_date_latest"]),
            birth_date_display=row["birth_date_display"],
            death_date_earliest=self._deserialize_datetime(row["death_date_earliest"]),
            death_date_latest=self._deserialize_datetime(row["death_date_latest"]),
            death_date_display=row["death_date_display"],
            birth_place=row["birth_place"],
            birth_place_normalized=row["birth_place_normalized"],
            death_place=row["death_place"],
            death_place_normalized=row["death_place_normalized"],
            is_living=bool(row["is_living"]),
            privacy_redacted=bool(row["privacy_redacted"]),
            confidence=row["confidence"],
            merge_cluster_id=UUID(row["merge_cluster_id"]) if row["merge_cluster_id"] else None,
            created_at=self._deserialize_datetime(row["created_at"]) or datetime.now(UTC),
            updated_at=self._deserialize_datetime(row["updated_at"]) or datetime.now(UTC),
        )

    def list_persons(self, limit: int = 100, offset: int = 0) -> list[Person]:
        """List all persons."""
        with self.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM persons ORDER BY canonical_name LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [self._row_to_person(row) for row in cursor.fetchall()]

    # =========================================================================
    # Source Record CRUD
    # =========================================================================

    def save_source_record(self, record: SourceRecord) -> None:
        """Save a source record."""
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO source_records (
                    id, url, source_name, source_tier, accessed_at,
                    content_hash, raw_text, raw_extracted, metadata,
                    robots_respected, cache_hit, rate_limited
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    record.url,
                    record.source_name,
                    record.source_tier.value,
                    self._serialize_datetime(record.accessed_at),
                    record.content_hash,
                    record.raw_text,
                    self._serialize_json(record.raw_extracted),
                    self._serialize_json(record.metadata),
                    int(record.robots_respected),
                    int(record.cache_hit),
                    int(record.rate_limited),
                ),
            )

    def get_source_record(self, record_id: UUID | str) -> SourceRecord | None:
        """Get a source record by ID."""
        with self.transaction() as cursor:
            cursor.execute("SELECT * FROM source_records WHERE id = ?", (str(record_id),))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_source_record(row)

    def _row_to_source_record(self, row: sqlite3.Row) -> SourceRecord:
        """Convert database row to SourceRecord model."""
        return SourceRecord(
            id=UUID(row["id"]),
            url=row["url"],
            source_name=row["source_name"],
            source_tier=SourceTier(row["source_tier"]),
            accessed_at=self._deserialize_datetime(row["accessed_at"]) or datetime.now(UTC),
            content_hash=row["content_hash"],
            raw_text=row["raw_text"],
            raw_extracted=self._deserialize_json(row["raw_extracted"]) or {},
            metadata=self._deserialize_json(row["metadata"]) or {},
            robots_respected=bool(row["robots_respected"]),
            cache_hit=bool(row["cache_hit"]),
            rate_limited=bool(row["rate_limited"]),
        )

    # =========================================================================
    # Audit Log
    # =========================================================================

    def save_audit_log(self, log: AuditLog) -> None:
        """Save an audit log entry."""
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_log (
                    id, action_type, entity_id, entity_type,
                    before_state, after_state, agent_name, rationale, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(log.id),
                    log.action_type.value,
                    str(log.entity_id),
                    log.entity_type,
                    self._serialize_json(log.before_state),
                    self._serialize_json(log.after_state),
                    log.agent_name,
                    log.rationale,
                    self._serialize_datetime(log.timestamp),
                ),
            )

    def get_audit_log(
        self,
        entity_id: UUID | str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit log entries."""
        with self.transaction() as cursor:
            if entity_id:
                cursor.execute(
                    "SELECT * FROM audit_log WHERE entity_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (str(entity_id), limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            return [self._row_to_audit_log(row) for row in cursor.fetchall()]

    def _row_to_audit_log(self, row: sqlite3.Row) -> AuditLog:
        """Convert database row to AuditLog model."""
        return AuditLog(
            id=UUID(row["id"]),
            action_type=AuditActionType(row["action_type"]),
            entity_id=UUID(row["entity_id"]),
            entity_type=row["entity_type"],
            before_state=self._deserialize_json(row["before_state"]),
            after_state=self._deserialize_json(row["after_state"]),
            agent_name=row["agent_name"],
            rationale=row["rationale"],
            timestamp=self._deserialize_datetime(row["timestamp"]) or datetime.now(UTC),
        )

    # =========================================================================
    # State Persistence
    # =========================================================================

    def save_state(self, state: CrawlerState) -> None:
        """Save complete crawler state to database."""
        # Save session
        with self.transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO crawler_sessions (
                    session_id, started_at, seed_person_id, target_generations,
                    budget_limit, budget_used, max_iterations, iteration_count,
                    queries_since_last_discovery, recent_discovery_rate,
                    is_running, is_terminated, termination_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(state.session_id),
                    self._serialize_datetime(state.started_at),
                    str(state.seed_person_id) if state.seed_person_id else None,
                    state.target_generations,
                    state.budget_limit,
                    state.budget_used,
                    state.max_iterations,
                    state.iteration_count,
                    state.queries_since_last_discovery,
                    state.recent_discovery_rate,
                    int(state.is_running),
                    int(state.is_terminated),
                    state.termination_reason,
                ),
            )

        # Save all persons
        for person in state.persons.values():
            self.save_person(person)

        # Save all source records
        for record in state.source_records.values():
            self.save_source_record(record)

        # Save all audit logs
        for log in state.audit_log:
            self.save_audit_log(log)

    def load_state(self, session_id: UUID | str) -> CrawlerState | None:
        """Load crawler state from database."""
        with self.transaction() as cursor:
            cursor.execute(
                "SELECT * FROM crawler_sessions WHERE session_id = ?",
                (str(session_id),),
            )
            row = cursor.fetchone()
            if not row:
                return None

            state = CrawlerState(
                session_id=UUID(row["session_id"]),
                started_at=self._deserialize_datetime(row["started_at"]) or datetime.now(UTC),
                seed_person_id=UUID(row["seed_person_id"]) if row["seed_person_id"] else None,
                target_generations=row["target_generations"],
                budget_limit=row["budget_limit"],
                budget_used=row["budget_used"],
                max_iterations=row["max_iterations"],
                iteration_count=row["iteration_count"],
                queries_since_last_discovery=row["queries_since_last_discovery"],
                recent_discovery_rate=row["recent_discovery_rate"],
                is_running=bool(row["is_running"]),
                is_terminated=bool(row["is_terminated"]),
                termination_reason=row["termination_reason"],
            )

            # Load persons
            for person in self.list_persons(limit=10000):
                state.persons[str(person.id)] = person

            return state
