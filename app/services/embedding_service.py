"""Embedding service with a deterministic offline fallback.

When no embedding endpoint is configured (EMBEDDING_BASE_URL empty) we use a
stable hash-based pseudo-embedding so semantic search / RAG still functions
offline without any network dependency.
"""

from __future__ import annotations

import hashlib
import math


from app.config.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(
        self,
        dim: int = 384,
        *,
        enabled: bool = False,
        base_url: str = "",
        model_name: str = "",
        api_key: str = "not-required",
    ) -> None:
        self.dim = dim
        self.enabled = enabled
        self._base_url = base_url
        self._model_name = model_name
        self._api_key = api_key

    async def setup(self) -> None:
        if self.enabled:
            logger.info("EmbeddingService using endpoint %s", self._base_url)
        else:
            logger.info("EmbeddingService using deterministic offline fallback (dim=%d)", self.dim)

    def _offline(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        # Deterministic bag-of-words hashing into the dim space.
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            idx = h % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, text: str) -> list[float]:
        if not self.enabled:
            return self._offline(text)
        # Real endpoint path (best-effort; falls back to offline on failure).
        try:
            import httpx

            async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as c:
                r = await c.post(
                    "/embeddings",
                    json={"model": self._model_name, "input": text},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                r.raise_for_status()
                return r.json()["data"][0]["embedding"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding endpoint failed, using offline fallback: %s", exc)
            return self._offline(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]
