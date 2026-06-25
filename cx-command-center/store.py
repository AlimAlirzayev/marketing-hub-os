"""SQLite storage for the complaint command center."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import config


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                source TEXT NOT NULL,
                channel TEXT NOT NULL,
                account TEXT,
                external_id TEXT,
                author_name TEXT,
                author_handle TEXT,
                text TEXT NOT NULL,
                rating REAL,
                url TEXT,
                language TEXT,
                sentiment TEXT NOT NULL,
                severity TEXT NOT NULL,
                urgency_score INTEGER NOT NULL,
                category TEXT NOT NULL,
                intent TEXT NOT NULL,
                assigned_team TEXT NOT NULL,
                status TEXT NOT NULL,
                owner TEXT,
                sla_due_at TEXT NOT NULL,
                ai_summary TEXT NOT NULL,
                recommended_reply TEXT NOT NULL,
                tags TEXT NOT NULL,
                metadata TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                UNIQUE(channel, external_id)
            );

            CREATE TABLE IF NOT EXISTS complaint_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                note TEXT,
                before_status TEXT,
                after_status TEXT,
                FOREIGN KEY(complaint_id) REFERENCES complaints(id)
            );

            CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
            CREATE INDEX IF NOT EXISTS idx_complaints_severity ON complaints(severity);
            CREATE INDEX IF NOT EXISTS idx_complaints_channel ON complaints(channel);
            CREATE INDEX IF NOT EXISTS idx_complaints_occurred ON complaints(occurred_at);
            """
        )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _row_to_dict(row: sqlite3.Row) -> dict:
    out = dict(row)
    for key in ("tags", "metadata", "raw_payload"):
        if key in out:
            try:
                out[key] = json.loads(out[key] or "{}")
            except json.JSONDecodeError:
                out[key] = {}
    return out


def upsert_complaint(message: dict, triage: dict) -> dict:
    created = now_iso()
    occurred_at = message.get("occurred_at") or created
    if hasattr(occurred_at, "isoformat"):
        occurred_at = occurred_at.isoformat()
    external_id = message.get("external_id") or f"manual-{created}-{abs(hash(message.get('text', '')))}"
    channel = message.get("channel") or "manual"
    raw_payload = message.get("raw_payload") or message

    fields = {
        "created_at": created,
        "updated_at": created,
        "occurred_at": occurred_at,
        "source": message.get("source") or "manual",
        "channel": channel,
        "account": message.get("account"),
        "external_id": external_id,
        "author_name": message.get("author_name"),
        "author_handle": message.get("author_handle"),
        "text": message.get("text", ""),
        "rating": message.get("rating"),
        "url": message.get("url"),
        "language": message.get("language") or triage.get("language", "az"),
        "sentiment": triage["sentiment"],
        "severity": triage["severity"],
        "urgency_score": triage["urgency_score"],
        "category": triage["category"],
        "intent": triage["intent"],
        "assigned_team": triage["assigned_team"],
        "status": "new",
        "owner": None,
        "sla_due_at": triage["sla_due_at"],
        "ai_summary": triage["summary"],
        "recommended_reply": triage["recommended_reply"],
        "tags": _json(triage.get("tags", [])),
        "metadata": _json(message.get("metadata") or {}),
        "raw_payload": _json(raw_payload),
    }

    with connect() as conn:
        existing = conn.execute(
            "SELECT id, severity, status FROM complaints WHERE channel=? AND external_id=?",
            (channel, external_id),
        ).fetchone()
        columns = list(fields)
        placeholders = ", ".join("?" for _ in columns)
        update_cols = [c for c in columns if c not in {"created_at"}]
        updates = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        conn.execute(
            f"""
            INSERT INTO complaints ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(channel, external_id) DO UPDATE SET {updates}
            """,
            [fields[c] for c in columns],
        )
        row = conn.execute(
            "SELECT * FROM complaints WHERE channel=? AND external_id=?",
            (channel, external_id),
        ).fetchone()
        if row:
            conn.execute(
                """
                INSERT INTO complaint_events
                    (complaint_id, created_at, actor, event_type, note, after_status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["id"], created, "system", "ingested", "Message ingested and triaged", row["status"]),
            )
        out = _row_to_dict(row)
        out["_is_new"] = existing is None
        out["_previous_severity"] = existing["severity"] if existing else None
        return out


def list_complaints(
    *,
    status: str | None = None,
    severity: str | None = None,
    channel: str | None = None,
    q: str | None = None,
    days: int = 30,
    limit: int = 200,
) -> list[dict]:
    clauses = ["occurred_at >= datetime('now', ?)"]
    params: list[Any] = [f"-{days} days"]
    if status and status != "all":
        clauses.append("status = ?")
        params.append(status)
    if severity and severity != "all":
        clauses.append("severity = ?")
        params.append(severity)
    if channel and channel != "all":
        clauses.append("channel = ?")
        params.append(channel)
    if q:
        clauses.append("(text LIKE ? OR author_name LIKE ? OR author_handle LIKE ? OR category LIKE ?)")
        needle = f"%{q}%"
        params.extend([needle, needle, needle, needle])
    sql = f"""
        SELECT * FROM complaints
        WHERE {" AND ".join(clauses)}
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            sla_due_at ASC,
            occurred_at DESC
        LIMIT ?
    """
    params.append(limit)
    with connect() as conn:
        return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def update_status(complaint_id: int, status: str, owner: str | None, note: str | None) -> dict | None:
    ts = now_iso()
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
        if not row:
            return None
        before = row["status"]
        conn.execute(
            """
            UPDATE complaints
            SET status=?, owner=COALESCE(?, owner), updated_at=?
            WHERE id=?
            """,
            (status, owner, ts, complaint_id),
        )
        conn.execute(
            """
            INSERT INTO complaint_events
                (complaint_id, created_at, actor, event_type, note, before_status, after_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (complaint_id, ts, owner or "operator", "status_changed", note, before, status),
        )
        out = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
        return _row_to_dict(out)


def get_complaint(complaint_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
        return _row_to_dict(row) if row else None


def add_event(
    complaint_id: int,
    *,
    actor: str,
    event_type: str,
    note: str | None = None,
    before_status: str | None = None,
    after_status: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO complaint_events
                (complaint_id, created_at, actor, event_type, note, before_status, after_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (complaint_id, now_iso(), actor, event_type, note, before_status, after_status),
        )


def events_for(complaint_id: int) -> list[dict]:
    with connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM complaint_events WHERE complaint_id=? ORDER BY created_at DESC",
                (complaint_id,),
            ).fetchall()
        ]


def count_all() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM complaints").fetchone()
        return int(row["c"])
