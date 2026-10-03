"""memory_stats.py -- Memory system statistics and analytics.

Professional AI assistants track memory health: how many memories exist,
how often they're accessed, how important they are, and how well they're
being used. This module provides comprehensive statistics across all
memory subsystems.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryStats:
    """Comprehensive memory system statistics."""
    # LTM stats
    ltm_total: int = 0
    ltm_avg_importance: float = 0.0
    ltm_total_accesses: int = 0
    ltm_tags: int = 0

    # STM stats
    stm_total: int = 0
    stm_active: int = 0
    stm_promoted: int = 0
    stm_avg_importance: float = 0.0

    # Episodic stats
    episodic_total: int = 0
    episodic_success_rate: float = 0.0

    # Graph stats
    graph_nodes: int = 0
    graph_edges: int = 0
    graph_avg_degree: float = 0.0
    graph_density: float = 0.0

    # KB stats
    kb_documents: int = 0
    kb_chunks: int = 0

    # Overall
    total_memories: int = 0
    memory_types: dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ltm": {
                "total": self.ltm_total,
                "avg_importance": self.ltm_avg_importance,
                "total_accesses": self.ltm_total_accesses,
                "tags": self.ltm_tags,
            },
            "stm": {
                "total": self.stm_total,
                "active": self.stm_active,
                "promoted": self.stm_promoted,
                "avg_importance": self.stm_avg_importance,
            },
            "episodic": {
                "total": self.episodic_total,
                "success_rate": self.episodic_success_rate,
            },
            "graph": {
                "nodes": self.graph_nodes,
                "edges": self.graph_edges,
                "avg_degree": self.graph_avg_degree,
                "density": self.graph_density,
            },
            "knowledge_base": {
                "documents": self.kb_documents,
                "chunks": self.kb_chunks,
            },
            "overall": {
                "total_memories": self.total_memories,
                "memory_types": self.memory_types,
            },
            "timestamp": self.timestamp,
        }


class MemoryStatsCollector:
    """Collects and aggregates statistics from all memory subsystems."""

    def __init__(self) -> None:
        self._history: list[MemoryStats] = []
        self._max_history = 100

    async def collect(
        self,
        ltm: Any = None,
        stm: Any = None,
        episodic: Any = None,
        graph: Any = None,
        kb: Any = None,
    ) -> MemoryStats:
        """Collect statistics from all memory subsystems."""
        stats = MemoryStats()

        if ltm is not None and hasattr(ltm, "stats"):
            try:
                ltm_stats = ltm.stats()
                stats.ltm_total = ltm_stats.get("total", 0)
                stats.ltm_avg_importance = ltm_stats.get("avg_importance", 0.0)
                stats.ltm_total_accesses = ltm_stats.get("total_accesses", 0)
                stats.ltm_tags = ltm_stats.get("tags", 0)
            except Exception as exc:
                logger.debug("LTM stats collection failed: %s", exc)

        if stm is not None and hasattr(stm, "stats"):
            try:
                stm_stats = stm.stats()
                stats.stm_total = stm_stats.get("total", 0)
                stats.stm_active = stm_stats.get("active", 0)
                stats.stm_promoted = stm_stats.get("promoted", 0)
                stats.stm_avg_importance = stm_stats.get("avg_importance", 0.0)
            except Exception as exc:
                logger.debug("STM stats collection failed: %s", exc)

        if episodic is not None and hasattr(episodic, "stats"):
            try:
                ep_stats = episodic.stats()
                stats.episodic_total = ep_stats.get("total", 0)
                stats.episodic_success_rate = ep_stats.get("success_rate", 0.0)
            except Exception as exc:
                logger.debug("Episodic stats collection failed: %s", exc)

        if graph is not None and hasattr(graph, "stats"):
            try:
                g_stats = graph.stats()
                stats.graph_nodes = g_stats.get("nodes", 0)
                stats.graph_edges = g_stats.get("edges", 0)
                stats.graph_avg_degree = g_stats.get("avg_degree", 0.0)
                stats.graph_density = g_stats.get("density", 0.0)
            except Exception as exc:
                logger.debug("Graph stats collection failed: %s", exc)

        if kb is not None and hasattr(kb, "stats"):
            try:
                kb_stats = kb.stats()
                stats.kb_documents = kb_stats.get("documents", 0)
                stats.kb_chunks = kb_stats.get("chunks", 0)
            except Exception as exc:
                logger.debug("KB stats collection failed: %s", exc)

        # Overall
        stats.total_memories = stats.ltm_total + stats.stm_total + stats.episodic_total
        stats.memory_types = {
            "ltm": stats.ltm_total,
            "stm": stats.stm_total,
            "episodic": stats.episodic_total,
            "graph": stats.graph_nodes,
            "kb": stats.kb_documents,
        }

        self._history.append(stats)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return stats

    def get_history(self, n: int = 10) -> list[MemoryStats]:
        """Get last n stats snapshots."""
        return self._history[-n:]

    def record_store(self, memory_type: str) -> None:
        """Record a memory store event."""
        pass  # Stats are collected on-demand via collect()

    def record_recall(self, keyword: str, result_count: int) -> None:
        """Record a memory recall event."""
        pass  # Stats are collected on-demand via collect()

    def record_search(self, query: str, result_count: int) -> None:
        """Record a unified search event."""
        pass  # Stats are collected on-demand via collect()

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics snapshot."""
        if self._history:
            return self._history[-1].to_dict()
        return {}

    def get_trend(self) -> dict[str, Any]:
        """Get trend analysis from history."""
        if len(self._history) < 2:
            return {"trend": "insufficient_data"}
        recent = self._history[-10:]
        if len(recent) < 2:
            return {"trend": "insufficient_data"}

        first = recent[0]
        last = recent[-1]
        return {
            "ltm_growth": last.ltm_total - first.ltm_total,
            "stm_growth": last.stm_total - first.stm_total,
            "graph_growth": last.graph_nodes - first.graph_nodes,
            "kb_growth": last.kb_documents - first.kb_documents,
            "time_span_seconds": last.timestamp - first.timestamp,
        }
