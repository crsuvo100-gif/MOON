"""ContextRetriever — intelligent context retrieval with semantic search.

Every professional AI assistant needs to retrieve relevant context from
various sources: conversation history, knowledge base, semantic search,
and external tools. This module provides that retrieval capability
with relevance scoring and deduplication.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result."""
    content: str
    source: str
    relevance: float = 0.5
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextRetriever:
    """Intelligent context retrieval with semantic search integration.

    Retrieves context from multiple sources and ranks by relevance.
    Can be used standalone or as part of the ContextOrchestrator.
    """

    def __init__(
        self,
        *,
        semantic_search: Any = None,
        history: Any = None,
        knowledge_base: Any = None,
        max_results: int = 10,
        min_relevance: float = 0.3,
        deduplicate: bool = True,
    ) -> None:
        self._semantic = semantic_search
        self._history = history
        self._knowledge = knowledge_base
        self._max_results = max_results
        self._min_relevance = min_relevance
        self._deduplicate = deduplicate

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        sources: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve context relevant to a query.

        Args:
            query: The search query.
            top_k: Maximum number of results per source.
            sources: Optional list of sources to search (default: all).

        Returns:
            List of RetrievalResult objects ranked by relevance.
        """
        results: list[RetrievalResult] = []
        source_filter = set(sources) if sources else None

        # Semantic search
        if self._semantic is not None and (source_filter is None or "semantic" in source_filter):
            try:
                semantic_results = await self._semantic.search(query, top_k=top_k)
                for r in semantic_results:
                    results.append(RetrievalResult(
                        content=r.get("content", r.get("chunk", "")),
                        source="semantic",
                        relevance=r.get("score", 0.5),
                        importance=r.get("importance", 0.5),
                        metadata=r.get("metadata", {}),
                    ))
            except Exception as e:
                logger.debug(f"Semantic search failed: {e}")

        # History search
        if self._history is not None and (source_filter is None or "history" in source_filter):
            try:
                history_results = await self._history.search(query, top_k=top_k)
                for r in history_results:
                    results.append(RetrievalResult(
                        content=r.get("content", r.get("text", "")),
                        source="history",
                        relevance=r.get("score", 0.5),
                        importance=0.6,  # History is usually important
                        metadata=r.get("metadata", {}),
                    ))
            except Exception as e:
                logger.debug(f"History search failed: {e}")

        # Knowledge base search
        if self._knowledge is not None and (source_filter is None or "knowledge" in source_filter):
            try:
                kb_results = await self._knowledge.search(query, top_k=top_k)
                for r in kb_results:
                    results.append(RetrievalResult(
                        content=r.get("content", r.get("chunk", "")),
                        source="knowledge",
                        relevance=r.get("score", 0.5),
                        importance=r.get("importance", 0.5),
                        metadata=r.get("metadata", {}),
                    ))
            except Exception as e:
                logger.debug(f"Knowledge base search failed: {e}")

        # Filter by minimum relevance
        results = [r for r in results if r.relevance >= self._min_relevance]

        # Deduplicate
        if self._deduplicate:
            results = self._deduplicate_results(results)

        # Sort by relevance
        results.sort(key=lambda r: r.relevance, reverse=True)

        # Limit total results
        return results[:self._max_results]

    def _deduplicate_results(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Remove duplicate results based on content similarity."""
        unique: list[RetrievalResult] = []
        seen: set[str] = set()

        for r in results:
            # Simple dedup: first 100 chars as key
            key = r.content[:100].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(r)

        return unique

    async def retrieve_for_task(
        self,
        task_prompt: str,
        *,
        context_type: str = "general",
    ) -> list[RetrievalResult]:
        """Retrieve context specifically for a task.

        Args:
            task_prompt: The task prompt.
            context_type: Type of context needed (general, code, research, etc.).

        Returns:
            List of RetrievalResult objects.
        """
        # Enhance query based on context type
        query = task_prompt
        if context_type == "code":
            query = f"code implementation {task_prompt}"
        elif context_type == "research":
            query = f"research analysis {task_prompt}"
        elif context_type == "debug":
            query = f"debugging error {task_prompt}"

        return await self.retrieve(query)
