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
    telegram_status_message_id INTEGER,         -- editable progress/approval card
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    approval_expires_at REAL,
    progress_stage TEXT,
    progress_updated_at REAL,
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
CREATE TABLE IF NOT EXISTS channel_health (
    source                 TEXT PRIMARY KEY,
    last_poll_started_at   REAL,
    last_poll_completed_at REAL,
    last_error_at          REAL,
    last_error             TEXT,
    updated_at             REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ingress_dead_letters (
    source          TEXT NOT NULL,
    event_id        INTEGER NOT NULL,
    chat_id         TEXT,
    task            TEXT,
    attempts        INTEGER NOT NULL,
    last_error      TEXT,
    quarantined_at  REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'quarantined',
    resolved_at     REAL,
    resubmitted_job_id INTEGER,
    PRIMARY KEY (source, event_id)
);
"""

# Pre-approval databases lack the column; add it in place (SQLite has no
# IF NOT EXISTS for columns, so probe-and-alter).
_MIGRATIONS = (
    "ALTER TABLE jobs ADD COLUMN approved INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN ingress_key TEXT",
    "ALTER TABLE jobs ADD COLUMN telegram_status_message_id INTEGER",
    "ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs ADD COLUMN approval_expires_at REAL",
    "ALTER TABLE jobs ADD COLUMN progress_stage TEXT",
    "ALTER TABLE jobs ADD COLUMN progress_updated_at REAL",
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
    telegram_status_message_id: int | None = None
    cancel_requested: bool = False
    approval_expires_at: float | None = None
    progress_stage: str | None = None
    progress_updated_at: float | None = None

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
            telegram_status_message_id=(
                int(row["telegram_status_message_id"])
                if "telegram_status_message_id" in row.keys()
                and row["telegram_status_message_id"] is not None
                else None
            ),
            cancel_requested=bool(
                row["cancel_requested"] if "cancel_requested" in row.keys() else 0
            ),
            approval_expires_at=(
                float(row["approval_expires_at"])
                if "approval_expires_at" in row.keys()
                and row["approval_expires_at"] is not None
                else None
            ),
            progress_stage=(
                row["progress_stage"] if "progress_stage" in row.keys() else None
            ),
            progress_updated_at=(
                float(row["progress_updated_at"])
                if "progress_updated_at" in row.keys()
                and row["progress_updated_at"] is not None
                else None
            ),
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


def update_channel_health(source: str, **fields) -> None:
    """Persist cross-process channel liveness for Workdesk and diagnostics."""
    allowed = {
        "last_poll_started_at",
        "last_poll_completed_at",
        "last_error_at",
        "last_error",
    }
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO channel_health (source, updated_at) VALUES (?,?)",
            (source, time.time()),
        )
        assignments = ", ".join(f"{key}=?" for key in values)
        conn.execute(
            f"UPDATE channel_health SET {assignments}, updated_at=? WHERE source=?",
            (*values.values(), time.time(), source),
        )


def channel_health(source: str) -> dict:
    """Read one channel's durable, secret-free liveness record."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM channel_health WHERE source=?",
            (source,),
        ).fetchone()
        return dict(row) if row else {}


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
        rows = conn.execute(
            "SELECT id,cancel_requested FROM jobs WHERE status='running'"
        ).fetchall()
        ids = [int(r["id"]) for r in rows if not bool(r["cancel_requested"])]
        cancelled = [int(r["id"]) for r in rows if bool(r["cancel_requested"])]
        if ids:
            conn.execute(
                "UPDATE jobs SET status='queued', started_at=NULL WHERE status='running' "
                "AND cancel_requested=0"
            )
        if cancelled:
            marks = ",".join("?" for _ in cancelled)
            conn.execute(
                f"UPDATE jobs SET status='cancelled', error='cancelled by owner', "
                f"finished_at=? WHERE id IN ({marks})",
                (time.time(), *cancelled),
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
            "WHERE id=? AND status='running' AND cancel_requested=0",
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

def park_for_approval(
    job_id: int,
    reason: str = "",
    *,
    ttl_seconds: int = 1800,
) -> bool:
    """Move a running job to 'awaiting_approval'. The operator decides its fate
    (approve/reject); until then no executor will touch it."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='awaiting_approval', error=?, "
            "approval_expires_at=? WHERE id=? AND status IN ('queued','running') "
            "AND cancel_requested=0",
            (reason or None, time.time() + max(60, int(ttl_seconds)), job_id),
        )
        return cur.rowcount > 0


def approve(job_id: int) -> bool:
    """Operator approved a parked risky job: mark approved and re-queue it.
    Returns False if the job wasn't awaiting approval (already decided/gone)."""
    with _connect() as conn:
        now = time.time()
        cur = conn.execute(
            "UPDATE jobs SET status='queued', approved=1, error=NULL, started_at=NULL, "
            "approval_expires_at=NULL WHERE id=? AND status='awaiting_approval' "
            "AND (approval_expires_at IS NULL OR approval_expires_at>=?)",
            (job_id, now),
        )
        return cur.rowcount > 0


def reject(job_id: int) -> bool:
    """Operator rejected a parked risky job: close it without executing."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='rejected', approval_expires_at=NULL, finished_at=? "
            "WHERE id=? AND status='awaiting_approval'",
            (time.time(), job_id),
        )
        return cur.rowcount > 0


def cancel(job_id: int) -> bool:
    """Compatibility boolean for callers that only cancel stoppable work."""
    return request_cancel(job_id) == "cancelled"


def request_cancel(job_id: int) -> str:
    """Cancel now or request cooperative cancellation of a running job.

    Returns ``cancelled`` for work stopped before execution, ``requested`` when
    a running job will stop at its next safe checkpoint, or ``unavailable`` for
    terminal/missing work.
    """
    with _connect() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        row = conn.execute(
            "SELECT status FROM jobs WHERE id=?",
            (int(job_id),),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT;")
            return "unavailable"
        if row["status"] in ("queued", "awaiting_approval"):
            conn.execute(
                "UPDATE jobs SET status='cancelled', cancel_requested=1, "
                "approval_expires_at=NULL, error='cancelled by owner', finished_at=? "
                "WHERE id=?",
                (time.time(), int(job_id)),
            )
            conn.execute("COMMIT;")
            return "cancelled"
        if row["status"] == "running":
            conn.execute(
                "UPDATE jobs SET cancel_requested=1, error='cancellation requested' "
                "WHERE id=? AND status='running'",
                (int(job_id),),
            )
            conn.execute("COMMIT;")
            return "requested"
        conn.execute("COMMIT;")
        return "unavailable"


class JobCancelled(RuntimeError):
    """Raised only at a governed cooperative cancellation checkpoint."""


def cancellation_checkpoint(job_id: int) -> None:
    """Raise when the owner requested cancellation of this running job."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM jobs WHERE id=? AND status='running'",
            (int(job_id),),
        ).fetchone()
    if row and bool(row["cancel_requested"]):
        raise JobCancelled(f"job #{job_id} cancelled by owner")


def mark_cancelled(job_id: int) -> bool:
    """Commit a running job's cooperative cancellation."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='cancelled', error='cancelled by owner', "
            "finished_at=? WHERE id=? AND status='running' AND cancel_requested=1",
            (time.time(), int(job_id)),
        )
        return cur.rowcount > 0


def expire_approvals(now: float | None = None) -> list[int]:
    """Expire stale human checkpoints and return affected job ids."""
    cutoff = time.time() if now is None else float(now)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status='awaiting_approval' "
            "AND approval_expires_at IS NOT NULL AND approval_expires_at<?",
            (cutoff,),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if ids:
            marks = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE jobs SET status='cancelled', error='approval expired', "
                f"finished_at=?, approval_expires_at=NULL WHERE id IN ({marks})",
                (cutoff, *ids),
            )
        return ids


def set_progress(job_id: int, stage: str) -> bool:
    """Persist a short operator-facing stage for Telegram and Workdesk."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET progress_stage=?, progress_updated_at=? WHERE id=?",
            (str(stage)[:240], time.time(), int(job_id)),
        )
        return cur.rowcount > 0


def quarantine_ingress(
    source: str,
    event_id: int,
    *,
    chat_id: str | None,
    task: str | None,
    attempts: int,
    error: str,
) -> None:
    """Retain a redacted, re-playable task envelope without raw Telegram JSON."""
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO ingress_dead_letters "
            "(source,event_id,chat_id,task,attempts,last_error,quarantined_at,status) "
            "VALUES (?,?,?,?,?,?,?,'quarantined') "
            "ON CONFLICT(source,event_id) DO UPDATE SET attempts=excluded.attempts, "
            "last_error=excluded.last_error, quarantined_at=excluded.quarantined_at, "
            "task=excluded.task, chat_id=excluded.chat_id, status='quarantined', "
            "resolved_at=NULL, resubmitted_job_id=NULL",
            (
                source,
                int(event_id),
                chat_id,
                task,
                int(attempts),
                str(error)[:240],
                time.time(),
            ),
        )


def list_dead_letters(
    *,
    source: str = "telegram",
    status: str = "quarantined",
    limit: int = 50,
) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ingress_dead_letters WHERE source=? AND status=? "
            "ORDER BY quarantined_at DESC LIMIT ?",
            (source, status, max(1, min(int(limit), 200))),
        ).fetchall()
        return [dict(row) for row in rows]


def resubmit_dead_letter(source: str, event_id: int) -> int | None:
    """Atomically resubmit one safe retained task exactly once."""
    init_db()
    with _connect() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        row = conn.execute(
            "SELECT * FROM ingress_dead_letters WHERE source=? AND event_id=? "
            "AND status='quarantined'",
            (source, int(event_id)),
        ).fetchone()
        if row is None or not row["task"]:
            conn.execute("COMMIT;")
            return None
        cur = conn.execute(
            "INSERT INTO jobs (source,chat_id,ingress_key,task,created_at) "
            "VALUES (?,?,?,?,?)",
            (
                source,
                row["chat_id"],
                f"dead-letter:{source}:{int(event_id)}",
                row["task"],
                time.time(),
            ),
        )
        job_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE ingress_dead_letters SET status='resubmitted', resolved_at=?, "
            "resubmitted_job_id=? WHERE source=? AND event_id=?",
            (time.time(), job_id, source, int(event_id)),
        )
        conn.execute("COMMIT;")
        return job_id


def dismiss_dead_letter(source: str, event_id: int) -> bool:
    """Close a quarantined event without executing it."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE ingress_dead_letters SET status='dismissed', resolved_at=? "
            "WHERE source=? AND event_id=? AND status='quarantined'",
            (time.time(), source, int(event_id)),
        )
        return cur.rowcount > 0


def set_telegram_status_message(job_id: int, message_id: int) -> bool:
    """Persist the editable Telegram card so worker restarts can resume it."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET telegram_status_message_id=? WHERE id=?",
            (int(message_id), int(job_id)),
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
