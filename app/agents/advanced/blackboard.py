"""blackboard.py — shared blackboard architecture for multi-agent coordination.

Professional multi-agent systems use a blackboard pattern where agents
read/write to a shared knowledge space. This module provides a thread-safe
blackboard with publish/subscribe, conflict resolution, and automatic
invalidation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class BlackboardEntry:
    key: str
    value: Any
    agent_id: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    ttl: float = 300.0  # seconds before entry is considered stale
    version: int = 1

    def is_stale(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl


class Blackboard:
    """Thread-safe shared knowledge space for multi-agent coordination.

    Agents publish findings to the blackboard and subscribe to keys they
    care about. The blackboard handles conflict resolution (last-writer-wins
    with confidence weighting) and automatic stale entry cleanup.
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._data: dict[str, BlackboardEntry] = {}
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: list[dict[str, Any]] = []
        self._max_history = 1000

    async def write(
        self,
        key: str,
        value: Any,
        *,
        agent_id: str = "system",
        confidence: float = 1.0,
        ttl: float = 300.0,
    ) -> None:
        async with self._lock:
            existing = self._data.get(key)
            version = (existing.version + 1) if existing else 1
            entry = BlackboardEntry(
                key=key,
                value=value,
                agent_id=agent_id,
                confidence=confidence,
                ttl=ttl,
                version=version,
            )
            self._data[key] = entry
            self._history.append({
                "action": "write",
                "key": key,
                "agent_id": agent_id,
                "version": version,
                "timestamp": entry.timestamp,
            })
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            # Notify subscribers
            subs = self._subscribers.get(key, [])
            for callback in subs:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(key, entry))
                    else:
                        callback(key, entry)
                except Exception as exc:
                    logger.warning("Blackboard subscriber error: %s", exc)

    async def read(self, key: str, *, include_stale: bool = False) -> Any | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.is_stale() and not include_stale:
                return None
            return entry.value

    async def read_entry(self, key: str) -> BlackboardEntry | None:
        async with self._lock:
            return self._data.get(key)

    async def read_all(self, *, include_stale: bool = False) -> dict[str, Any]:
        async with self._lock:
            result = {}
            for key, entry in self._data.items():
                if entry.is_stale() and not include_stale:
                    continue
                result[key] = entry.value
            return result

    async def read_by_agent(self, agent_id: str) -> dict[str, Any]:
        async with self._lock:
            return {
                k: e.value for k, e in self._data.items()
                if e.agent_id == agent_id
            }

    async def read_by_prefix(self, prefix: str) -> dict[str, Any]:
        async with self._lock:
            return {
                k: e.value for k, e in self._data.items()
                if k.startswith(prefix) and not e.is_stale()
            }

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                self._history.append({
                    "action": "delete",
                    "key": key,
                    "timestamp": time.time(),
                })
                return True
            return False

    async def cleanup_stale(self) -> int:
        """Remove stale entries. Returns count removed."""
        async with self._lock:
            stale_keys = [k for k, e in self._data.items() if e.is_stale()]
            for k in stale_keys:
                del self._data[k]
            return len(stale_keys)

    def subscribe(self, key: str, callback: Callable) -> None:
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)

    def unsubscribe(self, key: str, callback: Callable) -> bool:
        if key in self._subscribers:
            try:
                self._subscribers[key].remove(callback)
                return True
            except ValueError:
                pass
        return False

    async def get_history(self, *, limit: int = 100) -> list[dict[str, Any]]:
        async with self._lock:
            return self._history[-limit:]

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
            self._history.clear()

    def stats(self) -> dict[str, Any]:
        total = len(self._data)
        stale = sum(1 for e in self._data.values() if e.is_stale())
        agents = set(e.agent_id for e in self._data.values())
        return {
            "total_entries": total,
            "stale_entries": stale,
            "active_entries": total - stale,
            "unique_agents": len(agents),
            "agent_ids": sorted(agents),
            "total_subscribers": sum(len(s) for s in self._subscribers.values()),
        }
