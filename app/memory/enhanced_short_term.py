"""enhanced_short_term.py -- Short-term memory with automatic promotion to LTM.

Professional AI assistants don't just keep a rolling window of recent items --
they promote important items to long-term memory when they exceed a
relevance threshold, and they track access patterns to know what's worth
keeping. This module upgrades the plain deque into a real working memory.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ShortTermItem:
    """A short-term memory item with relevance scoring."""
    content: str
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    relevance: float = 0.5  # 0.0 - 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.access_count += 1
        # Boost relevance on access (capped at 1.0)
        self.relevance = min(1.0, self.relevance + 0.1)


class EnhancedShortTermMemory:
    """Short-term memory with relevance scoring and auto-promotion to LTM.

    Features:
    - Relevance scoring (0-1) with automatic boosting on access
    - Auto-promotion to LTM when relevance exceeds threshold
    - Access frequency tracking
    - Configurable max size with FIFO eviction
    - Callback-based promotion (no direct LTM dependency)
    """

    def __init__(
        self,
        max_items: int = 50,
        auto_promote_threshold: float = 0.7,
        promote_callback: Callable[[str, float], None] | None = None,
    ) -> None:
        self._max_items = max_items
        self._threshold = auto_promote_threshold
        self._promote_callback = promote_callback
        self._items: deque[ShortTermItem] = deque(maxlen=max_items)
        self._lock = asyncio.Lock()
        self._promoted_count = 0

    def add(self, content: str, relevance: float = 0.5, metadata: dict[str, Any] | None = None) -> None:
        """Add an item to short-term memory."""
        item = ShortTermItem(
            content=content,
            relevance=max(0.0, min(1.0, relevance)),
            metadata=metadata or {},
        )
        self._items.append(item)
        # Check for promotion
        if item.relevance >= self._threshold and self._promote_callback:
            try:
                self._promote_callback(content, item.relevance)
                self._promoted_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("STM promotion callback failed: %s", exc)

    def get(self, index: int) -> str | None:
        """Get item by index (0 = most recent)."""
        try:
            item = self._items[-(index + 1)]
            item.touch()
            return item.content
        except IndexError:
            return None

    def search(self, keyword: str, limit: int = 5) -> list[str]:
        """Search short-term items by keyword."""
        kw = keyword.lower()
        results = []
        for item in reversed(self._items):
            if kw in item.content.lower():
                item.touch()
                results.append(item.content)
                if len(results) >= limit:
                    break
        return results

    def recent(self, n: int = 10) -> list[str]:
        """Get n most recent items."""
        return [item.content for item in list(self._items)[-n:]]

    def clear(self) -> None:
        """Clear all short-term items."""
        self._items.clear()

    async def auto_promote(self, ltm: Any = None) -> int:
        """Promote items above threshold to LTM. Returns count promoted."""
        promoted = 0
        for item in list(self._items):
            if item.relevance >= self._threshold:
                if ltm is not None:
                    try:
                        await ltm.store({"content": item.content}, importance=item.relevance)
                        promoted += 1
                    except Exception as exc:
                        logger.debug("Auto-promote failed: %s", exc)
                elif self._promote_callback:
                    self._promote_callback(item.content, item.relevance)
                    promoted += 1
        return promoted

    def expire_old(self, max_age_seconds: float = 300.0) -> int:
        """Remove items older than max_age_seconds. Returns count expired."""
        now = time.time()
        before = len(self._items)
        self._items = deque(
            [item for item in self._items if now - item.created_at < max_age_seconds],
            maxlen=self._max_items,
        )
        return before - len(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def stats(self) -> dict[str, Any]:
        """Return short-term memory statistics."""
        if not self._items:
            return {"total": 0, "avg_relevance": 0.0, "promoted": self._promoted_count}
        avg_rel = sum(i.relevance for i in self._items) / len(self._items)
        return {
            "total": len(self._items),
            "avg_relevance": round(avg_rel, 3),
            "promoted": self._promoted_count,
        }
