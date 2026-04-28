#!/usr/bin/env python3
"""Show corpus_records metrics before/after Pinecone ingestion."""

import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parents[2] / "knowledge" / "stores" / "dharmagpt.sqlite3"


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return part / total * 100


def show_metrics():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    print("\n=== CORPUS METRICS ===\n")

    try:
        cur.execute('SELECT COUNT(*) FROM corpus_records')
    except sqlite3.OperationalError as exc:
        print(f"Corpus metrics unavailable: {exc}")
        conn.close()
        return

    # Total records
    total = cur.fetchone()[0]
    print(f"Total records: {total:,}")

    if total == 0:
        print("\nNo corpus records found yet.")
        conn.close()
        return

    # By source
    print("\nBy source:")
    cur.execute('''
    SELECT source, source_type, COUNT(*) as cnt
    FROM corpus_records
    GROUP BY source
    ORDER BY cnt DESC
    ''')
    for source, src_type, cnt in cur.fetchall():
        print(f"  {source} ({src_type}): {cnt:,}")

    # By language
    print("\nBy language:")
    cur.execute('SELECT language, COUNT(*) as cnt FROM corpus_records GROUP BY language ORDER BY cnt DESC')
    for lang, cnt in cur.fetchall():
        print(f"  {lang}: {cnt:,}")

    # Translation coverage
    print("\nTranslation coverage:")
    cur.execute('SELECT COUNT(*) FROM corpus_records WHERE text_te IS NOT NULL AND text_te != ""')
    has_te = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM corpus_records WHERE text_en_model IS NOT NULL AND text_en_model != ""')
    has_en_model = cur.fetchone()[0]
    print(f"  With Telugu (text_te): {has_te:,} ({_pct(has_te, total):.1f}%)")
    print(f"  With model translation: {has_en_model:,} ({_pct(has_en_model, total):.1f}%)")

    # Topics enrichment
    print("\nTopics enrichment:")
    cur.execute('''
    SELECT COUNT(*) FROM corpus_records
    WHERE topics != '[]' AND topics IS NOT NULL
    ''')
    has_topics = cur.fetchone()[0]
    print(f"  Records with topics: {has_topics:,} ({_pct(has_topics, total):.1f}%)")

    # Embedding status
    print("\nEmbedding status:")
    cur.execute('SELECT COUNT(*) FROM corpus_records WHERE embedded = 1')
    embedded = cur.fetchone()[0]
    print(f"  Embedded: {embedded:,} ({_pct(embedded, total):.1f}%)")
    print(f"  Pending: {total - embedded:,}")

    conn.close()

if __name__ == '__main__':
    show_metrics()
