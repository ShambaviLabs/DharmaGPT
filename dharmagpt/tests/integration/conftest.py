"""Shared fixtures for the offline integration suite."""

from __future__ import annotations

import pytest

from .local_pipeline import ollama_available


def pytest_collection_modifyitems(config, items):
    """Skip offline integration tests when the local Ollama service is unavailable."""
    if ollama_available():
        return

    skip = pytest.mark.skip(reason="Integration tests require local Ollama with the configured model")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture()
def offline_pipeline(monkeypatch):
    """Patch the RAG path so integration tests use local retrieval + local Ollama."""
    from .local_pipeline import local_call_llm_async, local_retrieve

    monkeypatch.setattr("core.rag_engine.retrieve", local_retrieve)
    monkeypatch.setattr("core.rag_engine._call_llm", local_call_llm_async)
