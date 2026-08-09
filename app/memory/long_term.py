"""long_term.py -- persistent long-term memory (disk-backed JSONL).

Long-term memory persists facts/documents across sessions. By default it is
a simple JSONL file store (one JSON object per line) so it is portable and
human-readable; swap in a database adapter for production scale.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.config.constants import MemoryScope
from app.config.logging import get_logger
from app.models.memory import MemoryEntry

logger = get_logger(__name__)


class LongTermMemory:
    """Append-only JSONL store of :class:`MemoryEntry` objects on disk."""

    def __init__(self, path: str = "app/logs/long_term.jsonl") -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._entries: list[MemoryEntry] = []

    async def setup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._path.read_text, "utf-8")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._entries.append(MemoryEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Skipping corrupt LTM line: %s", exc)
        logger.info("LTM loaded %d entries from %s", len(self._entries), self._path)

    async def store(self, data: dict[str, Any]) -> MemoryEntry:
        entry = MemoryEntry(
            content=data.get("content", ""),
            scope=MemoryScope.LONG_TERM,
            tags=list(data.get("tags", [])),
            metadata=data.get("metadata", {}),
        )
        async with self._lock:
            self._entries.append(entry)
            line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._append_line, line)
        logger.debug("LTM stored entry %s", entry.id)
        return entry

    def _append_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    async def query(self, keyword: str, limit: int = 10) -> list[MemoryEntry]:
        kw = keyword.lower()
        matches = [e for e in self._entries if kw in e.content.lower()]
        return matches[-limit:]

    async def all(self) -> list[MemoryEntry]:
        return list(self._entries)

    async def teardown(self) -> None:
        return
