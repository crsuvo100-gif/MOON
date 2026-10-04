"""Sync engine + conflict resolution + change log (spec 31-39, 57, 58).

Local-first: MOON must keep working with no network (spec 31). Writes are
recorded locally and queued; when a cloud provider is configured the queue is
pushed. Every operation is idempotent (spec 34) so a retry cannot duplicate a
memory, and conflicts are never resolved by blind overwrite (spec 36).

Cloud providers implement ``CloudMemoryProvider`` (spec 27) so MOON is not
hard-coded to one vendor. When none is configured, the engine reports
``local_only`` and does nothing destructive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.memory.record import MemoryRecord, SyncStatus

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# spec 33: change log
# --------------------------------------------------------------------------
class Operation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class ChangeEntry:
    operation_id: str
    memory_id: str
    operation: Operation
    version: int
    device_id: str
    timestamp: float = field(default_factory=time.time)
    payload_hash: str = ""
    status: str = "pending"          # pending | applied | failed | conflict

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["operation"] = self.operation.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChangeEntry":
        op = d.get("operation", "create")
        return cls(operation_id=d.get("operation_id", uuid.uuid4().hex),
                   memory_id=d.get("memory_id", ""),
                   operation=Operation(op), version=int(d.get("version", 1)),
                   device_id=d.get("device_id", ""),
                   timestamp=float(d.get("timestamp", time.time())),
                   payload_hash=d.get("payload_hash", ""),
                   status=d.get("status", "pending"))


def payload_hash(rec: MemoryRecord) -> str:
    """spec 34: stable hash of the meaningful payload (not timestamps)."""
    blob = json.dumps({"c": rec.content, "s": rec.scope.value, "t": rec.type.value,
                       "v": rec.version, "a": rec.agent_id},
                      sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class ChangeLog:
    """Durable, append-only operation log (spec 33)."""

    def __init__(self, path: Any = None) -> None:
        from pathlib import Path

        from app.memory.store import default_db_path

        self._path = Path(path) if path else (default_db_path().parent / "sync" / "changelog.jsonl")
        self._entries: list[ChangeEntry] = []
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                for line in self._path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self._entries.append(ChangeEntry.from_dict(json.loads(line)))
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("changelog load failed: %s", exc)

    def append(self, rec: MemoryRecord, op: Operation,
               device_id: str = "") -> ChangeEntry:
        # spec 34: an identical operation (same id+version+hash) is not re-logged
        ph = payload_hash(rec)
        for e in reversed(self._entries[-50:]):
            if (e.memory_id == rec.memory_id and e.operation is op
                    and e.version == rec.version and e.payload_hash == ph):
                return e
        entry = ChangeEntry(operation_id=uuid.uuid4().hex[:16],
                            memory_id=rec.memory_id, operation=op,
                            version=rec.version, device_id=device_id,
                            payload_hash=ph)
        self._entries.append(entry)
        self._persist(entry)
        return entry

    def _persist(self, entry: ChangeEntry) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("changelog append failed: %s", exc)

    def pending(self) -> list[ChangeEntry]:
        return [e for e in self._entries if e.status == "pending"]

    def mark(self, operation_ids: list[str], status: str) -> int:
        ids = set(operation_ids)
        n = 0
        for e in self._entries:
            if e.operation_id in ids:
                e.status = status
                n += 1
        self._rewrite()
        return n

    def _rewrite(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                for e in self._entries:
                    fh.write(json.dumps(e.to_dict()) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.warning("changelog rewrite failed: %s", exc)

    def all(self) -> list[ChangeEntry]:
        return list(self._entries)

    def stats(self) -> dict[str, Any]:
        return {"total": len(self._entries),
                "pending": len(self.pending()),
                "applied": sum(1 for e in self._entries if e.status == "applied"),
                "failed": sum(1 for e in self._entries if e.status == "failed"),
                "conflicts": sum(1 for e in self._entries if e.status == "conflict")}


# --------------------------------------------------------------------------
# spec 27/28: cloud provider abstraction
# --------------------------------------------------------------------------
class CloudMemoryProvider(ABC):
    """Provider-independent cloud memory (spec 27). Never hard-code a vendor."""

    name = "abstract"

    @abstractmethod
    def health(self) -> dict[str, Any]: ...

    @abstractmethod
    def push(self, entries: list[ChangeEntry],
             records: dict[str, MemoryRecord]) -> dict[str, Any]: ...

    @abstractmethod
    def pull(self, since: float | None = None) -> list[MemoryRecord]: ...


class NullCloudProvider(CloudMemoryProvider):
    """The default: no cloud configured (spec 31 local-first).

    Everything works; nothing is sent anywhere. Health is OFFLINE with a clear
    reason rather than a fabricated "connected".
    """

    name = "none"

    def health(self) -> dict[str, Any]:
        return {"status": "OFFLINE", "detail": "no cloud provider configured "
                                               "(local-first mode, spec 31)"}

    def push(self, entries: list[ChangeEntry],
             records: dict[str, MemoryRecord]) -> dict[str, Any]:
        return {"pushed": 0, "skipped": len(entries),
                "reason": "local-only mode; changes retained in the queue"}

    def pull(self, since: float | None = None) -> list[MemoryRecord]:
        return []


# --------------------------------------------------------------------------
# spec 36/37/38: conflict detection + resolution
# --------------------------------------------------------------------------
class ConflictType(str, Enum):
    UPDATE_UPDATE = "UPDATE/UPDATE"
    UPDATE_DELETE = "UPDATE/DELETE"
    DELETE_UPDATE = "DELETE/UPDATE"
    VERSION_MISMATCH = "VERSION MISMATCH"
    CONTENT_CONFLICT = "CONTENT CONFLICT"
    METADATA_CONFLICT = "METADATA CONFLICT"


@dataclass
class Conflict:
    memory_id: str
    type: ConflictType
    local: MemoryRecord | None
    remote: MemoryRecord | None
    detail: str = ""
    resolution: str = ""            # kept | merged | local_wins | remote_wins | manual
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"memory_id": self.memory_id, "type": self.type.value,
                "detail": self.detail, "resolution": self.resolution,
                "local_version": self.local.version if self.local else None,
                "remote_version": self.remote.version if self.remote else None,
                "detected_at": self.detected_at}


class ConflictEngine:
    """Detects conflicts and merges only when it is safe (spec 36/37/38)."""

    def detect(self, local: MemoryRecord | None,
               remote: MemoryRecord | None) -> Conflict | None:
        if local is None and remote is None:
            return None
        mid = (local or remote).memory_id  # type: ignore[union-attr]
        if local is not None and remote is not None:
            if local.deleted and remote.deleted:
                return None
            if local.deleted and not remote.deleted:
                return Conflict(mid, ConflictType.DELETE_UPDATE, local, remote,
                                "deleted locally, updated remotely")
            if remote.deleted and not local.deleted:
                return Conflict(mid, ConflictType.UPDATE_DELETE, local, remote,
                                "updated locally, deleted remotely")
            if local.content != remote.content:
                if local.version == remote.version:
                    return Conflict(mid, ConflictType.CONTENT_CONFLICT, local, remote,
                                    "same version, different content")
                return Conflict(mid, ConflictType.UPDATE_UPDATE, local, remote,
                                f"v{local.version} (local) vs v{remote.version} (remote)")
            # same content, differing metadata only
            if (local.scope != remote.scope or local.importance != remote.importance
                    or local.confidence != remote.confidence):
                return Conflict(mid, ConflictType.METADATA_CONFLICT, local, remote,
                                "same content, different metadata")
            if local.version != remote.version:
                return Conflict(mid, ConflictType.VERSION_MISMATCH, local, remote,
                                f"v{local.version} vs v{remote.version}")
        return None

    def resolve(self, conflict: Conflict) -> Conflict:
        """spec 36/38: never blind-overwrite; keep BOTH versions when unclear.

        A CONTENT_CONFLICT at the same version cannot be safely merged, so both
        are retained and the record is flagged for review (spec 38's port 8000
        vs 9000 example: do NOT merge into a false statement).
        """
        loc, rem = conflict.local, conflict.remote
        if conflict.type in (ConflictType.CONTENT_CONFLICT,
                             ConflictType.METADATA_CONFLICT):
            conflict.resolution = "manual"
            return conflict
        if conflict.type is ConflictType.VERSION_MISMATCH:
            # same content; the newer version number simply wins
            if loc and rem and loc.version >= rem.version:
                conflict.resolution = "local_wins"
            else:
                conflict.resolution = "remote_wins"
            return conflict
        # UPDATE/UPDATE with differing versions -> newest write wins, history kept
        if loc and rem:
            conflict.resolution = ("local_wins" if loc.updated_at >= rem.updated_at
                                   else "remote_wins")
        else:
            conflict.resolution = "manual"
        return conflict


# --------------------------------------------------------------------------
# spec 32/57/58: the sync engine
# --------------------------------------------------------------------------
class SyncEngine:
    """Queues local changes and pushes them when a cloud provider exists."""

    def __init__(self, store: Any, *, provider: CloudMemoryProvider | None = None,
                 changelog: ChangeLog | None = None, device_id: str = "",
                 strategy: str = "on_write", max_retries: int = 3) -> None:
        self._store = store
        self._provider = provider or NullCloudProvider()
        self._log = changelog or ChangeLog()
        self._device_id = device_id
        # spec 57: resource-conscious default
        self._strategy = strategy
        self._max_retries = max_retries
        self._conflicts: list[Conflict] = []
        self._engine = ConflictEngine()
        self._last_sync: float | None = None
        self._backoff = 0.0

    # -- queueing --------------------------------------------------------
    def record(self, rec: MemoryRecord, op: Operation = Operation.CREATE) -> ChangeEntry:
        """Queue a local change (spec 31: LOCAL + SYNC_QUEUE)."""
        return self._log.append(rec, op, device_id=self._device_id)

    # -- status ----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        st = self._log.stats()
        return {"pending": st["pending"], "total": st["total"],
                "applied": st["applied"], "failed": st["failed"],
                "conflicts": len(self._conflicts),
                "provider": self._provider.name,
                "cloud": self._provider.health().get("status", "UNKNOWN"),
                "strategy": self._strategy,
                "last_sync": self._last_sync,
                "local_only": isinstance(self._provider, NullCloudProvider)}

    def conflicts(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._conflicts]

    # -- sync ------------------------------------------------------------
    def sync(self) -> dict[str, Any]:
        """Push pending changes, pull remote ones, resolve conflicts (spec 32)."""
        pending = self._log.pending()
        if not pending:
            self._last_sync = time.time()
            return {"pushed": 0, "pulled": 0, "conflicts": 0,
                    "reason": "nothing pending", "local_only":
                        isinstance(self._provider, NullCloudProvider)}

        # spec 58: cloud unavailable -> keep the queue, do not fail MOON
        h = self._provider.health()
        if h.get("status") != "ONLINE":
            self._backoff = min(300.0, (self._backoff or 1.0) * 2)
            return {"pushed": 0, "pulled": 0, "conflicts": 0,
                    "queued": len(pending), "cloud": h.get("status"),
                    "reason": h.get("detail", "cloud unavailable"),
                    "retry_in_s": self._backoff, "local_only": True}

        # gather the records being pushed
        records: dict[str, MemoryRecord] = {}
        for e in pending:
            r = self._store.get(e.memory_id, include_deleted=True)
            if r is not None:
                records[e.memory_id] = r

        try:
            pushed = self._provider.push(pending, records)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sync push failed: %s", exc)
            self._log.mark([e.operation_id for e in pending], "failed")
            return {"pushed": 0, "pulled": 0, "conflicts": 0,
                    "failed": len(pending), "error": str(exc)}

        # spec 34: idempotent -- mark applied by operation id
        applied = pushed.get("applied_ids") or [e.operation_id for e in pending]
        self._log.mark(applied, "applied")
        self._store.mark_synced(list(records.keys()), SyncStatus.SYNCED)

        # pull + conflict-check (spec 36)
        pulled = 0
        try:
            remote_records = self._provider.pull(since=self._last_sync)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sync pull failed: %s", exc)
            remote_records = []

        for rr in remote_records:
            local = self._store.get(rr.memory_id, include_deleted=True)
            c = self._engine.detect(local, rr)
            if c is not None:
                self._conflicts.append(self._engine.resolve(c))
                self._store.mark_synced([rr.memory_id], SyncStatus.CONFLICT)
                logger.warning("sync conflict on %s: %s", rr.memory_id, c.type.value)
                continue
            self._store.upsert(rr)
            pulled += 1

        self._last_sync = time.time()
        self._backoff = 0.0
        return {"pushed": len(applied), "pulled": pulled,
                "conflicts": len([c for c in self._conflicts]),
                "cloud": "ONLINE", "local_only": False}


__all__ = [
    "SyncEngine", "ChangeLog", "ChangeEntry", "Operation", "payload_hash",
    "CloudMemoryProvider", "NullCloudProvider", "ConflictEngine", "Conflict",
    "ConflictType",
]
