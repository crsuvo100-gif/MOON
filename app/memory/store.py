"""Local-first SQLite memory store (spec 26, 28, 52, 71).

Local-first, zero-dependency (stdlib ``sqlite3``), lightweight enough for
low-resource hosts (spec 52). Implements the ``MemoryStore`` abstraction so a
cloud store can be added without MemoryManager knowing the difference (spec 28).

Design rules honoured here:
  * spec 26  default path ~/.moon/memory/moon.db (overridable via MOON_MEMORY_PATH)
  * spec 52  WAL journal, bounded page cache, no background workers
  * spec 71  versioned migrations (schema_version table), additive only
  * spec 18  soft delete (``deleted`` flag) -- data is never silently destroyed
  * spec 34  idempotent upsert keyed on memory_id
  * spec 88  this is STORAGE; it holds no context or instruction logic
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.memory.record import MemoryRecord, Scope, SyncStatus

logger = logging.getLogger(__name__)

# spec 26: preferred data directory
DEFAULT_MEMORY_DIR = Path(os.environ.get("MOON_MEMORY_PATH", "") or
                          (Path.home() / ".moon" / "memory"))

SCHEMA_VERSION = 1


def default_db_path() -> Path:
    d = Path(os.environ.get("MOON_MEMORY_PATH", "") or DEFAULT_MEMORY_DIR)
    return d / "moon.db"


# --------------------------------------------------------------------------
# spec 28: abstraction
# --------------------------------------------------------------------------
class MemoryStore(ABC):
    """Backend-agnostic memory persistence (spec 28).

    MemoryManager depends on THIS, never on SQLite/Postgres directly.
    """

    name: str = "abstract"

    @abstractmethod
    def upsert(self, rec: MemoryRecord) -> MemoryRecord: ...

    @abstractmethod
    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryRecord | None: ...

    @abstractmethod
    def delete(self, memory_id: str, *, hard: bool = False) -> bool: ...

    @abstractmethod
    def query(self, *, scope: Scope | None = None, type_: str | None = None,
              agent_id: str | None = None, project_id: str | None = None,
              task_id: str | None = None, tags: list[str] | None = None,
              keyword: str | None = None, include_archived: bool = False,
              include_deleted: bool = False, limit: int = 50,
              offset: int = 0) -> list[MemoryRecord]: ...

    @abstractmethod
    def count(self, **kw: Any) -> int: ...

    @abstractmethod
    def all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]: ...

    def touch(self, memory_id: str) -> None:
        """Record an access (feeds decay/ranking). Optional for backends."""
        return None

    @abstractmethod
    def health(self) -> dict[str, Any]: ...

    def close(self) -> None:  # pragma: no cover - optional
        return None


# --------------------------------------------------------------------------
# spec 26/71: local SQLite implementation
# --------------------------------------------------------------------------
_COLUMNS = (
    "memory_id", "content", "summary", "scope", "type", "owner_id", "agent_id",
    "project_id", "task_id", "session_id", "tags", "confidence", "importance",
    "relevance", "source_type", "source", "provenance", "created_at",
    "updated_at", "accessed_at", "expires_at", "version", "parent_version",
    "device_id", "sync_status", "deleted", "archived", "trusted",
    "embedding_pending", "canonical", "verified_at", "verified_by",
)


class LocalMemoryStore(MemoryStore):
    """SQLite-backed local store (spec 26)."""

    name = "local_sqlite"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else default_db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    # -- setup ----------------------------------------------------------
    def _configure(self) -> None:
        cur = self._conn.cursor()
        # spec 52: bounded, single-writer, no aggressive fsync churn
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-8000")      # ~8MB page cache
        cur.execute("PRAGMA busy_timeout=5000")     # spec 58: bounded retry
        self._conn.commit()

    def _migrate(self) -> None:
        """spec 71: versioned, additive migrations."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER PRIMARY KEY, applied_at REAL)")
            cur.execute("SELECT MAX(version) FROM schema_version")
            row = cur.fetchone()
            current = row[0] if row and row[0] is not None else 0

            if current < 1:
                cols = ", ".join(f"{c} TEXT" for c in _COLUMNS)
                # typed columns for the ones we filter/sort on
                typed = {
                    "confidence": "REAL", "relevance": "REAL",
                    "created_at": "REAL", "updated_at": "REAL",
                    "accessed_at": "REAL", "expires_at": "REAL",
                    "version": "INTEGER", "parent_version": "INTEGER",
                    "deleted": "INTEGER", "archived": "INTEGER",
                    "trusted": "INTEGER", "embedding_pending": "INTEGER",
                    "canonical": "INTEGER", "verified_at": "REAL",
                }
                cols = ", ".join(f"{c} {typed.get(c, 'TEXT')}" for c in _COLUMNS)
                cur.execute(f"CREATE TABLE IF NOT EXISTS memories ({cols}, "
                            "PRIMARY KEY (memory_id))")
                for idx in (
                    "CREATE INDEX IF NOT EXISTS ix_mem_scope ON memories(scope)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_type ON memories(type)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_agent ON memories(agent_id)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_project ON memories(project_id)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_task ON memories(task_id)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_sync ON memories(sync_status)",
                    "CREATE INDEX IF NOT EXISTS ix_mem_deleted ON memories(deleted)",
                ):
                    cur.execute(idx)
                cur.execute("INSERT OR REPLACE INTO schema_version VALUES (1, ?)",
                            (time.time(),))
                current = 1
            self._conn.commit()
        self._schema_version = current

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        d = dict(row)
        for k in ("tags", "provenance"):
            try:
                d[k] = json.loads(d.get(k) or ("[]" if k == "tags" else "{}"))
            except Exception:  # noqa: BLE001
                d[k] = [] if k == "tags" else {}
        for k in ("deleted", "archived", "trusted", "embedding_pending", "canonical"):
            d[k] = bool(d.get(k))
        return MemoryRecord.from_dict(d)

    @staticmethod
    def _record_to_params(rec: MemoryRecord) -> dict[str, Any]:
        d = rec.to_dict()
        return {
            "memory_id": d["memory_id"], "content": d.get("content", ""),
            "summary": d.get("summary", ""),
            "scope": d.get("scope"), "type": d.get("type"),
            "owner_id": d.get("owner_id", ""), "agent_id": d.get("agent_id", ""),
            "project_id": d.get("project_id", ""), "task_id": d.get("task_id", ""),
            "session_id": d.get("session_id", ""),
            "tags": json.dumps(d.get("tags") or []),
            "confidence": float(d.get("confidence") or 0.0),
            "importance": d.get("importance"),
            "relevance": float(d.get("relevance") or 0.0),
            "source_type": d.get("source_type"), "source": d.get("source", ""),
            "provenance": json.dumps(d.get("provenance") or {}),
            "created_at": float(d.get("created_at") or time.time()),
            "updated_at": float(d.get("updated_at") or time.time()),
            "accessed_at": float(d.get("accessed_at") or time.time()),
            "expires_at": d.get("expires_at"),
            "version": int(d.get("version") or 1),
            "parent_version": d.get("parent_version"),
            "device_id": d.get("device_id", ""),
            "sync_status": d.get("sync_status"),
            "deleted": int(bool(d.get("deleted"))),
            "archived": int(bool(d.get("archived"))),
            "trusted": int(bool(d.get("trusted"))),
            "embedding_pending": int(bool(d.get("embedding_pending"))),
            "canonical": int(bool(d.get("canonical"))),
            "verified_at": d.get("verified_at"),
            "verified_by": d.get("verified_by", ""),
        }

    # -- write ----------------------------------------------------------
    def upsert(self, rec: MemoryRecord) -> MemoryRecord:
        """spec 34: idempotent -- same memory_id updates in place."""
        params = self._record_to_params(rec)
        placeholders = ", ".join(f":{c}" for c in _COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS
                            if c != "memory_id")
        with self._lock:
            self._conn.execute(
                f"INSERT INTO memories ({', '.join(_COLUMNS)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(memory_id) DO UPDATE SET {updates}",
                params,
            )
            self._conn.commit()
        return rec

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        """spec 18: soft delete by default; hard only when explicitly asked."""
        with self._lock:
            cur = self._conn.cursor()
            if hard:
                cur.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
            else:
                cur.execute(
                    "UPDATE memories SET deleted=1, updated_at=?, "
                    "sync_status=? WHERE memory_id=?",
                    (time.time(), SyncStatus.PENDING.value, memory_id))
            self._conn.commit()
            return cur.rowcount > 0

    def touch(self, memory_id: str) -> None:
        """Record an access (feeds decay/ranking without changing content)."""
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET accessed_at=? WHERE memory_id=?",
                (time.time(), memory_id))
            self._conn.commit()

    def mark_synced(self, memory_ids: list[str], status: SyncStatus) -> int:
        if not memory_ids:
            return 0
        q = ",".join("?" for _ in memory_ids)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE memories SET sync_status=? WHERE memory_id IN ({q})",
                (status.value, *memory_ids))
            self._conn.commit()
            return cur.rowcount

    # -- read -----------------------------------------------------------
    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryRecord | None:
        sql = "SELECT * FROM memories WHERE memory_id=?"
        if not include_deleted:
            sql += " AND deleted=0"
        with self._lock:
            row = self._conn.execute(sql, (memory_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def query(self, *, scope: Scope | None = None, type_: str | None = None,
              agent_id: str | None = None, project_id: str | None = None,
              task_id: str | None = None, tags: list[str] | None = None,
              keyword: str | None = None, include_archived: bool = False,
              include_deleted: bool = False, limit: int = 50,
              offset: int = 0) -> list[MemoryRecord]:
        where: list[str] = []
        args: list[Any] = []
        if not include_deleted:
            where.append("deleted=0")
        if not include_archived:
            where.append("archived=0")
        if scope is not None:
            where.append("scope=?"); args.append(getattr(scope, "value", scope))
        if type_ is not None:
            where.append("type=?"); args.append(getattr(type_, "value", type_))
        if agent_id is not None:
            where.append("agent_id=?"); args.append(agent_id)
        if project_id is not None:
            where.append("project_id=?"); args.append(project_id)
        if task_id is not None:
            where.append("task_id=?"); args.append(task_id)
        if keyword:
            where.append("(LOWER(content) LIKE ? OR LOWER(summary) LIKE ?)")
            like = f"%{keyword.lower()}%"
            args.extend([like, like])
        if tags:
            for t in tags:
                where.append("tags LIKE ?"); args.append(f'%"{t}"%')
        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        args.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_record(r) for r in rows]

    def count(self, **kw: Any) -> int:
        where: list[str] = []
        args: list[Any] = []
        if not kw.get("include_deleted"):
            where.append("deleted=0")
        if not kw.get("include_archived"):
            where.append("archived=0")
        if kw.get("sync_status") is not None:
            where.append("sync_status=?"); args.append(kw["sync_status"])
        if kw.get("scope") is not None:
            where.append("scope=?"); args.append(getattr(kw["scope"], "value", kw["scope"]))
        sql = "SELECT COUNT(*) FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._lock:
            return int(self._conn.execute(sql, args).fetchone()[0])

    def all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]:
        sql = ("SELECT * FROM memories WHERE deleted=0 AND archived=0 "
               "AND embedding_pending=1 ORDER BY updated_at DESC")
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [self._row_to_record(r) for r in rows]

    # -- health / diagnostics -------------------------------------------
    def health(self) -> dict[str, Any]:
        try:
            with self._lock:
                total = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                active = self._conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE deleted=0").fetchone()[0]
                pending = self._conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE sync_status='PENDING'").fetchone()[0]
            size = self._path.stat().st_size if self._path.exists() else 0
            return {
                "store": self.name, "online": True, "path": str(self._path),
                "schema_version": self._schema_version,
                "total": total, "active": active, "pending_sync": pending,
                "size_bytes": size,
            }
        except Exception as exc:  # noqa: BLE001
            return {"store": self.name, "online": False, "error": str(exc)}

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass


__all__ = ["MemoryStore", "LocalMemoryStore", "default_db_path",
           "DEFAULT_MEMORY_DIR", "SCHEMA_VERSION"]
