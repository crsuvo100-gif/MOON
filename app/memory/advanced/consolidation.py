"""Memory consolidation pipeline -- moves important memories across subsystems.

Professional AI assistants don't just store memories in isolation; they
consolidate: promote important short-term items to long-term, extract
lessons from episodic outcomes, build graph associations between related
memories, and index everything into the knowledge base for semantic search.

This module runs periodically (via MemoryMaintenance) and on-demand after
significant interactions.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class ConsolidationPipeline:
    """Consolidates memories across all subsystems.

    Pipeline stages:
    1. STM -> LTM promotion (important short-term items become durable)
    2. Episodic -> LTM extraction (lessons from past tasks become facts)
    3. LTM -> KB indexing (long-term facts become semantically searchable)
    4. Graph building (related memories get linked)
    5. Decay (unused memories lose importance over time)
    """

    def __init__(
        self,
        short_term=None,
        long_term=None,
        episodic=None,
        graph=None,
        knowledge_base=None,
        consolidator=None,
    ) -> None:
        self._stm = short_term
        self._ltm = long_term
        self._episodic = episodic
        self._graph = graph
        self._kb = knowledge_base
        self._consolidator = consolidator
        self._last_consolidation = 0.0
        self._consolidation_count = 0

    async def consolidate(self, force: bool = False) -> dict[str, Any]:
        """Run the full consolidation pipeline.

        Args:
            force: If True, run even if recently consolidated.

        Returns:
            Summary dict with counts from each stage.
        """
        now = time.time()
        if not force and now - self._last_consolidation < 300:  # 5 min cooldown
            return {"skipped": True, "reason": "cooldown"}

        results: dict[str, Any] = {
            "stm_promoted": 0,
            "episodic_extracted": 0,
            "ltm_indexed": 0,
            "graph_links": 0,
            "decayed": 0,
        }

        try:
            # Stage 1: STM -> LTM promotion
            results["stm_promoted"] = await self._promote_stm_to_ltm()

            # Stage 2: Episodic -> LTM extraction
            results["episodic_extracted"] = await self._extract_episodic_lessons()

            # Stage 3: LTM -> KB indexing
            results["ltm_indexed"] = await self._index_ltm_to_kb()

            # Stage 4: Graph building
            results["graph_links"] = await self._build_graph_links()

            # Stage 5: Decay
            results["decayed"] = await self._decay_memories()

        except Exception as exc:
            logger.warning("Consolidation pipeline error: %s", exc)

        self._last_consolidation = now
        self._consolidation_count += 1
        results["total_stages"] = 5
        results["consolidation_id"] = self._consolidation_count
        logger.info(
            "Consolidation #%d: %d promoted, %d extracted, %d indexed, %d links, %d decayed",
            self._consolidation_count,
            results["stm_promoted"],
            results["episodic_extracted"],
            results["ltm_indexed"],
            results["graph_links"],
            results["decayed"],
        )
        return results

    async def _promote_stm_to_ltm(self) -> int:
        """Promote high-relevance STM items to LTM."""
        if self._stm is None or self._ltm is None:
            return 0
        try:
            # Use the enhanced STM's auto-promote if available
            if hasattr(self._stm, 'auto_promote'):
                return await self._stm.auto_promote(self._ltm)
            # Fallback: manual promotion of items above threshold
            promoted = 0
            if hasattr(self._stm, '_items'):
                for item in list(self._stm._items):
                    if item.relevance >= 0.7:
                        await self._ltm.store({
                            "content": item.content,
                            "tags": ["promoted_from_stm"],
                            "metadata": {"relevance": item.relevance},
                        })
                        promoted += 1
            return promoted
        except Exception as exc:
            logger.debug("STM->LTM promotion failed: %s", exc)
            return 0

    async def _extract_episodic_lessons(self) -> int:
        """Extract lessons from episodic memory into LTM."""
        if self._episodic is None or self._ltm is None:
            return 0
        try:
            extracted = 0
            for ep in self._episodic._eps:
                if ep.lesson and len(ep.lesson) > 10:
                    # Check if already extracted (avoid duplicates)
                    existing = await self._ltm.query(ep.lesson[:50], limit=1)
                    if not existing:
                        await self._ltm.store({
                            "content": f"[lesson from: {ep.goal[:80]}] {ep.lesson}",
                            "tags": ["episodic_lesson", "auto-extracted"],
                            "metadata": {"source": "episodic", "success": ep.success},
                        })
                        extracted += 1
            return extracted
        except Exception as exc:
            logger.debug("Episodic->LTM extraction failed: %s", exc)
            return 0

    async def _index_ltm_to_kb(self) -> int:
        """Index LTM entries into the knowledge base for semantic search."""
        if self._ltm is None or self._kb is None:
            return 0
        try:
            entries = await self._ltm.all()
            indexed = 0
            for entry in entries:
                doc_id = f"ltm_{entry.id}"
                # Check if already indexed
                if hasattr(self._kb, '_doc_chunks') and doc_id in self._kb._doc_chunks:
                    continue
                await self._kb.index_document(doc_id, entry.content)
                indexed += 1
            return indexed
        except Exception as exc:
            logger.debug("LTM->KB indexing failed: %s", exc)
            return 0

    async def _build_graph_links(self) -> int:
        """Build graph associations between related memories."""
        if self._graph is None or self._ltm is None:
            return 0
        try:
            entries = await self._ltm.all()
            links = 0
            # Link entries that share tags or keywords
            for i, e1 in enumerate(entries):
                for e2 in entries[i+1:]:
                    # Simple association: shared tags
                    shared_tags = set(e1.tags) & set(e2.tags)
                    if shared_tags:
                        await self._graph.add_edge(
                            f"ltm_{e1.id}", f"ltm_{e2.id}",
                            weight=0.5 + 0.1 * len(shared_tags),
                            edge_type="shared_tags",
                        )
                        links += 1
            return links
        except Exception as exc:
            logger.debug("Graph link building failed: %s", exc)
            return 0

    async def _decay_memories(self) -> int:
        """Decay importance of unused memories."""
        if self._ltm is None:
            return 0
        try:
            if hasattr(self._ltm, 'decay'):
                return await self._ltm.decay()
            return 0
        except Exception as exc:
            logger.debug("Memory decay failed: %s", exc)
            return 0

    def stats(self) -> dict[str, Any]:
        """Return consolidation statistics."""
        return {
            "consolidation_count": self._consolidation_count,
            "last_consolidation": self._last_consolidation,
        }
