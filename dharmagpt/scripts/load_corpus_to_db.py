#!/usr/bin/env python3
"""Load all corpus JSONL records into dharmagpt.sqlite3 corpus_records table."""

import sqlite3
import json
from pathlib import Path

def main():
    db = Path(__file__).parent.parent.parent / "knowledge" / "stores" / "dharmagpt.sqlite3"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()

    # Create corpus_records table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS corpus_records (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        source_type TEXT NOT NULL,
        kanda TEXT,
        citation TEXT,
        language TEXT DEFAULT 'en',
        text TEXT NOT NULL,
        text_en TEXT,
        text_te TEXT,
        text_en_model TEXT,
        tags TEXT,
        topics TEXT,
        characters TEXT,
        is_shloka BOOLEAN DEFAULT 0,
        url TEXT,
        notes TEXT,
        source_file TEXT,
        metadata_json TEXT,
        embedded BOOLEAN DEFAULT 0,
        embedding_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cur.execute('CREATE INDEX IF NOT EXISTS idx_corpus_source ON corpus_records(source)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_corpus_embedded ON corpus_records(embedded)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_corpus_source_type ON corpus_records(source_type)')

    print("Table created")

    # Load all JSONL records
    repo_root = Path(__file__).parent.parent
    base_text = repo_root / "knowledge" / "processed" / "text" / "valmiki_ramayana"
    base_audio_p1 = repo_root / "knowledge" / "processed" / "audio_transcript" / "01_01_sampoorna_ramayanam_part_1_by_sri_chaganti_koteswara_rao_garu"
    base_audio_p2 = repo_root / "knowledge" / "processed" / "audio_transcript" / "02_02_sampoorna_ramayanam_part_2_by_sri_chaganti_koteswara_rao_garu"

    files = list(base_text.rglob('*.jsonl')) + list(base_audio_p1.glob('*.jsonl')) + list(base_audio_p2.glob('*.jsonl'))
    print(f"Loading from {len(files)} JSONL files...")

    count = 0
    for jsonl_file in files:
        with jsonl_file.open(encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                cur.execute('''
                INSERT OR REPLACE INTO corpus_records
                (id, source, source_type, kanda, citation, language, text, text_en, text_te,
                 text_en_model, tags, topics, characters, is_shloka, url, notes, source_file, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('id'),
                    record.get('source'),
                    record.get('source_type'),
                    record.get('kanda') or record.get('section'),
                    record.get('citation'),
                    record.get('language', 'en'),
                    record.get('text'),
                    record.get('text_en'),
                    record.get('text_te'),
                    record.get('text_en_model'),
                    json.dumps(record.get('tags', [])),
                    json.dumps(record.get('topics', [])),
                    json.dumps(record.get('characters', [])),
                    record.get('is_shloka', False),
                    record.get('url'),
                    record.get('notes'),
                    jsonl_file.name,
                    json.dumps(record, ensure_ascii=False),
                ))
                count += 1
                if count % 5000 == 0:
                    print(f"  Loaded {count}...")

    conn.commit()

    # Show stats
    cur.execute('SELECT COUNT(*) FROM corpus_records')
    total = cur.fetchone()[0]

    print(f"\nBreakdown by source and type:")
    cur.execute('SELECT source, source_type, COUNT(*) as cnt FROM corpus_records GROUP BY source, source_type ORDER BY cnt DESC')
    for source, source_type, cnt in cur.fetchall():
        print(f"  {source} ({source_type}): {cnt}")

    print(f"\nLoaded {total} records into corpus_records table")
    conn.close()

if __name__ == '__main__':
    main()
