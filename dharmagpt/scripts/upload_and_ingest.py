#!/usr/bin/env python3
"""
upload_and_ingest.py — manually upload documents/audio and ingest to corpus_records table.

Usage:
  python scripts/upload_and_ingest.py --file my_document.pdf --source "my_source" --language en
  python scripts/upload_and_ingest.py --file audio.mp3 --source "speaker_name" --language te
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import structlog

log = structlog.get_logger()

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "dharmagpt"
INCOMING_DIR = PACKAGE_ROOT / "knowledge" / "incoming"
DB_PATH = REPO_ROOT / "knowledge" / "stores" / "dharmagpt.sqlite3"
CORPUS_METRICS = PACKAGE_ROOT / "scripts" / "corpus_metrics.py"

# Supported formats
SUPPORTED_DOCS = {".pdf", ".txt", ".md", ".text"}
SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def extract_text_from_doc(path: Path, source_type: str = "text") -> str:
    """Extract text from document."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("pypdf not installed: pip install pypdf")
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix in {".txt", ".md", ".text"}:
        return path.read_text(encoding="utf-8", errors="replace")

    raise ValueError(f"Unsupported document format: {suffix}")


def chunk_text(text: str, chunk_words: int = 400, overlap: int = 40) -> list[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_words])
        if len(chunk.split()) >= 20:  # Only keep substantial chunks
            chunks.append(chunk)
        i += chunk_words - overlap
    return chunks


def process_document(
    file_path: Path,
    *,
    source: str,
    language: str = "en",
    section: str = "",
) -> list[dict]:
    """Process a document file into corpus records."""
    print(f"Processing document: {file_path.name}")

    raw_text = extract_text_from_doc(file_path)
    if not raw_text.strip():
        print(f"  Warning: Document is empty or unreadable")
        return []

    # Clean up text
    import re

    raw_text = re.sub(r"\s+", " ", raw_text).strip()

    # Chunk the text
    chunks = chunk_text(raw_text)
    print(f"  Generated {len(chunks)} chunks from {len(raw_text)} characters")

    records = []
    for i, chunk_text_str in enumerate(chunks):
        record_id = f"{source}_{uuid.uuid4().hex[:8]}_{i:04d}"
        records.append({
            "id": record_id,
            "source": source,
            "source_type": "text",
            "source_file": file_path.name,
            "text": chunk_text_str,
            "language": language,
            "citation": f"{source}, chunk {i+1}/{len(chunks)}",
            "tags": ["uploaded"],
            "topics": [],
            "characters": [],
            "is_shloka": False,
            "url": "",
            "notes": f"Uploaded from {file_path.name}",
            "kanda": section or None,
        })

    return records


def process_audio_file(
    file_path: Path,
    *,
    source: str,
    language: str = "te",
) -> list[dict]:
    """Process audio file (placeholder — would integrate with transcription service)."""
    print(f"Processing audio: {file_path.name}")

    # For now, just create a single record with file metadata
    # In production, this would:
    # 1. Call transcription service (e.g., Whisper, Sarvam)
    # 2. Split into chunks
    # 3. Create records with transcript + translation

    record_id = f"{source}_audio_{uuid.uuid4().hex[:8]}"
    return [
        {
            "id": record_id,
            "source": source,
            "source_type": "audio_transcript",
            "source_file": file_path.name,
            "text": f"[Audio file: {file_path.name} — awaiting transcription]",
            "language": language,
            "citation": f"{source} (audio)",
            "tags": ["audio", "uploaded"],
            "topics": [],
            "characters": [],
            "is_shloka": False,
            "url": "",
            "notes": f"Audio uploaded from {file_path.name} — needs transcription",
        }
    ]


def ingest_records(records: list[dict]) -> int:
    """Insert records into corpus_records table."""
    if not records:
        print("No records to ingest")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    ingested = 0
    for record in records:
        try:
            cur.execute('''
            INSERT OR REPLACE INTO corpus_records
            (id, source, source_type, kanda, citation, language, text, tags, topics,
             characters, is_shloka, url, notes, source_file, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.get('id'),
                record.get('source'),
                record.get('source_type'),
                record.get('kanda'),
                record.get('citation'),
                record.get('language', 'en'),
                record.get('text'),
                json.dumps(record.get('tags', [])),
                json.dumps(record.get('topics', [])),
                json.dumps(record.get('characters', [])),
                record.get('is_shloka', False),
                record.get('url', ''),
                record.get('notes', ''),
                record.get('source_file', ''),
                json.dumps(record, ensure_ascii=False),
            ))
            ingested += 1
        except Exception as e:
            print(f"  Error ingesting {record.get('id')}: {e}")

    conn.commit()
    conn.close()
    return ingested


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload and ingest documents/audio into corpus_records"
    )
    parser.add_argument("--file", type=str, required=True, help="File to upload")
    parser.add_argument("--source", type=str, required=True, help="Source name/identifier")
    parser.add_argument(
        "--language", type=str, default="en", help="Language (en, te, hi, etc.)"
    )
    parser.add_argument("--section", type=str, default="", help="Section/kanda name")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        sys.exit(f"File not found: {file_path}")

    suffix = file_path.suffix.lower()

    # Determine file type and process
    if suffix in SUPPORTED_DOCS:
        records = process_document(
            file_path,
            source=args.source,
            language=args.language,
            section=args.section,
        )
    elif suffix in SUPPORTED_AUDIO:
        records = process_audio_file(
            file_path,
            source=args.source,
            language=args.language,
        )
    else:
        supported = ", ".join(sorted(SUPPORTED_DOCS | SUPPORTED_AUDIO))
        sys.exit(f"Unsupported file format. Supported: {supported}")

    if not records:
        sys.exit("No records generated from file")

    # Ingest to DB
    ingested = ingest_records(records)
    print(f"\nIngested {ingested} records into corpus_records")

    # Show metrics
    print("\nUpdated corpus metrics:")
    import subprocess

    subprocess.run([sys.executable, str(CORPUS_METRICS)], check=True)


if __name__ == "__main__":
    main()
