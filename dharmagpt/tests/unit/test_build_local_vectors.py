from __future__ import annotations

import json
from pathlib import Path

from scripts import build_local_vectors as blv


def test_best_embed_text_prefers_english_over_model_and_source() -> None:
    record = {
        "text": "original text",
        "text_en_model": "model english",
        "text_en": "human english",
    }

    assert blv.best_embed_text(record) == "human english"


def test_discover_files_filters_by_path_component(tmp_path, monkeypatch) -> None:
    processed = tmp_path / "processed"
    text_dir = processed / "text"
    audio_dir = processed / "audio_transcript" / "festival"
    text_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)

    (text_dir / "a.jsonl").write_text(json.dumps({"id": "1"}) + "\n", encoding="utf-8")
    (audio_dir / "b.jsonl").write_text(json.dumps({"id": "2"}) + "\n", encoding="utf-8")

    monkeypatch.setattr(blv, "PROCESSED_DIR", processed)

    all_files = blv.discover_files(None)
    text_files = blv.discover_files("text")
    audio_files = blv.discover_files("audio_transcript")

    assert {f.name for f in all_files} == {"a.jsonl", "b.jsonl"}
    assert [f.name for f in text_files] == ["a.jsonl"]
    assert [f.name for f in audio_files] == ["b.jsonl"]


def test_build_metadata_includes_translation_and_preview_fields() -> None:
    record = {
        "text": "original text",
        "text_en_model": "translated text",
        "source": "sample_source",
        "citation": "sample citation",
        "language": "te",
        "source_type": "audio_transcript",
        "tags": ["devotion"],
        "characters": ["Hanuman"],
        "topics": ["courage"],
        "is_shloka": True,
        "description": "audio clip",
        "speaker_type": "narrator",
        "source_file": "part01.mp3",
        "translation_backend": "sarvam",
        "transcription_mode": "manual",
        "verse_start": 7,
    }

    meta = blv.build_metadata(record)

    assert meta["text"] == "translated text"
    assert meta["text_en"] == "translated text"
    assert meta["text_preview"] == "original text"
    assert meta["text_en_preview"] == "translated text"
    assert meta["has_english"] is True
    assert meta["source_type"] == "audio_transcript"
    assert meta["topics"] == ["courage"]
    assert meta["verse_start"] == 7
