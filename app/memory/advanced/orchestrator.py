"""Advanced Memory Orchestrator -- ties all advanced memory features together.

This is the main entry point for the advanced memory system. It wires together:
- UnifiedSearch: search across all memory types simultaneously
- ConsolidationPipeline: promote, extract, index, link, and decay memories
- ProactiveMemory: automatically surface relevant context before tasks
- SessionContinuity: maintain memory across restarts
- MemoryCompactor: compress older memories to manage context space
- MemoryAnalytics: track and report memory system health

Usage:
    from app.memory.advanced import AdvancedMemoryOrchestrator

    amo = AdvancedMemoryOrchestrator(memory_manager)
    await amo.setup()

    # Before a task:
    context = await amo.before_task("analyze this vulnerability")

    # After a task:
    await amo.after_task("analyze this vulnerability", result, success=True)

    # Periodically:
    await amo.maintenance()

    # On shutdown:
    await amo.shutdown()
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.config.logging import get_logger
from app.memory.advanced.unified_search import UnifiedSearcher, UnifiedResult
from app.memory.advanced.consolidation import ConsolidationPipeline
from app.memory.advanced.proactive_memory import ProactiveMemory, ProactiveContext
from app.memory.advanced.session_continuity import SessionContinuity
from app.memory.advanced.compaction import MemoryCompactor, CompactionResult
from app.memory.advanced.analytics import MemoryAnalytics, MemoryHealthReport

logger = get_logger(__name__)


class AdvancedMemoryOrchestrator:
    """Orchestrates all advanced memory features.

    This is a facade that provides a simple interface to the full advanced
    memory system. It coordinates between all the specialized modules and
    integrates with the existing MemoryManager.
    """

    def __init__(
        self,
        memory_manager=None,
        llm_service=None,
        session_id: str = "",
        enable_consolidation: bool = True,
        enable_proactive: bool = True,
        enable_compaction: bool = True,
        enable_analytics: bool = True,
        enable_continuity: bool = True,
    ) -> None:
        self._mm = memory_manager
        self._llm = llm_service
        self._session_id = session_id or f"session_{int(time.time())}"

        # Feature flags
        self._enable_consolidation = enable_consolidation
        self._enable_proactive = enable_proactive
        self._enable_compaction = enable_compaction
        self._enable_analytics = enable_analytics
        self._enable_continuity = enable_continuity

        # Sub-modules (initialized in setup)
        self._searcher: UnifiedSearcher | None = None
        self._consolidation: ConsolidationPipeline | None = None
        self._proactive: ProactiveMemory | None = None
        self._continuity: SessionContinuity | None = None
        self._compactor: MemoryCompactor | None = None
        self._analytics: MemoryAnalytics | None = None

        self._setup_complete = False
        self._maintenance_interval = 300  # 5 minutes
        self._last_maintenance = 0.0
        self._shutdown = False

    async def setup(self) -> None:
        """Initialize all advanced memory sub-modules."""
        if self._setup_complete:
            return

        logger.info("AdvancedMemoryOrchestrator: setting up...")

        # Initialize unified searcher
        self._searcher = UnifiedSearcher(
            short_term=getattr(self._mm, '_stm', None),
            long_term=getattr(self._mm, '_ltm', None),
            episodic=getattr(self._mm, 'episodic', None),
            graph=getattr(self._mm, '_graph', None),
            knowledge_base=getattr(self._mm, '_kb', None),
        )

        # Initialize consolidation pipeline
        if self._enable_consolidation:
            self._consolidation = ConsolidationPipeline(
                short_term=getattr(self._mm, '_stm', None),
                long_term=getattr(self._mm, '_ltm', None),
                episodic=getattr(self._mm, 'episodic', None),
                graph=getattr(self._mm, '_graph', None),
                knowledge_base=getattr(self._mm, '_kb', None),
                consolidator=getattr(self._mm, '_consolidator', None),
            )

        # Initialize proactive memory
        if self._enable_proactive:
            self._proactive = ProactiveMemory(
                memory_manager=self._mm,
                searcher=self._searcher,
            )

        # Initialize session continuity
        if self._enable_continuity:
            self._continuity = SessionContinuity()
            await self._continuity.setup(self._session_id)

        # Initialize compactor
        if self._enable_compaction:
            self._compactor = MemoryCompactor(
                memory_manager=self._mm,
                llm_service=self._llm,
            )

        # Initialize analytics
        if self._enable_analytics:
            self._analytics = MemoryAnalytics(memory_manager=self._mm)

        self._setup_complete = True
        logger.info("AdvancedMemoryOrchestrator: setup complete")

    async def before_task(self, task_prompt: str) -> list[ProactiveContext]:
        """Get proactive memory context before executing a task.

        Args:
            task_prompt: The current task prompt.

        Returns:
            List of ProactiveContext to inject into the LLM context.
        """
        if not self._setup_complete:
            return []
        if self._proactive is None:
            return []

        try:
            context = await self._proactive.before_task(task_prompt)
            if self._analytics:
                self._analytics.record_proactive(len(context))
            return context
        except Exception as exc:
            logger.debug("before_task failed: %s", exc)
            return []

    async def after_task(
        self,
        task_prompt: str,
        result: str,
        success: bool = True,
        lesson: str = "",
    ) -> None:
        """Store task results in memory after completion.

        Args:
            task_prompt: The task that was executed.
            result: The result/output of the task.
            success: Whether the task succeeded.
            lesson: Optional explicit lesson to store.
        """
        if not self._setup_complete:
            return

        try:
            # Store in episodic + STM via proactive module
            if self._proactive:
                await self._proactive.after_task(task_prompt, result, success, lesson)

            # Record in session continuity
            if self._continuity:
                self._continuity.record_task(task_prompt, result, lesson)

            # Run consolidation if enabled
            if self._consolidation:
                await self._consolidation.consolidate()

        except Exception as exc:
            logger.debug("after_task failed: %s", exc)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        min_score: float = 0.1,
    ) -> list[UnifiedResult]:
        """Search across all memory types.

        Args:
            query: The search query.
            top_k: Maximum results to return.
            min_score: Minimum score threshold.

        Returns:
            List of UnifiedResult sorted by relevance.
        """
        if not self._setup_complete or self._searcher is None:
            return []

        try:
            searcher = self._searcher
            if searcher is None:
                return []
            results = await searcher.search(query, top_k, min_score)
            if self._analytics:
                self._analytics.record_search(query, len(results))
            return results
        except Exception as exc:
            logger.debug("search failed: %s", exc)
            return []

    async def maintenance(self) -> dict[str, Any]:
        """Run periodic maintenance: consolidation + compaction.

        Returns:
            Summary of maintenance operations.
        """
        if not self._setup_complete:
            return {"skipped": True, "reason": "not_setup"}

        now = time.time()
        if now - self._last_maintenance < self._maintenance_interval:
            return {"skipped": True, "reason": "cooldown"}

        self._last_maintenance = now
        results: dict[str, Any] = {}

        # Consolidation
        if self._consolidation:
            try:
                cons_results = await self._consolidation.consolidate(force=True)
                results["consolidation"] = cons_results
                if self._analytics:
                    self._analytics.record_consolidation(cons_results)
            except Exception as exc:
                logger.debug("maintenance consolidation failed: %s", exc)

        # Compaction
        if self._compactor:
            try:
                comp_results = await self._compactor.compact_all()
                results["compaction"] = [r.to_dict() for r in comp_results]
                if self._analytics:
                    self._analytics.record_compaction(comp_results)
            except Exception as exc:
                logger.debug("maintenance compaction failed: %s", exc)

        logger.info("AdvancedMemoryOrchestrator: maintenance complete")
        return results

    async def get_health_report(self) -> MemoryHealthReport | None:
        """Generate a comprehensive memory health report."""
        if not self._setup_complete or self._analytics is None:
            return None
        try:
            return await self._analytics.generate_report()
        except Exception as exc:
            logger.debug("health report failed: %s", exc)
            return None

    def get_continuity_context(self) -> list[dict[str, Any]]:
        """Get cross-session continuity context."""
        if self._continuity is None:
            return []
        return self._continuity.get_continuity_context()

    async def shutdown(self) -> None:
        """Shutdown the advanced memory orchestrator."""
        self._shutdown = True

        # Save session continuity
        if self._continuity:
            try:
                await self._continuity.shutdown()
            except Exception as exc:
                logger.debug("continuity shutdown failed: %s", exc)

        # Final consolidation
        if self._consolidation:
            try:
                await self._consolidation.consolidate(force=True)
            except Exception as exc:
                logger.debug("final consolidation failed: %s", exc)

        logger.info("AdvancedMemoryOrchestrator: shutdown complete")

    def stats(self) -> dict[str, Any]:
        """Return comprehensive statistics for all sub-modules."""
        stats: dict[str, Any] = {
            "session_id": self._session_id,
            "setup_complete": self._setup_complete,
            "features": {
                "consolidation": self._enable_consolidation,
                "proactive": self._enable_proactive,
                "compaction": self._enable_compaction,
                "analytics": self._enable_analytics,
                "continuity": self._enable_continuity,
            },
        }
        if self._consolidation:
            stats["consolidation"] = self._consolidation.stats()
        if self._proactive:
            stats["proactive"] = self._proactive.stats()
        if self._continuity:
            stats["continuity"] = self._continuity.stats()
        if self._compactor:
            stats["compaction"] = self._compactor.stats()
        if self._analytics:
            stats["analytics"] = self._analytics.stats()
        return stats
