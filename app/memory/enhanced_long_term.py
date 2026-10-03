"""enhanced_long_term.py -- Long-term memory with semantic search, importance
scoring, recency decay, and access-frequency tracking.

Professional AI assistants don't just store facts -- they rank them by
importance, decay unused ones, and retrieve by meaning (embeddings), not just
keywords. This module upgrades the plain JSONL store into a real memory system.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.logging import get_logger
from app.models.memory import MemoryEntry

logger = get_logger(__name__)


@dataclass
class EnhancedMemoryEntry:
    """A memory entry with importance, access count, and embedding."""
    entry: MemoryEntry
    importance: float = 0.5  # 0.0 - 1.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    embedding: list[float] | None = None

    @property
    def id(self) -> str:
        return self.entry.id

    @property
    def content(self) -> str:
        return self.entry.content

    def to_dict(self) -> dict[str, Any]:
        d = self.entry.to_dict()
        d["importance"] = self.importance
        d["access_count"] = self.access_count
        d["last_accessed"] = self.last_accessed
        if self.embedding is not None:
            d["embedding"] = self.embedding
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnhancedMemoryEntry:
        entry = MemoryEntry(
            content=data.get("content", ""),
            scope=data.get("scope", "long_term"),
            tags=list(data.get("tags", [])),
            metadata=data.get("metadata", {}),
            id=data.get("id", ""),
            created_at=data.get("created_at", time.time()),
        )
        return cls(
            entry=entry,
            importance=float(data.get("importance", 0.5)),
            access_count=int(data.get("access_count", 0)),
            last_accessed=float(data.get("last_accessed", time.time())),
            embedding=data.get("embedding"),
        )


class EnhancedLongTermMemory:
    """Long-term memory with semantic search, importance scoring, and decay.

    Features:
    - Embedding-based semantic search (falls back to keyword if no embeddings)
    - Importance scoring (0-1) with automatic boosting on access
    - Recency decay: unused memories gradually lose importance
    - Access frequency tracking
    - Tag-based filtering
    - Configurable max size with LRU eviction
    """

    def __init__(
        self,
        path: str = "app/logs/long_term.jsonl",
        max_entries: int = 10000,
        decay_rate: float = 0.01,  # importance loss per day of no access
        embedding_service: Any = None,
    ) -> None:
        self._path = Path(path)
        self._max_entries = max_entries
        self._decay_rate = decay_rate
        self._embedding_service = embedding_service
        self._lock = asyncio.Lock()
        self._entries: dict[str, EnhancedMemoryEntry] = {}
        self._tag_index: dict[str, set[str]] = {}

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
                    data = json.loads(line)
                    eme = EnhancedMemoryEntry.from_dict(data)
                    self._entries[eme.id] = eme
                    for tag in eme.entry.tags:
                        self._tag_index.setdefault(tag, set()).add(eme.id)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("Skipping corrupt LTM line: %s", exc)
        logger.info("Enhanced LTM loaded %d entries from %s", len(self._entries), self._path)

    async def store(
        self,
        data: dict[str, Any],
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> EnhancedMemoryEntry:
        content = data.get("content", "")
        # Generate embedding if service available
        embedding = None
        if self._embedding_service is not None and content:
            try:
                embedding = await self._embedding_service.embed(content)
            except Exception as exc:
                logger.debug("Embedding generation failed: %s", exc)

        entry = MemoryEntry(
            content=content,
            scope=data.get("scope", "long_term"),
            tags=tags or list(data.get("tags", [])),
            metadata=data.get("metadata", {}),
        )
        eme = EnhancedMemoryEntry(
            entry=entry,
            importance=max(0.0, min(1.0, importance)),
            embedding=embedding,
        )
        async with self._lock:
            self._entries[eme.id] = eme
            for tag in eme.entry.tags:
                self._tag_index.setdefault(tag, set()).add(eme.id)
            # Evict if over capacity
            if len(self._entries) > self._max_entries:
                self._evict_oldest()
            await self._persist_entry(eme)
        logger.debug("Enhanced LTM stored entry %s (importance=%.2f)", eme.id, importance)
        return eme

    async def query(
        self,
        keyword: str,
        limit: int = 10,
        min_importance: float = 0.0,
        tags: list[str] | None = None,
    ) -> list[EnhancedMemoryEntry]:
        """Search by keyword with importance filtering and tag filtering."""
        kw = keyword.lower()
        async with self._lock:
            candidates = list(self._entries.values())

        # Tag filter
        if tags:
            tag_ids = set()
            for tag in tags:
                tag_ids |= self._tag_index.get(tag, set())
            candidates = [e for e in candidates if e.id in tag_ids]

        # Keyword filter + score
        scored = []
        for e in candidates:
            if e.importance < min_importance:
                continue
            content_lower = e.content.lower()
            if kw in content_lower:
                # Score: importance * recency_factor * access_factor
                recency = 1.0 / (1.0 + (time.time() - e.last_accessed) / 86400.0)
                access = math.log1p(e.access_count) / 5.0
                score = e.importance * (0.5 + 0.3 * recency + 0.2 * access)
                scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:limit]]

        # Update access stats
        for e in results:
            e.access_count += 1
            e.last_accessed = time.time()

        return results

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> list[tuple[EnhancedMemoryEntry, float]]:
        """Semantic search using embeddings. Falls back to keyword if no embeddings."""
        if self._embedding_service is None:
            # Fallback to keyword search
            entries = await self.query(query, limit=top_k)
            return [(e, 0.5) for e in entries]

        try:
            qvec = await self._embedding_service.embed(query)
        except Exception as exc:
            logger.debug("Semantic search embedding failed: %s", exc)
            entries = await self.query(query, limit=top_k)
            return [(e, 0.5) for e in entries]

        async with self._lock:
            candidates = list(self._entries.values())

        scored = []
        for e in candidates:
            if e.embedding is None:
                continue
            sim = self._cosine(qvec, e.embedding)
            if sim >= threshold:
                # Combine similarity with importance
                score = sim * (0.7 + 0.3 * e.importance)
                scored.append((score, e, sim))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [(e, sim) for _, e, sim in scored[:top_k]]

    async def all(self) -> list[EnhancedMemoryEntry]:
        async with self._lock:
            return list(self._entries.values())

    async def get(self, entry_id: str) -> EnhancedMemoryEntry | None:
        async with self._lock:
            e = self._entries.get(entry_id)
            if e:
                e.access_count += 1
                e.last_accessed = time.time()
            return e

    async def update_importance(self, entry_id: str, delta: float) -> bool:
        """Adjust importance by delta (positive or negative)."""
        async with self._lock:
            e = self._entries.get(entry_id)
            if e is None:
                return False
            e.importance = max(0.0, min(1.0, e.importance + delta))
            await self._persist_all()
            return True

    async def decay(self) -> int:
        """Apply time-based decay to all entries. Returns count decayed."""
        now = time.time()
        decayed = 0
        async with self._lock:
            for e in self._entries.values():
                days_since_access = (now - e.last_accessed) / 86400.0
                if days_since_access > 1.0:
                    decay_amount = self._decay_rate * days_since_access
                    old = e.importance
                    e.importance = max(0.0, e.importance - decay_amount)
                    if e.importance < old:
                        decayed += 1
            if decayed:
                await self._persist_all()
        if decayed:
            logger.info("LTM decay: %d entries decayed", decayed)
        return decayed

    async def purge(self, n: int = 100) -> list[EnhancedMemoryEntry]:
        """Remove and return up to n lowest-importance entries."""
        async with self._lock:
            sorted_entries = sorted(self._entries.values(), key=lambda e: e.importance)
            to_remove = sorted_entries[:n]
            for e in to_remove:
                del self._entries[e.id]
                for tag in e.entry.tags:
                    self._tag_index.get(tag, set()).discard(e.id)
            await self._persist_all()
        return to_remove

    async def wipe(self) -> None:
        async with self._lock:
            self._entries.clear()
            self._tag_index.clear()
        self._path.write_text("", encoding="utf-8")
        logger.info("Enhanced LTM wiped")

    def _evict_oldest(self) -> None:
        """Evict lowest-importance entries when over capacity."""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: (e.importance, e.last_accessed),
        )
        to_remove = len(self._entries) - self._max_entries
        for e in sorted_entries[:to_remove]:
            del self._entries[e.id]
            for tag in e.entry.tags:
                self._tag_index.get(tag, set()).discard(e.id)

    async def _persist_entry(self, eme: EnhancedMemoryEntry) -> None:
        line = json.dumps(eme.to_dict(), ensure_ascii=False) + "\n"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._append_line, line)

    async def _persist_all(self) -> None:
        lines = []
        for e in self._entries.values():
            lines.append(json.dumps(e.to_dict(), ensure_ascii=False))
        text = "\n".join(lines) + "\n" if lines else ""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_text, text)

    def _append_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def _write_text(self, text: str) -> None:
        self._path.write_text(text, encoding="utf-8")

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        if not self._entries:
            return {"total": 0, "avg_importance": 0.0, "total_accesses": 0}
        total_access = sum(e.access_count for e in self._entries.values())
        avg_importance = sum(e.importance for e in self._entries.values()) / len(self._entries)
        return {
            "total": len(self._entries),
            "avg_importance": round(avg_importance, 3),
            "total_accesses": total_access,
            "tags": len(self._tag_index),
        }
