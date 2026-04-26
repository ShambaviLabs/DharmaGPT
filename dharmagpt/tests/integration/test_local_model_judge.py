"""
test_local_model_judge.py — integration tests for the validation pipeline using local Ollama models.

Each test runs the complete pipeline (query → RAG response → scored metrics) but uses a
local Ollama model as the judge instead of the Anthropic API. This lets the evaluation
pipeline run fully offline once the models are pulled.

Models tested:
  qwen2.5:3b  — faster, lower memory, good for quick CI validation
  qwen2.5:7b  — higher quality scores, used by default in translate_corpus.py

To pull models if not already present:
  ollama pull qwen2.5:3b
  ollama pull qwen2.5:7b

Requires: OPENAI_API_KEY, PINECONE_API_KEY (for retrieval + embedding)
          Ollama running at http://localhost:11434
Run with: pytest tests/integration/test_local_model_judge.py -v --timeout=180
"""

import pytest
import requests

from core.llm import LLMBackend, LLMConfig
from core.rag_engine import answer
from evaluation.response_scorer import validate_response
from models.schemas import QueryMode, QueryRequest


# ─── Ollama availability guard ────────────────────────────────────────────────


def _ollama_has_model(model: str) -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        names = [m["name"] for m in resp.json().get("models", [])]
        return model in names
    except Exception:
        return False


def _ollama_config(model: str) -> LLMConfig:
    return LLMConfig(
        backend=LLMBackend.ollama,
        model=model,
        base_url="http://localhost:11434",
        timeout_sec=180,
        max_tokens=1024,
    )


# ─── Shared query ─────────────────────────────────────────────────────────────

_QUERY = "How should I deal with anger and frustration in daily life?"


async def _scored_response(judge_model: str):
    """Run the full pipeline and score with the given local judge model."""
    request = QueryRequest(query=_QUERY, mode=QueryMode.guidance)
    response = await answer(request)
    config = _ollama_config(judge_model)
    result = validate_response(_QUERY, response, judge_config=config)
    return response, result


# ─── qwen2.5:3b ───────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen3b_full_pipeline_query_to_scored_response():
    """qwen2.5:3b judges the full query → response → metrics pipeline."""
    model = "qwen2.5:3b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    response, result = await _scored_response(model)

    assert response.answer, "Answer must not be empty"
    assert response.sources, "At least one source must be retrieved"

    assert 0.0 <= result.faithfulness.score <= 1.0
    assert 0.0 <= result.answer_relevance.score <= 1.0
    assert 0.0 <= result.context_utilization.score <= 1.0
    assert 0.0 <= result.citation_precision.score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0
    assert result.retrieval.source_count > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen3b_returns_reasoning_strings():
    """qwen2.5:3b must populate reasoning text for each metric."""
    model = "qwen2.5:3b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    _, result = await _scored_response(model)

    assert result.faithfulness.reasoning, "faithfulness.reasoning must not be empty"
    assert result.answer_relevance.reasoning, "answer_relevance.reasoning must not be empty"
    assert result.context_utilization.reasoning, "context_utilization.reasoning must not be empty"
    assert result.citation_precision.reasoning, "citation_precision.reasoning must not be empty"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen3b_result_is_serializable():
    """qwen2.5:3b scored result must be JSON-serializable."""
    import json

    model = "qwen2.5:3b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    _, result = await _scored_response(model)
    serialized = json.dumps(result.to_dict())
    assert json.loads(serialized)["overall_score"] >= 0.0


# ─── qwen2.5:7b ───────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen7b_full_pipeline_query_to_scored_response():
    """qwen2.5:7b judges the full query → response → metrics pipeline."""
    model = "qwen2.5:7b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    response, result = await _scored_response(model)

    assert response.answer
    assert response.sources

    assert 0.0 <= result.faithfulness.score <= 1.0
    assert 0.0 <= result.answer_relevance.score <= 1.0
    assert 0.0 <= result.context_utilization.score <= 1.0
    assert 0.0 <= result.citation_precision.score <= 1.0
    assert 0.0 <= result.overall_score <= 1.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen7b_returns_reasoning_strings():
    """qwen2.5:7b must populate reasoning text for each metric."""
    model = "qwen2.5:7b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    _, result = await _scored_response(model)

    assert result.faithfulness.reasoning
    assert result.answer_relevance.reasoning
    assert result.context_utilization.reasoning
    assert result.citation_precision.reasoning


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qwen7b_weighted_score_formula():
    """qwen2.5:7b overall_score must equal the documented weighted formula."""
    from evaluation.response_scorer import METRIC_WEIGHTS

    model = "qwen2.5:7b"
    if not _ollama_has_model(model):
        pytest.skip(f"{model} not available — run: ollama pull {model}")

    _, result = await _scored_response(model)

    expected = (
        METRIC_WEIGHTS["faithfulness"] * result.faithfulness.score
        + METRIC_WEIGHTS["answer_relevance"] * result.answer_relevance.score
        + METRIC_WEIGHTS["context_utilization"] * result.context_utilization.score
        + METRIC_WEIGHTS["citation_precision"] * result.citation_precision.score
    )
    assert abs(result.overall_score - expected) < 0.001


# ─── Cross-model comparison ───────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_both_models_agree_on_score_range():
    """Both models must score the same response within a reasonable range of each other."""
    small, large = "qwen2.5:3b", "qwen2.5:7b"
    if not (_ollama_has_model(small) and _ollama_has_model(large)):
        pytest.skip("Both qwen2.5:3b and qwen2.5:7b required for comparison test")

    request = QueryRequest(query=_QUERY, mode=QueryMode.guidance)
    response = await answer(request)

    result_small = validate_response(_QUERY, response, judge_config=_ollama_config(small))
    result_large = validate_response(_QUERY, response, judge_config=_ollama_config(large))

    # Scores should be in the same ballpark — not more than 0.4 apart
    assert abs(result_small.overall_score - result_large.overall_score) < 0.4, (
        f"Scores diverged too much: 3b={result_small.overall_score:.3f}, "
        f"7b={result_large.overall_score:.3f}"
    )
