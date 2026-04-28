"""
smoke_test_audio.py — DharmaGPT end-to-end audio pipeline smoke test.

Runs each stage in sequence and prints exactly which API is called and what
the result looks like. Stops immediately on any failure.

Stages:
  1. ffmpeg trim          — local, free
  2. Sarvam STT           — sarvam_api_key         (~1 credit / 10s clip)
  3. Sarvam translate     — sarvam_api_key         (same request, parallel)
  4. Chunk by pause       — local, free
  5. Translate chunks     — sarvam_api_key         (1 credit per chunk)
  6. OpenAI embed         — openai_api_key         (~$0.0001 for a few chunks)
  7. Pinecone upsert      — pinecone_api_key       (writes to smoke_test namespace)
  8. Pinecone query       — pinecone_api_key       (1 query to verify retrieval)
  9. Claude RAG answer    — anthropic_api_key      (~$0.01 for one question)

Usage:
    python scripts/smoke_test_audio.py --file /path/to/audio.mp3
    python scripts/smoke_test_audio.py --file /path/to/audio.mp3 --duration 10
    python scripts/smoke_test_audio.py --file /path/to/audio.mp3 --language hi-IN
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import structlog

# Force UTF-8 stdout on Windows (avoids cp1252 UnicodeEncodeError with box chars / Indic text)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = structlog.get_logger()

SARVAM_STT_URL       = "https://api.sarvam.ai/speech-to-text"
SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"
_MIME_MAP = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".aac": "audio/aac",  ".ogg": "audio/ogg", ".flac": "audio/flac",
}

SMOKE_NAMESPACE = "smoke_test"
SMOKE_SECTION   = "smoke_test"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sep(title: str) -> None:
    width = 60
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _info(msg: str) -> None:
    print(f"     {msg}")


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — ffmpeg trim (local, free)
# ─────────────────────────────────────────────────────────────────────────────

def stage_trim(file_path: str, duration: int, offset: int) -> tuple[bytes, str]:
    _sep("Stage 1 — ffmpeg trim  [local, free]")
    _info(f"source   : {file_path}")
    _info(f"clip     : {duration}s starting at {offset}s")

    suffix = Path(file_path).suffix.lower() or ".mp3"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name

    cmd = [
        _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(offset), "-i", file_path,
        "-t", str(duration), "-c:a", "libmp3lame", "-q:a", "4", tmp_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:300]}")

    audio_bytes = Path(tmp_path).read_bytes()
    os.unlink(tmp_path)

    _ok(f"{len(audio_bytes) / 1024:.1f} KB clip ready")
    return audio_bytes, ".mp3"


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2+3 — Sarvam STT + translate (parallel)
#   API  : POST api.sarvam.ai/speech-to-text         (sarvam_api_key)
#   API  : POST api.sarvam.ai/speech-to-text-translate (sarvam_api_key)
#   Cost : ~1 Sarvam credit per call
# ─────────────────────────────────────────────────────────────────────────────

async def stage_stt(
    audio_bytes: bytes, filename: str, language_code: str, suffix: str, api_key: str
) -> tuple[dict, str | None]:
    import httpx

    _sep("Stage 2+3 — Sarvam STT + translate  [API: sarvam_api_key]")
    _info(f"model    : saaras:v3  language: {language_code}")
    _info(f"endpoint : {SARVAM_STT_URL}  (STT)")
    _info(f"endpoint : {SARVAM_TRANSLATE_URL}  (translate, parallel)")

    mime = _MIME_MAP.get(suffix, "audio/mpeg")

    async def _post_with_retry(url: str, files: dict, data: dict, retries: int = 3) -> httpx.Response:
        for attempt in range(1, retries + 1):
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(url, headers={"api-subscription-key": api_key}, files=files, data=data)
            if r.status_code == 429:
                wait = 60 * attempt  # 60s, 120s, 180s
                print(f"  ⏳  Sarvam rate limit (429) — waiting {wait}s before retry {attempt}/{retries}...")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"Sarvam API still rate-limited after {retries} retries")

    async def _stt():
        r = await _post_with_retry(
            SARVAM_STT_URL,
            files={"file": (filename, audio_bytes, mime)},
            data={"model": "saaras:v3", "language_code": language_code, "with_timestamps": "true"},
        )
        return r.json()

    async def _translate():
        try:
            r = await _post_with_retry(
                SARVAM_TRANSLATE_URL,
                files={"file": (filename, audio_bytes, mime)},
                data={"model": "saaras:v2.5"},
            )
            return (r.json().get("transcript") or "").strip() or None
        except Exception:
            return None  # translate is non-fatal

    stt_result, translate_result = await asyncio.gather(
        _stt(), _translate(), return_exceptions=True
    )

    if isinstance(stt_result, Exception):
        raise stt_result

    transcript = (stt_result.get("transcript") or "").strip()
    words      = stt_result.get("words") or []

    if not transcript:
        raise RuntimeError("Sarvam STT returned empty transcript — no speech detected in clip")

    _ok(f"STT transcript  : {len(transcript)} chars, {len(words)} word timestamps")
    _info(f"preview         : {transcript[:120]}")

    en_text: str | None = None
    if isinstance(translate_result, Exception):
        print(f"  ⚠  Sarvam translate failed (non-fatal): {translate_result}")
    else:
        en_text = translate_result
        if en_text:
            _ok(f"STT translate   : {len(en_text)} chars English")
            _info(f"preview         : {en_text[:120]}")

    return stt_result, en_text


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — chunk by pause (local, free)
# ─────────────────────────────────────────────────────────────────────────────

def stage_chunk(stt_data: dict) -> list[dict]:
    from pipelines.audio_chunker import _chunk_by_pause, _fallback_chunk

    _sep("Stage 4 — Chunk by pause  [local, free]")

    words      = stt_data.get("words") or []
    transcript = (stt_data.get("transcript") or "").strip()
    chunks     = _chunk_by_pause(words) if words else _fallback_chunk(transcript)

    _ok(f"{len(chunks)} chunks from {'word timestamps' if words else 'sentence boundaries'}")
    for i, c in enumerate(chunks[:4]):
        t0 = c.get("start") or 0.0
        t1 = c.get("end") or 0.0
        _info(f"[{i}] {t0:.1f}s-{t1:.1f}s  {c['speaker']:<22}  {c['text'][:70]}")
    if len(chunks) > 4:
        _info(f"... +{len(chunks)-4} more chunks")

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Stage 5 — translate chunks
#   API  : POST api.sarvam.ai/translate   (sarvam_api_key)
#          — or Anthropic if TRANSLATION_BACKEND=anthropic
#   Cost : ~1 Sarvam credit per chunk (text translate, not audio)
#   Skip : if Sarvam STT already returned English in stage 3
# ─────────────────────────────────────────────────────────────────────────────

def stage_translate_chunks(
    chunks: list[dict], en_text: str | None, language_code: str, settings
) -> list[str | None]:
    from pipelines.audio_chunker import _translate_chunks_parallel

    source_lang = language_code.split("-")[0].lower()
    needs_translation = not source_lang.startswith("en")

    _sep("Stage 5 — Translate chunks")

    if not needs_translation:
        _ok("Source language is English — skipping translation")
        return [None] * len(chunks)

    if en_text:
        _ok(f"Reusing Sarvam STT translate result from Stage 3 — 0 extra API calls")
        _info(f"broadcast same translation to all {len(chunks)} chunks")
        return [en_text] * len(chunks)

    _info(f"API  : {settings.translation_backend} translate  (sarvam_api_key or anthropic_api_key)")
    _info(f"calls: {len(chunks)} chunk(s) via ThreadPoolExecutor")

    translated = _translate_chunks_parallel(chunks, source_lang=source_lang, target_lang="en")
    done = sum(1 for t in translated if t)
    _ok(f"{done}/{len(chunks)} chunks translated via {settings.translation_backend}")
    for i, t in enumerate(translated[:3]):
        if t:
            _info(f"[{i}] {t[:80]}")
    return translated


# ─────────────────────────────────────────────────────────────────────────────
# Stage 6 — OpenAI embed
#   API  : POST api.openai.com/v1/embeddings  (openai_api_key)
#   Model: text-embedding-3-large  (3072 dims)
#   Cost : ~$0.00013 per 1K tokens  (a few chunks is < $0.001)
# ─────────────────────────────────────────────────────────────────────────────

def stage_embed(chunks: list[dict], translated: list[str | None], settings) -> list[list[float]]:
    from core.backends.embedding import get_embedder
    from core.retrieval import embed_texts_local

    _sep("Stage 6 — OpenAI embed  [API: openai_api_key]")
    _info(f"model    : {settings.embedding_model}  dims={settings.embedding_dims}")
    _info(f"endpoint : https://api.openai.com/v1/embeddings")
    _info(f"inputs   : {len(chunks)} texts  (original + translation concatenated)")

    texts = [
        f"{c['text']} | {t.strip()}" if t and t.strip() else c["text"]
        for c, t in zip(chunks, translated)
    ]

    try:
        embedder = get_embedder()
        vectors  = embedder.embed_documents(texts)
        _ok(f"{len(vectors)} vectors  dim={len(vectors[0])}  [openai]")
        _info(f"sample[0] first 5 dims: {[round(x, 4) for x in vectors[0][:5]]}")
    except Exception as exc:
        if "insufficient_quota" in str(exc) or "quota" in str(exc).lower() or "429" in str(exc):
            print(f"  ⚠  OpenAI quota exceeded — falling back to local_hash embeddings for smoke test")
            print(f"     (Add billing at platform.openai.com/account/billing for real embeddings)")
            from core.backends.embedding import LocalHashEmbeddings
            hasher = LocalHashEmbeddings(dims=settings.embedding_dims)
            vectors = hasher.embed_documents(texts)
            _ok(f"{len(vectors)} vectors  dim={len(vectors[0])}  [local_hash — structural test only]")
        else:
            raise

    return vectors


# ─────────────────────────────────────────────────────────────────────────────
# Stage 7 — Pinecone upsert
#   API  : POST {pinecone_host}/vectors/upsert  (pinecone_api_key)
#   Cost : counts toward your Pinecone write units
#   Note : vectors written to metadata section="smoke_test" for easy cleanup
# ─────────────────────────────────────────────────────────────────────────────

def stage_upsert(
    chunks: list[dict], vectors: list[list[float]], translated: list[str | None],
    filename: str, language_code: str, settings
) -> list[str]:
    from core.retrieval import get_pinecone

    _sep("Stage 7 — Pinecone upsert  [API: pinecone_api_key]")
    _info(f"index    : {settings.pinecone_index_name}")
    _info(f"section  : {SMOKE_SECTION}  (safe to delete after test)")
    _info(f"vectors  : {len(vectors)}")

    records = []
    ids = []
    for i, (chunk, vec, en) in enumerate(zip(chunks, vectors, translated)):
        vid = f"smoke_{uuid.uuid4().hex[:8]}_{i:04d}"
        ids.append(vid)
        records.append({
            "id": vid,
            "values": vec,
            "metadata": {
                "text":           chunk["text"],
                "text_en":        en or "",
                "source":         filename,
                "source_type":    "audio",
                "speaker":        chunk["speaker"],
                "start_time_sec": chunk.get("start") or 0,
                "end_time_sec":   chunk.get("end") or 0,
                "section":        SMOKE_SECTION,
                "language":       language_code.split("-")[0].lower(),
            },
        })

    pc    = get_pinecone()
    index = pc.Index(settings.pinecone_index_name)
    index.upsert(vectors=records)

    _ok(f"Upserted {len(records)} vectors")
    _info(f"IDs: {ids[:3]}{'...' if len(ids) > 3 else ''}")
    return ids


# ─────────────────────────────────────────────────────────────────────────────
# Stage 8 — Pinecone query (retrieval check)
#   API  : POST {pinecone_host}/query  (pinecone_api_key)
#   Cost : counts toward your Pinecone read units
# ─────────────────────────────────────────────────────────────────────────────

def stage_query(vectors: list[list[float]], settings) -> list[dict]:
    from core.retrieval import get_pinecone

    _sep("Stage 8 — Pinecone query  [API: pinecone_api_key]")
    _info(f"query    : first chunk vector  top_k=3")
    _info(f"filter   : section={SMOKE_SECTION}")

    pc     = get_pinecone()
    index  = pc.Index(settings.pinecone_index_name)
    result = index.query(
        vector=vectors[0], top_k=3, include_metadata=True,
        filter={"section": {"$eq": SMOKE_SECTION}},
    )
    hits = result.get("matches") or []

    _ok(f"{len(hits)} hits returned")
    for h in hits:
        meta = h.get("metadata") or {}
        _info(f"score={h.get('score', 0):.4f}  {meta.get('text', '')[:80]}")

    if not hits:
        raise RuntimeError("Pinecone query returned 0 results — upsert may have not propagated yet")

    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Stage 9 — Claude RAG answer
#   API  : POST api.anthropic.com/v1/messages  (anthropic_api_key)
#   Model: claude-sonnet-4-20250514
#   Cost : ~$0.003 input + $0.015 output per 1K tokens  (~$0.01 for one question)
# ─────────────────────────────────────────────────────────────────────────────

def stage_rag_answer(hits: list[dict], settings) -> str:
    from anthropic import Anthropic

    _sep("Stage 9 — Claude RAG answer  [API: anthropic_api_key]")

    question = "Who is Rama and what is his significance?"
    context  = "\n\n".join(
        (h.get("metadata") or {}).get("text_en") or (h.get("metadata") or {}).get("text", "")
        for h in hits
    ).strip()

    _info(f"model    : {settings.anthropic_model}")
    _info(f"endpoint : https://api.anthropic.com/v1/messages")
    _info(f"question : {question}")
    _info(f"context  : {len(context)} chars from {len(hits)} retrieved chunks")

    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": (
                f"You are DharmaGPT, a guide grounded in Hindu sacred texts.\n\n"
                f"Context from the corpus:\n{context}\n\n"
                f"Question: {question}\n\n"
                f"Answer concisely based only on the context above."
            ),
        }],
    )
    answer = msg.content[0].text.strip()

    _ok(f"Answer ({len(answer)} chars)")
    for line in answer.splitlines():
        _info(line)

    return answer


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup helper
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_smoke_vectors(ids: list[str], settings) -> None:
    from core.retrieval import get_pinecone
    pc    = get_pinecone()
    index = pc.Index(settings.pinecone_index_name)
    index.delete(ids=ids)
    _ok(f"Cleaned up {len(ids)} smoke test vectors from Pinecone")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def run(args) -> None:
    from core.config import get_settings
    settings = get_settings()

    print("\n" + "═" * 60)
    print("  DharmaGPT — End-to-End Audio Pipeline Smoke Test")
    print("═" * 60)
    print(f"  file       : {args.file}")
    print(f"  clip       : {args.duration}s  offset={args.offset}s")
    print(f"  language   : {args.language}")
    print(f"  backends   : stt=sarvam | translation={settings.translation_backend} "
          f"| embedding={settings.embedding_backend} | rag={settings.rag_backend}")
    print(f"  pinecone   : {settings.pinecone_index_name}")
    print(f"  cleanup    : {'yes' if not args.keep else 'no (--keep)'}")

    filename = Path(args.file).name
    upserted_ids: list[str] = []

    try:
        # 1. trim
        audio_bytes, suffix = stage_trim(args.file, args.duration, args.offset)

        if args.skip_stt:
            # Use cached stub data so stages 6-9 can be tested without hitting Sarvam
            _sep("Stage 2+3 — Sarvam STT  [SKIPPED — using stub data]")
            print("  ⚠  --skip-stt: using stub transcript to test embed/Pinecone/Claude stages")
            stt_data = {"transcript": "రామ రామ జయ రాజా రామ సీతారాం", "words": []}
            en_text = "Rama Rama Jaya Raja Rama Sitaram — divine chant from the Ramayana"
            _ok("Stub transcript ready")
        else:
            # 2+3. STT + translate
            stt_data, en_text = await stage_stt(
                audio_bytes, filename, args.language, suffix, settings.sarvam_api_key
            )

        # 4. chunk
        chunks = stage_chunk(stt_data)

        # 5. translate chunks
        translated = stage_translate_chunks(chunks, en_text, args.language, settings)

        # 6. embed
        vectors = stage_embed(chunks, translated, settings)

        # 7. upsert
        upserted_ids = stage_upsert(chunks, vectors, translated, filename, args.language, settings)

        # 8. query
        hits = stage_query(vectors, settings)

        # 9. RAG answer
        stage_rag_answer(hits, settings)

    finally:
        if upserted_ids and not args.keep:
            _sep("Cleanup")
            cleanup_smoke_vectors(upserted_ids, settings)

    print("\n" + "═" * 60)
    print("  ALL STAGES PASSED")
    print("═" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="DharmaGPT end-to-end audio pipeline smoke test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file",     required=True, help="Path to audio file (mp3/wav/m4a)")
    parser.add_argument("--skip-stt", action="store_true", help="Skip Sarvam STT (use stub) to test stages 6-9 without hitting the API")
    parser.add_argument("--duration", type=int, default=10,    help="Clip length in seconds (default: 10)")
    parser.add_argument("--offset",   type=int, default=0,     help="Start offset in seconds (default: 0)")
    parser.add_argument("--language", default="te-IN",         help="Sarvam language code (default: te-IN)")
    parser.add_argument("--keep",     action="store_true",     help="Keep smoke test vectors in Pinecone after test")
    args = parser.parse_args()

    if not Path(args.file).exists():
        raise SystemExit(f"File not found: {args.file}")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
