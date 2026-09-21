"""
Short-term memory — in-memory ring buffer of recent messages.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Optional

from app.tools.base import ToolResult  # noqa: F401  (reexport for convenience)


class ShortTermMemory:
    """Lightweight in-memory buffer for recent conversation context."""

    def __init__(self, capacity: int = 200) -> None:
        self._buf: deque[str] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def add(self, content: str) -> None:
        with self._lock:
            self._buf.append(content)

    def recent(self, limit: int = 20) -> list[str]:
        with self._lock:
            return list(self._buf)[-limit:]

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)
