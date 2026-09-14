"""
KnowledgeBase — semantic search over embedded documents.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.memory.vector_db import InMemoryVectorStore
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger("moontm.kb")


class KnowledgeBase:
    """Wraps InMemoryVectorStore + EmbeddingService: index docs, semantic search."""

    def __init__(self, store: InMemoryVectorStore, embeddings: EmbeddingService) -> None:
        self._store = store
        self._embeddings = embeddings
        self._chunk_id = 0

    async def setup(self) -> None:
        await self._embeddings.setup()

    async def index_document(self, doc_id: str, text: str, chunk_size: int = 500) -> int:
        chunks: list[str] = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])

        vectors = await self._embeddings.embed_batch(chunks)
        for chunk, vec in zip(chunks, vectors):
            cid = f"{doc_id}_chunk_{self._chunk_id}"
            self._chunk_id += 1
            self._store.add(cid, vec, chunk)
        return len(chunks)

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        vec = await self._embeddings.embed(query)
        return self._store.search(vec, top_k=top_k)

    def __len__(self) -> int:
        return len(self._store)
