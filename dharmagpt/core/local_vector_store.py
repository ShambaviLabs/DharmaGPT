from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_DB_PATH = REPO_ROOT / "knowledge" / "stores" / "local_vectors.sqlite3"


def _connect() -> sqlite3.Connection:
    STORE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STORE_DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def healthcheck() -> bool:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_chunks (
            id TEXT PRIMARY KEY,
            index_name TEXT NOT NULL,
            namespace TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            citation TEXT,
            section TEXT,
            chapter INTEGER,
            verse INTEGER,
            source_type TEXT,
            url TEXT,
            metadata_json TEXT,
            embedding_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vector_chunks_lookup
        ON vector_chunks(index_name, namespace, section, source_type)
        """
    )
    conn.commit()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def upsert_vectors(
    *,
    index_name: str,
    namespace: str,
    records: list[dict],
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    namespace = namespace or ""

    with _connect() as conn:
        for rec in records:
            meta = rec.get("metadata") or {}
            chapter_raw = meta.get("chapter") or meta.get("sarga")
            verse_raw = meta.get("verse") or meta.get("verse_start")
            try:
                chapter = int(chapter_raw) if chapter_raw is not None else None
            except (TypeError, ValueError):
                chapter = None
            try:
                verse = int(verse_raw) if verse_raw is not None else None
            except (TypeError, ValueError):
                verse = None

            conn.execute(
                """
                INSERT OR REPLACE INTO vector_chunks (
                    id, index_name, namespace, text, citation, section, chapter, verse,
                    source_type, url, metadata_json, embedding_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["id"],
                    index_name,
                    namespace,
                    str(meta.get("text") or ""),
                    str(meta.get("citation") or ""),
                    str(meta.get("section") or meta.get("kanda") or "") or None,
                    chapter,
                    verse,
                    str(meta.get("source_type") or "text"),
                    str(meta.get("url") or "") or None,
                    json.dumps(meta, ensure_ascii=False),
                    json.dumps(rec.get("values") or []),
                    now,
                ),
            )
        conn.commit()

    return len(records)


def query_vectors(
    *,
    vector: list[float],
    top_k: int,
    min_score: float,
    index_name: str,
    namespace: str,
    filter_section: str | None = None,
    filter_source_type: str | None = None,
) -> list[dict]:
    namespace = namespace or ""
    where = ["index_name = ?", "namespace = ?"]
    params: list[object] = [index_name, namespace]
    if filter_section:
        where.append("section = ?")
        params.append(filter_section)
    if filter_source_type:
        where.append("source_type = ?")
        params.append(filter_source_type)

    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, text, citation, section, chapter, verse, source_type, url, metadata_json, embedding_json
            FROM vector_chunks
            WHERE {' AND '.join(where)}
            """,
            params,
        ).fetchall()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        try:
            emb = json.loads(row["embedding_json"])
        except Exception:
            continue
        score = _cosine_similarity(vector, emb)
        if score < min_score:
            continue
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except Exception:
            meta = {}
        scored.append(
            (
                score,
                {
                    "id": row["id"],
                    "score": score,
                    "metadata": {
                        **meta,
                        "text": meta.get("text") or row["text"],
                        "citation": meta.get("citation") or row["citation"],
                        "section": meta.get("section") or row["section"],
                        "chapter": meta.get("chapter") or row["chapter"],
                        "verse": meta.get("verse") or row["verse"],
                        "source_type": meta.get("source_type") or row["source_type"],
                        "url": meta.get("url") or row["url"],
                    },
                },
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]
