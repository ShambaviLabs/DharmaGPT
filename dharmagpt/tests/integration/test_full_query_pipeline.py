"""
test_full_query_pipeline.py — integration tests for the complete DharmaGPT pipeline.

Each test exercises the full path:
  user query → embed → Pinecone retrieve → Claude generate → LLM judge score

This is the primary integration suite. If these pass, the system is working
end-to-end for real users across all four query modes.

Requires: ANTHROPIC_API_KEY, OPENAI_API_KEY, PINECONE_API_KEY
Run with: pytest tests/integration/ -v --timeout=120
"""

import pytest

from core.rag_engine import answer
from evaluation.response_scorer import validate_response
from models.schemas import QueryMode, QueryRequest


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _run(query: str, mode: QueryMode):
    """Generate a response and score it — the full pipeline in one call."""
    request = QueryRequest(query=query, mode=mode)
    response = await answer(request)
    result = validate_response(query, response)
    return response, result


# ─── Full pipeline: each query mode ───────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guidance_query_returns_scored_response():
    """User asks a life guidance question — response + metrics both returned."""
    query = "How should I deal with anger and frustration in daily life?"
    response, result = await _run(query, QueryMode.guidance)

    assert response.answer, "Answer should not be empty"
    assert response.sources, "At least one source should be retrieved"
    assert response.query_id

    assert 0.0 <= result.faithfulness.score <= 1.0
    assert 0.0 <= result.answer_relevance.score <= 1.0
    assert 0.0 <= result.context_utilization.score <= 1.0
    assert 0.0 <= result.citation_precision.score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0
    assert result.retrieval.source_count > 0
    assert result.retrieval.score_mean > 0.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_story_query_returns_scored_response():
    """User requests a story retelling — response + metrics both returned."""
    query = "Tell me the story of Hanuman crossing the ocean to reach Lanka."
    response, result = await _run(query, QueryMode.story)

    assert response.answer
    assert result.overall_score >= 0.0
    assert result.mode == "story"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_children_query_returns_scored_response():
    """User asks for a child-friendly story — response + metrics both returned."""
    query = "Tell me about Hanuman's bravery in a way a young child would enjoy."
    response, result = await _run(query, QueryMode.children)

    assert response.answer
    assert result.mode == "children"
    assert 0.0 <= result.overall_score <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scholar_query_returns_scored_response():
    """User asks a scholarly question — response + metrics both returned."""
    query = "What does the Valmiki Ramayana say about the qualities of an ideal king?"
    response, result = await _run(query, QueryMode.scholar)

    assert response.answer
    assert result.mode == "scholar"
    assert 0.0 <= result.overall_score <= 1.0


# ─── Response quality assertions ──────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retrieved_sources_all_above_min_score():
    """Every retrieved source chunk must meet the minimum relevance threshold."""
    from core.config import get_settings
    settings = get_settings()

    request = QueryRequest(
        query="What is the role of dharma in the Ramayana?",
        mode=QueryMode.guidance,
    )
    response = await answer(request)

    for source in response.sources:
        assert source.score >= settings.rag_min_score, (
            f"Source score {source.score} is below min threshold {settings.rag_min_score}"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sources_have_required_fields():
    """Every retrieved source must have non-empty text and citation."""
    request = QueryRequest(
        query="Tell me about Sita's devotion to Rama.",
        mode=QueryMode.story,
    )
    response = await answer(request)

    for source in response.sources:
        assert source.text.strip(), "Source text must not be empty"
        assert source.citation.strip(), "Source citation must not be empty"
        assert 0.0 < source.score <= 1.0, f"Score {source.score} out of range"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validation_result_to_dict_is_serializable():
    """ValidationResult.to_dict() must produce JSON-serializable output."""
    import json

    query = "What is the meaning of ahimsa in Hindu philosophy?"
    request = QueryRequest(query=query, mode=QueryMode.guidance)
    response = await answer(request)
    result = validate_response(query, response)

    d = result.to_dict()
    serialized = json.dumps(d)  # raises if not serializable
    assert serialized

    parsed = json.loads(serialized)
    assert "overall_score" in parsed
    assert "metrics" in parsed
    assert "retrieval" in parsed
    assert "faithfulness" in parsed["metrics"]
    assert "answer_relevance" in parsed["metrics"]
    assert "context_utilization" in parsed["metrics"]
    assert "citation_precision" in parsed["metrics"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_overall_score_matches_weighted_formula():
    """overall_score must equal the weighted sum of the four judge metrics."""
    from evaluation.response_scorer import METRIC_WEIGHTS

    query = "How can I find peace when I am grieving a loss?"
    request = QueryRequest(query=query, mode=QueryMode.guidance)
    response = await answer(request)
    result = validate_response(query, response)

    expected = (
        METRIC_WEIGHTS["faithfulness"] * result.faithfulness.score
        + METRIC_WEIGHTS["answer_relevance"] * result.answer_relevance.score
        + METRIC_WEIGHTS["context_utilization"] * result.context_utilization.score
        + METRIC_WEIGHTS["citation_precision"] * result.citation_precision.score
    )
    assert abs(result.overall_score - expected) < 0.001


@pytest.mark.integration
@pytest.mark.asyncio
async def test_kanda_filter_scopes_retrieval():
    """filter_kanda must restrict retrieved chunks to the specified section."""
    request = QueryRequest(
        query="Describe the search for Sita.",
        mode=QueryMode.story,
        filter_kanda="Sundara Kanda",
    )
    response = await answer(request)

    for source in response.sources:
        if source.kanda:
            assert source.kanda == "Sundara Kanda", (
                f"Expected Sundara Kanda but got: {source.kanda}"
            )
