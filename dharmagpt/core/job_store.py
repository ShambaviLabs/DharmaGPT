"""SQLite-backed job store for tracking long-running ingest jobs."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "knowledge" / "stores" / "dharmagpt.sqlite3"

_DDL = """
CREATE TABLE IF NOT EXISTS ingest_jobs (
    id          TEXT PRIMARY KEY,
    job_type    TEXT NOT NULL,
    source_name TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',
    total       INTEGER DEFAULT 0,
    done        INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    completed_at TEXT,
    error       TEXT,
    meta        TEXT DEFAULT '{}'
);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_type: str, source_name: str, total: int = 0, meta: dict | None = None) -> str:
    job_id = uuid.uuid4().hex
    now = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO ingest_jobs (id,job_type,source_name,status,total,created_at,updated_at,meta) VALUES (?,?,?,?,?,?,?,?)",
            (job_id, job_type, source_name, "queued", total, now, now, json.dumps(meta or {})),
        )
    return job_id


def update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    if fields.get("status") in {"done", "failed"}:
        fields.setdefault("completed_at", _now())
    clause = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as conn:
        conn.execute(f"UPDATE ingest_jobs SET {clause} WHERE id = ?", [*fields.values(), job_id])


def get_job(job_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 100) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ingest_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
