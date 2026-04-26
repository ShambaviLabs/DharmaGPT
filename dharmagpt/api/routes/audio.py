import json
import os
import tempfile
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from models.schemas import AudioTranscribeResponse
from core.config import get_settings
from pipelines.audio_chunker import chunk_and_index
from utils.naming import canonical_jsonl_filename, normalize_language_tag, part_number_from_filename, source_stem_from_audio_filename

router = APIRouter()
log = structlog.get_logger()
settings = get_settings()

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "processed"
TRANSCRIPT_DIR = PROCESSED_DIR / "audio_transcript"

_MIME_MAP = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac", ".opus": "audio/opus",
}
_LANG_SHORT = {
    "te-in": "te", "hi-in": "hi", "sa-in": "sa", "en-in": "en", "en-us": "en",
}


# ── STT backends ──────────────────────────────────────────────────────────────

async def _transcribe_with_sarvam(audio_bytes: bytes, filename: str, language_code: str, suffix: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": settings.sarvam_api_key},
            files={"file": (filename, audio_bytes, _MIME_MAP.get(suffix, "audio/mpeg"))},
            data={"model": "saaras:v3", "language_code": language_code, "with_timestamps": "true"},
        )
        response.raise_for_status()
        return response.json()


async def _transcribe_with_claude(audio_bytes: bytes, filename: str, language_code: str, suffix: str) -> dict:
    import base64
    audio_b64 = base64.standard_b64encode(audio_bytes).decode()
    media_type = _MIME_MAP.get(suffix, "audio/mpeg")
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "audio-1",
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": 4096,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "source": {"type": "base64", "media_type": media_type, "data": audio_b64},
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Transcribe this {language_code} audio exactly as spoken. "
                                "Return only the transcription text, nothing else."
                            ),
                        },
                    ],
                }],
            },
        )
        response.raise_for_status()
        data = response.json()
    transcript = data["content"][0]["text"].strip()
    return {"transcript": transcript, "words": []}


_indicwhisper_pipeline_cache: dict = {}

def _transcribe_with_indicwhisper(audio_bytes: bytes, filename: str, language_code: str, suffix: str) -> dict:
    from transformers import pipeline as hf_pipeline

    model_name = settings.indicwhisper_model
    if model_name not in _indicwhisper_pipeline_cache:
        log.info("indicwhisper_loading_model", model=model_name)
        _indicwhisper_pipeline_cache[model_name] = hf_pipeline(
            "automatic-speech-recognition",
            model=model_name,
            return_timestamps="word",
        )
    pipe = _indicwhisper_pipeline_cache[model_name]

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        result = pipe(tmp_path)
    finally:
        os.unlink(tmp_path)

    transcript = (result.get("text") or "").strip()
    words = []
    for chunk in result.get("chunks", []):
        ts = chunk.get("timestamp") or (None, None)
        words.append({"word": chunk["text"].strip(), "start": ts[0] or 0.0, "end": ts[1] or 0.0})
    return {"transcript": transcript, "words": words}


# ── Fallback chain ────────────────────────────────────────────────────────────

_AUTO_ORDER = ["sarvam", "claude", "indicwhisper"]


def _stt_backends() -> dict:
    return {
        "sarvam":       ("sarvam_stt",        "saaras:v3",                   "async", _transcribe_with_sarvam),
        "claude":       ("claude_stt",         settings.anthropic_model,      "async", _transcribe_with_claude),
        "indicwhisper": ("indicwhisper_local", settings.indicwhisper_model,   "sync",  _transcribe_with_indicwhisper),
    }


async def _transcribe_audio(audio_bytes: bytes, filename: str, language_code: str, suffix: str) -> tuple[dict, str, str]:
    """Returns (transcript_data, transcription_mode, transcription_version).

    STT_BACKEND in .env controls behaviour:
      "sarvam"       — Sarvam only, no fallback
      "claude"       — Claude API only
      "indicwhisper" — local IndicWhisper only
      "auto"         — tries Sarvam → Claude → IndicWhisper, stops at first success
    """
    import asyncio

    backend = settings.stt_backend.lower()
    backends = _stt_backends()

    if backend in backends:
        mode_label, version_label, call_type, fn = backends[backend]
        if call_type == "sync":
            data = await asyncio.to_thread(fn, audio_bytes, filename, language_code, suffix)
        else:
            data = await fn(audio_bytes, filename, language_code, suffix)
        return data, mode_label, version_label

    # "auto" — try each backend in order, fall back on any error
    last_exc: Exception | None = None
    for key in _AUTO_ORDER:
        mode_label, version_label, call_type, fn = backends[key]
        try:
            if call_type == "sync":
                data = await asyncio.to_thread(fn, audio_bytes, filename, language_code, suffix)
            else:
                data = await fn(audio_bytes, filename, language_code, suffix)
            if last_exc:
                log.info("stt_fallback_succeeded", backend=key, previous_error=str(last_exc))
            return data, mode_label, version_label
        except Exception as exc:
            log.warning("stt_backend_failed", backend=key, error=str(exc))
            last_exc = exc

    raise last_exc or RuntimeError("All STT backends failed")


@router.post("/transcribe", response_model=AudioTranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language_code: str = Form("hi-IN"),
    section: str = Form(None),
    description: str = Form(None),
) -> AudioTranscribeResponse:
    """
    Upload a Sanskrit/Hindi audio file (chanting, pravachanam, discourse).
    STT backend is controlled by STT_BACKEND in .env: "sarvam" | "whisper" | "auto".
    """
    suffix = "." + (file.filename or "").split(".")[-1].lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {SUPPORTED_FORMATS}")

    audio_bytes = await file.read()
    if len(audio_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 100MB.")

    log.info("audio_transcribe_start", file=file.filename, lang=language_code, size_mb=round(len(audio_bytes)/1e6, 2), stt_backend=settings.stt_backend)

    try:
        transcript_data, transcription_mode, transcription_version = await _transcribe_audio(
            audio_bytes, file.filename, language_code, suffix
        )
    except Exception as e:
        log.error("stt_error", error=str(e), stt_backend=settings.stt_backend)
        raise HTTPException(status_code=502, detail="Audio transcription service unavailable.")

    transcript_text = transcript_data.get("transcript", "")
    if not transcript_text:
        raise HTTPException(status_code=422, detail="No speech detected in audio file.")

    # Chunk and index
    file_metadata = {
        "language_code": language_code,
        "section": section,
        "description": description or file.filename,
        "transcription_mode": transcription_mode,
        "transcription_version": transcription_version,
        "text_source": "Valmiki Ramayana",
        "source_file": file.filename,
    }
    chunk_result = await chunk_and_index(transcript_data, file.filename, file_metadata)

    transcript_language = normalize_language_tag(language_code)
    transcript_base = source_stem_from_audio_filename(file.filename, language=transcript_language)
    transcript_part = part_number_from_filename(file.filename)
    transcript_file_name = canonical_jsonl_filename(
        transcript_base,
        language=transcript_language,
        kind="transcript",
        part=transcript_part,
    )
    transcript_path = TRANSCRIPT_DIR / transcript_base / transcript_file_name
    transcript_record = {
        "id": transcript_path.stem,
        "text": transcript_text,
        "text_en": chunk_result.get("translated_transcript"),
        "source": transcript_base,
        "section": section,
        "citation": f"Audio transcription: {description or file.filename}",
        "language": transcript_language,
        "source_type": "audio_transcript",
        "tags": ["shloka"] if "॥" in transcript_text or "।" in transcript_text else ["story"],
        "topics": [],
        "characters": [],
        "is_shloka": "॥" in transcript_text or "।" in transcript_text,
        "url": "",
        "notes": f"Transcribed from {file.filename}",
        "source_file": file.filename,
        "description": description or file.filename,
        "transcription_mode": transcription_mode,
        "transcription_version": transcription_version,
        "translation_mode": chunk_result.get("translation_mode"),
        "translation_backend": chunk_result.get("translation_backend"),
        "translation_version": chunk_result.get("translation_version"),
        "translation_fallback_reason": chunk_result.get("translation_fallback_reason"),
        "translation_attempted_backends": chunk_result.get("translation_attempted_backends") or [],
        "chunks_created": chunk_result["chunks_created"],
    }

    try:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        with transcript_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(transcript_record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.error("audio_transcript_save_failed", file=file.filename, path=str(transcript_path), error=str(exc))
        raise HTTPException(status_code=500, detail="Transcript artifact could not be saved.")

    log.info(
        "audio_transcribe_done",
        file=file.filename,
        chunks=chunk_result["chunks_created"],
        translation_backend=chunk_result.get("translation_backend"),
        translation_version=chunk_result.get("translation_version"),
        transcript_file=transcript_file_name,
    )

    return AudioTranscribeResponse(
        transcript=transcript_text,
        translated_transcript=chunk_result.get("translated_transcript"),
        chunks_created=chunk_result["chunks_created"],
        file_name=file.filename,
        transcript_file_name=transcript_file_name,
        translation_mode=chunk_result.get("translation_mode"),
        translation_backend=chunk_result.get("translation_backend"),
        translation_version=chunk_result.get("translation_version"),
        translation_fallback_reason=chunk_result.get("translation_fallback_reason"),
    )
