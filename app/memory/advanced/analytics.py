"""Memory analytics -- track and report memory system health.

Professional AI assistants monitor their memory system's effectiveness:
hit rates, coverage gaps, consolidation efficiency, and memory growth
patterns. This module provides visibility into how well the memory system
is working and suggests improvements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryHealthReport:
    """A comprehensive health report for the memory system."""
    timestamp: float = field(default_factory=time.time)

    # Subsystem sizes
    stm_count: int = 0
    ltm_count: int = 0
    episodic_count: int = 0
    graph_node_count: int = 0
    kb_doc_count: int = 0

    # Search effectiveness
    total_searches: int = 0
    total_results: int = 0
    avg_results_per_search: float = 0.0
    zero_result_searches: int = 0

    # Consolidation
    consolidation_count: int = 0
    last_consolidation: float = 0.0
    items_promoted: int = 0
    items_extracted: int = 0
    items_indexed: int = 0

    # Compaction
    compaction_count: int = 0
    items_compacted: int = 0

    # Proactive surfacing
    proactive_injections: int = 0
    proactive_tasks: int = 0

    # Session continuity
    session_count: int = 0
    total_tasks: int = 0
    total_lessons: int = 0

    # Derived metrics
    @property
    def total_memories(self) -> int:
        return self.stm_count + self.ltm_count + self.episodic_count + self.graph_node_count

    @property
    def search_hit_rate(self) -> float:
        if self.total_searches == 0:
            return 0.0
        return (self.total_searches - self.zero_result_searches) / self.total_searches

    @property
    def proactive_rate(self) -> float:
        if self.proactive_tasks == 0:
            return 0.0
        return self.proactive_injections / self.proactive_tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "subsystem_sizes": {
                "stm": self.stm_count,
                "ltm": self.ltm_count,
                "episodic": self.episodic_count,
                "graph_nodes": self.graph_node_count,
                "kb_docs": self.kb_doc_count,
            },
            "total_memories": self.total_memories,
            "search_effectiveness": {
                "total_searches": self.total_searches,
                "total_results": self.total_results,
                "avg_results": round(self.avg_results_per_search, 2),
                "hit_rate": round(self.search_hit_rate, 3),
                "zero_result_searches": self.zero_result_searches,
            },
            "consolidation": {
                "count": self.consolidation_count,
                "last": self.last_consolidation,
                "items_promoted": self.items_promoted,
                "items_extracted": self.items_extracted,
                "items_indexed": self.items_indexed,
            },
            "compaction": {
                "count": self.compaction_count,
                "items_compacted": self.items_compacted,
            },
            "proactive": {
                "injections": self.proactive_injections,
                "tasks": self.proactive_tasks,
                "rate": round(self.proactive_rate, 2),
            },
            "sessions": {
                "count": self.session_count,
                "total_tasks": self.total_tasks,
                "total_lessons": self.total_lessons,
            },
        }


class MemoryAnalytics:
    """Tracks and reports memory system health and effectiveness.

    Usage:
        analytics = MemoryAnalytics(memory_manager)
        # After each search:
        analytics.record_search(query, result_count)
        # After consolidation:
        analytics.record_consolidation(results)
        # Periodically:
        report = await analytics.generate_report()
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._total_searches = 0
        self._total_results = 0
        self._zero_result_searches = 0
        self._consolidation_count = 0
        self._items_promoted = 0
        self._items_extracted = 0
        self._items_indexed = 0
        self._compaction_count = 0
        self._items_compacted = 0
        self._proactive_injections = 0
        self._proactive_tasks = 0
        self._search_history: list[dict[str, Any]] = []
        self._max_history = 1000

    def record_search(self, query: str, result_count: int) -> None:
        """Record a memory search for analytics."""
        self._total_searches += 1
        self._total_results += result_count
        if result_count == 0:
            self._zero_result_searches += 1
        self._search_history.append({
            "query": query[:100],
            "results": result_count,
            "timestamp": time.time(),
        })
        if len(self._search_history) > self._max_history:
            self._search_history = self._search_history[-self._max_history:]

    def record_consolidation(self, results: dict[str, Any]) -> None:
        """Record a consolidation run."""
        self._consolidation_count += 1
        self._items_promoted += results.get("stm_promoted", 0)
        self._items_extracted += results.get("episodic_extracted", 0)
        self._items_indexed += results.get("ltm_indexed", 0)

    def record_compaction(self, results: list) -> None:
        """Record a compaction run."""
        self._compaction_count += 1
        for r in results:
            self._items_compacted += r.items_removed

    def record_proactive(self, injection_count: int) -> None:
        """Record proactive memory surfacing."""
        self._proactive_tasks += 1
        self._proactive_injections += injection_count

    async def generate_report(self) -> MemoryHealthReport:
        """Generate a comprehensive memory health report."""
        report = MemoryHealthReport(
            total_searches=self._total_searches,
            total_results=self._total_results,
            avg_results_per_search=self._total_results / max(1, self._total_searches),
            zero_result_searches=self._zero_result_searches,
            consolidation_count=self._consolidation_count,
            items_promoted=self._items_promoted,
            items_extracted=self._items_extracted,
            items_indexed=self._items_indexed,
            compaction_count=self._compaction_count,
            items_compacted=self._items_compacted,
            proactive_injections=self._proactive_injections,
            proactive_tasks=self._proactive_tasks,
        )

        # Fill in subsystem sizes from memory manager
        if self._mm is not None:
            try:
                if hasattr(self._mm, 'short_term'):
                    report.stm_count = len(self._mm.short_term)
                if hasattr(self._mm, 'long_term'):
                    report.ltm_count = len(await self._mm.long_term.all())
                if hasattr(self._mm, 'episodic'):
                    report.episodic_count = len(self._mm.episodic._eps) if hasattr(self._mm.episodic, '_eps') else 0
                if hasattr(self._mm, 'graph'):
                    report.graph_node_count = len(self._mm.graph._nodes) if hasattr(self._mm.graph, '_nodes') else 0
                if hasattr(self._mm, 'knowledge_base'):
                    kb = self._mm.knowledge_base
                    report.kb_doc_count = len(kb._docs) if hasattr(kb, '_docs') else 0
            except Exception as exc:
                logger.debug("Failed to get subsystem sizes: %s", exc)

        return report

    def get_slow_queries(self, threshold: float = 1.0, limit: int = 10) -> list[dict[str, Any]]:
        """Get searches that returned zero results (potential gaps)."""
        return [h for h in self._search_history if h["results"] == 0][-limit:]

    def stats(self) -> dict[str, Any]:
        """Return analytics statistics."""
        return {
            "total_searches": self._total_searches,
            "total_results": self._total_results,
            "hit_rate": round(1.0 - (self._zero_result_searches / max(1, self._total_searches)), 3),
            "consolidation_count": self._consolidation_count,
            "compaction_count": self._compaction_count,
            "proactive_injections": self._proactive_injections,
        }
