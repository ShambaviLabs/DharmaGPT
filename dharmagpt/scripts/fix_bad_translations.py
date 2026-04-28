"""
fix_bad_translations.py — Pass 2 of the two-pass translation pipeline.

Scans all processed JSONL files, detects low-quality translations produced by
the local model (transliteration instead of translation, leaked prompts, etc.),
and re-translates only those records using the Sarvam translate API which is
purpose-built for Indic languages.

Two-pass pipeline (run in order after audio transcription):
  1. python scripts/translate_corpus.py --backend ollama   # fast, local, ~78% accurate
  2. python scripts/fix_bad_translations.py                # Sarvam fixes the ~22% failures

Usage:
  python scripts/fix_bad_translations.py              # scan + fix all parts
  python scripts/fix_bad_translations.py --dry-run    # report only, no writes
  python scripts/fix_bad_translations.py --part audio_transcript/01_01_...
  python scripts/fix_bad_translations.py --sample 5   # show 5 bad examples and stop
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import structlog

# Force UTF-8 stdout on Windows (Indic/IAST chars fail on cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.backends.translation import Translator, get_translator  # noqa: E402

log = structlog.get_logger()
PROCESSED_DIR = REPO_ROOT / "knowledge" / "processed"

# ── Bad-translation detectors ─────────────────────────────────────────────────

# IAST diacritics that appear when the model phonetically encodes Indic text
_IAST = re.compile(r"[āīūṭḍṇṃḥśṣĀĪŪṬḌṆŚṢṚṜḷḸ]")
# Suspiciously long "words" — telugu words encoded as single latin tokens
_LONG_TOKEN = re.compile(r"\b[A-Za-z]{16,}\b")
# Model leaked its own instruction
_LEAKED_PROMPT = re.compile(r"translat\w+ from \w+_\w+ to \w+_\w+", re.IGNORECASE)


def _bad_translation(en_text: str, te_text: str) -> str | None:
    """Return a reason string if the translation looks bad, else None."""
    if not en_text:
        return None
    if len(_IAST.findall(en_text)) > 5:
        return "iast_transliteration"
    if len(_LONG_TOKEN.findall(en_text)) > 3:
        return "long_latin_tokens"
    if _LEAKED_PROMPT.search(en_text):
        return "leaked_prompt"
    # English shorter than 15% of Telugu word count — likely incomplete
    te_words = len(te_text.split()) if te_text else 0
    en_words = len(en_text.split())
    if te_words > 30 and en_words < te_words * 0.15:
        return "too_short"
    return None


# ── Language code normalisation ───────────────────────────────────────────────

_LANG_MAP = {
    "te": "te-IN", "hi": "hi-IN", "sa": "sa-IN",
    "ta": "ta-IN", "kn": "kn-IN", "ml": "ml-IN",
    "en": "en-IN",
}


def _src_lang(record: dict) -> str:
    lang = (record.get("language") or "te").strip().lower()
    return _LANG_MAP.get(lang, lang if "-" in lang else f"{lang}-IN")


# ── Per-file processing ───────────────────────────────────────────────────────

def _load(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _save(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    tmp.replace(path)


def process_file(
    path: Path,
    *,
    translator: Translator,
    dry_run: bool,
    rate_delay: float,
) -> dict:
    records = _load(path)
    bad_count = fixed = errors = 0

    for i, record in enumerate(records):
        en = (record.get("text_en") or record.get("text_en_model") or "").strip()
        te = (record.get("text_te") or record.get("text") or "").strip()

        reason = _bad_translation(en, te)
        if not reason:
            continue
        bad_count += 1

        if dry_run:
            log.info("bad_translation_found", file=path.name, reason=reason)
            continue

        if not te:
            continue

        try:
            result = translator.translate(te, source_lang=_src_lang(record), target_lang="en-IN")
            records[i]["text_en"] = result.text
            records[i]["text_en_model"] = result.text
            # Preserve original backend so audit queries can see the full pass history
            records[i]["translation_backend_pass1"] = record.get("translation_backend") or "unknown"
            records[i]["translation_backend"] = result.backend
            records[i]["translation_mode"] = "sarvam_fix"
            records[i]["translation_version"] = "sarvam-translate-v1"
            records[i]["translation_fix_reason"] = reason  # why pass 1 was rejected
            records[i]["translation_fallback_reason"] = f"fixed:{reason}"
            fixed += 1
            if rate_delay:
                time.sleep(rate_delay)
        except Exception as exc:
            log.warning("fix_failed", file=path.name, error=str(exc))
            errors += 1

    if fixed and not dry_run:
        _save(path, records)

    return {"file": path.name, "records": len(records), "bad": bad_count, "fixed": fixed, "errors": errors}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pass 2: detect and fix bad translations using Sarvam.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--part", type=str, default=None,
        help="Target a specific subdirectory under knowledge/processed/ (e.g. audio_transcript/01_01_...)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report bad translations without fixing them",
    )
    parser.add_argument(
        "--sample", type=int, default=0,
        help="Print N bad examples and exit (implies --dry-run)",
    )
    parser.add_argument(
        "--rate-delay", type=float, default=0.3,
        help="Seconds between Sarvam API calls to avoid rate limiting (default: 0.3)",
    )
    args = parser.parse_args()

    dry_run = args.dry_run or bool(args.sample)

    # Force Sarvam for pass 2 — this is always the fix backend
    import os
    os.environ["TRANSLATION_BACKEND"] = "sarvam"
    get_translator.cache_clear()
    translator = get_translator()

    if args.part:
        target = PROCESSED_DIR / args.part
        if not target.exists():
            raise SystemExit(f"Not found: {target}")
        files = sorted(target.glob("**/*.jsonl")) if target.is_dir() else [target]
    else:
        files = sorted(PROCESSED_DIR.glob("**/*.jsonl"))

    if not files:
        raise SystemExit(f"No .jsonl files found under {PROCESSED_DIR}")

    print(f"{'DRY RUN — ' if dry_run else ''}Backend: {translator.backend_name}  |  Files: {len(files)}")
    print()

    total_bad = total_fixed = total_errors = 0
    sample_shown = 0

    for path in files:
        if args.sample and sample_shown >= args.sample:
            break

        records = _load(path)
        for record in records:
            en = (record.get("text_en") or record.get("text_en_model") or "").strip()
            te = (record.get("text_te") or record.get("text") or "").strip()
            reason = _bad_translation(en, te)
            if reason and args.sample:
                print(f"[{reason}] {path.name}")
                print(f"  TE: {te[:180]}")
                print(f"  EN: {en[:180]}")
                print()
                sample_shown += 1
                if sample_shown >= args.sample:
                    break

        if args.sample:
            continue

        result = process_file(path, translator=translator, dry_run=dry_run, rate_delay=args.rate_delay)
        if result["bad"]:
            status = f"found {result['bad']}"
            if not dry_run:
                status += f", fixed {result['fixed']}"
                if result["errors"]:
                    status += f", {result['errors']} errors"
            print(f"  {path.name}: {status}")
        total_bad += result["bad"]
        total_fixed += result["fixed"]
        total_errors += result["errors"]

    print()
    if dry_run:
        print(f"Bad translations found: {total_bad}")
        print("Re-run without --dry-run to fix them.")
    else:
        print(f"Bad found: {total_bad}  |  Fixed: {total_fixed}  |  Errors: {total_errors}")


if __name__ == "__main__":
    main()
