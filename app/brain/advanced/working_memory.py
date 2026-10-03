"""Working memory with attention and decay for agent cognition.

Implements a bounded working memory that tracks items with attention scores,
recency, and importance. Items decay over time unless reinforced.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryItem:
    """An item in working memory."""
    content: str
    importance: float = 0.5  # 0..1
    attention: float = 0.0   # accumulated attention
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def score(self) -> float:
        """Combined score for retrieval ranking."""
        age = time.time() - self.timestamp
        recency = 1.0 / (1.0 + age / 60.0)  # decay over 60s
        return self.importance * 0.4 + self.attention * 0.3 + recency * 0.3

    def reinforce(self, boost: float = 0.1) -> None:
        """Reinforce this item (increase attention)."""
        self.attention = min(1.0, self.attention + boost)
        self.access_count += 1


class WorkingMemory:
    """Bounded working memory with attention-based retrieval.

    Maintains a fixed-capacity memory of items with importance scoring,
    attention tracking, and automatic eviction of low-scoring items.
    """

    def __init__(self, *, capacity: int = 20, decay_rate: float = 0.01) -> None:
        self._capacity = capacity
        self._decay_rate = decay_rate
        self._items: list[MemoryItem] = []
        self._lock = asyncio.Lock()

    async def add(self, content: str, *, importance: float = 0.5, metadata: dict[str, Any] | None = None) -> None:
        """Add an item to working memory."""
        async with self._lock:
            item = MemoryItem(
                content=content,
                importance=max(0.0, min(1.0, importance)),
                metadata=metadata or {},
            )
            self._items.append(item)
            await self._evict_if_needed()

    async def reinforce(self, content: str, *, boost: float = 0.1) -> bool:
        """Reinforce items matching the content."""
        async with self._lock:
            found = False
            for item in self._items:
                if content.lower() in item.content.lower():
                    item.reinforce(boost)
                    found = True
            return found

    async def retrieve(self, query: str, *, top_k: int = 5) -> list[MemoryItem]:
        """Retrieve most relevant items for a query."""
        async with self._lock:
            # Score items by relevance to query
            scored: list[tuple[float, MemoryItem]] = []
            query_lower = query.lower()
            for item in self._items:
                relevance = 0.0
                if query_lower in item.content.lower():
                    relevance = 1.0
                else:
                    # Simple token overlap
                    query_tokens = set(query_lower.split())
                    item_tokens = set(item.content.lower().split())
                    if query_tokens and item_tokens:
                        overlap = len(query_tokens & item_tokens) / len(query_tokens)
                        relevance = overlap
                combined = item.score * 0.5 + relevance * 0.5
                scored.append((combined, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            # Reinforce retrieved items
            for _, item in scored[:top_k]:
                item.reinforce(0.05)
            return [item for _, item in scored[:top_k]]

    async def get_all(self) -> list[MemoryItem]:
        """Get all items sorted by score."""
        async with self._lock:
            return sorted(self._items, key=lambda x: x.score, reverse=True)

    async def clear(self) -> None:
        """Clear all items."""
        async with self._lock:
            self._items.clear()

    async def decay(self) -> None:
        """Apply time-based decay to all items."""
        async with self._lock:
            now = time.time()
            for item in self._items:
                age = now - item.timestamp
                item.attention = max(0.0, item.attention - self._decay_rate * age / 60.0)

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def is_full(self) -> bool:
        return len(self._items) >= self._capacity

    async def _evict_if_needed(self) -> None:
        """Evict lowest-scoring items if over capacity."""
        while len(self._items) > self._capacity:
            self._items.sort(key=lambda x: x.score)
            self._items.pop(0)

    def to_context_string(self, *, max_items: int = 10) -> str:
        """Convert working memory to a context string for prompt injection."""
        items = sorted(self._items, key=lambda x: x.score, reverse=True)[:max_items]
        if not items:
            return ""
        lines = ["Working memory:"]
        for i, item in enumerate(items, 1):
            lines.append(f"  {i}. [{item.importance:.1f}] {item.content[:200]}")
        return "\n".join(lines)
