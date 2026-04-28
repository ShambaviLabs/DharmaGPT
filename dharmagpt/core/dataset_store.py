"""
dataset_store.py — lightweight SQLite registry for named vector datasets.

A dataset is a logical grouping of vectors identified by a shared dataset_id
metadata field in Pinecone (or namespace in local SQLite).  Active/inactive
state lives here; Pinecone itself has no concept of enabled/disabled.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = REPO_ROOT / "knowledge" / "stores" / "local_vectors.sqlite3"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS datasets (
            name         TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            active       INTEGER NOT NULL DEFAULT 1,
            vector_count INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            level      TEXT NOT NULL DEFAULT 'error',
            event      TEXT NOT NULL,
            detail     TEXT,
            file_name  TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


# ── Notification API ──────────────────────────────────────────────────────────

def push_notification(event: str, detail: str = "", file_name: str = "", level: str = "error") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notifications (level, event, detail, file_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (level, event, detail[:2000], file_name[:500], now),
        )
        conn.commit()


def list_notifications(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, level, event, detail, file_name, created_at FROM notifications ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_notifications() -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM notifications")
        conn.commit()
        return cur.rowcount


def register(name: str, display_name: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO datasets (name, display_name, active, vector_count, created_at) VALUES (?, ?, 1, 0, ?)",
            (name.strip(), (display_name or name).strip(), now),
        )
        conn.commit()


def increment_count(name: str, count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE datasets SET vector_count = vector_count + ? WHERE name = ?",
            (count, name.strip()),
        )
        conn.commit()


def list_all() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name, display_name, active, vector_count, created_at FROM datasets ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def set_active(name: str, active: bool) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE datasets SET active = ? WHERE name = ?",
            (1 if active else 0, name.strip()),
        )
        conn.commit()
        return cur.rowcount > 0


def remove(name: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM datasets WHERE name = ?", (name.strip(),))
        conn.commit()
        return cur.rowcount > 0


def get_active_names() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT name FROM datasets WHERE active = 1"
        ).fetchall()
    return [r["name"] for r in rows]


def any_registered() -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM datasets").fetchone()
    return (row["cnt"] or 0) > 0
