import hmac
import time
from typing import Optional

import structlog
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.config import get_settings
from core.rag_engine import answer
from models.schemas import ChatMessage, QueryMode, QueryRequest

log = structlog.get_logger()
router = APIRouter()


# ── OpenAI-compatible request/response shapes ──────────────────────────────

class OAIMessage(BaseModel):
    role: str
    content: str


class OAIChatRequest(BaseModel):
    model: str = "dharmagpt"
    messages: list[OAIMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


class OAIChoice(BaseModel):
    index: int = 0
    message: OAIMessage
    finish_reason: str = "stop"


class OAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[OAIChoice]
    usage: OAIUsage = OAIUsage()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _require_key(authorization: Optional[str]) -> None:
    settings = get_settings()
    expected_keys = [
        k.strip()
        for k in (settings.staging_api_key, settings.admin_api_key, settings.admin_operator_api_key)
        if k and k.strip()
    ]
    if not expected_keys:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or not any(hmac.compare_digest(token, k) for k in expected_keys):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _detect_mode(model: str, messages: list[OAIMessage]) -> QueryMode:
    """Infer query mode from model name suffix or system message keywords."""
    for mode in ("scholar", "story", "children", "guidance"):
        if model.lower().endswith(mode):
            return QueryMode(mode)
    for msg in messages:
        if msg.role == "system":
            c = msg.content.lower()
            if "scholar" in c or "academic" in c or "iast" in c:
                return QueryMode.scholar
            if "story" in c or "retell" in c or "narrative" in c:
                return QueryMode.story
            if "child" in c:
                return QueryMode.children
    return QueryMode.guidance


def _format_sources(sources) -> str:
    if not sources:
        return ""
    lines = ["\n\n---\n**Sources**"]
    for i, s in enumerate(sources, 1):
        lines.append(f"[{i}] {s.citation}")
        if s.url:
            lines.append(f"    {s.url}")
    return "\n".join(lines)


# ── Models list ─────────────────────────────────────────────────────────────

_MODELS = [
    {"id": "dharmagpt",          "description": "Guidance mode — dharmic wisdom, emotional support"},
    {"id": "dharmagpt-scholar",  "description": "Academic, structured, IAST citations"},
    {"id": "dharmagpt-story",    "description": "Narrative retelling grounded in source texts"},
    {"id": "dharmagpt-children", "description": "Age-appropriate stories with moral lessons"},
]

@router.get("/v1/models", tags=["openai-compat"])
async def list_models(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    _require_key(authorization)
    return {
        "object": "list",
        "data": [
            {"id": m["id"], "object": "model", "created": 1747000000, "owned_by": "shambavilabs"}
            for m in _MODELS
        ],
    }


# ── Endpoint ────────────────────────────────────────────────────────────────

@router.post("/v1/chat/completions", response_model=OAIChatResponse, tags=["openai-compat"])
async def chat_completions(
    request: OAIChatRequest,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    _require_key(authorization)

    if request.stream:
        raise HTTPException(status_code=422, detail="Streaming is not yet supported")

    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="Request must include at least one user message")

    query_text = user_messages[-1].content
    history = [
        ChatMessage(role=m.role, content=m.content)
        for m in request.messages[:-1]
        if m.role in ("user", "assistant")
    ]

    mode = _detect_mode(request.model, request.messages)
    q = QueryRequest(query=query_text, mode=mode, history=history[:10])

    log.info("openai_compat_request", model=request.model, mode=mode.value)
    result = await answer(q)

    content = result.answer + _format_sources(result.sources)

    return OAIChatResponse(
        id=f"chatcmpl-{result.query_id}",
        created=int(time.time()),
        model=request.model,
        choices=[OAIChoice(message=OAIMessage(role="assistant", content=content))],
    )
