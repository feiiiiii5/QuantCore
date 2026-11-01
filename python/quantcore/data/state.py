"""SQLite application state: versioned migrations, watermarks, snapshots and jobs.

One SQLite file per workspace (default ``data/state.sqlite``).  Migrations are applied
inside a transaction and recorded in ``schema_migrations``; re-running ``migrate`` is a
no-op.  The file stores *state*, not market data (Parquet is authoritative for data).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS datasets (
            name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            rows INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            watermark_date INTEGER,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            snapshot_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            synthetic INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            result TEXT,
            error TEXT,
            progress REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
        """,
    ),
    (
        4,
        """
        ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0;
        """,
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteState:
    """Application state store with explicit, idempotent migrations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    # -- connection plumbing ---------------------------------------------
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        finally:
            connection.close()

    # -- migrations -------------------------------------------------------
    def current_version(self) -> int:
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            row = connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)

    def migrate(self) -> int:
        """Apply all pending migrations; returns the resulting schema version."""
        applied: list[int] = []
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = int(
                connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()[
                    "v"
                ]
                or 0
            )
            for version, script in MIGRATIONS:
                if version <= current:
                    continue
                try:
                    connection.executescript(script)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, _now()),
                    )
                    connection.commit()
                except sqlite3.DatabaseError:
                    connection.rollback()
                    raise
                applied.append(version)
        return self.current_version()

    # -- meta -------------------------------------------------------------
    def set_meta(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO meta(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, payload, _now()),
            )
            connection.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    # -- datasets ---------------------------------------------------------
    def upsert_dataset(
        self,
        name: str,
        path: str,
        rows: int,
        content_hash: str,
        watermark_date: int | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO datasets(name, path, rows, content_hash, watermark_date, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                "path=excluded.path, rows=excluded.rows, content_hash=excluded.content_hash, "
                "watermark_date=excluded.watermark_date, updated_at=excluded.updated_at",
                (name, path, rows, content_hash, watermark_date, _now()),
            )
            connection.commit()

    def dataset_info(self, name: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM datasets WHERE name=?", (name,)).fetchone()
        return dict(row) if row is not None else None

    def dataset_rows(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name, rows FROM datasets").fetchall()
        return {row["name"]: int(row["rows"]) for row in rows}

    def watermark(self, name: str) -> int | None:
        info = self.dataset_info(name)
        return None if info is None else info.get("watermark_date")

    # -- snapshots --------------------------------------------------------
    def record_snapshot(
        self, snapshot_id: str, path: str, content_hash: str, synthetic: bool
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO snapshots(snapshot_id, path, content_hash, synthetic, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(snapshot_id) DO NOTHING",
                (snapshot_id, path, content_hash, int(synthetic), _now()),
            )
            connection.commit()

    def list_snapshots(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM snapshots ORDER BY created_at DESC").fetchall()
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            snapshots.append(dict(row))
        return snapshots

    # -- jobs -------------------------------------------------------------
    def enqueue_job(self, kind: str, payload: dict[str, Any]) -> str:
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO jobs(id, kind, status, payload, created_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (job_id, kind, json.dumps(payload, ensure_ascii=False, sort_keys=True), _now()),
            )
            connection.commit()
        return job_id

    def claim_job(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            job_id = row["id"]
            connection.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='pending'",
                (_now(), job_id),
            )
            connection.commit()
            claimed = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job_row(claimed)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job_row(row)

    def list_jobs(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            job = _job_row(row)
            if job is not None:
                jobs.append(job)
        return jobs

    def complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='done', result=?, progress=1.0, finished_at=? "
                "WHERE id=? AND status IN ('pending','running')",
                (json.dumps(result, ensure_ascii=False, sort_keys=True), _now(), job_id),
            )
            connection.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                (error, _now(), job_id),
            )
            connection.commit()

    def cancel_job(self, job_id: str, reason: str = "cancelled by user") -> bool:
        """Mark a pending/running job as cancelled; returns True if it changed state."""
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status='cancelled', error=?, finished_at=? "
                "WHERE id=? AND status IN ('pending', 'running')",
                (reason, _now(), job_id),
            )
            connection.commit()
        return bool(cursor.rowcount)

    def update_job_progress(self, job_id: str, progress: float) -> None:
        value = max(0.0, min(1.0, float(progress)))
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET progress=? WHERE id=?", (value, job_id))
            connection.commit()

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        """Cancel a job: queued jobs finish immediately, running jobs are flagged.

        Returns the updated job row (``None`` when the id is unknown).  A running job keeps
        ``status='running'`` plus ``cancel_requested=1`` until the worker observes the flag
        and transitions it to ``cancelled``; terminal jobs are left untouched.
        """
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                connection.rollback()
                return None
            status = str(row["status"])
            if status in {"pending"}:
                connection.execute(
                    "UPDATE jobs SET status='cancelled', cancel_requested=1, finished_at=? "
                    "WHERE id=?",
                    (_now(), job_id),
                )
            elif status == "running":
                connection.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
            connection.commit()
            updated = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job_row(updated)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def mark_cancelled(self, job_id: str, error: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='cancelled', error=COALESCE(?, error), "
                "cancel_requested=1, finished_at=? WHERE id=? AND status IN ('pending','running')",
                (error, _now(), job_id),
            )
            connection.commit()

    def recover_running_jobs(self) -> int:
        """Mark jobs interrupted by a crash/restart as failed (M5 crash recovery)."""
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE status='running'",
                ("interrupted by server restart", _now()),
            )
            connection.commit()
        return int(cursor.rowcount)

    def clear_jobs(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM jobs")
            connection.commit()


TERMINAL_JOB_STATUSES: frozenset[str] = frozenset({"done", "failed", "cancelled"})
VALID_JOB_STATUSES: frozenset[str] = frozenset(
    {"pending", "running", "done", "failed", "cancelled"}
)


def _job_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["payload"] = json.loads(payload["payload"]) if payload.get("payload") else {}
    payload["result"] = json.loads(payload["result"]) if payload.get("result") else None
    payload["cancel_requested"] = bool(payload.get("cancel_requested"))
    payload["progress"] = float(payload.get("progress") or 0.0)
    return payload
