"""Recurring jobs — the cron half of "send at night, get in the morning".

A tiny, dependency-free scheduler: store "run this task every day at HH:MM"
entries, and a loop (driven by the supervisor) enqueues them onto the normal job
queue when due. Reuses the durable queue, so a scheduled job is executed and
delivered exactly like a Telegram/CLI job — including the council, security, and
memory paths.

The due-decision is a pure function (``is_due``) so it is fully unit-testable
without sleeping or threads.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import queue

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "jobs.sqlite"
_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _db_path() -> Path:
    return Path(os.getenv("SCHED_DB_PATH", str(_DEFAULT_DB)))


@contextmanager
def _db():
    conn = sqlite3.connect(str(_db_path()), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    _db_path().parent.mkdir(parents=True, exist_ok=True)
    with _db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at_hhmm TEXT NOT NULL,
                task TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'schedule',
                chat_id TEXT,
                last_run_date TEXT,
                enabled INTEGER NOT NULL DEFAULT 1)"""
        )


def add_schedule(at_hhmm: str, task: str, *, source: str = "schedule", chat_id: str | None = None) -> int:
    if not _HHMM_RE.match(at_hhmm.strip()):
        raise ValueError(f"vaxt 'HH:MM' formatında olmalıdır, alındı: {at_hhmm!r}")
    init_db()
    with _db() as c:
        cur = c.execute(
            "INSERT INTO schedules (at_hhmm, task, source, chat_id) VALUES (?,?,?,?)",
            (at_hhmm.strip(), task.strip(), source, chat_id),
        )
        return int(cur.lastrowid)


def list_schedules() -> list[dict]:
    init_db()
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM schedules ORDER BY at_hhmm").fetchall()]


def remove_schedule(schedule_id: int) -> bool:
    init_db()
    with _db() as c:
        cur = c.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        return cur.rowcount > 0


def set_enabled(schedule_id: int, enabled: bool) -> None:
    init_db()
    with _db() as c:
        c.execute("UPDATE schedules SET enabled=? WHERE id=?", (1 if enabled else 0, schedule_id))


def is_due(at_hhmm: str, now: _dt.datetime, last_run_date: str | None) -> bool:
    """Due if we've passed today's scheduled minute and haven't run it today yet."""
    m = _HHMM_RE.match((at_hhmm or "").strip())
    if not m:
        return False
    today = now.date().isoformat()
    if last_run_date == today:
        return False
    hh, mm = int(m.group(1)), int(m.group(2))
    return (now.hour, now.minute) >= (hh, mm)


def run_pending(now: _dt.datetime | None = None) -> list[tuple[int, str]]:
    """Enqueue every due schedule onto the job queue; mark it run for today.
    Returns [(job_id, task)] for what was submitted."""
    now = now or _dt.datetime.now()
    today = now.date().isoformat()
    submitted: list[tuple[int, str]] = []
    init_db()
    with _db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM schedules WHERE enabled=1").fetchall()]
    for s in rows:
        if not is_due(s["at_hhmm"], now, s["last_run_date"]):
            continue
        job_id = queue.submit(s["task"], source=s.get("source") or "schedule", chat_id=s.get("chat_id"))
        with _db() as c:
            c.execute("UPDATE schedules SET last_run_date=? WHERE id=?", (today, s["id"]))
        try:
            from . import sense
            sense.emit("schedule", f"due → job #{job_id}", {"task": s["task"][:80]})
        except Exception:
            pass
        submitted.append((job_id, s["task"]))
    return submitted


if __name__ == "__main__":  # tiny CLI: add / list / remove
    import sys

    args = sys.argv[1:]
    if args and args[0] == "add" and len(args) >= 3:
        sid = add_schedule(args[1], " ".join(args[2:]))
        print(f"added schedule #{sid} at {args[1]}")
    elif args and args[0] == "remove" and len(args) == 2:
        print("removed" if remove_schedule(int(args[1])) else "not found")
    else:
        for s in list_schedules():
            state = "on" if s["enabled"] else "off"
            print(f"#{s['id']} [{state}] {s['at_hhmm']} -> {s['task'][:60]} (last: {s['last_run_date']})")
