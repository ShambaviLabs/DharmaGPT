"""
gold_store.py - curated gold-answer storage for DharmaGPT.

This module keeps the gold store separate from live serving:

* raw feedback is appended to knowledge/feedback/responses.jsonl
* approved gold answers are versioned in knowledge/gold_store/gold.jsonl
* every review action is audit-logged in knowledge/gold_store/audit.jsonl

The live RAG path should not depend on this module. It is used for:

* review workflow persistence
* gold set evaluation and regression tests
* optional few-shot examples in offline analysis only
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

REPO_ROOT = Path(__file__).resolve().parents[2]
FEEDBACK_DIR = REPO_ROOT / "knowledge" / "feedback"
GOLD_STORE_DIR = REPO_ROOT / "knowledge" / "gold_store"

RESPONSES_FILE = FEEDBACK_DIR / "responses.jsonl"
GOLD_FILE = GOLD_STORE_DIR / "gold.jsonl"
AUDIT_FILE = GOLD_STORE_DIR / "audit.jsonl"

RESPONSES_LOCK = FileLock(str(RESPONSES_FILE) + ".lock")
GOLD_LOCK = FileLock(str(GOLD_FILE) + ".lock")
AUDIT_LOCK = FileLock(str(AUDIT_FILE) + ".lock")

_STOPWORDS = {
    "a", "an", "and", "are", "be", "can", "do", "for", "from", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "should",
    "tell", "the", "to", "what", "when", "where", "which", "with",
    "you", "your",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if raw:
                records.append(json.loads(raw))
    return records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp_path, path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9']+", text or "")
        if len(token) > 2 and token.lower() not in _STOPWORDS
    }


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def gold_id_for(query: str, mode: str) -> str:
    """
    Build a stable identifier for a canonical gold answer.

    We intentionally key on normalized query + mode so paraphrases can be
    clustered under the same benchmark record when the reviewer approves them.
    """
    digest = hashlib.sha1(f"{mode}|{_normalize_text(query)}".encode("utf-8")).hexdigest()
    return f"{mode}:{digest[:16]}"


def load_feedback_responses() -> list[dict]:
    with RESPONSES_LOCK:
        return _read_jsonl(RESPONSES_FILE)


def save_feedback_response(record: dict) -> dict:
    """
    Persist a raw feedback response.

    The record should already include the query, answer, sources, rating, and
    review_status fields. We add a timestamp if one was not provided.
    """
    normalized = dict(record)
    normalized.setdefault("timestamp", _timestamp())
    normalized.setdefault("review_status", "pending")
    with RESPONSES_LOCK:
        _append_jsonl(RESPONSES_FILE, normalized)
    return normalized


def list_pending_feedback() -> list[dict]:
    """
    Return upvoted responses that still need human review.

    This is the review queue that feeds the gold store.
    """
    records = load_feedback_responses()
    return [
        r for r in records
        if r.get("rating") == "up" and r.get("review_status") == "pending"
    ]


def load_gold_entries() -> list[dict]:
    with GOLD_LOCK:
        return _read_jsonl(GOLD_FILE)


def _audit(event: dict) -> None:
    entry = {"timestamp": _timestamp(), **event}
    with AUDIT_LOCK:
        _append_jsonl(AUDIT_FILE, entry)


def _build_gold_entry(
    feedback_record: dict,
    *,
    reviewer: str | None,
    review_note: str | None,
    gold_id: str | None = None,
    canonical_query: str | None = None,
) -> dict:
    query = feedback_record.get("query", "")
    mode = feedback_record.get("mode", "")
    gold_id = gold_id or gold_id_for(query, mode)
    now = _timestamp()
    sources = feedback_record.get("sources") or []

    return {
        "gold_id": gold_id,
        "query_id": feedback_record.get("query_id"),
        "query": query,
        "canonical_query": canonical_query or _normalize_text(query),
        "mode": mode,
        "gold_answer": feedback_record.get("answer", ""),
        "evidence": sources,
        "source_count": len(sources),
        "query_variants": [query],
        "review_status": "approved",
        "reviewer": reviewer or feedback_record.get("reviewer"),
        "review_note": review_note or feedback_record.get("review_note") or feedback_record.get("note"),
        "feedback_timestamp": feedback_record.get("timestamp"),
        "reviewed_at": feedback_record.get("reviewed_at") or now,
        "promoted_at": now,
        "created_at": feedback_record.get("timestamp") or now,
        "updated_at": now,
        "version": 1,
    }


def upsert_gold_entry(
    feedback_record: dict,
    *,
    reviewer: str | None = None,
    review_note: str | None = None,
) -> dict:
    """
    Promote a reviewed feedback record into the canonical gold store.

    Gold records are deduped by `gold_id`. If a matching gold record already
    exists, its version is incremented and the new approved answer replaces the
    previous entry.
    """
    with GOLD_LOCK:
        records = _read_jsonl(GOLD_FILE)
        query = feedback_record.get("query", "")
        mode = feedback_record.get("mode", "")
        matched = None
        for existing in records:
            if existing.get("mode") != mode:
                continue
            existing_query = existing.get("query", "")
            if _normalize_text(existing_query) == _normalize_text(query):
                matched = existing
                break
            if _overlap(query, existing_query) >= 0.85:
                matched = existing
                break

        entry = _build_gold_entry(
            feedback_record,
            reviewer=reviewer,
            review_note=review_note,
            gold_id=matched.get("gold_id") if matched else None,
            canonical_query=matched.get("canonical_query") if matched else None,
        )
        updated = False
        for i, existing in enumerate(records):
            if existing.get("gold_id") == entry["gold_id"]:
                entry["version"] = int(existing.get("version", 1)) + 1
                entry["created_at"] = existing.get("created_at", entry["created_at"])
                entry["updated_at"] = _timestamp()
                records[i] = {**existing, **entry}
                updated = True
                break
        if not updated:
            records.append(entry)
        _write_jsonl(GOLD_FILE, records)

    _audit(
        {
            "event": "gold_upserted",
            "gold_id": entry["gold_id"],
            "query_id": entry.get("query_id"),
            "mode": entry.get("mode"),
            "reviewer": entry.get("reviewer"),
            "version": entry.get("version"),
            "source_count": entry.get("source_count", 0),
        }
    )
    return entry


def review_feedback_response(
    query_id: str,
    review_status: str,
    *,
    reviewer: str | None = None,
    review_note: str | None = None,
) -> dict:
    """
    Update a stored feedback response and optionally promote it into the gold set.
    """
    if review_status not in {"approved", "rejected"}:
        raise ValueError("review_status must be 'approved' or 'rejected'")

    with RESPONSES_LOCK:
        records = _read_jsonl(RESPONSES_FILE)
        updated: dict | None = None
        for record in records:
            if record.get("query_id") != query_id:
                continue
            record["review_status"] = review_status
            record["reviewed_at"] = _timestamp()
            if reviewer is not None:
                record["reviewer"] = reviewer
            if review_note is not None:
                record["review_note"] = review_note
            updated = record
            break

        if not updated:
            raise LookupError(f"query_id not found: {query_id!r}")

        _write_jsonl(RESPONSES_FILE, records)

    _audit(
        {
            "event": "feedback_reviewed",
            "query_id": query_id,
            "review_status": review_status,
            "reviewer": reviewer,
            "review_note": review_note,
        }
    )

    if review_status == "approved":
        upsert_gold_entry(updated, reviewer=reviewer, review_note=review_note)

    return updated


def list_gold_examples(query: str, mode: str, n: int = 2) -> list[dict]:
    """
    Return up to n gold examples relevant to a query and mode.

    This is intentionally kept for offline analysis and prompt experiments,
    not for the live RAG serving path.
    """
    records = [
        r for r in load_gold_entries()
        if r.get("mode") == mode and r.get("gold_answer")
    ]
    if not records:
        return []
    scored = sorted(
        records,
        key=lambda r: _overlap(query, r.get("query", "")),
        reverse=True,
    )
    return [{"query": r["query"], "answer": r["gold_answer"]} for r in scored[:n]]


def find_gold_answer(query: str, mode: str) -> str | None:
    """
    Return the approved gold answer for a query/mode pair.

    Matching is exact first, then a conservative overlap fallback for
    paraphrases that were approved by the reviewer.
    """
    q_norm = _normalize_text(query)
    records = load_gold_entries()

    for record in records:
        if record.get("mode") == mode and _normalize_text(record.get("query")) == q_norm:
            return record.get("gold_answer")

    for record in records:
        if record.get("mode") == mode and _overlap(query, record.get("query", "")) >= 0.85:
            return record.get("gold_answer")

    return None
