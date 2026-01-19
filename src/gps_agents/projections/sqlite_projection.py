"""SQLite read projection for fast queries."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from ..models.fact import Fact, FactStatus


class SQLiteProjection:
    """SQLite-based read model for fast queries.

    This is the read store in the CQRS architecture. It's rebuilt from
    the authoritative RocksDB ledger and optimized for queries.
    """

    def __init__(self, db_path: str | Path):
        """Initialize the projection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.executescript("""
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
            """)
            conn.commit()

    def upsert_fact(self, fact: Fact) -> None:
        """Insert or update a fact in the projection.

        Args:
            fact: The fact to upsert
        """
        with self._get_conn() as conn:
            # Upsert main fact record
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

            # Update sources index
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

    def get_fact(self, fact_id: UUID) -> Fact | None:
        """Retrieve a fact by ID.

        Args:
            fact_id: The fact's UUID

        Returns:
            The Fact or None if not found
        """
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
        """Query facts with filters.

        Args:
            status: Filter by status
            person_id: Filter by person
            fact_type: Filter by fact type
            min_confidence: Minimum confidence score
            repository: Filter by source repository
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of matching facts
        """
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
            # Join with sources table
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
        """Full-text search on fact statements.

        Args:
            search_term: Text to search for
            limit: Maximum results

        Returns:
            Matching facts
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT full_json FROM facts
                WHERE statement LIKE ?
                ORDER BY confidence_score DESC
                LIMIT ?
                """,
                (f"%{search_term}%", limit),
            ).fetchall()
            return [Fact.model_validate_json(row["full_json"]) for row in rows]

    def get_statistics(self) -> dict:
        """Get summary statistics about the projection.

        Returns:
            Dictionary of statistics
        """
        with self._get_conn() as conn:
            stats = {}

            # Count by status
            for status in FactStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM facts WHERE status = ?", (status.value,)
                ).fetchone()[0]
                stats[f"count_{status.value}"] = count

            # Total facts
            stats["total_facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

            # Average confidence
            avg = conn.execute(
                "SELECT AVG(confidence_score) FROM facts WHERE status = 'accepted'"
            ).fetchone()[0]
            stats["avg_confidence_accepted"] = avg or 0.0

            # Source breakdown
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
        """Rebuild the projection from the authoritative ledger.

        Args:
            ledger: FactLedger instance

        Returns:
            Number of facts processed
        """
        count = 0
        for fact in ledger.iter_all_facts():
            self.upsert_fact(fact)
            count += 1
        return count
