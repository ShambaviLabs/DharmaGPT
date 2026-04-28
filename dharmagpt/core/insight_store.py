from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.postgres_db import connect as pg_connect, ensure_schema as pg_ensure_schema, use_postgres


REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_DB_PATH = REPO_ROOT / "knowledge" / "stores" / "ingestion_insights.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sqlite_connect() -> sqlite3.Connection:
    STORE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STORE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_runs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            source_title TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            dataset_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            chunks INTEGER NOT NULL DEFAULT 0,
            vectors INTEGER NOT NULL DEFAULT 0,
            vector_db TEXT NOT NULL DEFAULT '',
            embedding_backend TEXT NOT NULL DEFAULT '',
            transcription_mode TEXT NOT NULL DEFAULT '',
            transcription_version TEXT NOT NULL DEFAULT '',
            translation_backend TEXT NOT NULL DEFAULT '',
            translation_version TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT,
            finished_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS query_runs (
            query_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            llm_backend TEXT NOT NULL DEFAULT '',
            llm_model TEXT NOT NULL DEFAULT '',
            llm_attempted_backends TEXT NOT NULL DEFAULT '[]',
            llm_fallback_reason TEXT NOT NULL DEFAULT '',
            source_count INTEGER NOT NULL DEFAULT 0,
            rating TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record_ingestion_run(**kwargs: Any) -> str:
    run_id = str(kwargs.get("id") or uuid.uuid4())
    now = _now()
    row = {
        "id": run_id,
        "kind": kwargs.get("kind") or "unknown",
        "source": kwargs.get("source") or "",
        "source_title": kwargs.get("source_title") or "",
        "file_name": kwargs.get("file_name") or "",
        "language": kwargs.get("language") or "",
        "dataset_id": kwargs.get("dataset_id") or "",
        "status": kwargs.get("status") or "unknown",
        "chunks": int(kwargs.get("chunks") or 0),
        "vectors": int(kwargs.get("vectors") or 0),
        "vector_db": kwargs.get("vector_db") or "",
        "embedding_backend": kwargs.get("embedding_backend") or "",
        "transcription_mode": kwargs.get("transcription_mode") or "",
        "transcription_version": kwargs.get("transcription_version") or "",
        "translation_backend": kwargs.get("translation_backend") or "",
        "translation_version": kwargs.get("translation_version") or "",
        "error": str(kwargs.get("error") or "")[:2000],
        "metadata_json": json.dumps(kwargs.get("metadata") or {}, ensure_ascii=False),
        "started_at": kwargs.get("started_at"),
        "finished_at": kwargs.get("finished_at") or now,
    }

    if use_postgres():
        with pg_connect() as conn:
            pg_ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO ingestion_runs (
                    id, kind, source, source_title, file_name, language, dataset_id, status,
                    chunks, vectors, vector_db, embedding_backend, transcription_mode,
                    transcription_version, translation_backend, translation_version, error,
                    metadata_json, started_at, finished_at
                ) VALUES (
                    %(id)s, %(kind)s, %(source)s, %(source_title)s, %(file_name)s, %(language)s,
                    %(dataset_id)s, %(status)s, %(chunks)s, %(vectors)s, %(vector_db)s,
                    %(embedding_backend)s, %(transcription_mode)s, %(transcription_version)s,
                    %(translation_backend)s, %(translation_version)s, %(error)s,
                    %(metadata_json)s::jsonb, %(started_at)s, %(finished_at)s
                )
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    chunks = EXCLUDED.chunks,
                    vectors = EXCLUDED.vectors,
                    error = EXCLUDED.error,
                    metadata_json = EXCLUDED.metadata_json,
                    finished_at = EXCLUDED.finished_at
                """,
                row,
            )
            conn.commit()
        return run_id

    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ingestion_runs (
                id, kind, source, source_title, file_name, language, dataset_id, status,
                chunks, vectors, vector_db, embedding_backend, transcription_mode,
                transcription_version, translation_backend, translation_version, error,
                metadata_json, started_at, finished_at
            ) VALUES (
                :id, :kind, :source, :source_title, :file_name, :language, :dataset_id, :status,
                :chunks, :vectors, :vector_db, :embedding_backend, :transcription_mode,
                :transcription_version, :translation_backend, :translation_version, :error,
                :metadata_json, :started_at, :finished_at
            )
            """,
            row,
        )
        conn.commit()
    return run_id


def record_query_run(**kwargs: Any) -> str:
    query_id = str(kwargs.get("query_id") or uuid.uuid4())
    row = {
        "query_id": query_id,
        "query": kwargs.get("query") or "",
        "mode": kwargs.get("mode") or "",
        "language": kwargs.get("language") or "",
        "status": kwargs.get("status") or "unknown",
        "llm_backend": kwargs.get("llm_backend") or "",
        "llm_model": kwargs.get("llm_model") or "",
        "llm_attempted_backends": json.dumps(kwargs.get("llm_attempted_backends") or [], ensure_ascii=False),
        "llm_fallback_reason": kwargs.get("llm_fallback_reason") or "",
        "source_count": int(kwargs.get("source_count") or 0),
        "rating": kwargs.get("rating") or "",
        "error": str(kwargs.get("error") or "")[:2000],
        "created_at": kwargs.get("created_at") or _now(),
    }
    if use_postgres():
        with pg_connect() as conn:
            pg_ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO query_runs (
                    query_id, query, mode, language, status, llm_backend, llm_model,
                    llm_attempted_backends, llm_fallback_reason, source_count, rating,
                    error, created_at
                ) VALUES (
                    %(query_id)s, %(query)s, %(mode)s, %(language)s, %(status)s,
                    %(llm_backend)s, %(llm_model)s, %(llm_attempted_backends)s::jsonb,
                    %(llm_fallback_reason)s, %(source_count)s, %(rating)s,
                    %(error)s, %(created_at)s
                )
                ON CONFLICT (query_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    llm_backend = EXCLUDED.llm_backend,
                    llm_model = EXCLUDED.llm_model,
                    llm_attempted_backends = EXCLUDED.llm_attempted_backends,
                    llm_fallback_reason = EXCLUDED.llm_fallback_reason,
                    source_count = EXCLUDED.source_count,
                    error = EXCLUDED.error
                """,
                row,
            )
            conn.commit()
        return query_id

    with _sqlite_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO query_runs (
                query_id, query, mode, language, status, llm_backend, llm_model,
                llm_attempted_backends, llm_fallback_reason, source_count, rating,
                error, created_at
            ) VALUES (
                :query_id, :query, :mode, :language, :status, :llm_backend, :llm_model,
                :llm_attempted_backends, :llm_fallback_reason, :source_count, :rating,
                :error, :created_at
            )
            """,
            row,
        )
        conn.commit()
    return query_id


def update_query_rating(query_id: str, rating: str) -> None:
    if use_postgres():
        with pg_connect() as conn:
            pg_ensure_schema(conn)
            conn.execute("UPDATE query_runs SET rating = %s WHERE query_id = %s", (rating, query_id))
            conn.commit()
        return
    with _sqlite_connect() as conn:
        conn.execute("UPDATE query_runs SET rating = ? WHERE query_id = ?", (rating, query_id))
        conn.commit()


def list_query_runs(limit: int = 1000) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 5000))
    if use_postgres():
        with pg_connect() as conn:
            pg_ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM query_runs ORDER BY created_at DESC LIMIT %s",
                (safe_limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    with _sqlite_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM query_runs ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def list_ingestion_runs(limit: int = 100) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    if use_postgres():
        with pg_connect() as conn:
            pg_ensure_schema(conn)
            rows = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY finished_at DESC LIMIT %s",
                (safe_limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    with _sqlite_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ingestion_runs ORDER BY finished_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [dict(row) for row in rows]
