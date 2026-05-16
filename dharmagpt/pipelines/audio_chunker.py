"""
audio_chunker.py
Receives Sarvam STT transcript (with word timestamps + diarization),
applies pause-boundary chunking, and upserts enriched chunks to the
configured vector DB.

Translation is NOT done automatically — translations are provided manually
via the discourse_translations table in Postgres.

All backends pluggable via .env:
  EMBEDDING_BACKEND = openai | local_hash
  RAG_BACKEND       = local | pinecone
"""
from __future__ import annotations

import re
import uuid

import structlog

from core.config import get_settings
from core.local_vector_store import upsert_vectors
from core.retrieval import embed_texts, get_pinecone

log = structlog.get_logger()
settings = get_settings()

SACRED_MARKERS = [
    "shri ram", "jai ram", "jai hanuman", "namah shivaya",
    "om namo", "sita ram", "jai siya ram", "pavan putra",
    "anjaneya", "bajrangbali",
]
SHLOKA_PATTERN = re.compile(r"[।॥|]+")


def _detect_speaker(text: str) -> str:
    has_danda = bool(SHLOKA_PATTERN.search(text))
    en_ratio = len(re.findall(r"\b[a-zA-Z]{3,}\b", text)) / max(len(text.split()), 1)
    if has_danda or any(m in text.lower() for m in SACRED_MARKERS):
        return "chanting"
    return "commentary_english" if en_ratio > 0.5 else "commentary_hindi"


def _chunk_by_pause(words: list[dict], min_words: int = 12, max_words: int = 70) -> list[dict]:
    chunks, buf, start = [], [], 0.0
    for i, w in enumerate(words):
        buf.append(w)
        is_last = i == len(words) - 1
        gap = (words[i + 1].get("start", 0) - w.get("end", 0)) if not is_last else 999
        text_so_far = " ".join(x.get("word", "") for x in buf)
        should_cut = (
            (gap > 0.8 and len(buf) >= min_words)
            or bool(SHLOKA_PATTERN.search(text_so_far) and len(buf) >= min_words)
            or len(buf) >= max_words
            or is_last
        )
        if should_cut and buf:
            text = re.sub(r"\s+", " ", text_so_far).strip()
            chunks.append({
                "text": text,
                "start": start,
                "end": w.get("end", 0),
                "speaker": _detect_speaker(text),
                "has_shloka": bool(SHLOKA_PATTERN.search(text)),
            })
            buf = []
            start = words[i + 1].get("start", 0) if not is_last else 0
    return chunks


def _fallback_chunk(text: str) -> list[dict]:
    """When timestamps are unavailable, chunk by sentence boundaries."""
    segs = re.split(r"[।॥|]{1,2}|\.(?=\s)", text)
    chunks, buf = [], []
    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        buf.append(seg)
        if len(" ".join(buf).split()) >= 20:
            t = " ".join(buf)
            chunks.append({
                "text": t, "start": None, "end": None,
                "speaker": _detect_speaker(t),
                "has_shloka": bool(SHLOKA_PATTERN.search(t)),
            })
            buf = []
    if buf:
        t = " ".join(buf)
        chunks.append({
            "text": t, "start": None, "end": None,
            "speaker": _detect_speaker(t),
            "has_shloka": bool(SHLOKA_PATTERN.search(t)),
        })
    return chunks


def _normalize_language_code(language_code: str) -> str:
    lang = (language_code or "").strip().lower()
    if not lang or lang.startswith("en"):
        return "en"
    if "-" in lang:
        return lang.split("-", 1)[0]
    return lang


async def chunk_and_index(
    transcript_data: dict,
    filename: str,
    file_metadata: dict,
    dataset_id: str = "",
) -> dict:
    """Main entry: chunk -> embed -> upsert to configured vector DB.

    No automatic translation. Translations are provided manually via the
    discourse_translations Postgres table and linked by source + chunk index.
    """
    words = transcript_data.get("words", [])
    raw_text = transcript_data.get("transcript", "")

    raw_chunks = _chunk_by_pause(words) if words else _fallback_chunk(raw_text)
    if not raw_chunks:
        return {"chunks_created": 0, "vector_db": None, "vectors_upserted": 0, "embedding_backend": None}

    stem = filename.rsplit(".", 1)[0]
    texts = [chunk["text"] for chunk in raw_chunks]

    try:
        vectors, embedding_backend = await embed_texts(texts)
    except Exception as exc:
        log.warning("audio_indexing_skipped", file=filename, reason=str(exc))
        vectors = []
        embedding_backend = None

    records = []
    for i, (chunk, vec) in enumerate(zip(raw_chunks, vectors)):
        record_metadata = {
            "source_type": "audio",
            "source_file": filename,
            "source": file_metadata.get("source") or stem,
            "source_title": file_metadata.get("source_title") or file_metadata.get("description", stem),
            "text": chunk["text"],
            "text_preview": chunk["text"][:300],
            "start_time_sec": chunk.get("start") or "",
            "end_time_sec": chunk.get("end") or "",
            "speaker_type": chunk["speaker"],
            "has_shloka": chunk["has_shloka"],
            "section": file_metadata.get("section") or "",
            "language": file_metadata.get("language_code", "hi-IN"),
            "description": file_metadata.get("description", stem),
            "citation": f"Audio: {file_metadata.get('description', stem)}",
            "word_count": len(chunk["text"].split()),
            "transcription_mode": file_metadata.get("transcription_mode", "sarvam_stt"),
            "transcription_version": file_metadata.get("transcription_version", "saaras:v3"),
            "embedding_backend": embedding_backend or "",
            "chunk_index": i,
        }
        if dataset_id:
            record_metadata["dataset_id"] = dataset_id

        records.append({
            "id": f"audio_{stem}_{uuid.uuid4().hex[:8]}_{i:04d}",
            "values": vec,
            "metadata": record_metadata,
        })

    vector_db = (settings.rag_backend or settings.vector_db_backend or "local").lower()
    upserted = 0
    if records:
        batch_size = 100
        if vector_db == "local":
            upserted = upsert_vectors(
                index_name=settings.local_vector_index_name,
                namespace=settings.local_vector_namespace,
                records=records,
            )
        else:
            index = get_pinecone().Index(settings.pinecone_index_name)
            for i in range(0, len(records), batch_size):
                batch = records[i: i + batch_size]
                index.upsert(vectors=batch)
                upserted += len(batch)

    log.info(
        "audio_indexed",
        file=filename,
        chunks=len(raw_chunks),
        vector_db=vector_db,
        vectors=upserted,
        embedding_backend=embedding_backend,
    )
    return {
        "chunks_created": len(raw_chunks),
        "vector_db": vector_db,
        "vectors_upserted": upserted,
        "embedding_backend": embedding_backend,
    }
