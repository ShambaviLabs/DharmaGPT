"""
test_full_query_pipeline.py - offline integration tests for the DharmaGPT pipeline.

Each test exercises the full path:
  user query -> local corpus retrieval -> Ollama answer generation -> local judge scoring

No external API calls are made. The suite uses:
  - a local seed corpus from knowledge/processed/seed_corpus.jsonl
  - local retrieval logic for source selection
  - a local Ollama model for answer generation and scoring
"""

from __future__ import annotations

import json

import pytest

from core.rag_engine import answer
from evaluation.response_scorer import METRIC_WEIGHTS, validate_response
from models.schemas import QueryMode, QueryRequest

from .local_pipeline import ollama_config


async def _run(query: str, mode: QueryMode, *, filter_section: str | None = None):
    request = QueryRequest(query=query, mode=mode, filter_section=filter_section)
    response = await answer(request)
    result = validate_response(query, response, judge_config=ollama_config())
    return response, result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guidance_query_returns_scored_response(offline_pipeline):
    query = "How should I deal with anger and frustration in daily life?"
    response, result = await _run(query, QueryMode.guidance)

    assert response.answer
    assert response.sources
    assert response.query_id

    assert 0.0 <= result.faithfulness.score <= 1.0
    assert 0.0 <= result.answer_relevance.score <= 1.0
    assert 0.0 <= result.context_utilization.score <= 1.0
    assert 0.0 <= result.citation_precision.score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0
    assert result.retrieval.source_count > 0
    assert result.retrieval.score_mean > 0.0
    assert result.faithfulness.reasoning
    assert result.answer_relevance.reasoning
    assert result.context_utilization.reasoning
    assert result.citation_precision.reasoning

    serialized = json.dumps(result.to_dict())
    parsed = json.loads(serialized)
    assert parsed["overall_score"] >= 0.0

    expected = (
        METRIC_WEIGHTS["faithfulness"] * result.faithfulness.score
        + METRIC_WEIGHTS["answer_relevance"] * result.answer_relevance.score
        + METRIC_WEIGHTS["context_utilization"] * result.context_utilization.score
        + METRIC_WEIGHTS["citation_precision"] * result.citation_precision.score
    )
    assert abs(result.overall_score - expected) < 0.001


@pytest.mark.integration
@pytest.mark.asyncio
async def test_story_query_returns_scored_response(offline_pipeline):
    query = "Tell me the story of Hanuman crossing the ocean to reach Lanka."
    response, result = await _run(query, QueryMode.story, filter_section="Sundara Kanda")

    assert response.answer
    assert result.overall_score >= 0.0
    assert result.mode == "story"
    assert response.sources
    for source in response.sources:
        assert source.text.strip()
        assert source.citation.strip()
        assert 0.0 < source.score <= 1.0
        if source.section:
            assert source.section == "Sundara Kanda"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_children_query_returns_scored_response(offline_pipeline):
    query = "Tell me about Hanuman's bravery in a way a young child would enjoy."
    response, result = await _run(query, QueryMode.children)

    assert response.answer
    assert result.mode == "children"
    assert 0.0 <= result.overall_score <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scholar_query_returns_scored_response(offline_pipeline):
    query = "What does the Valmiki Ramayana say about the qualities of an ideal king?"
    response, result = await _run(query, QueryMode.scholar)

    assert response.answer
    assert result.mode == "scholar"
    assert 0.0 <= result.overall_score <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_section_filter_scopes_retrieval(offline_pipeline):
    request = QueryRequest(query="Describe the search for Sita.", mode=QueryMode.story, filter_section="Sundara Kanda")
    response = await answer(request)

    assert response.sources
    for source in response.sources:
        if source.section:
            assert source.section == "Sundara Kanda"
