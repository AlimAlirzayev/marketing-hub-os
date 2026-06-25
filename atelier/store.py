"""SQLite persistence for Atelier.

Briefs -> concepts -> (uploaded image + critique + rating). Local-first by
design: SQLite keeps the MVP zero-infra and portable on the locked-down
machine. The connector boundary is deliberately small, so swapping to the
Postgres already in docker-compose later is a contained change.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brief       TEXT NOT NULL,
    style       TEXT,
    voice       TEXT,
    dialect     TEXT,
    format      TEXT,
    source      TEXT,
    created     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concepts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id    INTEGER NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    angle       TEXT,
    rationale   TEXT,
    prompt      TEXT NOT NULL,
    caption     TEXT,
    image_path  TEXT,
    critique    TEXT,
    score       INTEGER,
    rating      INTEGER DEFAULT 0,
    starred     INTEGER DEFAULT 0,
    created     TEXT NOT NULL
);
"""


@contextmanager
def _conn():
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)


def _row_to_concept(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["critique"] = json.loads(d["critique"]) if d.get("critique") else None
    d["starred"] = bool(d["starred"])
    return d


def create_brief(brief: str, meta: dict, source: str,
                 concepts: list[dict]) -> dict:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO briefs (brief, style, voice, dialect, format, source, "
            "created) VALUES (?,?,?,?,?,?,?)",
            (brief, meta.get("style"), meta.get("voice"), meta.get("dialect"),
             meta.get("format"), source, config.now_iso()))
        brief_id = cur.lastrowid
        for c in concepts:
            con.execute(
                "INSERT INTO concepts (brief_id, idx, angle, rationale, prompt, "
                "caption, created) VALUES (?,?,?,?,?,?,?)",
                (brief_id, c["idx"], c.get("angle"), c.get("rationale"),
                 c["prompt"], c.get("caption", ""), config.now_iso()))
    return get_brief(brief_id)


def get_brief(brief_id: int) -> dict | None:
    with _conn() as con:
        b = con.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()
        if not b:
            return None
        rows = con.execute(
            "SELECT * FROM concepts WHERE brief_id=? ORDER BY idx", (brief_id,)
        ).fetchall()
    out = dict(b)
    out["concepts"] = [_row_to_concept(r) for r in rows]
    return out


def get_concept(concept_id: int) -> dict | None:
    with _conn() as con:
        r = con.execute("SELECT * FROM concepts WHERE id=?", (concept_id,)).fetchone()
    return _row_to_concept(r) if r else None


def set_image(concept_id: int, image_path: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE concepts SET image_path=?, critique=NULL, score=NULL "
            "WHERE id=?", (image_path, concept_id))


def set_critique(concept_id: int, critique: dict) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE concepts SET critique=?, score=? WHERE id=?",
            (json.dumps(critique, ensure_ascii=False), critique.get("score"),
             concept_id))


def set_rating(concept_id: int, rating: int | None = None,
               starred: bool | None = None) -> dict | None:
    with _conn() as con:
        if rating is not None:
            con.execute("UPDATE concepts SET rating=? WHERE id=?",
                        (max(0, min(5, int(rating))), concept_id))
        if starred is not None:
            con.execute("UPDATE concepts SET starred=? WHERE id=?",
                        (1 if starred else 0, concept_id))
    return get_concept(concept_id)


def recent_briefs(limit: int = 30) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT b.*, "
            "  (SELECT COUNT(*) FROM concepts c WHERE c.brief_id=b.id) AS n, "
            "  (SELECT COUNT(*) FROM concepts c WHERE c.brief_id=b.id "
            "     AND c.image_path IS NOT NULL) AS n_images, "
            "  (SELECT MAX(c.score) FROM concepts c WHERE c.brief_id=b.id) AS top_score "
            "FROM briefs b ORDER BY b.id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
