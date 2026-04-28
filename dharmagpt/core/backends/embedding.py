"""
Embedding backend registry.

Default: openai  (EMBEDDING_BACKEND in .env)
No fallback — if the configured backend fails, the exception propagates immediately.

Supported values:
  openai      — OpenAI text-embedding-3-large (default, best quality)
  local_hash  — Deterministic hash embedding, free, no API — for smoke tests only
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

import structlog

log = structlog.get_logger()


class OpenAIEmbeddings:
    def __init__(self, model: str, api_key: str, dims: int):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._dims = dims

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [r.embedding for r in response.data]

    def embed_query(self, text: str) -> List[float]:
        response = self._client.embeddings.create(model=self._model, input=[text])
        return response.data[0].embedding


class LocalHashEmbeddings:
    """Deterministic hash-based embeddings for smoke tests and offline dev.
    Vectors are NOT semantically meaningful — use only for pipeline verification.
    """

    def __init__(self, dims: int = 3072):
        import hashlib
        import math
        import re
        self._dims = dims
        self._re = re.compile(r"[\wऀ-ൿ]+", re.UNICODE)
        self._hashlib = hashlib
        self._math = math

    def _embed_one(self, text: str) -> List[float]:
        vec = [0.0] * self._dims
        tokens = self._re.findall(text.lower()) or [text.lower()]
        for tok in tokens:
            digest = self._hashlib.blake2b(tok.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dims
            vec[bucket] += 1.0 if digest[4] & 1 else -1.0
        norm = self._math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_one(text)


@lru_cache(maxsize=1)
def get_embedder():
    """Returns the configured embedder, cached for the process lifetime."""
    from core.config import get_settings
    s = get_settings()
    backend = (s.embedding_backend or "openai").lower()

    if backend == "local_hash":
        log.info("embedding_backend_loaded", backend="local_hash")
        return LocalHashEmbeddings(dims=s.embedding_dims)

    if backend == "openai":
        log.info("embedding_backend_loaded", backend="openai", model=s.embedding_model)
        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key, dims=s.embedding_dims)

    raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend!r}. Valid values: openai | local_hash")
