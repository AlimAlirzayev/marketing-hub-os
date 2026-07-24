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
    ingress_key TEXT,                        -- durable source event id (dedup)
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
CREATE TABLE IF NOT EXISTS ingress_events (
    source       TEXT NOT NULL,
    event_id     INTEGER NOT NULL,
    processed_at REAL NOT NULL,
    PRIMARY KEY (source, event_id)
);
CREATE TABLE IF NOT EXISTS ingress_failures (
    source       TEXT NOT NULL,
    event_id     INTEGER NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    updated_at   REAL NOT NULL,
    PRIMARY KEY (source, event_id)
);
"""

# Pre-approval databases lack the column; add it in place (SQLite has no
# IF NOT EXISTS for columns, so probe-and-alter).
_MIGRATIONS = (
    "ALTER TABLE jobs ADD COLUMN approved INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN ingress_key TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_ingress_key "
    "ON jobs(ingress_key) WHERE ingress_key IS NOT NULL",
)


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
    ingress_key: str | None = None

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> "Job":
        return cls(
            id=row["id"],
            source=row["source"],
            chat_id=row["chat_id"],
            ingress_key=row["ingress_key"] if "ingress_key" in row.keys() else None,
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


def submit_once(
    task: str,
    *,
    source: str,
    chat_id: str | None,
    ingress_key: str,
) -> tuple[int, bool]:
    """Atomically enqueue one externally identified input.

    Returns ``(job_id, created)``. Replaying the same Telegram update returns
    the original job instead of creating a second agent run. The unique key is
    source-scoped by the caller (for example ``telegram:123456``).
    """
    init_db()
    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO jobs (source, chat_id, ingress_key, task, created_at) "
                "VALUES (?,?,?,?,?)",
                (source, chat_id, ingress_key, task, time.time()),
            )
            return int(cur.lastrowid), True
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM jobs WHERE ingress_key=?",
                (ingress_key,),
            ).fetchone()
            if row is None:
                raise
            return int(row["id"]), False


def ingress_processed(source: str, event_id: int) -> bool:
    """Whether a source update completed its handler successfully."""
    init_db()
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM ingress_events WHERE source=? AND event_id=?",
            (source, int(event_id)),
        ).fetchone() is not None


def mark_ingress_processed(source: str, event_id: int) -> None:
    """Persist successful handling before Telegram is asked for newer updates."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ingress_events (source, event_id, processed_at) "
            "VALUES (?,?,?)",
            (source, int(event_id), time.time()),
        )
        conn.execute(
            "DELETE FROM ingress_failures WHERE source=? AND event_id=?",
            (source, int(event_id)),
        )


def record_ingress_failure(source: str, event_id: int, error: str) -> int:
    """Record a poison/update failure and return its durable attempt count."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO ingress_failures "
            "(source, event_id, attempts, last_error, updated_at) VALUES (?,?,1,?,?) "
            "ON CONFLICT(source, event_id) DO UPDATE SET "
            "attempts=attempts+1, last_error=excluded.last_error, "
            "updated_at=excluded.updated_at",
            (source, int(event_id), str(error)[:240], time.time()),
        )
        row = conn.execute(
            "SELECT attempts FROM ingress_failures WHERE source=? AND event_id=?",
            (source, int(event_id)),
        ).fetchone()
        return int(row["attempts"])


def last_ingress_event(source: str) -> int | None:
    """Newest durably handled event for restart-safe long-polling."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(event_id) AS event_id FROM ingress_events WHERE source=?",
            (source,),
        ).fetchone()
        value = row["event_id"] if row else None
        return int(value) if value is not None else None


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


def recover_stale_running() -> list[int]:
    """Re-queue jobs left 'running' by a crashed/killed worker.

    Called at worker/supervisor STARTUP only: at that moment no job can
    legitimately be running (single-worker design), so anything still marked
    'running' is an orphan of a previous process death — without this it would
    hang in that state forever and its requester would never get an answer."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT id FROM jobs WHERE status='running'").fetchall()
        ids = [int(r["id"]) for r in rows]
        if ids:
            conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL WHERE status='running'"
            )
        return ids


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


def complete(job_id: int, result: str, artifacts: list[str] | None = None) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='done', result=?, error=NULL, artifacts=?, finished_at=? "
            "WHERE id=? AND status='running'",
            (result, json.dumps(artifacts or []), time.time(), job_id),
        )
        return cur.rowcount > 0


def fail(job_id: int, error: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='error', error=?, finished_at=? "
            "WHERE id=? AND status='running'",
            (error, time.time(), job_id),
        )
        return cur.rowcount > 0


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


def done_between(start_ts: float, end_ts: float) -> list[Job]:
    """Jobs that FINISHED (status='done') within [start_ts, end_ts). The impact
    ledger reads this to count real deliverables the OS produced in a period.
    Read-only; oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status='done' AND finished_at >= ? "
            "AND finished_at < ? ORDER BY finished_at ASC",
            (start_ts, end_ts),
        ).fetchall()
        return [Job._from_row(r) for r in rows]
