"""knowledge_base.py -- curated, indexed knowledge store (RAG)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.utils.text import chunk_text

if TYPE_CHECKING:
    from app.memory.vector_db import VectorStore
    from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


class KnowledgeBase:
    """Document indexing + semantic retrieval over a vector store."""

    def __init__(self, store: "VectorStore", embeddings: "EmbeddingService", chunk_size: int = 1500) -> None:
        self._store = store
        self._embeddings = embeddings
        self._chunk_size = chunk_size
        self._doc_chunks: dict[str, list[str]] = {}

    async def setup(self) -> None:
        await self._embeddings.setup()

    async def index_document(self, doc_id: str, text: str) -> int:
        chunks = chunk_text(text, max_chars=self._chunk_size)
        self._doc_chunks[doc_id] = chunks
        vectors = await self._embeddings.embed_many(chunks)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=False)):
            self._store.add(f"{doc_id}#{i}", vec, {"doc_id": doc_id, "chunk": chunk, "index": i})
        logger.info("Indexed doc %s -> %d chunks", doc_id, len(chunks))
        return len(chunks)

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        qvec = await self._embeddings.embed(query)
        hits = self._store.search(qvec, top_k=top_k)
        return [{"id": h[0], "score": h[1], "chunk": h[2].get("chunk", "")} for h in hits]

    def list_docs(self) -> list[str]:
        return list(self._doc_chunks.keys())
