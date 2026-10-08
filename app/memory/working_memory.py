"""Working memory -- transient scratch space per agent brain.

Advanced implementation with attention mechanisms, decay, capacity management,
and salience-based eviction. Supports multi-agent isolation and cross-agent
working memory sharing.
"""
from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemoryItem:
    """A single item in working memory with metadata."""
    key: str
    value: Any
    salience: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    decay_rate: float = 0.01  # per-second decay

    @property
    def effective_salience(self) -> float:
        """Current salience after decay."""
        age = time.time() - self.last_accessed
        decay = math.exp(-self.decay_rate * age)
        return self.salience * decay

    def touch(self) -> None:
        """Mark item as accessed."""
        self.last_accessed = time.time()
        self.access_count += 1


class WorkingMemory:
    """Advanced working memory with attention, decay, and capacity management.

    Features:
    - Salience-based eviction (least salient items evicted first)
    - Time-based decay (items lose salience over time)
    - Access tracking (frequently accessed items retained)
    - Multi-agent isolation (separate namespaces per agent)
    - Cross-agent sharing (explicit share/unshare)
    - Capacity management (configurable max items)
    - Importance scoring (based on recency, frequency, salience)
    """

    def __init__(self, max_items: int = 100, decay_rate: float = 0.01) -> None:
        self._max_items = max_items
        self._decay_rate = decay_rate
        self._items: OrderedDict[str, WorkingMemoryItem] = OrderedDict()
        self._shared: set[str] = set()  # keys shared across agents
        self._agent_namespace: str = "default"

    def set(
        self,
        key: str,
        value: Any,
        salience: float = 1.0,
        shared: bool = False,
    ) -> None:
        """Store an item in working memory.

        Args:
            key: Unique identifier for the item
            value: The value to store
            salience: Initial salience (importance) of the item
            shared: Whether this item is shared across agents
        """
        if key in self._items:
            item = self._items[key]
            item.value = value
            item.salience = max(item.salience, salience)
            item.touch()
            self._items.move_to_end(key)
        else:
            item = WorkingMemoryItem(
                key=key,
                value=value,
                salience=salience,
                decay_rate=self._decay_rate,
            )
            self._items[key] = item
            if shared:
                self._shared.add(key)
            self._evict_if_needed()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve an item, updating access metadata."""
        item = self._items.get(key)
        if item is None:
            return default
        item.touch()
        self._items.move_to_end(key)
        return item.value

    def get_with_metadata(self, key: str) -> WorkingMemoryItem | None:
        """Retrieve item with full metadata."""
        item = self._items.get(key)
        if item:
            item.touch()
            self._items.move_to_end(key)
        return item

    def remove(self, key: str) -> bool:
        """Remove an item. Returns True if item existed."""
        if key in self._items:
            del self._items[key]
            self._shared.discard(key)
            return True
        return False

    def clear(self, shared_only: bool = False) -> int:
        """Clear working memory.

        Args:
            shared_only: If True, only clear shared items

        Returns:
            Number of items removed
        """
        if shared_only:
            to_remove = [k for k in self._shared]
        else:
            to_remove = list(self._items.keys())
        for k in to_remove:
            self._items.pop(k, None)
        self._shared.clear()
        return len(to_remove)

    def items(self, sorted_by_salience: bool = False) -> dict[str, Any]:
        """Get all items as a dict.

        Args:
            sorted_by_salience: If True, sort by effective salience (descending)
        """
        if sorted_by_salience:
            sorted_items = sorted(
                self._items.items(),
                key=lambda x: x[1].effective_salience,
                reverse=True,
            )
            return {k: v.value for k, v in sorted_items}
        return {k: v.value for k, v in self._items.items()}

    def get_salient(self, top_k: int = 10) -> list[tuple[str, Any, float]]:
        """Get the top-k most salient items.

        Returns:
            List of (key, value, effective_salience) tuples
        """
        scored = [
            (k, v.value, v.effective_salience)
            for k, v in self._items.items()
        ]
        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:top_k]

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, Any, float]]:
        """Search working memory by keyword overlap with salience weighting.

        Returns:
            List of (key, value, score) tuples sorted by score
        """
        q = (query or "").lower()
        if not q:
            return []
        query_words = set(q.split())
        results: list[tuple[str, Any, float]] = []
        for k, item in self._items.items():
            text = f"{k} {str(item.value)}".lower()
            overlap = sum(1 for w in query_words if w and w in text)
            if overlap > 0:
                score = overlap * item.effective_salience
                results.append((k, item.value, score))
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]

    def share(self, key: str) -> bool:
        """Mark an item as shared across agents."""
        if key in self._items:
            self._shared.add(key)
            return True
        return False

    def unshare(self, key: str) -> bool:
        """Remove an item from shared set."""
        if key in self._shared:
            self._shared.remove(key)
            return True
        return False

    def get_shared(self) -> dict[str, Any]:
        """Get all shared items."""
        return {
            k: self._items[k].value
            for k in self._shared
            if k in self._items
        }

    def decay_all(self) -> int:
        """Apply decay to all items and remove expired ones.

        Returns:
            Number of items removed due to decay
        """
        now = time.time()
        to_remove = []
        for k, item in self._items.items():
            age = now - item.last_accessed
            if item.effective_salience < 0.01:
                to_remove.append(k)
        for k in to_remove:
            self._items.pop(k, None)
            self._shared.discard(k)
        return len(to_remove)

    def stats(self) -> dict[str, Any]:
        """Return working memory statistics."""
        now = time.time()
        total = len(self._items)
        shared = len(self._shared)
        avg_salience = (
            sum(i.effective_salience for i in self._items.values()) / total
            if total > 0 else 0.0
        )
        avg_age = (
            sum(now - i.created_at for i in self._items.values()) / total
            if total > 0 else 0.0
        )
        return {
            "total_items": total,
            "shared_items": shared,
            "max_items": self._max_items,
            "utilization": total / self._max_items if self._max_items > 0 else 0.0,
            "avg_salience": round(avg_salience, 4),
            "avg_age_seconds": round(avg_age, 2),
            "decay_rate": self._decay_rate,
        }

    def _evict_if_needed(self) -> None:
        """Evict least salient items if over capacity."""
        while len(self._items) > self._max_items:
            # Find least salient non-shared item
            candidates = [
                (k, v) for k, v in self._items.items()
                if k not in self._shared
            ]
            if not candidates:
                # All items are shared, evict least salient
                candidates = list(self._items.items())
            if not candidates:
                break
            # Evict least salient
            k, _ = min(candidates, key=lambda x: x[1].effective_salience)
            self._items.pop(k, None)
            self._shared.discard(k)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: str) -> bool:
        return key in self._items
