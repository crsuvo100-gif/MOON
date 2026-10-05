"""Cloud (or remote) memory store stub.

This provides a *placeholder* implementation that satisfies the abstract
:class:`MemoryStore` interface while storing records in an in‑memory dict.
It is intended for development or testing when ``MOON_MEMORY_BACKEND`` is set
to ``cloud``. In production a real remote store (PostgreSQL, DynamoDB, etc.)
should replace this class.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from .record import MemoryRecord, MemoryType, Scope, SyncStatus
from .store import MemoryStore


class CloudMemoryStore(MemoryStore):
    """Simple in‑memory cloud store.

    Records are kept in a thread‑safe ``dict`` keyed by ``memory_id``.
    ``sync_status`` is always ``SYNCED`` because there is no external service.
    """

    name = "cloud_stub"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: Dict[str, MemoryRecord] = {}
        # Simulated schema version for health reports.
        self._schema_version = 1

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def upsert(self, rec: MemoryRecord) -> MemoryRecord:
        with self._lock:
            # Ensure timestamps are realistic.
            now = time.time()
            rec.updated_at = now
            rec.accessed_at = now
            # In this stub we consider everything immediately synced.
            rec.sync_status = SyncStatus.SYNCED
            self._store[rec.memory_id] = rec
        return rec

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        with self._lock:
            if memory_id not in self._store:
                return False
            if hard:
                del self._store[memory_id]
            else:
                rec = self._store[memory_id]
                rec.deleted = True
                rec.updated_at = time.time()
                rec.sync_status = SyncStatus.PENDING
                self._store[memory_id] = rec
        return True

    def touch(self, memory_id: str) -> None:
        with self._lock:
            rec = self._store.get(memory_id)
            if rec:
                rec.accessed_at = time.time()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryRecord | None:
        with self._lock:
            rec = self._store.get(memory_id)
            if rec and (include_deleted or not rec.deleted):
                return rec
            return None

    def query(
        self,
        *,
        scope: Scope | None = None,
        type_: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        tags: List[str] | None = None,
        keyword: str | None = None,
        include_archived: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MemoryRecord]:
        with self._lock:
            records = list(self._store.values())
            # Apply filters sequentially.
            if not include_deleted:
                records = [r for r in records if not r.deleted]
            if not include_archived:
                records = [r for r in records if not r.archived]
            if scope is not None:
                records = [r for r in records if r.scope == scope]
            if type_ is not None:
                records = [r for r in records if r.type == type_]
            if agent_id is not None:
                records = [r for r in records if r.agent_id == agent_id]
            if project_id is not None:
                records = [r for r in records if r.project_id == project_id]
            if task_id is not None:
                records = [r for r in records if r.task_id == task_id]
            if tags:
                records = [r for r in records if set(tags).issubset(set(r.tags))]
            if keyword:
                kw = keyword.lower()
                records = [r for r in records if kw in r.content.lower() or kw in r.summary.lower()]
            # Order by updated_at descending.
            records.sort(key=lambda r: r.updated_at, reverse=True)
            return records[offset : offset + limit]

    def count(self, **kw: Any) -> int:
        return len(self.query(**kw))

    def all_for_embedding(self, *, limit: int = 0) -> List[MemoryRecord]:
        # In this stub we treat all records as eligible for embedding.
        with self._lock:
            records = [r for r in self._store.values() if not r.deleted and not r.archived]
            if limit:
                records = records[:limit]
            return records

    # ------------------------------------------------------------------
    # Diagnostics / health
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._store)
            active = len([r for r in self._store.values() if not r.deleted])
            pending = len([r for r in self._store.values() if r.sync_status == SyncStatus.PENDING])
            return {
                "store": self.name,
                "online": True,
                "schema_version": self._schema_version,
                "total": total,
                "active": active,
                "pending_sync": pending,
            }

    def close(self) -> None:
        # No external resources to close.
        pass

__all__ = ["CloudMemoryStore"]
