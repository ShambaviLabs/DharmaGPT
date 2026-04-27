from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Iterator

from pinecone import ServerlessSpec

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from core.config import get_settings
from core.retrieval import get_pinecone


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_VECTOR_DB = REPO_ROOT / "knowledge" / "stores" / "local_vectors.sqlite3"


def _iter_records(
    *,
    index_name: str,
    namespace: str,
    limit: int | None,
) -> Iterator[dict]:
    sql = """
        SELECT id, metadata_json, embedding_json
        FROM vector_chunks
        WHERE index_name = ? AND namespace = ?
        ORDER BY id
    """
    params: list[object] = [index_name, namespace]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    with sqlite3.connect(str(LOCAL_VECTOR_DB)) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(sql, params):
            metadata = json.loads(row["metadata_json"] or "{}")
            values = json.loads(row["embedding_json"] or "[]")
            yield {
                "id": row["id"],
                "values": values,
                "metadata": metadata,
            }


def _ensure_index(index_name: str) -> None:
    settings = get_settings()
    pc = get_pinecone()
    existing = set(pc.list_indexes().names())
    if index_name in existing:
        return

    pc.create_index(
        name=index_name,
        dimension=settings.embedding_dims,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region=settings.pinecone_environment),
    )

    while not pc.describe_index(index_name).status["ready"]:
        time.sleep(2)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Copy local SQLite vectors into Pinecone.")
    parser.add_argument("--source-index", default=settings.local_vector_index_name)
    parser.add_argument("--source-namespace", default=settings.local_vector_namespace)
    parser.add_argument("--pinecone-index", default=settings.pinecone_index_name)
    parser.add_argument("--pinecone-namespace", default="")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--create-index", action="store_true")
    args = parser.parse_args()

    if args.create_index:
        _ensure_index(args.pinecone_index)

    pc = get_pinecone()
    index = pc.Index(args.pinecone_index)
    batch: list[dict] = []
    total = 0

    for record in _iter_records(
        index_name=args.source_index,
        namespace=args.source_namespace,
        limit=args.limit,
    ):
        batch.append(record)
        if len(batch) < args.batch_size:
            continue
        index.upsert(vectors=batch, namespace=args.pinecone_namespace)
        total += len(batch)
        print(f"upserted={total}")
        batch = []

    if batch:
        index.upsert(vectors=batch, namespace=args.pinecone_namespace)
        total += len(batch)

    print(
        json.dumps(
            {
                "status": "ok",
                "pinecone_index": args.pinecone_index,
                "pinecone_namespace": args.pinecone_namespace,
                "vectors_upserted": total,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
