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

    def search(self, keyword: str, limit: int = 5) -> list[str]:
        """Search recent items by keyword."""
        kw = keyword.lower()
        return [item for item in self._buf if kw in item.lower()][-limit:]

    def stats(self) -> dict[str, int]:
        """Return basic stats."""
        return {"total": len(self._buf)}

    def __len__(self) -> int:
        return len(self._buf)
