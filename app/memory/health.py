"""Memory health + terminal status (spec 50, 51, 59).

Spec 59 asks the terminal to be able to show:

    MOON MEMORY
    Local DB       : ONLINE
    Vector Memory  : ONLINE
    Cloud Memory   : ONLINE
    Sync           : SYNCED
    Pending        : 0
    Conflicts      : 0
    Last Sync      : timestamp

and, during a task, a retrieval/usage summary. This module produces that data
from REAL state -- never fabricated numbers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthReport:
    ok: bool
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checked_at": self.checked_at,
                "components": self.components}


class MemoryHealthService:
    """Aggregates health across every memory component (spec 50)."""

    def __init__(self, *, manager: Any = None, context_engine: Any = None,
                 cloud: Any = None, sync: Any = None) -> None:
        self._manager = manager
        self._context = context_engine
        self._cloud = cloud
        self._sync = sync
        self._last_sync: float | None = None

    def note_sync(self, when: float | None = None) -> None:
        self._last_sync = when or time.time()

    # -- individual probes ----------------------------------------------
    def _probe_local(self) -> dict[str, Any]:
        if self._manager is None:
            return {"status": "UNKNOWN", "detail": "no manager"}
        try:
            h = self._manager.health()
            db = h.get("local_db", {})
            return {"status": "ONLINE" if db.get("online") else "OFFLINE",
                    "detail": db}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}

    def _probe_vector(self) -> dict[str, Any]:
        """spec 58: vector memory degrades to keyword search, it does not fail."""
        if self._manager is None:
            return {"status": "UNKNOWN"}
        try:
            r = getattr(self._manager, "_retriever", None)
            embed = getattr(r, "_embed", None) if r is not None else None
            store = getattr(r, "_vectors", None) if r is not None else None
            if embed is None:
                return {"status": "DEGRADED", "detail":
                        "no embedding provider -- keyword/hybrid search active (spec 58)"}
            n = store.size if hasattr(store, "size") else "?"
            return {"status": "ONLINE", "detail": {"vectors": n}}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}

    def _probe_cloud(self) -> dict[str, Any]:
        """spec 55: cloud absence must never block local operation."""
        if self._cloud is None:
            return {"status": "OFFLINE",
                    "detail": "not configured -- local-only mode (spec 31/55)"}
        try:
            return self._cloud.health()
        except Exception as exc:  # noqa: BLE001
            return {"status": "OFFLINE", "detail": str(exc)}

    def _probe_sync(self) -> dict[str, Any]:
        pending = conflicts = 0
        try:
            if self._manager is not None:
                pending = self._manager._store.count(sync_status="PENDING")
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._sync is not None:
                st = self._sync.status() if hasattr(self._sync, "status") else {}
                pending = st.get("pending", pending)
                conflicts = st.get("conflicts", 0)
        except Exception:  # noqa: BLE001
            pass
        return {"status": "SYNCED" if pending == 0 else "PENDING",
                "pending": pending, "conflicts": conflicts,
                "last_sync": self._last_sync}

    def _probe_embedding(self) -> dict[str, Any]:
        if self._manager is None:
            return {"status": "UNKNOWN"}
        try:
            r = getattr(self._manager, "_retriever", None)
            if r is not None and getattr(r, "_embed", None) is not None:
                return {"status": "ONLINE"}
            return {"status": "UNAVAILABLE",
                    "detail": "embeddings deferred; text memory still stored (spec 58)"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}

    def _probe_storage(self) -> dict[str, Any]:
        if self._manager is None:
            return {"status": "UNKNOWN"}
        try:
            db = self._manager.health().get("local_db", {})
            return {"status": "OK", "size_bytes": db.get("size_bytes", 0),
                    "path": db.get("path", "")}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}

    # -- aggregate -------------------------------------------------------
    def check(self) -> HealthReport:
        comps = {
            "local_db": self._probe_local(),
            "vector_memory": self._probe_vector(),
            "cloud_memory": self._probe_cloud(),
            "sync": self._probe_sync(),
            "embedding_provider": self._probe_embedding(),
            "storage": self._probe_storage(),
        }
        # ok = the parts MOON cannot run without are healthy
        ok = comps["local_db"].get("status") == "ONLINE"
        return HealthReport(ok=ok, components=comps)

    # -- spec 59: terminal panel -----------------------------------------
    def terminal_status(self) -> str:
        rep = self.check()
        c = rep.components
        sync = c.get("sync", {})
        last = sync.get("last_sync")
        last_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last)) if last else "never"
        lines = [
            "MOON MEMORY",
            f"Local DB       : {c['local_db'].get('status', '?')}",
            f"Vector Memory  : {c['vector_memory'].get('status', '?')}",
            f"Cloud Memory   : {c['cloud_memory'].get('status', '?')}",
            f"Sync           : {sync.get('status', '?')}",
            f"Pending        : {sync.get('pending', 0)}",
            f"Conflicts      : {sync.get('conflicts', 0)}",
            f"Last Sync      : {last_s}",
        ]
        return "\n".join(lines)

    def task_summary(self, *, retrieved: int, used: int,
                     filtered: int | None = None) -> str:
        """spec 59: the during-task retrieval line."""
        filtered = filtered if filtered is not None else max(0, retrieved - used)
        return (f"Memory Retrieved: {retrieved}\n"
                f"Relevant: {used}\n"
                f"Filtered: {filtered}\n"
                f"Context Used: {used}")


__all__ = ["MemoryHealthService", "HealthReport"]
