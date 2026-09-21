"""Simple TTL cache for repeated retrievals."""

from __future__ import annotations

import time
from collections import OrderedDict


class MemoryCache:
    def __init__(self, max_size: int = 256, ttl: float = 600.0) -> None:
        self._max = max_size
        self._ttl = ttl
        self._data: OrderedDict[str, tuple[float, object]] = OrderedDict()

    def get(self, key: str):
        item = self._data.get(key)
        if item is None:
            return None
        ts, val = item
        if time.time() - ts > self._ttl:
            self._data.pop(key, None)
            return None
        return val

    def put(self, key: str, val) -> None:
        self._data[key] = (time.time(), val)
        if len(self._data) > self._max:
            self._data.popitem(last=False)
