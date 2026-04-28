#!/usr/bin/env python3
"""
end_to_end_pipeline_test.py — Manual corpus upload and end-to-end pipeline test.

Test the complete workflow:
  1. Upload documents/audio to local DB (corpus_records)
  2. Show corpus metrics (coverage, enrichment status)
  3. Embed with OpenAI
  4. Ingest to Pinecone
  5. Query and verify retrieval

Usage:
  python scripts/end_to_end_pipeline_test.py --file document.pdf --source "my_docs"
  python scripts/end_to_end_pipeline_test.py --file audio.mp3 --source "speaker_name" --language te
  python scripts/end_to_end_pipeline_test.py --batch docs/ --source "bulk_upload"
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

log = structlog.get_logger()
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
UPLOAD_AND_INGEST = REPO_ROOT / "dharmagpt" / "scripts" / "upload_and_ingest.py"
CORPUS_METRICS = REPO_ROOT / "dharmagpt" / "scripts" / "corpus_metrics.py"
PINECONE_INGEST = REPO_ROOT / "dharmagpt" / "scripts" / "ingest_to_pinecone_from_db.py"

# Force UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _sep(title: str) -> None:
    """Print section separator."""
    width = 70
    print(f"\n{('─' * width)}")
    print(f"  {title}")
    print(f"{('─' * width)}")


def _ok(msg: str) -> None:
    """Print success message."""
    print(f"  ✓ {msg}")


def _info(msg: str) -> None:
    """Print info message."""
    print(f"    {msg}")


def _warn(msg: str) -> None:
    """Print warning message."""
    print(f"  ⚠ {msg}")


def stage_upload(file_path: str, source: str, language: str = "en") -> None:
    """Stage 1: Upload document/audio to DB."""
    _sep("STAGE 1 — Upload to Corpus DB")

    file_p = Path(file_path).expanduser().resolve()
    if not file_p.exists():
        print(f"  ERROR: File not found: {file_path}")
        sys.exit(1)

    _info(f"File: {file_path}")
    _info(f"Source: {source}")
    _info(f"Language: {language}")
    _info(f"Size: {file_p.stat().st_size / 1024 / 1024:.2f} MB")

    # Run upload script
    cmd = [
        sys.executable,
        str(UPLOAD_AND_INGEST),
        "--file", str(file_p),
        "--source", source,
        "--language", language,
    ]

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"  ERROR: Upload failed")
        sys.exit(1)

    _ok("Document uploaded and ingested into corpus_records")


def stage_metrics() -> None:
    """Stage 2: Show corpus metrics."""
    _sep("STAGE 2 — Corpus Metrics & Coverage")

    cmd = [sys.executable, str(CORPUS_METRICS)]
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        sys.exit("ERROR: Metrics stage failed")


def stage_embed(limit: int | None = None) -> None:
    """Stage 3: Embed pending records."""
    _sep("STAGE 3 — Embed with OpenAI & Upsert to Pinecone")

    _info("This will:")
    _info("  1. Find all embedded=0 records")
    _info("  2. Call OpenAI embeddings API")
    _info("  3. Upsert vectors to Pinecone")
    _info("  4. Mark records as embedded in DB")

    if limit:
        _info(f"  (Limited to {limit} records for testing)")

    confirm = input("\n  Proceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Skipped")
        return

    cmd = [
        sys.executable,
        str(PINECONE_INGEST),
    ]
    if limit:
        cmd.extend(["--limit", str(limit)])

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        _warn("Embedding/ingestion failed")
        return

    _ok("Records embedded and ingested to Pinecone")


def stage_query_test() -> None:
    """Stage 4: Test query retrieval."""
    _sep("STAGE 4 — Query Test (Local Retrieval)")

    _info("Running a test query against the corpus...")

    # Test query code
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from core.retrieval import retrieve_sources
        from models.schemas import QueryRequest

        request = QueryRequest(
            query="What is dharma?",
            filter_section=None,
        )

        sources = asyncio.run(retrieve_sources(request))

        if sources:
            _ok(f"Retrieved {len(sources)} source(s)")
            for i, source in enumerate(sources[:3], 1):
                _info(f"  [{i}] {source.citation[:60]}")
                _info(f"      Score: {source.relevance_score:.3f}")
        else:
            _warn("No sources retrieved — corpus may be empty or not indexed")

    except Exception as e:
        _warn(f"Query test failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end corpus pipeline test"
    )
    parser.add_argument(
        "--file", type=str, help="Single file to upload"
    )
    parser.add_argument(
        "--batch", type=str, help="Directory of files to upload"
    )
    parser.add_argument(
        "--source", type=str, required=True, help="Source name/identifier"
    )
    parser.add_argument(
        "--language", type=str, default="en", help="Language code (en, te, hi)"
    )
    parser.add_argument(
        "--embed", action="store_true", help="Run embedding stage"
    )
    parser.add_argument(
        "--query-test", action="store_true", help="Run query test"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit embedding to N records"
    )
    parser.add_argument(
        "--full", action="store_true", help="Run all stages (upload → metrics → embed → query)"
    )

    args = parser.parse_args()

    if args.full:
        args.embed = True
        args.query_test = True

    # Validate inputs
    file_count = sum([bool(args.file), bool(args.batch)])
    if file_count == 0:
        parser.print_help()
        sys.exit(1)
    if file_count > 1:
        sys.exit("ERROR: Use either --file or --batch, not both")

    # Stage 1: Upload
    if args.file:
        stage_upload(args.file, args.source, args.language)
    elif args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            sys.exit(f"ERROR: Directory not found: {args.batch}")
        files = sorted(batch_dir.glob("*"))
        for file_p in files:
            if file_p.is_file():
                _info(f"Uploading {file_p.name}...")
                stage_upload(str(file_p), args.source, args.language)

    # Stage 2: Metrics
    stage_metrics()

    # Stage 3: Embed (optional)
    if args.embed:
        stage_embed(limit=args.limit)

    # Stage 4: Query test (optional)
    if args.query_test:
        stage_query_test()

    print("\n" + "─" * 70)
    print("  Test pipeline complete!")
    print("─" * 70 + "\n")


if __name__ == "__main__":
    main()
