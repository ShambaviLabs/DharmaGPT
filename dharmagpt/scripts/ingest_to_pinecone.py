"""
ingest_to_pinecone.py — embed corpus JSONL records and upsert to Pinecone.

Resume support
--------------
A checkpoint file (knowledge/stores/ingest_checkpoint.json) tracks every
processed JSONL file by its absolute path + mtime.  On the next run the script
skips any file whose path+mtime is already in the checkpoint.  This means:

  - Interrupted runs resume from the last unfinished file.
  - Re-processed source files (new mtime) are automatically re-ingested.
  - Unchanged files are always skipped — safe to run repeatedly.

Pass --reset to wipe the checkpoint and re-ingest everything from scratch.

Usage
-----
  python scripts/ingest_to_pinecone.py                   # all JSONL, resume-safe
  python scripts/ingest_to_pinecone.py --file seed_corpus.jsonl
  python scripts/ingest_to_pinecone.py --dry-run         # validate only, no upsert
  python scripts/ingest_to_pinecone.py --reset           # wipe checkpoint + re-ingest
  python scripts/ingest_to_pinecone.py --delete-index    # wipe Pinecone index + re-ingest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Generator

import structlog
from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

from utils.naming import dataset_id_from_path, is_canonical_part_file

load_dotenv()
log = structlog.get_logger()

# ── Config ────────────────────────────────────────────────────────────────────

PROCESSED_DIR    = Path(__file__).parent.parent / "knowledge" / "processed"
CHECKPOINT_PATH  = Path(__file__).parent.parent / "knowledge" / "stores" / "ingest_checkpoint.json"
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIMS   = int(os.getenv("EMBEDDING_DIMS", "3072"))
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "dharma-gpt")
PINECONE_ENV     = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
BATCH_SIZE       = 50    # records per Pinecone upsert
EMBED_BATCH_SIZE = 20    # texts per OpenAI embeddings call
MAX_TEXT_CHARS   = 2000  # truncate before embedding

REQUIRED_FIELDS = {"id", "text", "source", "citation", "language", "source_type",
                   "tags", "is_shloka"}


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _load_checkpoint() -> dict[str, float]:
    """Returns {abs_path: mtime} for all already-ingested files."""
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_checkpoint(checkpoint: dict[str, float]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _file_key(path: Path) -> str:
    return str(path.resolve())


def _already_ingested(path: Path, checkpoint: dict[str, float]) -> bool:
    key = _file_key(path)
    if key not in checkpoint:
        return False
    return checkpoint[key] == path.stat().st_mtime


def _mark_ingested(path: Path, checkpoint: dict[str, float]) -> None:
    checkpoint[_file_key(path)] = path.stat().st_mtime


# ── Clients ───────────────────────────────────────────────────────────────────

def get_openai() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


def get_pinecone_index(pc: Pinecone):
    existing = [i["name"] for i in pc.list_indexes()]
    if PINECONE_INDEX not in existing:
        log.info("creating_pinecone_index", name=PINECONE_INDEX)
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIMS,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=PINECONE_ENV),
        )
        for _ in range(30):
            if pc.describe_index(PINECONE_INDEX).status.get("ready"):
                break
            time.sleep(2)
    return pc.Index(PINECONE_INDEX)


# ── Validation ────────────────────────────────────────────────────────────────

def validate_record(record: dict, line_no: int, filename: str) -> list[str]:
    errors = []
    missing = REQUIRED_FIELDS - set(record.keys())
    if missing:
        errors.append(f"{filename}:{line_no} missing fields: {missing}")
    if "text" in record and len(record["text"].strip()) < 20:
        errors.append(f"{filename}:{line_no} text too short (<20 chars)")
    if "id" in record and not record["id"].strip():
        errors.append(f"{filename}:{line_no} empty id")
    if "language" in record and record["language"] not in {"sa", "en", "hi", "te", "ta"}:
        errors.append(f"{filename}:{line_no} unknown language: {record['language']}")
    if "source_type" in record and record["source_type"] not in {"text", "commentary", "audio_transcript"}:
        errors.append(f"{filename}:{line_no} unknown source_type: {record['source_type']}")
    return errors


# ── Loading ───────────────────────────────────────────────────────────────────

def iter_records(f: Path) -> Generator[tuple[dict, str], None, None]:
    """Yield (record, dataset_id) for all valid records in a single file."""
    dataset_id = dataset_id_from_path(f, root=PROCESSED_DIR)
    total_errors = 0
    with f.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                log.error("json_parse_error", file=f.name, line=line_no, error=str(e))
                total_errors += 1
                continue
            errors = validate_record(record, line_no, f.name)
            if errors:
                for err in errors:
                    log.warning("validation_error", msg=err)
                total_errors += 1
                continue
            yield record, dataset_id
    if total_errors:
        log.warning("file_validation_summary", file=f.name, errors=total_errors)


# ── Embedding ─────────────────────────────────────────────────────────────────

def batch_embed(texts: list[str], client: OpenAI) -> list[list[float]]:
    all_vectors = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = [t[:MAX_TEXT_CHARS] for t in texts[i:i + EMBED_BATCH_SIZE]]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_vectors.extend([r.embedding for r in response.data])
    return all_vectors


# ── Metadata ──────────────────────────────────────────────────────────────────

def build_embed_text(record: dict) -> str:
    parts = [record["text"]]
    if record.get("text_te"):
        parts.append(record["text_te"])
    text_en = record.get("text_en") or record.get("text_en_model")
    if text_en and record.get("language") != "en":
        parts.append(text_en)
    parts.append(record.get("citation", ""))
    return " | ".join(p for p in parts if p.strip())


def build_metadata(record: dict, dataset_id: str) -> dict:
    text    = record.get("text", "")
    text_en = record.get("text_en") or record.get("text_en_model") or ""
    meta: dict = {
        "source":        record.get("source", ""),
        "source_type":   record.get("source_type", "text"),
        "citation":      record.get("citation", ""),
        "language":      record.get("language", "en"),
        "is_shloka":     bool(record.get("is_shloka", False)),
        "tags":          record.get("tags", []),
        "characters":    record.get("characters", []),
        "topics":        record.get("topics", []),
        "text":          text,
        "text_preview":  text[:500],
        "text_en":       text_en,
        "text_en_preview": text_en[:500],
        "url":           record.get("url", ""),
        "has_telugu":    bool(record.get("text_te", "").strip()),
        "has_english":   bool(text_en.strip()),
        "dataset_id":    dataset_id,
    }
    section = record.get("section") or record.get("kanda")
    chapter = record.get("chapter") if record.get("chapter") is not None else record.get("sarga")
    verse   = record.get("verse")   if record.get("verse")   is not None else record.get("verse_start")
    if section:
        meta["section"] = section
        meta["kanda"]   = section
    if chapter is not None:
        meta["chapter"] = int(chapter)
        meta["sarga"]   = int(chapter)
    if verse is not None:
        meta["verse"] = int(verse)
    return meta


# ── Per-file ingestion ────────────────────────────────────────────────────────

def ingest_file(
    f: Path,
    index,
    openai_client: OpenAI,
    checkpoint: dict[str, float],
    dry_run: bool,
) -> int:
    """Ingest a single JSONL file. Returns number of records upserted."""
    records_list = list(iter_records(f))
    if not records_list:
        log.info("file_empty_or_all_invalid", file=f.name)
        if not dry_run:
            _mark_ingested(f, checkpoint)
            _save_checkpoint(checkpoint)
        return 0

    if dry_run:
        log.info("dry_run_file", file=f.name, valid_records=len(records_list))
        return len(records_list)

    embed_texts_list = [build_embed_text(r) for r, _ in records_list]
    vectors = batch_embed(embed_texts_list, openai_client)

    pinecone_records = [
        {
            "id":       record["id"],
            "values":   vector,
            "metadata": build_metadata(record, dataset_id),
        }
        for (record, dataset_id), vector in zip(records_list, vectors)
    ]

    upserted = 0
    for i in range(0, len(pinecone_records), BATCH_SIZE):
        batch = pinecone_records[i:i + BATCH_SIZE]
        index.upsert(vectors=batch)
        upserted += len(batch)

    # Mark file complete only after all batches succeeded
    _mark_ingested(f, checkpoint)
    _save_checkpoint(checkpoint)

    log.info("file_ingested", file=f.name, records=upserted)
    return upserted


# ── Main ──────────────────────────────────────────────────────────────────────

def ingest(files: list[Path], dry_run: bool = False, delete_index: bool = False, reset: bool = False) -> None:
    checkpoint = {}
    if reset:
        log.warning("checkpoint_reset")
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()
    else:
        checkpoint = _load_checkpoint()

    # Filter to files not yet ingested
    pending = [f for f in files if not _already_ingested(f, checkpoint)]
    skipped = len(files) - len(pending)

    if skipped:
        print(f"Skipping {skipped} already-ingested file(s) (checkpoint). Use --reset to re-ingest all.")
    if not pending:
        print("Nothing to do — all files already ingested.")
        return

    print(f"Files to process: {len(pending)}")

    if dry_run:
        total = sum(
            len(list(iter_records(f))) for f in pending
        )
        print(f"Dry run: {total} valid records across {len(pending)} file(s).")
        return

    openai_client = get_openai()
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])

    if delete_index:
        existing = [i["name"] for i in pc.list_indexes()]
        if PINECONE_INDEX in existing:
            log.warning("deleting_index", name=PINECONE_INDEX)
            pc.delete_index(PINECONE_INDEX)
            time.sleep(5)
        checkpoint = {}  # full re-ingest

    index = get_pinecone_index(pc)

    total_upserted = 0
    for i, f in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] {f.relative_to(PROCESSED_DIR)}")
        total_upserted += ingest_file(f, index, openai_client, checkpoint, dry_run=False)

    print(f"\nDone. {total_upserted} records upserted to '{PINECONE_INDEX}'.")
    print(f"Checkpoint: {CHECKPOINT_PATH}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest DharmaGPT corpus into Pinecone (resume-safe)")
    parser.add_argument("--file", type=str, default=None,
                        help="Ingest a single JSONL file from knowledge/processed/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate records without embedding or upserting")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe checkpoint and re-ingest all files")
    parser.add_argument("--delete-index", action="store_true",
                        help="Delete the Pinecone index before ingestion")
    parser.add_argument("--recursive", action="store_true",
                        help="Scan knowledge/processed/ recursively (default: yes)")
    parser.add_argument("--partitioned-only", action="store_true",
                        help="Only ingest canonical part-*.jsonl files")
    args = parser.parse_args()

    if args.file:
        target = PROCESSED_DIR / args.file
        if not target.exists():
            sys.exit(f"File not found: {target}")
        files = [target]
    else:
        files = sorted(PROCESSED_DIR.glob("**/*.jsonl"))
        if args.partitioned_only:
            files = [f for f in files if is_canonical_part_file(f)]
        if not files:
            sys.exit(f"No .jsonl files found in {PROCESSED_DIR}")

    ingest(files, dry_run=args.dry_run, delete_index=args.delete_index, reset=args.reset)


if __name__ == "__main__":
    main()
