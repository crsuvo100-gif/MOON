"""memory_maintenance.py -- Periodic memory maintenance tasks.

Professional AI assistants regularly maintain their memory: decay unused
entries, promote important short-term items, clean up expired entries,
and rebalance the memory graph. This module provides a maintenance scheduler
that runs these tasks periodically.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` when it is awaitable, otherwise return it as-is.

    Memory backends are inconsistent by design: ``EnhancedLongTermMemory.decay``
    and ``EnhancedShortTermMemory.auto_promote`` are coroutines, but
    ``EnhancedShortTermMemory.expire_old`` is a plain synchronous method that
    returns an ``int``. Unconditionally awaiting the sync one raised
    ``TypeError: object int can't be used in 'await' expression`` on every
    maintenance tick (logged as "Maintenance expiry failed: 'int' object can't
    be awaited") and silently disabled short-term-memory expiry.
    """
    if inspect.isawaitable(value):
        return await value
    return value


class MemoryMaintenance:
    """Periodic memory maintenance scheduler.

    Runs maintenance tasks at configurable intervals:
    - LTM decay: reduce importance of unused memories
    - STM promotion: auto-promote important short-term items
    - STM expiry: remove expired short-term items
    - Graph cleanup: remove orphaned nodes
    - Stats collection: snapshot memory health
    """

    def __init__(
        self,
        ltm: Any = None,
        stm: Any = None,
        graph: Any = None,
        episodic: Any = None,
        kb: Any = None,
        stats_collector: Any = None,
        decay_interval: float = 3600.0,  # 1 hour
        promotion_interval: float = 300.0,  # 5 minutes
        expiry_interval: float = 600.0,  # 10 minutes
        stats_interval: float = 1800.0,  # 30 minutes
    ) -> None:
        self._ltm = ltm
        self._stm = stm
        self._graph = graph
        self._episodic = episodic
        self._kb = kb
        self._stats = stats_collector
        self._decay_interval = decay_interval
        self._promotion_interval = promotion_interval
        self._expiry_interval = expiry_interval
        self._stats_interval = stats_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_decay = 0.0
        self._last_promotion = 0.0
        self._last_expiry = 0.0
        self._last_stats = 0.0

    async def start(self) -> None:
        """Start the maintenance loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._maintenance_loop())
        logger.info("Memory maintenance started")

    async def stop(self) -> None:
        """Stop the maintenance loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Memory maintenance stopped")

    async def run_all(self) -> dict[str, Any]:
        """Run all maintenance tasks once (alias for run_once)."""
        return await self.run_once()

    async def run_once(self) -> dict[str, Any]:
        """Run all maintenance tasks once. Returns summary."""
        results = {}
        if self._ltm is not None and hasattr(self._ltm, "decay"):
            try:
                results["ltm_decayed"] = await self._ltm.decay()
            except Exception as exc:
                logger.warning("LTM decay failed: %s", exc)
                results["ltm_decayed"] = 0
        if self._stm is not None and hasattr(self._stm, "auto_promote"):
            try:
                results["stm_promoted"] = await self._stm.auto_promote()
            except Exception as exc:
                logger.warning("STM auto-promote failed: %s", exc)
                results["stm_promoted"] = 0
        if self._stm is not None and hasattr(self._stm, "expire_old"):
            try:
                results["stm_expired"] = await _maybe_await(self._stm.expire_old())
            except Exception as exc:
                logger.warning("STM expiry failed: %s", exc)
                results["stm_expired"] = 0
        if self._stats is not None and hasattr(self._stats, "collect"):
            try:
                stats = await self._stats.collect(
                    ltm=self._ltm,
                    stm=self._stm,
                    episodic=self._episodic,
                    graph=self._graph,
                    kb=self._kb,
                )
                results["stats"] = stats.to_dict()
            except Exception as exc:
                logger.warning("Stats collection failed: %s", exc)
        return results

    async def _maintenance_loop(self) -> None:
        """Main maintenance loop."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute
                if not self._running:
                    break
                now = asyncio.get_event_loop().time()
                if now - self._last_decay >= self._decay_interval:
                    await self._run_decay()
                    self._last_decay = now
                if now - self._last_promotion >= self._promotion_interval:
                    await self._run_promotion()
                    self._last_promotion = now
                if now - self._last_expiry >= self._expiry_interval:
                    await self._run_expiry()
                    self._last_expiry = now
                if now - self._last_stats >= self._stats_interval:
                    await self._run_stats()
                    self._last_stats = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Maintenance loop error: %s", exc)
                await asyncio.sleep(60)

    async def _run_decay(self) -> None:
        if self._ltm is not None and hasattr(self._ltm, "decay"):
            try:
                decayed = await self._ltm.decay()
                if decayed:
                    logger.info("Maintenance: decayed %d LTM entries", decayed)
            except Exception as exc:
                logger.warning("Maintenance decay failed: %s", exc)

    async def _run_promotion(self) -> None:
        if self._stm is not None and hasattr(self._stm, "auto_promote"):
            try:
                promoted = await self._stm.auto_promote()
                if promoted:
                    logger.info("Maintenance: promoted %d STM items", promoted)
            except Exception as exc:
                logger.warning("Maintenance promotion failed: %s", exc)

    async def _run_expiry(self) -> None:
        if self._stm is not None and hasattr(self._stm, "expire_old"):
            try:
                expired = await _maybe_await(self._stm.expire_old())
                if expired:
                    logger.info("Maintenance: expired %d STM items", expired)
            except Exception as exc:
                logger.warning("Maintenance expiry failed: %s", exc)

    async def _run_stats(self) -> None:
        if self._stats is not None and hasattr(self._stats, "collect"):
            try:
                await self._stats.collect(
                    ltm=self._ltm,
                    stm=self._stm,
                    episodic=self._episodic,
                    graph=self._graph,
                    kb=self._kb,
                )
            except Exception as exc:
                logger.warning("Maintenance stats failed: %s", exc)
