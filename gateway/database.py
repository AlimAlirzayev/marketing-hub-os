"""Xalq Insurance Digital OS Core Database Engine.

Replaces mock DataFrames with a persistent SQLite database for
storing CX tickets, job states, and analytics.
"""

import shutil
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "xidigitalos.db"
_OLD_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "raminos.db"


def _migrate_old_name():
    if _OLD_DB_PATH.exists() and not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_OLD_DB_PATH, DB_PATH)

def get_connection():
    _migrate_old_name()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cx_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT,
                text TEXT,
                category TEXT,
                sentiment TEXT,
                severity TEXT,
                recommended_reply TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def add_cx_ticket(channel: str, text: str, category: str, sentiment: str, severity: str, reply: str):
    with get_connection() as conn:
        conn.execute("INSERT INTO cx_tickets (channel, text, category, sentiment, severity, recommended_reply) VALUES (?, ?, ?, ?, ?, ?)", (channel, text, category, sentiment, severity, reply))
        conn.commit()

def get_recent_cx_tickets(limit=50):
    with get_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT channel as Kanal, sentiment as Sentiment, category as Kateqoriya, text as Mesaj, recommended_reply as 'AI Cavabı' FROM cx_tickets ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

def add_agent_message(role: str, content: str):
    with get_connection() as conn:
        conn.execute("INSERT INTO agent_messages (role, content) VALUES (?, ?)", (role, content))
        conn.commit()

def get_agent_messages(limit=50):
    with get_connection() as conn:
        # Çat interfeysi üçün xronoloji sıraya (ASC) salırıq
        return [dict(row) for row in conn.execute("SELECT role, content FROM (SELECT * FROM agent_messages ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()]

init_db()
