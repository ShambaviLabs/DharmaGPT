import json
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


@router.post("/transcribe", response_model=AudioTranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language_code: str = Form("hi-IN"),
    kanda: str = Form(None),
    description: str = Form(None),
) -> AudioTranscribeResponse:
    """
    Upload a Sanskrit/Hindi audio file (chanting, pravachanam, discourse).
    Transcribes via Sarvam Saaras v3, chunks intelligently, indexes to Pinecone.
    """
    suffix = "." + (file.filename or "").split(".")[-1].lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported format. Use: {SUPPORTED_FORMATS}")

    audio_bytes = await file.read()
    if len(audio_bytes) > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(status_code=413, detail="File too large. Max 100MB.")

    log.info("audio_transcribe_start", file=file.filename, lang=language_code, size_mb=round(len(audio_bytes)/1e6, 2))

    # Call Sarvam STT
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                SARVAM_STT_URL,
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": (file.filename, audio_bytes, f"audio/{suffix.lstrip('.')}")},
                data={
                    "model": "saaras:v3",
                    "language_code": language_code,
                    "with_timestamps": "true",
                },
            )
            response.raise_for_status()
            transcript_data = response.json()
    except httpx.HTTPError as e:
        log.error("sarvam_stt_error", error=str(e))
        raise HTTPException(status_code=502, detail="Audio transcription service unavailable.")

    transcript_text = transcript_data.get("transcript", "")
    if not transcript_text:
        raise HTTPException(status_code=422, detail="No speech detected in audio file.")

    # Chunk and index
    file_metadata = {
        "language_code": language_code,
        "kanda": kanda,
        "description": description or file.filename,
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
        "kanda": kanda,
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
        "transcription_mode": chunk_result.get("transcription_mode") or "sarvam_stt",
        "transcription_version": chunk_result.get("transcription_version") or "saaras:v3",
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
