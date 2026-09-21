"""
EmbeddingService — wraps an embedding model (local or remote).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
import numpy as np

from app.config.settings import get_settings

logger = logging.getLogger("moontm.embed")


class EmbeddingService:
    """Embeds text via a local or remote embedding model."""

    def __init__(
        self,
        dim: int = 384,
        enabled: bool = True,
        base_url: str = "",
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._dim = dim
        self._enabled = enabled
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._model_name = model_name
        self._client: Optional[httpx.AsyncClient] = None
        if not enabled:
            logger.info("EmbeddingService disabled — semantic search will degrade")

    async def setup(self) -> None:
        if not self._enabled:
            return
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url or "http://127.0.0.1:11434/v1",
                timeout=60.0,
            )

    async def embed(self, text: str) -> list[float]:
        if not self._enabled:
            return [0.0] * self._dim
        if not self._client:
            await self.setup()

        payload = {"model": self._model_name, "input": text}
        try:
            resp = await self._client.post("/embeddings", json=payload, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()
            emb = data["data"][0]["embedding"]
            return emb[: self._dim] if len(emb) > self._dim else emb + [0.0] * (self._dim - len(emb))
        except Exception as exc:
            logger.warning("Embedding failed: %s — returning zero vector", exc)
            return [0.0] * self._dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for t in texts:
            results.append(await self.embed(t))
        return results

    async def teardown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
