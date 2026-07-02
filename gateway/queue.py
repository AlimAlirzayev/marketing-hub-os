"""Durable SQLite job queue for the Xalq Insurance Digital OS gateway.

Why SQLite (not Redis/Postgres): zero external services, no Docker, survives a
restart, and is safe for one writer (the worker) plus many readers (the
front-ends). WAL mode keeps reads non-blocking while the worker writes.

A job moves through:  queued -> running -> done | error | needs_input
                                        -> awaiting_approval -> queued (approved) | rejected
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

# data/ already exists in the repo; the DB lives next to logs and memory.
_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT    NOT NULL,            -- 'cli' | 'telegram'
    chat_id     TEXT,                        -- where to deliver the result
    task        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'queued',
    result      TEXT,
    error       TEXT,
    artifacts   TEXT    NOT NULL DEFAULT '[]',  -- JSON list of file paths
    approved    INTEGER NOT NULL DEFAULT 0,     -- operator approved a risky action
    created_at  REAL    NOT NULL,
    started_at  REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

# Pre-approval databases lack the column; add it in place (SQLite has no
# IF NOT EXISTS for columns, so probe-and-alter).
_MIGRATIONS = ("ALTER TABLE jobs ADD COLUMN approved INTEGER NOT NULL DEFAULT 0",)


@dataclass
class Job:
    id: int
    source: str
    chat_id: str | None
    task: str
    status: str
    result: str | None
    error: str | None
    artifacts: list[str]
    created_at: float
    started_at: float | None
    finished_at: float | None
    approved: bool = False

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> "Job":
        return cls(
            id=row["id"],
            source=row["source"],
            chat_id=row["chat_id"],
            task=row["task"],
            status=row["status"],
            result=row["result"],
            error=row["error"],
            artifacts=json.loads(row["artifacts"] or "[]"),
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            approved=bool(row["approved"] if "approved" in row.keys() else 0),
        )


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        for stmt in _MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def submit(task: str, source: str = "cli", chat_id: str | None = None) -> int:
    """Enqueue a task and return its job id. Returns immediately."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (source, chat_id, task, created_at) VALUES (?,?,?,?)",
            (source, chat_id, task, time.time()),
        )
        return int(cur.lastrowid)


def has_queued_task(task: str, source: str | None = None) -> bool:
    """True if an identical task is already waiting (status='queued').

    Lets recurring producers (e.g. the scheduler) avoid stacking duplicate,
    still-unprocessed jobs when no worker has drained the queue for a while —
    one undelivered morning report is enough, not seven."""
    init_db()
    sql = "SELECT 1 FROM jobs WHERE status='queued' AND task=?"
    params: list = [task]
    if source is not None:
        sql += " AND source=?"
        params.append(source)
    with _connect() as conn:
        return conn.execute(sql + " LIMIT 1", params).fetchone() is not None


def claim_next() -> Job | None:
    """Atomically grab the oldest queued job and mark it running.

    BEGIN IMMEDIATE takes a write lock so two workers can never claim the
    same job. Returns None if the queue is empty.
    """
    with _connect() as conn:
        conn.isolation_level = None  # manual transaction control
        conn.execute("BEGIN IMMEDIATE;")
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT;")
            return None
        conn.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?",
            (time.time(), row["id"]),
        )
        conn.execute("COMMIT;")
        return Job._from_row(row)


def complete(job_id: int, result: str, artifacts: list[str] | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='done', result=?, artifacts=?, finished_at=? WHERE id=?",
            (result, json.dumps(artifacts or []), time.time(), job_id),
        )


def fail(job_id: int, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='error', error=?, finished_at=? WHERE id=?",
            (error, time.time(), job_id),
        )


# --- the human checkpoint (risky actions pause here, never auto-run) -------

def park_for_approval(job_id: int, reason: str = "") -> None:
    """Move a running job to 'awaiting_approval'. The operator decides its fate
    (approve/reject); until then no executor will touch it."""
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status='awaiting_approval', error=? WHERE id=?",
            (reason or None, job_id),
        )


def approve(job_id: int) -> bool:
    """Operator approved a parked risky job: mark approved and re-queue it.
    Returns False if the job wasn't awaiting approval (already decided/gone)."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='queued', approved=1, error=NULL, started_at=NULL "
            "WHERE id=? AND status='awaiting_approval'",
            (job_id,),
        )
        return cur.rowcount > 0


def reject(job_id: int) -> bool:
    """Operator rejected a parked risky job: close it without executing."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='rejected', finished_at=? "
            "WHERE id=? AND status='awaiting_approval'",
            (time.time(), job_id),
        )
        return cur.rowcount > 0


def get(job_id: int) -> Job | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return Job._from_row(row) if row else None


def list_jobs(status: str | None = None, limit: int = 20) -> list[Job]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Job._from_row(r) for r in rows]
