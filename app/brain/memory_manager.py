"""memory_manager.py -- coordinates short/long-term memory and knowledge base.

Enhanced with unified search, memory graph, stats, and maintenance.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.memory.episodic_memory import EpisodicMemory

logger = get_logger(__name__)

EPISODE_PATH = Path(__file__).resolve().parent.parent / "memory" / "episodes.json"

if TYPE_CHECKING:
    from app.memory.knowledge_base import KnowledgeBase
    from app.memory.long_term import LongTermMemory
    from app.memory.short_term import ShortTermMemory
    from app.memory.enhanced_long_term import EnhancedLongTermMemory
    from app.memory.enhanced_short_term import EnhancedShortTermMemory
    from app.memory.memory_graph import MemoryGraph
    from app.memory.memory_stats import MemoryStatsCollector
    from app.memory.memory_maintenance import MemoryMaintenance


class MemoryManager:
    """Unified interface over the memory subsystems.

    Supports both base and enhanced memory classes. When enhanced classes
    are provided, enables unified search, memory graph, stats, and
    maintenance tasks.
    """

    def __init__(
        self,
        short_term: ShortTermMemory | EnhancedShortTermMemory | None = None,
        long_term: LongTermMemory | EnhancedLongTermMemory | None = None,
        knowledge_base: KnowledgeBase | None = None,
        episodic: EpisodicMemory | None = None,
        memory_graph: MemoryGraph | None = None,
        stats_collector: MemoryStatsCollector | None = None,
        maintenance: MemoryMaintenance | None = None,
    ) -> None:
        self._stm = short_term
        self._ltm = long_term
        self._kb = knowledge_base
        self.episodic = episodic or EpisodicMemory()
        self._graph = memory_graph
        self._stats = stats_collector
        self._maintenance = maintenance
        self._load_episodes()

    def _load_episodes(self) -> None:
        try:
            if EPISODE_PATH.exists():
                data = json.loads(EPISODE_PATH.read_text())
                for d in data:
                    self.episodic.record(
                        goal=d.get("goal", ""),
                        outcome=d.get("outcome", ""),
                        lesson=d.get("lesson", ""),
                        success=bool(d.get("success", True)),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load episodes (%s); starting fresh", exc)

    def save_episodes(self) -> None:
        try:
            eps = [
                {"goal": e.goal, "outcome": e.outcome, "lesson": e.lesson, "success": e.success}
                for e in self.episodic._eps
            ]
            EPISODE_PATH.parent.mkdir(parents=True, exist_ok=True)
            EPISODE_PATH.write_text(json.dumps(eps, indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save episodes (%s)", exc)

    async def setup(self) -> None:
        if self._ltm is not None:
            await self._ltm.setup()
        if self._kb is not None:
            await self._kb.setup()
        if self._graph is not None:
            await self._graph.setup()

    async def remember(self, content: str, *, long_term: bool = False, tags: list[str] | None = None, importance: float = 0.5) -> None:
        """Store content in memory.

        Args:
            content: The content to remember.
            long_term: If True, also store in long-term memory.
            tags: Optional tags for categorization.
            importance: Importance score (0-1) for enhanced LTM.
        """
        if self._stm is not None:
            self._stm.add(content)
        if self._ltm is not None and long_term:
            if hasattr(self._ltm, '_enhanced_entries'):
                await self._ltm.store({"content": content, "tags": tags or []}, importance=importance)
            else:
                await self._ltm.store({"content": content, "tags": tags or []})
        if self._graph is not None:
            await self._graph.add_memory(content, tags=tags, importance=importance)
        if self._stats is not None:
            self._stats.record_store("long_term" if long_term else "short_term")

    async def learn(self, content: str, *, tags: list[str] | None = None, importance: float = 0.5) -> None:
        """Consolidate ``content`` into MOON's durable brain."""
        if self._ltm is not None:
            if hasattr(self._ltm, '_enhanced_entries'):
                await self._ltm.store({"content": content, "tags": tags or []}, importance=importance)
            else:
                await self._ltm.store({"content": content, "tags": tags or []})
        else:
            if self._stm is not None:
                self._stm.add(content)
        if self._kb is not None:
            try:
                doc_id = f"learn_{int(time.time() * 1000)}_{abs(hash(content)) & 0xFFFF}"
                await self._kb.index_document(doc_id, content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("learn: KB index skipped (%s)", exc)
        if self._graph is not None:
            await self._graph.add_memory(content, tags=tags, importance=importance)
        if self._stats is not None:
            self._stats.record_store("knowledge_base")

    async def recall(self, keyword: str, limit: int = 5) -> list[str]:
        """Recall memories matching keyword across all memory types."""
        results: list[str] = []
        if self._ltm is not None:
            entries = await self._ltm.query(keyword, limit=limit)
            results.extend([e.content for e in entries])
        if self._stm is not None and len(results) < limit:
            if hasattr(self._stm, 'search'):
                stm_results = self._stm.search(keyword, limit=limit - len(results))
                results.extend(stm_results)
        if self._graph is not None and len(results) < limit:
            graph_results = await self._graph.search(keyword, limit=limit - len(results))
            results.extend([r for r in graph_results if r not in results])
        if self._stats is not None:
            self._stats.record_recall(keyword, len(results))
        return results[:limit]

    async def unified_search(self, query: str, limit: int = 10) -> dict[str, list[str]]:
        """Search across all memory types and return categorized results."""
        results: dict[str, list[str]] = {
            "long_term": [],
            "short_term": [],
            "knowledge_base": [],
            "episodic": [],
            "graph": [],
        }
        if self._ltm is not None:
            entries = await self._ltm.query(query, limit=limit)
            results["long_term"] = [e.content for e in entries]
        if self._stm is not None:
            if hasattr(self._stm, 'search'):
                results["short_term"] = self._stm.search(query, limit=limit)
        if self._kb is not None:
            kb_results = await self._kb.search(query, top_k=limit)
            results["knowledge_base"] = [r.get("text", "") for r in kb_results]
        if self.episodic is not None:
            ep_results = self.episodic.recall(query, k=limit)
            results["episodic"] = [e.outcome for e in ep_results]
        if self._graph is not None:
            results["graph"] = await self._graph.search(query, limit=limit)
        if self._stats is not None:
            self._stats.record_search(query, sum(len(v) for v in results.values()))
        return results

    async def index_document(self, doc_id: str, text: str) -> int:
        if self._kb is not None:
            return await self._kb.index_document(doc_id, text)
        logger.warning("No knowledge base configured; skipping index")
        return 0

    async def semantic_recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic recall using embeddings."""
        if self._kb is not None:
            return await self._kb.search(query, top_k=top_k)
        return []

    async def get_stats(self) -> dict[str, Any]:
        """Get comprehensive memory statistics."""
        stats: dict[str, Any] = {
            "short_term": {"total": 0},
            "long_term": {"total": 0},
            "episodic": {"total": len(self.episodic._eps)},
        }
        if self._stm is not None:
            if hasattr(self._stm, 'stats'):
                stats["short_term"] = self._stm.stats()
            else:
                stats["short_term"]["total"] = len(self._stm)
        if self._ltm is not None:
            if hasattr(self._ltm, 'stats'):
                stats["long_term"] = self._ltm.stats()
            elif hasattr(self._ltm, '_entries'):
                stats["long_term"]["total"] = len(self._ltm._entries)
        if self._graph is not None:
            stats["graph"] = self._graph.stats()
        if self._stats is not None:
            stats["access"] = self._stats.get_stats()
        return stats

    async def run_maintenance(self) -> dict[str, Any]:
        """Run memory maintenance tasks (decay, promotion, cleanup)."""
        results: dict[str, Any] = {}
        if self._maintenance is not None:
            results = await self._maintenance.run_all()
        return results
