"""
RAG engine — thin async wrapper around the LangChain LCEL chain from core.backends.rag.

get_rag_chain() returns the fully wired chain (embedder + vector store + LLM).
Swapping any component is a single .env change — no code changes needed.

Supported backend combos (set in .env):
    EMBEDDING_BACKEND=local_hash   RAG_BACKEND=local    LLM_BACKEND=anthropic  ← default
    EMBEDDING_BACKEND=openai       RAG_BACKEND=pinecone LLM_BACKEND=anthropic
    EMBEDDING_BACKEND=local_hash   RAG_BACKEND=local    LLM_BACKEND=sarvam
    EMBEDDING_BACKEND=local_hash   RAG_BACKEND=local    LLM_BACKEND=ollama
"""
from __future__ import annotations

import asyncio
import uuid
import structlog

from core.backends.rag import get_rag_chain
from core.retrieval import retrieve as _retrieve_sources, format_context
from models.schemas import QueryRequest, QueryResponse, SourceChunk

log = structlog.get_logger()


def _doc_to_source_chunk(doc) -> SourceChunk:
    meta = doc.metadata or {}
    section = meta.get("section") or meta.get("kanda") or None
    chapter_raw = meta.get("chapter") or meta.get("sarga")
    verse_raw = meta.get("verse")
    return SourceChunk(
        text=doc.page_content,
        citation=meta.get("citation", ""),
        section=section,
        chapter=int(chapter_raw) if chapter_raw is not None else None,
        verse=int(verse_raw) if verse_raw is not None else None,
        score=round(float(meta.get("score", 0.0)), 4),
        source_type=meta.get("source_type", "text"),
        audio_timestamp=(
            f"{meta.get('start_time_sec', '')}s–{meta.get('end_time_sec', '')}s"
            if meta.get("source_type") == "audio" else None
        ),
        url=meta.get("url"),
    )


async def retrieve(
    query: str,
    top_k: int | None = None,
    filter_section: str | None = None,
    filter_source_type: str | None = None,
) -> list[SourceChunk]:
    return await _retrieve_sources(
        query,
        top_k=top_k,
        filter_section=filter_section,
        filter_source_type=filter_source_type,
    )


async def _call_llm(system: str, messages: list[dict]) -> str:
    from core.backends.llm import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = get_llm()
    query = messages[-1]["content"] if messages else ""
    response = await asyncio.to_thread(
        llm.invoke,
        [SystemMessage(content=system), HumanMessage(content=query)],
    )
    return response.content if hasattr(response, "content") else str(response)


async def answer(request: QueryRequest) -> QueryResponse:
    """
    Full RAG pipeline via the pluggable LangChain chain.
    Falls back gracefully to LLM-only if retrieval fails.
    """
    log.info("rag_query", mode=request.mode, query=request.query[:80])

    try:
        chunks = await retrieve(
            request.query,
            filter_section=request.filter_section,
        )
        from core.prompts import get_system_prompt

        system_prompt = get_system_prompt(request.mode.value, format_context(chunks))
        answer_text = await _call_llm(system_prompt, [{"role": "user", "content": request.query}])

    except Exception as exc:
        log.warning("rag_chain_failed_fallback", error=str(exc))
        # Fallback: LLM-only answer with no retrieved context
        from core.backends.llm import get_llm
        from core.prompts import get_system_prompt

        llm = get_llm()
        system = get_system_prompt(request.mode.value, "")
        try:
            response = await asyncio.to_thread(
                llm.invoke,
                [{"role": "system", "content": system}, {"role": "user", "content": request.query}],
            )
            answer_text = response.content if hasattr(response, "content") else str(response)
        except Exception as llm_exc:
            log.error("llm_fallback_also_failed", error=str(llm_exc))
            answer_text = "I encountered an error while processing your query. Please try again."
        chunks = []

    log.info("rag_answer_done", chars=len(answer_text), sources=len(chunks))

    return QueryResponse(
        answer=answer_text,
        sources=chunks,
        mode=request.mode,
        language=request.language,
        query_id=str(uuid.uuid4()),
    )
