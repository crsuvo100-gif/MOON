"""ContextWindow — manages a token-budgeted context window.

Every professional AI assistant needs to manage its context window:
tracking token usage, evicting low-value items when full, and
maintaining a balanced mix of context sources. This module provides
that capability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class EvictionPolicy(Enum):
    """Policy for evicting items when the window is full."""
    LRU = "lru"                   # Least Recently Used
    LFU = "lfu"                   # Least Frequently Used
    LOW_RELEVANCE = "low_relevance"  # Lowest relevance first
    LOW_IMPORTANCE = "low_importance"  # Lowest importance first
    HYBRID = "hybrid"             # Combined score (relevance * importance)


@dataclass
class ContextItem:
    """A single item in the context window."""
    content: str
    source: str = "unknown"
    relevance: float = 0.5
    importance: float = 0.5
    tokens: int = 0
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age(self) -> float:
        return time.time() - self.timestamp

    @property
    def value_score(self) -> float:
        """Combined value score for eviction decisions."""
        return self.relevance * self.importance


class ContextWindow:
    """Token-budgeted context window with automatic eviction.

    Manages a collection of context items within a token budget.
    When the budget is exceeded, items are evicted based on the
    configured policy.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 8000,
        reserved_tokens: int = 2000,
        eviction_policy: EvictionPolicy = EvictionPolicy.HYBRID,
        auto_evict: bool = True,
    ) -> None:
        self._max_tokens = max_tokens
        self._reserved_tokens = reserved_tokens
        self._eviction_policy = eviction_policy
        self._auto_evict = auto_evict
        self._items: list[ContextItem] = []
        self._total_tokens = 0

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def reserved_tokens(self) -> int:
        return self._reserved_tokens

    @property
    def available_tokens(self) -> int:
        return self._max_tokens - self._reserved_tokens - self._total_tokens

    @property
    def used_tokens(self) -> int:
        return self._total_tokens

    @property
    def utilization(self) -> float:
        usable = self._max_tokens - self._reserved_tokens
        if usable <= 0:
            return 1.0
        return self._total_tokens / usable

    @property
    def items(self) -> list[ContextItem]:
        return list(self._items)

    @property
    def is_full(self) -> bool:
        return self._total_tokens >= (self._max_tokens - self._reserved_tokens)

    def add(
        self,
        content: str,
        *,
        source: str = "unknown",
        relevance: float = 0.5,
        importance: float = 0.5,
        tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextItem:
        """Add an item to the context window.

        If the window is full, items are evicted based on the policy.
        """
        if tokens is None:
            tokens = len(content) // 4  # Rough estimate

        item = ContextItem(
            content=content,
            source=source,
            relevance=relevance,
            importance=importance,
            tokens=tokens,
            metadata=metadata or {},
        )

        self._items.append(item)
        self._total_tokens += tokens

        if self._auto_evict:
            self._evict_if_needed()

        return item

    def remove(self, item: ContextItem) -> bool:
        """Remove a specific item from the window."""
        if item in self._items:
            self._items.remove(item)
            self._total_tokens -= item.tokens
            return True
        return False

    def clear(self, *, source: str | None = None) -> int:
        """Clear items from the window, optionally only from a source."""
        if source is None:
            count = len(self._items)
            self._items.clear()
            self._total_tokens = 0
            return count

        to_remove = [item for item in self._items if item.source == source]
        for item in to_remove:
            self._items.remove(item)
            self._total_tokens -= item.tokens
        return len(to_remove)

    def get(self, *, source: str | None = None, min_relevance: float = 0.0) -> list[ContextItem]:
        """Get items, optionally filtered by source and relevance."""
        items = self._items
        if source is not None:
            items = [i for i in items if i.source == source]
        if min_relevance > 0:
            items = [i for i in items if i.relevance >= min_relevance]
        return items

    def compress(self, *, target_tokens: int | None = None) -> str:
        """Compress all items into a single string."""
        if not self._items:
            return ""
        target = target_tokens or self.available_tokens
        parts = []
        current = 0
        for item in self._items:
            if current + item.tokens > target and parts:
                parts.append("...[truncated]...")
                break
            parts.append(item.content)
            current += item.tokens
        return "\n\n".join(parts)

    def summary(self) -> dict[str, Any]:
        """Get a summary of the window state."""
        sources: dict[str, int] = {}
        for item in self._items:
            sources[item.source] = sources.get(item.source, 0) + 1

        return {
            "total_items": len(self._items),
            "total_tokens": self._total_tokens,
            "max_tokens": self._max_tokens,
            "reserved_tokens": self._reserved_tokens,
            "available_tokens": self.available_tokens,
            "utilization": round(self.utilization, 3),
            "is_full": self.is_full,
            "sources": sources,
            "eviction_policy": self._eviction_policy.value,
        }

    def _evict_if_needed(self) -> None:
        """Evict items if the window is over budget."""
        usable = self._max_tokens - self._reserved_tokens
        while self._total_tokens > usable and self._items:
            victim = self._select_eviction_victim()
            if victim is None:
                break
            self._items.remove(victim)
            self._total_tokens -= victim.tokens
            logger.debug(f"Evicted context item from {victim.source} ({victim.tokens} tokens)")

    def _select_eviction_victim(self) -> ContextItem | None:
        """Select the best item to evict based on the policy."""
        if not self._items:
            return None

        if self._eviction_policy == EvictionPolicy.LRU:
            return min(self._items, key=lambda i: i.last_access)
        elif self._eviction_policy == EvictionPolicy.LFU:
            return min(self._items, key=lambda i: i.access_count)
        elif self._eviction_policy == EvictionPolicy.LOW_RELEVANCE:
            return min(self._items, key=lambda i: i.relevance)
        elif self._eviction_policy == EvictionPolicy.LOW_IMPORTANCE:
            return min(self._items, key=lambda i: i.importance)
        else:  # HYBRID
            return min(self._items, key=lambda i: i.value_score)
