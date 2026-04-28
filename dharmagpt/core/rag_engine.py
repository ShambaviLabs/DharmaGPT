import uuid
import structlog

from core.config import get_settings
from core.llm import LLMBackend, LLMConfig, generate_text_with_fallback
from core.insight_store import record_query_run
from core.retrieval import retrieve, format_context
from core.prompts import get_system_prompt
from models.schemas import QueryRequest, QueryResponse, SourceChunk

log = structlog.get_logger()
settings = get_settings()


async def _call_llm(system: str, messages: list[dict]) -> tuple[str, LLMConfig, tuple[str, ...], str | None]:
    configured = [item.strip().lower() for item in (settings.llm_backend_order or "").split(",") if item.strip()]
    if not configured:
        configured = [(settings.llm_backend or "anthropic").lower()]

    configs: list[LLMConfig] = []
    for item in configured:
        backend = LLMBackend(item)
        if backend == LLMBackend.anthropic:
            model = settings.llm_model or settings.anthropic_model
            api_key = settings.llm_api_key or settings.anthropic_api_key
            base_url = settings.llm_base_url
        elif backend == LLMBackend.openai:
            model = settings.llm_model or settings.openai_translation_model
            api_key = settings.llm_api_key or settings.openai_api_key
            base_url = "" if settings.llm_base_url.startswith("http://localhost") else settings.llm_base_url
        else:
            model = settings.llm_model or settings.ollama_model
            api_key = ""
            base_url = settings.ollama_url
        configs.append(
            LLMConfig(
                backend=backend,
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout_sec=settings.llm_timeout_sec,
            )
        )

    text, used_config, attempted, fallback_reason = await generate_text_with_fallback(system, messages, configs)
    log.info(
        "llm_call_done",
        backend=used_config.backend.value,
        model=used_config.model,
        attempted=list(attempted),
        fallback_reason=fallback_reason,
    )
    return text, used_config, attempted, fallback_reason


async def answer(request: QueryRequest) -> QueryResponse:
    """
    Full RAG pipeline:
    1. Retrieve relevant chunks from Pinecone
    2. Format context
    3. Build system prompt with context injected
    4. Call Claude with conversation history
    5. Return structured response with sources
    """
    log.info("rag_query", mode=request.mode, query=request.query[:80])

    # 1. Retrieve. If embeddings/vector retrieval are unavailable, keep the
    # beta answer path alive and let the LLM respond without retrieved sources.
    try:
        chunks: list[SourceChunk] = await retrieve(
            query=request.query,
            filter_section=request.filter_section,
        )
    except Exception as exc:
        log.warning("retrieval_unavailable", error=str(exc))
        chunks = []

    # 2. Format context
    context = format_context(chunks)

    # 3. System prompt
    system = get_system_prompt(request.mode.value, context)

    # 4. Build messages (include history for multi-turn)
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.history[-6:]  # last 6 turns max
    ]
    messages.append({"role": "user", "content": request.query})

    # 5. Call LLM
    query_id = str(uuid.uuid4())
    llm_result = await _call_llm(system, messages)
    if isinstance(llm_result, str):
        answer_text = llm_result
        used_config = LLMConfig(
            backend=LLMBackend((settings.llm_backend or "anthropic").lower()),
            model=settings.resolved_llm_model,
        )
        attempted = (used_config.backend.value,)
        fallback_reason = None
    else:
        answer_text, used_config, attempted, fallback_reason = llm_result
    record_query_run(
        query_id=query_id,
        query=request.query,
        mode=request.mode.value,
        language=request.language,
        status="ok",
        llm_backend=used_config.backend.value,
        llm_model=used_config.model,
        llm_attempted_backends=list(attempted),
        llm_fallback_reason=fallback_reason or "",
        source_count=len(chunks),
    )

    log.info("rag_answer_done", chars=len(answer_text), sources=len(chunks))

    return QueryResponse(
        answer=answer_text,
        sources=chunks,
        mode=request.mode,
        language=request.language,
        query_id=query_id,
        llm_backend=used_config.backend.value,
        llm_model=used_config.model,
        llm_attempted_backends=list(attempted),
        llm_fallback_reason=fallback_reason,
    )
