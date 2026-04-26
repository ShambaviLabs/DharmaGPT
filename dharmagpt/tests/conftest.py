"""
conftest.py — shared pytest fixtures for all test suites.

Unit tests import from this file for lightweight helpers.
Integration tests use the fixtures in tests/integration/conftest.py
which build on top of these.
"""

import pytest
from models.schemas import QueryMode, QueryRequest, SourceChunk


@pytest.fixture
def sample_source():
    return SourceChunk(
        text="Hanuman leapt across the ocean with the strength of devotion.",
        citation="Valmiki Ramayana",
        kanda="Sundara Kanda",
        sarga=1,
        score=0.88,
        source_type="text",
    )


@pytest.fixture
def sample_sources(sample_source):
    return [
        sample_source,
        SourceChunk(
            text="Rama stood firm in dharma even in exile.",
            citation="Valmiki Ramayana",
            kanda="Ayodhya Kanda",
            sarga=20,
            score=0.76,
            source_type="text",
        ),
        SourceChunk(
            text="Sita endured with grace, her faith in Rama unwavering.",
            citation="Valmiki Ramayana",
            kanda="Sundara Kanda",
            sarga=15,
            score=0.71,
            source_type="text",
        ),
    ]


@pytest.fixture
def guidance_request():
    return QueryRequest(
        query="How should I deal with anger and frustration in daily life?",
        mode=QueryMode.guidance,
    )


@pytest.fixture
def story_request():
    return QueryRequest(
        query="Tell me the story of Hanuman crossing the ocean to reach Lanka.",
        mode=QueryMode.story,
    )
