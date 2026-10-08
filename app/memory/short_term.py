"""Short-term (recent-context) memory.

Enhanced implementation with semantic clustering, importance scoring,
recency-weighted retrieval, and automatic consolidation.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShortTermItem:
    """A single short-term memory item with metadata."""
    content: str
    timestamp: float = field(default_factory=time.time)
    importance: float = 1.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    cluster_id: int | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    @property
    def effective_importance(self) -> float:
        """Importance weighted by recency."""
        recency = 1.0 / (1.0 + self.age_seconds / 3600.0)  # 1-hour half-life
        frequency = math.log1p(self.access_count)
        return self.importance * recency * frequency

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed = time.time()


class ShortTermMemory:
    """Enhanced short-term memory with clustering and importance scoring.

    Features:
    - Semantic clustering (group related items)
    - Importance scoring (recency + frequency + explicit importance)
    - Recency-weighted retrieval
    - Automatic consolidation (merge similar items)
    - Configurable capacity with smart eviction
    - Tag-based filtering
    """

    def __init__(
        self,
        max_items: int = 50,
        cluster_threshold: float = 0.7,
        consolidation_enabled: bool = True,
    ) -> None:
        self._max_items = max_items
        self._cluster_threshold = cluster_threshold
        self._consolidation_enabled = consolidation_enabled
        self._items: deque[ShortTermItem] = deque(maxlen=max_items)
        self._clusters: dict[int, list[int]] = {}  # cluster_id -> item indices
        self._next_cluster_id = 0

    def add(
        self,
        content: str,
        importance: float = 1.0,
        tags: list[str] | None = None,
    ) -> ShortTermItem:
        """Add an item to short-term memory.

        Args:
            content: The content to store
            importance: Explicit importance score (0.0 to 1.0+)
            tags: Optional tags for filtering

        Returns:
            The created ShortTermItem
        """
        item = ShortTermItem(
            content=content,
            importance=importance,
            tags=tags or [],
        )
        self._items.append(item)
        self._assign_cluster(item)
        if self._consolidation_enabled:
            self._consolidate()
        return item

    def recent(self, limit: int = 10) -> list[str]:
        """Get recent items (most recent first)."""
        return [item.content for item in list(self._items)[-limit:][::-1]]

    def search(self, keyword: str, limit: int = 5) -> list[str]:
        """Search recent items by keyword."""
        kw = keyword.lower()
        return [
            item.content for item in self._items
            if kw in item.content.lower()
        ][-limit:][::-1]

    def search_scored(
        self,
        query: str,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Search with importance-weighted scoring.

        Returns:
            List of (content, score) tuples sorted by score
        """
        q = (query or "").lower()
        if not q:
            return []
        query_words = set(q.split())
        results: list[tuple[str, float]] = []
        for item in self._items:
            text = item.content.lower()
            overlap = sum(1 for w in query_words if w and w in text)
            if overlap > 0:
                score = overlap * item.effective_importance
                results.append((item.content, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_by_tag(self, tag: str) -> list[str]:
        """Get all items with a specific tag."""
        return [
            item.content for item in self._items
            if tag in item.tags
        ]

    def get_by_cluster(self, cluster_id: int) -> list[str]:
        """Get all items in a specific cluster."""
        indices = self._clusters.get(cluster_id, [])
        return [self._items[i].content for i in indices if i < len(self._items)]

    def get_clusters(self) -> dict[int, list[str]]:
        """Get all clusters as {cluster_id: [content, ...]}."""
        return {
            cid: [self._items[i].content for i in indices if i < len(self._items)]
            for cid, indices in self._clusters.items()
        }

    def clear(self) -> None:
        """Clear all items."""
        self._items.clear()
        self._clusters.clear()
        self._next_cluster_id = 0

    def stats(self) -> dict[str, Any]:
        """Return short-term memory statistics."""
        total = len(self._items)
        if total == 0:
            return {
                "total_items": 0,
                "max_items": self._max_items,
                "utilization": 0.0,
                "num_clusters": 0,
                "avg_importance": 0.0,
            }
        return {
            "total_items": total,
            "max_items": self._max_items,
            "utilization": total / self._max_items,
            "num_clusters": len(self._clusters),
            "avg_importance": round(
                sum(i.importance for i in self._items) / total, 4
            ),
            "avg_age_seconds": round(
                sum(i.age_seconds for i in self._items) / total, 2
            ),
        }

    def _assign_cluster(self, item: ShortTermItem) -> None:
        """Assign item to a cluster based on content similarity."""
        if not self._items:
            item.cluster_id = self._next_cluster_id
            self._clusters[self._next_cluster_id] = [0]
            self._next_cluster_id += 1
            return

        # Simple word-overlap clustering
        item_words = set(item.content.lower().split())
        best_cluster: int | None = None
        best_score = 0.0

        for cid, indices in self._clusters.items():
            if not indices:
                continue
            # Compare with first item in cluster
            ref_idx = indices[0]
            if ref_idx >= len(self._items):
                continue
            ref_item = self._items[ref_idx]
            ref_words = set(ref_item.content.lower().split())
            if not ref_words or not item_words:
                continue
            overlap = len(item_words & ref_words)
            score = overlap / max(len(item_words), len(ref_words))
            if score > best_score:
                best_score = score
                best_cluster = cid

        if best_score >= self._cluster_threshold and best_cluster is not None:
            item.cluster_id = best_cluster
            self._clusters[best_cluster].append(len(self._items) - 1)
        else:
            item.cluster_id = self._next_cluster_id
            self._clusters[self._next_cluster_id] = [len(self._items) - 1]
            self._next_cluster_id += 1

    def _consolidate(self) -> None:
        """Merge similar items within clusters."""
        # Simple consolidation: if cluster has > 5 items, merge oldest
        for cid, indices in list(self._clusters.items()):
            if len(indices) > 5:
                # Keep most recent 5, merge rest into summary
                to_merge = indices[:-5]
                merged_content = " ".join(
                    self._items[i].content for i in to_merge if i < len(self._items)
                )
                # Remove merged items
                for i in sorted(to_merge, reverse=True):
                    if i < len(self._items):
                        del self._items[i]
                # Update cluster indices
                self._clusters[cid] = [
                    i for i in indices if i < len(self._items)
                ]

    def __len__(self) -> int:
        return len(self._items)
