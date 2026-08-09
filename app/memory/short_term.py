"""Short-term (recent-context) memory."""

from __future__ import annotations

from collections import deque


class ShortTermMemory:
    def __init__(self, max_items: int = 50) -> None:
        self._buf: deque[str] = deque(maxlen=max_items)

    def add(self, content: str) -> None:
        self._buf.append(content)

    def recent(self, limit: int = 10) -> list[str]:
        return list(self._buf)[-limit:]

    def clear(self) -> None:
        self._buf.clear()
