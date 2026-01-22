"""SQLite read projection + durable idempotency mapping store."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ..models.fact import Fact, FactStatus

if TYPE_CHECKING:
    from uuid import UUID


class SQLiteProjection:
    """SQLite-based read model and durable idempotency mapping.

    Responsibilities:
    - Fast queries over facts (read model)
    - Durable mapping store for idempotency:
      * external_ids(fingerprint -> gramps_handle, wikidata_qid, wikitree_id, familysearch_id, last_synced_at)
      * fingerprint_index(fingerprint -> entity_type, gramps_handle)
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Enforce PRAGMAs per-connection
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            # Note: PRAGMAs are centralized in _get_conn() to avoid redundant execution
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    statement TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    fact_type TEXT,
                    person_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sources_json TEXT,
                    gps_evaluation_json TEXT,
                    full_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
                CREATE INDEX IF NOT EXISTS idx_facts_person ON facts(person_id);
                CREATE INDEX IF NOT EXISTS idx_facts_type ON facts(fact_type);
                CREATE INDEX IF NOT EXISTS idx_facts_confidence ON facts(confidence_score);

                CREATE TABLE IF NOT EXISTS fact_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_id TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    evidence_type TEXT,
                    FOREIGN KEY (fact_id) REFERENCES facts(fact_id)
                );

                CREATE INDEX IF NOT EXISTS idx_sources_repo ON fact_sources(repository);
                CREATE INDEX IF NOT EXISTS idx_sources_fact ON fact_sources(fact_id);

                CREATE TABLE IF NOT EXISTS persons (
                    person_id TEXT PRIMARY KEY,
                    given_name TEXT,
                    surname TEXT,
                    birth_year INTEGER,
                    death_year INTEGER,
                    fact_count INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(surname, given_name);

                -- Durable idempotency mapping tables
                CREATE TABLE IF NOT EXISTS external_ids (
                    fingerprint TEXT PRIMARY KEY,
                    gramps_handle TEXT,
                    wikidata_qid TEXT,
                    wikitree_id TEXT,
                    familysearch_id TEXT,
                    last_synced_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_external_ids_handles ON external_ids(gramps_handle, wikidata_qid, wikitree_id);

                CREATE TABLE IF NOT EXISTS fingerprint_index (
                    fingerprint TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    gramps_handle TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fingerprint_entity ON fingerprint_index(entity_type);

                -- Locks for claim-before-create (separate table to avoid altering index schema)
                CREATE TABLE IF NOT EXISTS fingerprint_locks (
                    fingerprint TEXT PRIMARY KEY,
                    reserved_by TEXT NOT NULL,
                    reserved_at TEXT NOT NULL
                );

                -- Wikidata statement fingerprint cache
                CREATE TABLE IF NOT EXISTS wikidata_statement_cache (
                    fingerprint TEXT PRIMARY KEY,
                    guid TEXT NOT NULL,
                    entity_id TEXT,
                    property_id TEXT
                );

                -- Revisit history for durable RevisitScheduler state
                CREATE TABLE IF NOT EXISTS revisit_history (
                    source_id TEXT NOT NULL,
                    visit_timestamp TEXT NOT NULL,
                    PRIMARY KEY (source_id, visit_timestamp)
                );
                CREATE INDEX IF NOT EXISTS idx_revisit_source ON revisit_history(source_id);
                """
            )
            conn.commit()

    # --------------------------- Facts API ---------------------------

    def upsert_fact(self, fact: Fact) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO facts (
                    fact_id, version, statement, status, confidence_score,
                    fact_type, person_id, created_at, updated_at,
                    sources_json, gps_evaluation_json, full_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fact_id) DO UPDATE SET
                    version = excluded.version,
                    statement = excluded.statement,
                    status = excluded.status,
                    confidence_score = excluded.confidence_score,
                    fact_type = excluded.fact_type,
                    person_id = excluded.person_id,
                    updated_at = excluded.updated_at,
                    sources_json = excluded.sources_json,
                    gps_evaluation_json = excluded.gps_evaluation_json,
                    full_json = excluded.full_json
                """,
                (
                    str(fact.fact_id),
                    fact.version,
                    fact.statement,
                    fact.status.value,
                    fact.confidence_score,
                    fact.fact_type,
                    fact.person_id,
                    fact.created_at.isoformat(),
                    fact.updated_at.isoformat(),
                    fact.model_dump_json(include={"sources"}),
                    fact.gps_evaluation.model_dump_json() if fact.gps_evaluation else None,
                    fact.model_dump_json(),
                ),
            )

            conn.execute("DELETE FROM fact_sources WHERE fact_id = ?", (str(fact.fact_id),))
            for source in fact.sources:
                conn.execute(
                    """
                    INSERT INTO fact_sources (fact_id, repository, record_id, evidence_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(fact.fact_id),
                        source.repository,
                        source.record_id,
                        source.evidence_type.value,
                    ),
                )

            conn.commit()

    # ------------------------ Idempotency mapping --------------------

    def get_external_ids(self, fingerprint: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM external_ids WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            return dict(row) if row else None

    def set_external_ids(
        self,
        fingerprint: str,
        *,
        gramps_handle: str | None = None,
        wikidata_qid: str | None = None,
        wikitree_id: str | None = None,
        familysearch_id: str | None = None,
        last_synced_at: str | None = None,
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO external_ids (
                    fingerprint, gramps_handle, wikidata_qid, wikitree_id, familysearch_id, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    gramps_handle = COALESCE(excluded.gramps_handle, external_ids.gramps_handle),
                    wikidata_qid = COALESCE(excluded.wikidata_qid, external_ids.wikidata_qid),
                    wikitree_id = COALESCE(excluded.wikitree_id, external_ids.wikitree_id),
                    familysearch_id = COALESCE(excluded.familysearch_id, external_ids.familysearch_id),
                    last_synced_at = COALESCE(excluded.last_synced_at, external_ids.last_synced_at)
                """,
                (fingerprint, gramps_handle, wikidata_qid, wikitree_id, familysearch_id, last_synced_at),
            )
            conn.commit()

    def save_fingerprint(self, entity_type: str, fingerprint: str, gramps_handle: str | None) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO fingerprint_index (fingerprint, entity_type, gramps_handle)
                VALUES (?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    gramps_handle = COALESCE(excluded.gramps_handle, fingerprint_index.gramps_handle)
                """,
                (fingerprint, entity_type, gramps_handle),
            )
            conn.commit()

    def get_gramps_handle_by_fingerprint(self, fingerprint: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT gramps_handle FROM fingerprint_index WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            return row["gramps_handle"] if row and row["gramps_handle"] else None

    # --------------------------- Queries -----------------------------

    def get_fact(self, fact_id: UUID) -> Fact | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT full_json FROM facts WHERE fact_id = ?", (str(fact_id),)
            ).fetchone()
            if row is None:
                return None
            return Fact.model_validate_json(row["full_json"])

    def query_facts(
        self,
        status: FactStatus | None = None,
        person_id: str | None = None,
        fact_type: str | None = None,
        min_confidence: float | None = None,
        repository: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Fact]:
        conditions = []
        params: list = []

        if status is not None:
            conditions.append("f.status = ?")
            params.append(status.value)
        if person_id is not None:
            conditions.append("f.person_id = ?")
            params.append(person_id)
        if fact_type is not None:
            conditions.append("f.fact_type = ?")
            params.append(fact_type)
        if min_confidence is not None:
            conditions.append("f.confidence_score >= ?")
            params.append(min_confidence)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        if repository is not None:
            query = f"""
                SELECT DISTINCT f.full_json FROM facts f
                JOIN fact_sources s ON f.fact_id = s.fact_id
                {where_clause}
                {"AND" if conditions else "WHERE"} s.repository = ?
                ORDER BY f.confidence_score DESC
                LIMIT ? OFFSET ?
            """
            params.extend([repository, limit, offset])
        else:
            query = f"""
                SELECT full_json FROM facts f
                {where_clause}
                ORDER BY f.confidence_score DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [Fact.model_validate_json(row["full_json"]) for row in rows]

    def search_statements(self, search_term: str, limit: int = 50) -> list[Fact]:
        escaped_term = (
            search_term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT full_json FROM facts
                WHERE statement LIKE ? ESCAPE '\\'
                ORDER BY confidence_score DESC
                LIMIT ?
                """,
                (f"%{escaped_term}%", limit),
            ).fetchall()
            return [Fact.model_validate_json(row["full_json"]) for row in rows]

    def get_statistics(self) -> dict:
        with self._get_conn() as conn:
            stats = {}
            for status in FactStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM facts WHERE status = ?", (status.value,)
                ).fetchone()[0]
                stats[f"count_{status.value}"] = count
            stats["total_facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            avg = conn.execute(
                "SELECT AVG(confidence_score) FROM facts WHERE status = 'accepted'"
            ).fetchone()[0]
            stats["avg_confidence_accepted"] = avg or 0.0
            repos = conn.execute(
                """
                SELECT repository, COUNT(*) as cnt
                FROM fact_sources
                GROUP BY repository
                ORDER BY cnt DESC
                """
            ).fetchall()
            stats["sources"] = {row["repository"]: row["cnt"] for row in repos}
            return stats

    def rebuild_from_ledger(self, ledger) -> int:
        """Rebuild the projection from a ledger's facts.

        Args:
            ledger: A FactLedger instance to iterate over

        Returns:
            Number of facts upserted
        """
        count = 0
        for fact in ledger.iter_all_facts():
            self.upsert_fact(fact)
            count += 1
        return count  # Fixed: return outside loop to process all facts

    # ------------------- Transaction API ----------------------------

    @contextmanager
    def transaction(self):
        with self._get_conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ------------------- Fingerprint Reservation API -----------------

    def reserve_fingerprint_lock(self, fingerprint: str, reserved_by: str, ttl_seconds: int = 300) -> bool:
        """Attempt to reserve a lock for a fingerprint (non-blocking).

        Returns True if reserved by this caller. Cleans up stale locks older than ttl_seconds.
        """
        from datetime import datetime, UTC
        now = datetime.now(UTC)
        cutoff = (now.timestamp() - ttl_seconds)
        with self._get_conn() as conn:
            # cleanup stale
            try:
                rows = conn.execute("SELECT fingerprint, reserved_at FROM fingerprint_locks").fetchall()
                for row in rows:
                    try:
                        ts = datetime.fromisoformat(row["reserved_at"]).timestamp()
                        if ts < cutoff:
                            conn.execute("DELETE FROM fingerprint_locks WHERE fingerprint = ?", (row["fingerprint"],))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                conn.execute(
                    "INSERT INTO fingerprint_locks (fingerprint, reserved_by, reserved_at) VALUES (?, ?, ?)",
                    (fingerprint, reserved_by, now.isoformat()),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def release_fingerprint_lock(self, fingerprint: str, reserved_by: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM fingerprint_locks WHERE fingerprint = ? AND reserved_by = ?",
                (fingerprint, reserved_by),
            )
            conn.commit()

    # ------------------- Fingerprint Index Claim API -----------------

    def ensure_fingerprint_row(self, entity_type: str, fingerprint: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO fingerprint_index (fingerprint, entity_type, gramps_handle)
                VALUES (?, ?, NULL)
                ON CONFLICT(fingerprint) DO NOTHING
                """,
                (fingerprint, entity_type),
            )
            conn.commit()

    def claim_fingerprint_handle(self, fingerprint: str, handle: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE fingerprint_index SET gramps_handle = ? WHERE fingerprint = ? AND gramps_handle IS NULL",
                (handle, fingerprint),
            )
            conn.commit()
            return cur.rowcount

    # --------------------- Wikidata Statement Cache ------------------

    def get_statement_guid(self, fingerprint: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT guid FROM wikidata_statement_cache WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            return row["guid"] if row else None

    def set_statement_guid(self, fingerprint: str, guid: str, *, entity_id: str | None = None, property_id: str | None = None) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO wikidata_statement_cache (fingerprint, guid, entity_id, property_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                  guid = excluded.guid,
                  entity_id = COALESCE(excluded.entity_id, wikidata_statement_cache.entity_id),
                  property_id = COALESCE(excluded.property_id, wikidata_statement_cache.property_id)
                """,
                (fingerprint, guid, entity_id, property_id),
            )
            conn.commit()

    # --------------------- Revisit History API ----------------------

    def record_revisit(self, source_id: str, visit_timestamp: str) -> None:
        """Record a source revisit for durable RevisitScheduler state.

        Args:
            source_id: The source ID being revisited
            visit_timestamp: ISO-8601 timestamp of the visit
        """
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO revisit_history (source_id, visit_timestamp)
                VALUES (?, ?)
                """,
                (source_id, visit_timestamp),
            )
            conn.commit()

    def get_revisit_history(self, source_id: str) -> list[str]:
        """Get all revisit timestamps for a source.

        Args:
            source_id: The source ID to look up

        Returns:
            List of ISO-8601 timestamps, sorted ascending
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT visit_timestamp FROM revisit_history WHERE source_id = ? ORDER BY visit_timestamp",
                (source_id,),
            ).fetchall()
            return [row["visit_timestamp"] for row in rows]

    def get_revisit_count(self, source_id: str) -> int:
        """Get the number of times a source has been revisited.

        Args:
            source_id: The source ID to count

        Returns:
            Number of recorded revisits
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM revisit_history WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            return row[0] if row else 0

    def load_all_revisit_history(self) -> dict[str, list[str]]:
        """Load all revisit history into memory.

        Returns:
            Dict mapping source_id to list of ISO-8601 timestamps
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT source_id, visit_timestamp FROM revisit_history ORDER BY source_id, visit_timestamp"
            ).fetchall()
            history: dict[str, list[str]] = {}
            for row in rows:
                source_id = row["source_id"]
                if source_id not in history:
                    history[source_id] = []
                history[source_id].append(row["visit_timestamp"])
            return history

    # ---------------------- Transaction helper ----------------------

    @contextmanager
    def transaction(self):
        with self._get_conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # -------------- Fingerprint index reservation/claim -------------

    def ensure_fingerprint_row(self, entity_type: str, fingerprint: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO fingerprint_index (fingerprint, entity_type, gramps_handle)
                VALUES (?, ?, NULL)
                ON CONFLICT(fingerprint) DO NOTHING
                """,
                (fingerprint, entity_type),
            )
            conn.commit()

    def claim_fingerprint_handle(self, fingerprint: str, handle: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE fingerprint_index SET gramps_handle = ? WHERE fingerprint = ? AND gramps_handle IS NULL",
                (handle, fingerprint),
            )
            conn.commit()
            return cur.rowcount
