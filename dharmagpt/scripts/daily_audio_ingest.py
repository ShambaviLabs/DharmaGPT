"""
daily_audio_ingest.py - process at most one pending audio file per run.

This is intentionally conservative for API credits. Put source audio files in
dharmagpt/knowledge/incoming/audio, then run this script manually or from the
systemd timer. Successfully processed files are remembered in a private state
file so the next day picks up the next pending file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DHARMAGPT_DIR = REPO_ROOT / "dharmagpt"
DEFAULT_INPUT_DIR = DHARMAGPT_DIR / "knowledge" / "incoming" / "audio"
DEFAULT_STATE_FILE = DHARMAGPT_DIR / "knowledge" / "audit" / "daily_audio_ingest_state.json"
DEFAULT_LOG_FILE = DHARMAGPT_DIR / "knowledge" / "audit" / "daily_audio_ingest.jsonl"

load_dotenv(DHARMAGPT_DIR / ".env")

SUPPORTED = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"processed": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"processed": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def _append_log(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _file_key(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve()}::{stat.st_size}::{int(stat.st_mtime)}"


def discover_pending(input_dir: Path, state: dict[str, Any]) -> list[Path]:
    processed = state.get("processed") or {}
    if not input_dir.exists():
        return []
    files = sorted(
        p
        for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED
    )
    return [p for p in files if _file_key(p) not in processed]


def upload_audio(
    path: Path,
    *,
    api_url: str,
    admin_api_key: str,
    language_code: str,
    dataset_name: str,
    section: str,
    timeout: int,
) -> dict[str, Any]:
    mime_map = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".opus": "audio/opus",
        ".wma": "audio/x-ms-wma",
    }
    headers = {"X-Admin-Key": admin_api_key, "X-API-Key": admin_api_key}
    with path.open("rb") as fh:
        resp = requests.post(
            api_url,
            headers=headers,
            files={"file": (path.name, fh, mime_map.get(path.suffix.lower(), "audio/mpeg"))},
            data={
                "language_code": language_code,
                "dataset_name": dataset_name,
                "section": section,
                "description": path.stem,
                "source_title": path.stem,
                "source": path.stem.lower().replace(" ", "_"),
            },
            timeout=timeout,
        )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one daily audio ingestion into Pinecone")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_FILE))
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1/audio/transcribe")
    parser.add_argument("--admin-api-key", default=os.getenv("ADMIN_OPERATOR_API_KEY") or os.getenv("ADMIN_API_KEY") or "")
    parser.add_argument("--language-code", default=os.getenv("DAILY_AUDIO_LANGUAGE_CODE") or "te-IN")
    parser.add_argument("--dataset-name", default=os.getenv("DAILY_AUDIO_DATASET_NAME") or "daily-audio")
    parser.add_argument("--section", default=os.getenv("DAILY_AUDIO_SECTION") or "")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser()
    state_file = Path(args.state_file).expanduser()
    log_file = Path(args.log_file).expanduser()
    state = _load_state(state_file)
    pending = discover_pending(input_dir, state)

    if not pending:
        row = {"timestamp": _now(), "status": "idle", "reason": "no_pending_audio", "input_dir": str(input_dir)}
        _append_log(log_file, row)
        print(json.dumps(row, ensure_ascii=False))
        return 0

    target = pending[0]
    row: dict[str, Any] = {
        "timestamp": _now(),
        "status": "dry_run" if args.dry_run else "started",
        "file": str(target),
        "dataset_name": args.dataset_name,
        "language_code": args.language_code,
    }
    _append_log(log_file, row)

    if args.dry_run:
        print(json.dumps(row, ensure_ascii=False))
        return 0

    if not args.admin_api_key:
        row.update({"status": "failed", "error": "ADMIN_API_KEY or ADMIN_OPERATOR_API_KEY is required"})
        _append_log(log_file, row)
        print(json.dumps(row, ensure_ascii=False))
        return 2

    last_error: str = ""
    for attempt in range(1, args.retries + 1):
        try:
            response = upload_audio(
                target,
                api_url=args.api_url,
                admin_api_key=args.admin_api_key,
                language_code=args.language_code,
                dataset_name=args.dataset_name,
                section=args.section,
                timeout=args.timeout,
            )
            key = _file_key(target)
            state.setdefault("processed", {})[key] = {
                "timestamp": _now(),
                "file": str(target),
                "response": {
                    "file_name": response.get("file_name"),
                    "transcript_file_name": response.get("transcript_file_name"),
                    "chunks_created": response.get("chunks_created"),
                    "translation_backend": response.get("translation_backend"),
                    "translation_version": response.get("translation_version"),
                },
            }
            _save_state(state_file, state)
            row.update({"status": "ok", "response": state["processed"][key]["response"]})
            _append_log(log_file, row)
            print(json.dumps(row, ensure_ascii=False))
            return 0
        except Exception as exc:
            last_error = str(exc)
            if attempt < args.retries:
                time.sleep(10 * attempt)

    row.update({"status": "failed", "error": last_error})
    _append_log(log_file, row)
    print(json.dumps(row, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
