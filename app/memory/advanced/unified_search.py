"""Unified search across ALL memory types with combined relevance ranking.

Professional AI assistants search across every memory subsystem simultaneously
and return results ranked by a unified relevance score. This module searches
STM, LTM, Episodic, Graph, and KnowledgeBase in one call.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UnifiedResult:
    """A single search result from any memory subsystem."""
    source: str          # "stm", "ltm", "episodic", "graph", "kb"
    content: str
    score: float         # 0.0 - 1.0 combined relevance
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "content": self.content,
            "score": round(self.score, 4),
            "importance": self.importance,
            "tags": self.tags,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


class UnifiedSearcher:
    """Search across all memory subsystems with combined relevance scoring.

    Weighting scheme (tunable):
    - Episodic (past task outcomes + lessons): highest weight -- direct
      experience with similar tasks is the most valuable signal.
    - LTM (long-term facts): high weight -- durable knowledge.
    - Graph (associations): medium weight -- related concepts.
    - KB (indexed documents): medium weight -- curated knowledge.
    - STM (recent context): lower weight -- transient, but high recency.

    Final score = weighted_recency * 0.3 + importance * 0.2 + keyword_match * 0.3 + source_weight * 0.2
    """

    SOURCE_WEIGHTS = {
        "episodic": 0.9,
        "ltm": 0.8,
        "graph": 0.7,
        "kb": 0.7,
        "stm": 0.5,
    }

    def __init__(
        self,
        short_term=None,
        long_term=None,
        episodic=None,
        graph=None,
        knowledge_base=None,
    ) -> None:
        self._stm = short_term
        self._ltm = long_term
        self._episodic = episodic
        self._graph = graph
        self._kb = knowledge_base

    async def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.1,
        include_sources: list[str] | None = None,
    ) -> list[UnifiedResult]:
        """Search all memory subsystems and return unified ranked results.

        Args:
            query: The search query.
            top_k: Maximum results to return.
            min_score: Minimum combined score to include (0.0-1.0).
            include_sources: Optional list of source names to search.
                If None, searches all. Valid: "stm", "ltm", "episodic", "graph", "kb".

        Returns:
            List of UnifiedResult sorted by score (highest first).
        """
        sources = include_sources or ["stm", "ltm", "episodic", "graph", "kb"]
        query_lower = (query or "").lower()
        query_words = set(query_lower.split())
        results: list[UnifiedResult] = []

        # --- Search Episodic Memory ---
        if "episodic" in sources and self._episodic is not None:
            try:
                episodes = self._episodic.recall(query, k=top_k)
                for ep in episodes:
                    text = f"{ep.goal} {ep.outcome} {ep.lesson}"
                    kw_score = self._keyword_score(query_lower, text.lower())
                    recency = 1.0 / (1.0 + (time.time() - ep.ts) / 86400.0)
                    score = 0.3 * recency + 0.3 * kw_score + 0.2 * 0.9  # source weight
                    score += 0.2 * (1.0 if ep.success else 0.5)
                    if score >= min_score:
                        results.append(UnifiedResult(
                            source="episodic",
                            content=f"Goal: {ep.goal} | Outcome: {ep.outcome} | Lesson: {ep.lesson}",
                            score=score,
                            importance=1.0 if ep.success else 0.5,
                            tags=["episodic", "lesson" if ep.lesson else "outcome"],
                            metadata={"success": ep.success, "ts": ep.ts},
                            timestamp=ep.ts,
                        ))
            except Exception as exc:
                logger.debug("Episodic search failed: %s", exc)

        # --- Search LTM ---
        if "ltm" in sources and self._ltm is not None:
            try:
                entries = await self._ltm.query(query_lower, limit=top_k)
                for entry in entries:
                    kw_score = self._keyword_score(query_lower, entry.content.lower())
                    # EnhancedMemoryEntry has .importance directly
                    importance = getattr(entry, 'importance', 0.5)
                    # tags and created_at are on the inner MemoryEntry
                    inner = getattr(entry, 'entry', entry)
                    tags = getattr(inner, 'tags', [])
                    created_at = getattr(inner, 'created_at', 0.0)
                    score = 0.3 * 0.5 + 0.3 * kw_score + 0.2 * 0.8  # source weight
                    score += 0.2 * importance
                    if score >= min_score:
                        results.append(UnifiedResult(
                            source="ltm",
                            content=entry.content,
                            score=score,
                            importance=importance,
                            tags=tags,
                            metadata={"id": entry.id, "created_at": created_at},
                            timestamp=created_at,
                        ))
            except Exception as exc:
                logger.debug("LTM search failed: %s", exc)

        # --- Search Knowledge Base ---
        if "kb" in sources and self._kb is not None:
            try:
                kb_results = await self._kb.search(query, top_k=top_k)
                for hit in kb_results:
                    content = hit.get("chunk", hit.get("content", ""))
                    score = hit.get("score", 0.5)
                    results.append(UnifiedResult(
                        source="kb",
                        content=content,
                        score=0.3 * 0.5 + 0.3 * score + 0.2 * 0.7,  # source weight
                        importance=0.6,
                        tags=["knowledge"],
                        metadata={"id": hit.get("id", "")},
                    ))
            except Exception as exc:
                logger.debug("KB search failed: %s", exc)

        # --- Search Memory Graph ---
        if "graph" in sources and self._graph is not None:
            try:
                # graph.search() returns list[str] of matching node contents
                node_contents = await self._graph.search(query_lower, limit=top_k)
                for content in node_contents:
                    kw_score = self._keyword_score(query_lower, content.lower())
                    score = 0.3 * 0.5 + 0.3 * kw_score + 0.2 * 0.7  # source weight
                    if score >= min_score:
                        results.append(UnifiedResult(
                            source="graph",
                            content=content,
                            score=score,
                            importance=0.5,
                            tags=["graph"],
                        ))
            except Exception as exc:
                logger.debug("Graph search failed: %s", exc)

        # --- Search STM ---
        if "stm" in sources and self._stm is not None:
            try:
                items = self._stm.search(query_lower, limit=top_k)
                for item in items:
                    kw_score = self._keyword_score(query_lower, item.lower())
                    score = 0.3 * 0.8 + 0.3 * kw_score + 0.2 * 0.5  # source weight
                    if score >= min_score:
                        results.append(UnifiedResult(
                            source="stm",
                            content=item,
                            score=score,
                            importance=0.4,
                            tags=["short_term"],
                        ))
            except Exception as exc:
                logger.debug("STM search failed: %s", exc)

        # Sort by score descending, return top_k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        """Simple keyword overlap score (0.0-1.0)."""
        q_words = set(query.split())
        if not q_words:
            return 0.0
        t_words = set(text.split())
        overlap = q_words & t_words
        return len(overlap) / len(q_words)
