"""Semantic search facade over the knowledge base + history.

Enhanced implementation with embedding-based search, hybrid scoring,
and result reranking.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class SemanticSearch:
    """Semantic search with embedding-based retrieval and hybrid scoring.

    Features:
    - Embedding-based semantic search
    - Hybrid scoring (semantic + keyword + recency)
    - Result reranking
    - Configurable top_k
    - Fallback to keyword search
    """

    def __init__(
        self,
        knowledge_base: Any = None,
        history: Any = None,
        embedding_service: Any = None,
    ) -> None:
        self._kb = knowledge_base
        self._history = history
        self._embeddings = embedding_service

    async def search(
        self,
        query: str,
        top_k: int = 5,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]:
        """Search for relevant content.

        Args:
            query: Search query
            top_k: Number of results to return
            hybrid: Whether to use hybrid scoring

        Returns:
            List of result dicts with 'id', 'score', 'content', 'source'
        """
        if self._kb is None:
            return []

        try:
            # Try embedding-based search first
            if self._embeddings is not None:
                results = await self._embedding_search(query, top_k * 2)
                if results and hybrid:
                    results = self._hybrid_rerank(query, results, top_k)
                return results[:top_k]

            # Fall back to knowledge base search
            return await self._kb.search(query, top_k=top_k)
        except Exception as exc:
            logger.warning("Semantic search failed: %s", exc)
            return []

    async def _embedding_search(
        self,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search using embeddings."""
        try:
            qvec = await self._embeddings.embed(query)
            hits = self._kb._store.search(qvec, top_k=top_k)
            return [
                {
                    "id": h[0],
                    "score": h[1],
                    "content": h[2].get("chunk", ""),
                    "source": "embedding",
                }
                for h in hits
            ]
        except Exception as exc:
            logger.debug("Embedding search failed: %s", exc)
            return []

    def _hybrid_rerank(
        self,
        query: str,
        results: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Rerank results using hybrid scoring.

        Combines:
        - Semantic score (from embeddings)
        - Keyword overlap (BM25-like)
        - Recency (if timestamp available)
        """
        q = (query or "").lower()
        query_words = set(q.split())

        for r in results:
            content = r.get("content", "").lower()
            content_words = set(content.split())

            # Keyword overlap score
            if query_words and content_words:
                overlap = len(query_words & content_words)
                keyword_score = overlap / math.sqrt(len(query_words) * len(content_words))
            else:
                keyword_score = 0.0

            # Semantic score (normalized)
            semantic_score = r.get("score", 0.0)

            # Recency score (if timestamp available)
            recency_score = 0.0
            if "timestamp" in r:
                age_hours = (r["timestamp"]) / 3600.0
                recency_score = 1.0 / (1.0 + age_hours)

            # Hybrid score (weighted combination)
            r["score"] = (
                0.5 * semantic_score
                + 0.3 * keyword_score
                + 0.2 * recency_score
            )
            r["source"] = "hybrid"

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def search_with_fallback(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search with fallback to history if KB returns no results."""
        results = await self.search(query, top_k)
        if results:
            return results

        # Fallback to history search
        if self._history is not None:
            try:
                history_results = self._history.search(query, limit=top_k)
                return [
                    {
                        "id": f"hist_{i}",
                        "score": 1.0 - (i * 0.1),
                        "content": item,
                        "source": "history",
                    }
                    for i, item in enumerate(history_results)
                ]
            except Exception as exc:
                logger.debug("History fallback search failed: %s", exc)

        return []
