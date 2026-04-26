"""
test_rag_pipeline.py — unit tests for the RAG-adjacent data flow.

These tests focus on compatibility between translation, ingestion, and
retrieval so corpus content keeps its provenance and stays usable by the
query-time RAG path.
"""

from __future__ import annotations

from core.retrieval import _source_text_from_metadata
from core.translation import TranslationBackend, TranslationConfig, TranslationOutcome
from scripts.ingest_to_pinecone import build_embed_text, build_metadata
from scripts.translate_corpus import _translate_record


def test_source_text_prefers_full_text_and_translation_for_non_english():
    meta = {
        "text": "मूल पाठ",
        "text_en": "English translation",
        "language": "te",
        "source_type": "text",
    }

    text = _source_text_from_metadata(meta)

    assert "मूल पाठ" in text
    assert "English translation" in text


def test_source_text_falls_back_to_preview_when_full_text_missing():
    meta = {
        "text_preview": "preview only",
        "citation": "Valmiki Ramayana",
    }

    assert _source_text_from_metadata(meta) == "preview only"


def test_build_embed_text_uses_text_en_model_fallback():
    record = {
        "text": "తెలుగు మూలం",
        "text_te": "తెలుగు మూలం",
        "text_en_model": "English gloss",
        "language": "te",
        "citation": "Valmiki Ramayana",
    }

    embed_text = build_embed_text(record)

    assert "తెలుగు మూలం" in embed_text
    assert "English gloss" in embed_text
    assert "Valmiki Ramayana" in embed_text


def test_build_metadata_carries_full_text_and_translation():
    record = {
        "text": "Full corpus text",
        "text_en_model": "English corpus text",
        "source": "valmiki_ramayana",
        "citation": "Valmiki Ramayana, Sundara Kanda, Sarga 15",
        "language": "te",
        "source_type": "text",
        "tags": ["devotion"],
        "characters": ["Hanuman"],
        "topics": ["courage"],
        "is_shloka": True,
        "text_te": "మూల పాఠ్యం",
    }

    meta = build_metadata(record, dataset_id="dataset-01")

    assert meta["text"] == "Full corpus text"
    assert meta["text_en"] == "English corpus text"
    assert meta["has_english"] is True
    assert meta["dataset_id"] == "dataset-01"


def test_translate_record_sets_compatibility_fields(monkeypatch):
    outcome = TranslationOutcome(
        text="English translation",
        requested_mode=TranslationBackend.auto.value,
        backend=TranslationBackend.anthropic.value,
        version="claude-test",
        source_lang="te",
        target_lang="en",
        attempted_backends=("anthropic",),
        fallback_reason=None,
    )

    monkeypatch.setattr(
        "scripts.translate_corpus.translate_text",
        lambda *args, **kwargs: outcome,
    )

    record, changed = _translate_record(
        {"text": "మూల పాఠ్యం", "language": "te"},
        config=TranslationConfig(backend=TranslationBackend.auto),
        force=False,
    )

    assert changed is True
    assert record["text_en_model"] == "English translation"
    assert record["text_en"] == "English translation"
    assert record["translation_backend"] == "anthropic"
    assert record["translation_version"] == "claude-test"

