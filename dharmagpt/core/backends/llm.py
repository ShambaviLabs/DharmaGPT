"""
LLM backend registry — powered by LangChain BaseChatModel.

Default: anthropic  (LLM_BACKEND in .env)
No fallback — if the configured backend fails, the exception propagates immediately.

Supported values:
  anthropic  — Claude via Anthropic API (default)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import structlog

log = structlog.get_logger()


@dataclass
class _ChatResponse:
    content: str


class OllamaChatModel:
    def __init__(self, model: str, base_url: str, timeout: int):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def invoke(self, messages) -> _ChatResponse:
        import requests

        payload_messages = []
        for message in messages:
            if isinstance(message, dict):
                role = message.get("role", "user")
                content = message.get("content", "")
            else:
                role = getattr(message, "type", "") or getattr(message, "role", "") or "user"
                content = getattr(message, "content", "")
                if role == "human":
                    role = "user"
                elif role == "ai":
                    role = "assistant"
            payload_messages.append({"role": role, "content": content})

        response = requests.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": payload_messages,
                "options": {"temperature": 0.2, "num_predict": 1024},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return _ChatResponse(content=((data.get("message") or {}).get("content") or "").strip())


@lru_cache(maxsize=1)
def get_llm():
    """
    Returns a LangChain BaseChatModel configured from env settings.
    Cached for the process lifetime.
    """
    from core.config import get_settings
    s = get_settings()
    backend = (s.llm_backend or "anthropic").lower()

    if backend == "ollama":
        model = s.resolved_llm_model
        log.info("llm_backend_loaded", backend="ollama", model=model)
        return OllamaChatModel(model=model, base_url=s.ollama_url, timeout=s.llm_timeout_sec)

    if backend != "anthropic":
        raise ValueError(
            f"Unknown LLM_BACKEND: {backend!r}. Valid values: anthropic | ollama"
        )

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise RuntimeError(
            "langchain_anthropic is not installed — run: pip install langchain-anthropic"
        )

    model = s.resolved_llm_model
    log.info("llm_backend_loaded", backend="anthropic", model=model)
    return ChatAnthropic(
        model=model,
        anthropic_api_key=s.anthropic_api_key,
        max_tokens=1024,
        timeout=s.llm_timeout_sec,
    )
