"""Simple TTL cache for repeated retrievals.

Enhanced implementation with LRU+TTL hybrid eviction, prefetching,
and cache statistics.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class MemoryCache:
    """LRU+TTL hybrid cache for memory retrieval results.

    Features:
    - LRU eviction (least recently used)
    - TTL expiration (time-to-live)
    - Size-based eviction
    - Prefetch support
    - Cache statistics (hit rate, eviction count)
    - Thread-safe operations (via GIL)
    """

    def __init__(
        self,
        max_size: int = 256,
        ttl: float = 600.0,
    ) -> None:
        self._max_size = max_size
        self._ttl = ttl
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Any | None:
        """Get value from cache. Returns None if not found or expired."""
        item = self._data.get(key)
        if item is None:
            self._misses += 1
            return None
        ts, val = item
        if time.time() - ts > self._ttl:
            self._data.pop(key, None)
            self._misses += 1
            self._evictions += 1
            return None
        # Move to end (most recently used)
        self._data.move_to_end(key)
        self._hits += 1
        return val

    def put(self, key: str, val: Any) -> None:
        """Store value in cache."""
        self._data[key] = (time.time(), val)
        self._data.move_to_end(key)
        if len(self._data) > self._max_size:
            # Evict least recently used
            self._data.popitem(last=False)
            self._evictions += 1

    def invalidate(self, key: str) -> bool:
        """Remove a key from cache. Returns True if key existed."""
        if key in self._data:
            del self._data[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._data.clear()

    def prefetch(self, keys: list[str], fetch_fn: Any) -> int:
        """Prefetch multiple keys using a fetch function.

        Args:
            keys: List of keys to prefetch
            fetch_fn: Function that takes a key and returns a value

        Returns:
            Number of keys successfully prefetched
        """
        count = 0
        for key in keys:
            if key not in self._data:
                try:
                    val = fetch_fn(key)
                    if val is not None:
                        self.put(key, val)
                        count += 1
                except Exception:  # noqa: BLE001
                    pass
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._data),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 4),
            "evictions": self._evictions,
        }

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        item = self._data.get(key)
        if item is None:
            return False
        ts, _ = item
        if time.time() - ts > self._ttl:
            self._data.pop(key, None)
            return False
        return True
