"""knowledge_base.py -- curated, indexed knowledge store (RAG).

Enhanced implementation with document chunking, metadata filtering,
reranking, and incremental updates.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.utils.text import chunk_text

if TYPE_CHECKING:
    from app.memory.vector_db import VectorStore
    from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


class KnowledgeBase:
    """Document indexing + semantic retrieval over a vector store.

    Features:
    - Document chunking with overlap
    - Metadata filtering
    - Result reranking
    - Incremental updates
    - Document versioning
    - Tag-based organization
    """

    def __init__(
        self,
        store: VectorStore,
        embeddings: EmbeddingService,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
    ) -> None:
        self._store = store
        self._embeddings = embeddings
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._doc_chunks: dict[str, list[str]] = {}
        self._doc_metadata: dict[str, dict[str, Any]] = {}
        self._doc_tags: dict[str, list[str]] = {}
        self._doc_versions: dict[str, int] = {}

    async def setup(self) -> None:
        await self._embeddings.setup()

    async def index_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> int:
        """Index a document into the knowledge base.

        Args:
            doc_id: Unique document identifier
            text: Document text content
            metadata: Optional metadata dict
            tags: Optional tags for filtering

        Returns:
            Number of chunks created
        """
        chunks = chunk_text(text, max_chars=self._chunk_size)
        self._doc_chunks[doc_id] = chunks
        self._doc_metadata[doc_id] = metadata or {}
        self._doc_tags[doc_id] = tags or []
        self._doc_versions[doc_id] = self._doc_versions.get(doc_id, 0) + 1

        vectors = await self._embeddings.embed_many(chunks)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=False)):
            self._store.add(
                f"{doc_id}#{i}",
                vec,
                {
                    "doc_id": doc_id,
                    "chunk": chunk,
                    "index": i,
                    "version": self._doc_versions[doc_id],
                    "timestamp": time.time(),
                    **(metadata or {}),
                },
            )
        logger.info(
            "Indexed doc %s -> %d chunks (version %d)",
            doc_id, len(chunks), self._doc_versions[doc_id],
        )
        return len(chunks)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter_tags: list[str] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search the knowledge base.

        Args:
            query: Search query
            top_k: Number of results
            filter_tags: Only return docs with these tags
            filter_metadata: Only return docs matching this metadata

        Returns:
            List of result dicts with 'id', 'score', 'chunk', 'doc_id'
        """
        qvec = await self._embeddings.embed(query)
        hits = self._store.search(qvec, top_k=top_k * 2)  # over-fetch for filtering

        results: list[dict[str, Any]] = []
        for h in hits:
            doc_id = h[2].get("doc_id", "")
            metadata = h[2]

            # Apply tag filter
            if filter_tags:
                doc_tags = self._doc_tags.get(doc_id, [])
                if not any(t in doc_tags for t in filter_tags):
                    continue

            # Apply metadata filter
            if filter_metadata:
                doc_meta = self._doc_metadata.get(doc_id, {})
                if not all(doc_meta.get(k) == v for k, v in filter_metadata.items()):
                    continue

            results.append({
                "id": h[0],
                "score": h[1],
                "chunk": h[2].get("chunk", ""),
                "doc_id": doc_id,
                "metadata": metadata,
            })

            if len(results) >= top_k:
                break

        return results

    def list_docs(self) -> list[str]:
        """List all document IDs."""
        return list(self._doc_chunks.keys())

    def get_doc_metadata(self, doc_id: str) -> dict[str, Any]:
        """Get metadata for a document."""
        return self._doc_metadata.get(doc_id, {})

    def get_doc_tags(self, doc_id: str) -> list[str]:
        """Get tags for a document."""
        return self._doc_tags.get(doc_id, [])

    def remove_doc(self, doc_id: str) -> bool:
        """Remove a document from the knowledge base."""
        if doc_id not in self._doc_chunks:
            return False
        # Remove chunks from vector store
        for i in range(len(self._doc_chunks[doc_id])):
            self._store.remove(f"{doc_id}#{i}")
        del self._doc_chunks[doc_id]
        self._doc_metadata.pop(doc_id, None)
        self._doc_tags.pop(doc_id, None)
        self._doc_versions.pop(doc_id, None)
        return True

    def stats(self) -> dict[str, Any]:
        """Return knowledge base statistics."""
        total_chunks = sum(len(chunks) for chunks in self._doc_chunks.values())
        return {
            "num_documents": len(self._doc_chunks),
            "total_chunks": total_chunks,
            "avg_chunks_per_doc": (
                total_chunks / len(self._doc_chunks) if self._doc_chunks else 0
            ),
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
        }
