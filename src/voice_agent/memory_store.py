"""Persistent long-term memory — facts the agent is told to remember.

Backed by SQLite, in a separate table from the LangGraph checkpointer (which
stores per-conversation thread state). This is cross-conversation memory the
agent controls through the remember_fact / recall_facts tools.

Single-user for now: facts are global. Per-caller scoping (a namespace column
keyed by conversation/caller id) is a future step.
"""

import sqlite3
from pathlib import Path

from voice_agent.config import settings


def _connect() -> sqlite3.Connection:
    path = Path(settings.agent_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


_conn = _connect()
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS facts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        fact       TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """
)
_conn.commit()


def save_fact(fact: str) -> None:
    _conn.execute("INSERT INTO facts (fact) VALUES (?)", (fact.strip(),))
    _conn.commit()


def list_facts() -> list[str]:
    rows = _conn.execute("SELECT fact FROM facts ORDER BY id").fetchall()
    return [row[0] for row in rows]
