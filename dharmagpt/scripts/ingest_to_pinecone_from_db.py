#!/usr/bin/env python3
"""
ingest_to_pinecone_from_db.py — embed corpus_records from DB and upsert to Pinecone.

Reads from the local corpus_records table, embeds text, and upserts to Pinecone.
Tracks progress via the 'embedded' flag in the DB.

Usage:
  python scripts/ingest_to_pinecone_from_db.py              # ingest all pending records
  python scripts/ingest_to_pinecone_from_db.py --dry-run    # validate only, no upsert
  python scripts/ingest_to_pinecone_from_db.py --reset      # mark all as unembed, re-ingest
  python scripts/ingest_to_pinecone_from_db.py --limit 100  # test with 100 records
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

load_dotenv()
log = structlog.get_logger()

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent.parent / "knowledge" / "stores" / "dharmagpt.sqlite3"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "3072"))
PINECONE_INDEX = os.getenv("PINECONE_INDEX_NAME", "dharma-gpt")
PINECONE_ENV = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
BATCH_SIZE = 50  # records per Pinecone upsert
EMBED_BATCH_SIZE = 20  # texts per OpenAI embeddings call
MAX_TEXT_CHARS = 2000


# ── Clients ───────────────────────────────────────────────────────────────────

def get_openai() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        sys.exit("ERROR: OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


def get_pinecone() -> Pinecone:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        sys.exit("ERROR: PINECONE_API_KEY not set")
    return Pinecone(api_key=api_key)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_pending_records(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    """Get records where embedded=0."""
    cur = conn.cursor()
    query = "SELECT * FROM corpus_records WHERE embedded = 0 ORDER BY rowid"
    if limit:
        query += f" LIMIT {limit}"
    cur.execute(query)

    columns = [desc[0] for desc in cur.description]
    records = []
    for row in cur.fetchall():
        records.append(dict(zip(columns, row)))
    return records


def mark_embedded(conn: sqlite3.Connection, record_ids: list[str], embedding_ids: list[str]) -> None:
    """Mark records as embedded."""
    cur = conn.cursor()
    for rec_id, emb_id in zip(record_ids, embedding_ids):
        cur.execute('''
        UPDATE corpus_records
        SET embedded = 1, embedding_id = ?
        WHERE id = ?
        ''', (emb_id, rec_id))
    conn.commit()


# ── Embedding helpers ─────────────────────────────────────────────────────────

def build_metadata(record: dict) -> dict:
    """Extract metadata for Pinecone."""
    return {
        "source": record.get("source"),
        "source_type": record.get("source_type"),
        "kanda": record.get("kanda"),
        "citation": record.get("citation"),
        "language": record.get("language"),
        "tags": json.loads(record.get("tags", "[]")),
        "characters": json.loads(record.get("characters", "[]")),
        "is_shloka": bool(record.get("is_shloka")),
        "url": record.get("url", ""),
    }


def chunk_batch(items: list, size: int) -> list[list]:
    """Split list into chunks."""
    return [items[i:i+size] for i in range(0, len(items), size)]


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using OpenAI."""
    # Truncate to max chars
    texts = [t[:MAX_TEXT_CHARS] if t else "" for t in texts]

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        encoding_format="float",
    )
    return [item.embedding for item in response.data]


# ── Main ingestion ────────────────────────────────────────────────────────────

def ingest(dry_run: bool = False, limit: int | None = None, reset: bool = False) -> None:
    """Main ingestion loop."""

    # Connect to local DB
    conn = sqlite3.connect(str(DB_PATH))

    if reset:
        print("Resetting embedded flag for all records...")
        conn.execute("UPDATE corpus_records SET embedded = 0")
        conn.commit()

    # Get records to embed
    pending = get_pending_records(conn, limit=limit)
    if not pending:
        print("No pending records to embed")
        conn.close()
        return

    print(f"Found {len(pending)} records to embed")

    if dry_run:
        print(f"DRY RUN: Would embed {len(pending)} records")
        sample = pending[0]
        print(f"\nSample record:")
        print(f"  ID: {sample['id']}")
        print(f"  Text: {sample['text'][:100]}...")
        print(f"  Source: {sample['source']}")
        conn.close()
        return

    # Initialize clients
    openai_client = get_openai()
    pinecone_client = get_pinecone()

    # Get or create Pinecone index
    try:
        index = pinecone_client.Index(PINECONE_INDEX)
        print(f"Connected to Pinecone index: {PINECONE_INDEX}")
    except Exception as e:
        print(f"Creating Pinecone index: {PINECONE_INDEX}")
        pinecone_client.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIMS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=PINECONE_ENV),
        )
        index = pinecone_client.Index(PINECONE_INDEX)

    # Process batches
    total_embedded = 0
    for i, batch in enumerate(chunk_batch(pending, EMBED_BATCH_SIZE)):
        print(f"\nBatch {i+1}/{(len(pending)-1)//EMBED_BATCH_SIZE + 1}")

        # Extract texts to embed
        texts = [r['text'] for r in batch]

        try:
            # Embed
            embeddings = embed_texts(openai_client, texts)
            print(f"  Embedded {len(batch)} texts")

            # Prepare for Pinecone upsert
            vectors = []
            record_ids = []
            embedding_ids = []

            for record, embedding in zip(batch, embeddings):
                vectors.append({
                    'id': record['id'],
                    'values': embedding,
                    'metadata': build_metadata(record),
                })
                record_ids.append(record['id'])
                embedding_ids.append(record['id'])  # Store ID as embedding reference

            # Upsert in batches (Pinecone has limits)
            for vec_batch in chunk_batch(vectors, BATCH_SIZE):
                index.upsert(vectors=vec_batch, namespace="default")

            print(f"  Upserted {len(vectors)} vectors to Pinecone")

            # Mark as embedded in DB
            mark_embedded(conn, record_ids, embedding_ids)
            total_embedded += len(batch)

        except Exception as e:
            print(f"  ERROR: {e}")
            print(f"  Stopping ingestion")
            break

    conn.close()
    print(f"\nTotal embedded: {total_embedded}")

    # Show updated metrics
    print("\n=== POST-INGEST METRICS ===")
    os.system("python scripts/corpus_metrics.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed corpus_records from DB and upsert to Pinecone",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't upsert")
    parser.add_argument("--reset", action="store_true", help="Reset embedded flag for all records")
    parser.add_argument("--limit", type=int, default=None, help="Only embed N records (for testing)")
    args = parser.parse_args()

    ingest(dry_run=args.dry_run, limit=args.limit, reset=args.reset)


if __name__ == "__main__":
    main()
