from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.insight_store import list_ingestion_runs, list_query_runs


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = REPO_ROOT / "dharmagpt" / "knowledge" / "audit"
TRANSCRIPT_DIR = REPO_ROOT / "dharmagpt" / "knowledge" / "processed" / "audio_transcript"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _audio_transcript_records(limit: int = 500) -> list[dict[str, Any]]:
    if not TRANSCRIPT_DIR.exists():
        return []
    paths = sorted(TRANSCRIPT_DIR.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows: list[dict[str, Any]] = []
    for path in paths[:limit]:
        for row in _read_jsonl(path):
            row["_artifact_path"] = str(path)
            row["_artifact_mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            rows.append(row)
    return rows


def _counter_items(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"name": name or "unknown", "count": count} for name, count in counter.most_common(limit)]


def summarize_usage(limit: int = 50) -> dict[str, Any]:
    stored_runs = list_ingestion_runs(limit=500)
    query_runs = list_query_runs(limit=1000)
    audio_audit = _read_jsonl(AUDIT_DIR / "audio_uploads.jsonl")
    corpus_audit = _read_jsonl(AUDIT_DIR / "corpus_uploads.jsonl")
    transcripts = _audio_transcript_records()

    runs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in stored_runs:
        run_id = str(row.get("id") or "")
        if run_id:
            seen_ids.add(run_id)
        ts = _parse_ts(str(row.get("finished_at") or ""))
        runs.append(
            {
                "id": run_id,
                "timestamp": str(row.get("finished_at") or ""),
                "kind": row.get("kind"),
                "source": row.get("source"),
                "source_title": row.get("source_title"),
                "file": row.get("file_name"),
                "language": row.get("language"),
                "dataset_id": row.get("dataset_id"),
                "chunks": int(row.get("chunks") or 0),
                "vectors": int(row.get("vectors") or 0),
                "vector_db": row.get("vector_db"),
                "embedding_backend": row.get("embedding_backend"),
                "transcription_mode": row.get("transcription_mode"),
                "transcription_version": row.get("transcription_version"),
                "translation_backend": row.get("translation_backend"),
                "translation_version": row.get("translation_version"),
                "status": row.get("status") or "unknown",
                "error": row.get("error") or "",
                "_sort": ts.timestamp() if ts else 0,
            }
        )

    for row in audio_audit:
        audit_id = str(row.get("run_id") or "")
        if audit_id and audit_id in seen_ids:
            continue
        ts = _parse_ts(row.get("timestamp"))
        runs.append(
            {
                "timestamp": row.get("timestamp"),
                "kind": "audio",
                "source": row.get("source") or row.get("original_filename"),
                "source_title": row.get("source_title") or row.get("original_filename"),
                "file": row.get("original_filename") or row.get("file_path"),
                "language": row.get("language_code"),
                "chunks": int(row.get("chunks_created") or 0),
                "vectors": int(row.get("vectors_upserted") or 0),
                "vector_db": row.get("vector_db"),
                "embedding_backend": row.get("embedding_backend"),
                "transcription_mode": row.get("transcription_mode"),
                "transcription_version": row.get("transcription_version"),
                "translation_backend": row.get("translation_backend"),
                "translation_version": row.get("translation_version"),
                "status": "ok" if int(row.get("vectors_upserted") or 0) > 0 else "unknown",
                "_sort": ts.timestamp() if ts else 0,
            }
        )

    transcript_by_file = {Path(str(r.get("source_file") or "")).name: r for r in transcripts}
    for run in runs:
        transcript = transcript_by_file.get(Path(str(run.get("file") or "")).name)
        if not transcript:
            continue
        for key in (
            "transcription_mode",
            "transcription_version",
            "translation_backend",
            "translation_version",
            "embedding_backend",
        ):
            run[key] = run.get(key) or transcript.get(key)

    for row in corpus_audit:
        ts = _parse_ts(row.get("timestamp"))
        runs.append(
            {
                "timestamp": row.get("timestamp"),
                "kind": row.get("source_type") or "document",
                "source": row.get("source"),
                "source_title": row.get("source_title"),
                "file": row.get("original_filename") or row.get("file_path"),
                "language": row.get("language"),
                "chunks": int(row.get("chunks_created") or 0),
                "vectors": int(row.get("vectors_upserted") or 0),
                "vector_db": row.get("vector_db"),
                "embedding_backend": row.get("embedding_backend"),
                "status": "ok" if int(row.get("vectors_upserted") or 0) > 0 else "unknown",
                "_sort": ts.timestamp() if ts else 0,
            }
        )

    runs.sort(key=lambda item: item.get("_sort") or 0, reverse=True)
    latest = [{k: v for k, v in row.items() if not k.startswith("_")} for row in runs[:limit]]

    transcription = Counter(
        f"{row.get('transcription_mode') or 'unknown'} / {row.get('transcription_version') or 'unknown'}"
        for row in runs
        if row.get("kind") == "audio"
    )
    translation = Counter(
        f"{row.get('translation_backend') or 'unknown'} / {row.get('translation_version') or 'unknown'}"
        for row in runs
        if row.get("kind") == "audio"
    )
    embedding = Counter(row.get("embedding_backend") or "unknown" for row in runs)
    vector_db = Counter(row.get("vector_db") or "unknown" for row in runs)
    status = Counter(row.get("status") or "unknown" for row in runs)
    query_models = Counter(
        f"{row.get('llm_backend') or 'unknown'} / {row.get('llm_model') or 'unknown'}"
        for row in query_runs
    )
    query_ratings = Counter(
        f"{row.get('llm_backend') or 'unknown'} / {row.get('rating') or 'unrated'}"
        for row in query_runs
    )

    daily = Counter()
    for row in runs:
        ts = _parse_ts(row.get("timestamp"))
        if ts:
            daily[ts.date().isoformat()] += int(row.get("vectors") or 0)

    return {
        "totals": {
            "runs": len(runs),
            "query_runs": len(query_runs),
            "audio_runs": sum(1 for row in runs if row.get("kind") == "audio"),
            "document_runs": sum(1 for row in runs if row.get("kind") != "audio"),
            "chunks": sum(int(row.get("chunks") or 0) for row in runs),
            "vectors": sum(int(row.get("vectors") or 0) for row in runs),
        },
        "usage": {
            "transcription": _counter_items(transcription),
            "translation": _counter_items(translation),
            "embedding": _counter_items(embedding),
            "vector_db": _counter_items(vector_db),
            "status": _counter_items(status),
            "query_models": _counter_items(query_models),
            "query_ratings": _counter_items(query_ratings),
            "daily_vectors": [{"date": date, "vectors": count} for date, count in sorted(daily.items())[-14:]],
        },
        "latest": latest,
    }
