"""
audio_chunker.py
Receives Sarvam STT transcript (with word timestamps + diarization),
applies pause-boundary chunking, translates chunks in parallel when needed,
and upserts enriched chunks to Pinecone.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import uuid

import structlog

from core.config import get_settings
from core.chunk_store import upsert_chunk
from core.retrieval import embed_texts, get_pinecone
from core.translation import TranslationBackend, TranslationConfig, TranslationOutcome, translate_text

log = structlog.get_logger()
settings = get_settings()

SACRED_MARKERS = [
    "shri ram",
    "jai ram",
    "jai hanuman",
    "namah shivaya",
    "om namo",
    "sita ram",
    "jai siya ram",
    "pavan putra",
    "anjaneya",
    "bajrangbali",
]
SHLOKA_PATTERN = re.compile(r"[।॥|]+")
CHUNK_WINDOW_SECS = 30


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
            chunks.append(
                {
                    "text": text,
                    "start": start,
                    "end": w.get("end", 0),
                    "speaker": _detect_speaker(text),
                    "has_shloka": bool(SHLOKA_PATTERN.search(text)),
                }
            )
            buf = []
            start = words[i + 1].get("start", 0) if not is_last else 0
    return chunks


def _chunk_by_time_window(words: list[dict], window_secs: int = CHUNK_WINDOW_SECS) -> list[dict]:
    """Group words into fixed-width time windows based on start timestamps."""
    if not words:
        return []

    chunks: list[dict] = []
    buf: list[dict] = []
    bucket = None
    window_start = 0.0

    for word in words:
        start = word.get("start")
        end = word.get("end")
        if not isinstance(start, (int, float)):
            continue
        word_bucket = int(start // window_secs)
        if bucket is None:
            bucket = word_bucket
            window_start = float(bucket * window_secs)
        if word_bucket != bucket and buf:
            text = re.sub(r"\s+", " ", " ".join(x.get("word", "") for x in buf)).strip()
            chunks.append(
                {
                    "text": text,
                    "start": window_start,
                    "end": buf[-1].get("end", window_start),
                    "speaker": _detect_speaker(text),
                    "has_shloka": bool(SHLOKA_PATTERN.search(text)),
                    "word_count": len(buf),
                }
            )
            buf = []
            bucket = word_bucket
            window_start = float(bucket * window_secs)
        buf.append(word)

    if buf:
        text = re.sub(r"\s+", " ", " ".join(x.get("word", "") for x in buf)).strip()
        chunks.append(
            {
                "text": text,
                "start": window_start,
                "end": buf[-1].get("end", window_start),
                "speaker": _detect_speaker(text),
                "has_shloka": bool(SHLOKA_PATTERN.search(text)),
                "word_count": len(buf),
            }
        )

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
            chunks.append(
                {
                    "text": t,
                    "start": None,
                    "end": None,
                    "speaker": _detect_speaker(t),
                    "has_shloka": bool(SHLOKA_PATTERN.search(t)),
                }
            )
            buf = []
    if buf:
        t = " ".join(buf)
        chunks.append(
            {
                "text": t,
                "start": None,
                "end": None,
                "speaker": _detect_speaker(t),
                "has_shloka": bool(SHLOKA_PATTERN.search(t)),
            }
        )
    return chunks


def _normalize_language_code(language_code: str) -> str:
    lang = (language_code or "").strip().lower()
    if not lang:
        return "en"
    if lang.startswith("en"):
        return "en"
    if "-" in lang:
        return lang.split("-", 1)[0]
    return lang


def _build_translation_config() -> TranslationConfig:
    return TranslationConfig(
        backend=TranslationBackend.auto,
        sarvam_model=settings.sarvam_translation_model,
        sarvam_api_key=settings.sarvam_api_key,
        anthropic_model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        openai_model=settings.openai_translation_model,
        openai_api_key=settings.openai_api_key,
        ollama_model=settings.ollama_model,
        ollama_url=settings.ollama_url,
        indictrans2_model=settings.indictrans2_model,
        local_first=settings.translation_local_first,
        backend_order=tuple(
            item.strip()
            for item in (settings.translation_backend_order or "").split(",")
            if item.strip()
        ),
    )


def _translate_chunks_parallel(
    chunks: list[dict],
    *,
    source_lang: str,
    target_lang: str = "en",
) -> list[TranslationOutcome | None]:
    if not chunks:
        return []

    config = _build_translation_config()
    results: list[TranslationOutcome | None] = [None] * len(chunks)
    max_workers = max(1, min(settings.translation_max_workers, len(chunks)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                translate_text,
                chunk["text"],
                config=config,
                source_lang=source_lang,
                target_lang=target_lang,
            ): idx
            for idx, chunk in enumerate(chunks)
        }

        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                log.warning("audio_translation_failed", chunk_index=idx, error=str(exc))
                results[idx] = None

    return results


def _summarize_provenance(outcomes: list[TranslationOutcome | None]) -> dict[str, str | list[str] | None]:
    completed = [item for item in outcomes if item is not None]
    if not completed:
        return {
            "translation_mode": None,
            "translation_backend": None,
            "translation_version": None,
            "translation_fallback_reason": None,
            "translation_attempted_backends": None,
        }

    backend_set = {item.backend for item in completed}
    version_set = {item.version for item in completed}
    fallback_set = {item.fallback_reason for item in completed if item.fallback_reason}
    attempted: list[str] = []
    for item in completed:
        for backend in item.attempted_backends:
            if backend not in attempted:
                attempted.append(backend)

    return {
        "translation_mode": "auto" if len(backend_set) > 1 else completed[0].requested_mode,
        "translation_backend": "mixed" if len(backend_set) > 1 else completed[0].backend,
        "translation_version": "mixed" if len(version_set) > 1 else completed[0].version,
        "translation_fallback_reason": "mixed" if len(fallback_set) > 1 else (next(iter(fallback_set)) if fallback_set else None),
        "translation_attempted_backends": attempted,
    }


async def chunk_and_index(transcript_data: dict, filename: str, file_metadata: dict, dataset_id: str = "") -> dict:
    """Main entry: chunk transcript -> translate if needed -> embed -> upsert to configured vector DB."""
    words = transcript_data.get("words", [])
    raw_text = transcript_data.get("transcript", "")

    raw_chunks = _chunk_by_time_window(words) if words else _fallback_chunk(raw_text)
    if not raw_chunks:
        return {
            "chunks_created": 0,
            "translated_transcript": None,
            "translation_mode": None,
            "translation_backend": None,
            "translation_version": None,
            "translation_fallback_reason": None,
            "translation_attempted_backends": None,
        }

    source_lang = _normalize_language_code(file_metadata.get("language_code", "en"))
    needs_translation = source_lang != "en"
    outcomes: list[TranslationOutcome | None] = []
    translated_chunks: list[str] = []

    if needs_translation:
        outcomes = _translate_chunks_parallel(raw_chunks, source_lang=source_lang, target_lang="en")
        if not any(item is not None for item in outcomes):
            raise RuntimeError("All translation backends failed; indexing paused for retry")
        translated_chunks = [item.text if item is not None else "" for item in outcomes]
    else:
        outcomes = [None] * len(raw_chunks)
        translated_chunks = ["" for _ in raw_chunks]

    provenance = _summarize_provenance(outcomes)
    stem = filename.rsplit(".", 1)[0]
    records = []

    texts = []
    for chunk, translated in zip(raw_chunks, translated_chunks):
        if translated.strip():
            texts.append(f"{chunk['text']} | {translated.strip()}")
        else:
            texts.append(chunk["text"])

    try:
        vectors, embedding_backend = await embed_texts(texts)
    except Exception as exc:
        log.warning("audio_indexing_skipped", file=filename, reason=str(exc))
        vectors = []
        embedding_backend = None

    for i, (chunk, vec, translated, outcome) in enumerate(zip(raw_chunks, vectors, translated_chunks, outcomes)):
        chunk_id = f"audio_{stem}_{uuid.uuid4().hex[:8]}_{i:04d}"
        record_metadata = {
            "source_type": "audio",
            "source": file_metadata.get("source") or stem,
            "source_title": file_metadata.get("source_title") or file_metadata.get("description", stem),
            "citation": f"Audio: {file_metadata.get('description', stem)}",
            "section": file_metadata.get("section") or "",
            "language": file_metadata.get("language_code", "hi-IN"),
            "start_time_sec": chunk.get("start") if chunk.get("start") is not None else "",
            "end_time_sec": chunk.get("end") if chunk.get("end") is not None else "",
            "speaker_type": chunk.get("speaker") or "",
            "word_count": chunk.get("word_count") or len(chunk["text"].split()),
            "text_preview": chunk["text"][:300],
            "translated_text_preview": translated[:300] if translated.strip() else "",
            "has_shloka": chunk["has_shloka"],
        }
        if dataset_id:
            record_metadata["dataset_id"] = dataset_id
        upsert_chunk(
            chunk_id,
            text=chunk["text"],
            translated_text=translated.strip(),
            metadata=record_metadata,
        )
        records.append(
            {
                "id": chunk_id,
                "values": vec,
                "metadata": record_metadata,
            }
        )

    vector_db = settings.vector_db_backend.lower()
    if vector_db != "pinecone":
        raise RuntimeError("Pinecone is required for vector indexing")

    upserted = 0
    if records:
        batch_size = 100
        index = get_pinecone().Index(settings.pinecone_index_name)
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            index.upsert(vectors=batch)
            upserted += len(batch)

    translated_transcript = "\n".join(piece for piece in translated_chunks if piece.strip()) if needs_translation else None
    log.info(
        "audio_indexed",
        file=filename,
        chunks=len(raw_chunks),
        vector_db=vector_db,
        vectors=upserted,
        translation_backend=provenance["translation_backend"],
        translation_version=provenance["translation_version"],
    )
    return {
        "chunks_created": len(raw_chunks),
        "translated_transcript": translated_transcript,
        "translation_mode": provenance["translation_mode"],
        "translation_backend": provenance["translation_backend"],
        "translation_version": provenance["translation_version"],
        "translation_fallback_reason": provenance["translation_fallback_reason"],
        "translation_attempted_backends": provenance["translation_attempted_backends"],
        "vector_db": vector_db,
        "vectors_upserted": upserted,
        "embedding_backend": embedding_backend,
    }
