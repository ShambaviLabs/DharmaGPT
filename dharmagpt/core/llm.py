from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import threading

import requests


class LLMBackend(str, Enum):
    anthropic = "anthropic"
    openai = "openai"
    ollama = "ollama"


@dataclass(frozen=True)
class LLMConfig:
    backend: LLMBackend
    model: str
    api_key: str = ""
    base_url: str = "http://localhost:11434"
    timeout_sec: int = 120
    max_tokens: int = 1024


_DISABLED_REMOTE_BACKENDS: set[LLMBackend] = set()
_DISABLED_LOCK = threading.Lock()


def reset_llm_provider_state() -> None:
    with _DISABLED_LOCK:
        _DISABLED_REMOTE_BACKENDS.clear()


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "too many requests" in text or "429" in text


def _disable_remote_backend(backend: LLMBackend) -> None:
    if backend in {LLMBackend.anthropic, LLMBackend.openai}:
        with _DISABLED_LOCK:
            _DISABLED_REMOTE_BACKENDS.add(backend)


def _remote_backend_disabled(backend: LLMBackend) -> bool:
    with _DISABLED_LOCK:
        return backend in _DISABLED_REMOTE_BACKENDS


def generate_text_sync(system: str, messages: list[dict], config: LLMConfig) -> str:
    """
    Generate a chat-style response using a selectable backend.
    """
    if config.backend == LLMBackend.anthropic:
        from anthropic import Anthropic

        if not config.api_key:
            raise RuntimeError("Anthropic backend selected but no API key was provided")

        client = Anthropic(api_key=config.api_key)
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    if config.backend == LLMBackend.openai:
        from openai import OpenAI

        client = OpenAI(api_key=config.api_key or "EMPTY", base_url=config.base_url or None)
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=config.max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    if config.backend == LLMBackend.ollama:
        endpoint = config.base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": config.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {"temperature": 0.2, "num_predict": config.max_tokens},
        }
        resp = requests.post(endpoint, json=payload, timeout=config.timeout_sec)
        resp.raise_for_status()
        data = resp.json()
        return ((data.get("message") or {}).get("content") or "").strip()

    raise ValueError(f"Unsupported LLM backend: {config.backend}")


async def generate_text_async(system: str, messages: list[dict], config: LLMConfig) -> str:
    return await asyncio.to_thread(generate_text_sync, system, messages, config)


async def generate_text_with_fallback(
    system: str,
    messages: list[dict],
    configs: list[LLMConfig],
) -> tuple[str, LLMConfig, tuple[str, ...], str | None]:
    attempted: list[str] = []
    fallback_reason: str | None = None
    last_exc: Exception | None = None

    for config in configs:
        backend = config.backend
        if _remote_backend_disabled(backend):
            attempted.append(f"{backend.value}:disabled")
            fallback_reason = f"rate_limited:{backend.value}"
            continue
        attempted.append(backend.value)
        try:
            text = await generate_text_async(system, messages, config)
            return text, config, tuple(attempted), fallback_reason
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc):
                _disable_remote_backend(backend)
                fallback_reason = f"rate_limited:{backend.value}"
                continue
            fallback_reason = f"failed:{backend.value}"
            continue

    raise RuntimeError(f"No LLM backend succeeded: {fallback_reason or last_exc}")
