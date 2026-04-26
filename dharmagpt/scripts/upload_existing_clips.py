"""
upload_existing_clips.py — upload pre-split 29s clips directly to the transcription API.

Use this when clips are already split (in downloads/clips_29s_full/) but haven't been
transcribed yet. Skips clips whose transcript JSONL already exists in knowledge/processed/.

Usage:
    cd dharmagpt
    python scripts/upload_existing_clips.py --clips-dir ../downloads/clips_29s_full \
        --language-code te-IN --limit 5

    # Run all clips:
    python scripts/upload_existing_clips.py --clips-dir ../downloads/clips_29s_full \
        --language-code te-IN
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "dharmagpt" / ".env")

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dharmagpt.utils.naming import (  # noqa: E402
    canonical_jsonl_filename,
    normalize_language_tag,
    part_number_from_filename,
    source_stem_from_audio_filename,
)

TRANSCRIPT_BASE = REPO_ROOT / "dharmagpt" / "knowledge" / "processed" / "audio_transcript"
SUPPORTED = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def discover_clips(clips_dir: Path) -> list[Path]:
    return sorted(p for p in clips_dir.rglob("*.mp3") if p.suffix.lower() in SUPPORTED)


def transcript_exists(clip_path: Path, language_tag: str) -> tuple[bool, Path]:
    base = source_stem_from_audio_filename(clip_path.name, language=language_tag)
    part = part_number_from_filename(clip_path.name)
    fname = canonical_jsonl_filename(base, language=language_tag, kind="transcript", part=part)
    path = TRANSCRIPT_BASE / base / fname
    return path.exists(), path


def upload_clip(clip_path: Path, *, language_code: str, api_url: str, timeout: int, retries: int) -> dict:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with clip_path.open("rb") as fh:
                resp = requests.post(
                    api_url,
                    files={"file": (clip_path.name, fh, "audio/mpeg")},
                    data={"language_code": language_code, "description": clip_path.stem},
                    timeout=timeout,
                )
            if resp.status_code in {429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:300]}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(5 * attempt)
    raise last_err or RuntimeError("upload failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload pre-split clips to the transcription API")
    parser.add_argument("--clips-dir", required=True, help="Directory containing pre-split MP3 clips (searched recursively)")
    parser.add_argument("--language-code", default="te-IN", help="Sarvam language code")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1/audio/transcribe")
    parser.add_argument("--timeout", type=int, default=120, help="Per-clip upload timeout in seconds")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--chunk-delay", type=float, default=1.0, help="Delay between clips in seconds")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N clips (0 = all)")
    parser.add_argument("--overwrite", action="store_true", help="Re-upload even if transcript exists")
    args = parser.parse_args()

    clips_dir = Path(args.clips_dir)
    if not clips_dir.exists():
        raise SystemExit(f"Clips directory not found: {clips_dir}")

    language_tag = normalize_language_tag(args.language_code)
    all_clips = discover_clips(clips_dir)
    if not all_clips:
        raise SystemExit(f"No audio clips found in {clips_dir}")

    print(f"Found {len(all_clips)} clip(s) in {clips_dir}")
    print(f"API: {args.api_url}\n")

    ok = failed = skipped = 0
    results: list[dict] = []

    for i, clip in enumerate(all_clips, 1):
        if args.limit and i > args.limit:
            break

        exists, transcript_path = transcript_exists(clip, language_tag)
        if exists and not args.overwrite:
            print(f"[{i}] skip {clip.name} (transcript exists)")
            skipped += 1
            results.append({"clip": str(clip), "status": "skipped", "transcript": str(transcript_path)})
            continue

        print(f"[{i}] uploading {clip.name} ...", end=" ", flush=True)
        try:
            resp = upload_clip(clip, language_code=args.language_code, api_url=args.api_url, timeout=args.timeout, retries=args.retries)
            ok += 1
            print(f"ok  chunks={resp.get('chunks_created')}  backend={resp.get('translation_backend')}  -> {resp.get('transcript_file_name')}")
            results.append({"clip": str(clip), "status": "ok", "response": resp})
        except Exception as exc:
            failed += 1
            print(f"FAIL: {exc}")
            results.append({"clip": str(clip), "status": "failed", "error": str(exc)})

        time.sleep(args.chunk_delay)

    manifest_path = clips_dir / "upload_manifest.json"
    manifest_path.write_text(json.dumps({"ok": ok, "failed": failed, "skipped": skipped, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone — ok={ok}  failed={failed}  skipped={skipped}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
