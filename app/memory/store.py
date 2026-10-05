"""Local-first SQLite memory store (spec 26, 28, 52, 71).

Supports per‑memory‑type database files. Each logical memory layer (MemoryType) lives in its own
SQLite file under ``MOON_MEMORY_PATH`` (or the default ``~/.moon/memory``). The function
``default_db_path`` accepts an optional ``memory_type`` to compute the filename; if omitted
the historic ``moon.db`` file is used for backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from app.memory.record import MemoryRecord, Scope, SyncStatus, MemoryType

logger = logging.getLogger(__name__)

# spec 26: preferred data directory
DEFAULT_MEMORY_DIR = Path(os.environ.get("MOON_MEMORY_PATH", "") or (Path.home() / ".moon" / "memory"))

SCHEMA_VERSION = 1

def default_db_path(memory_type: str | None = None) -> Path:
    """Return the default SQLite database path.
    If ``memory_type`` is provided, the file is ``<memory_type>.db``; otherwise the historic
    ``moon.db`` file is used. ``MOON_MEMORY_PATH`` overrides the base directory for all
    stores.
    """
    base = Path(os.environ.get("MOON_MEMORY_PATH", "") or DEFAULT_MEMORY_DIR)
    filename = f"{memory_type}.db" if memory_type else "moon.db"
    return base / filename

# --------------------------------------------------------------------------
# spec 28: abstraction
# --------------------------------------------------------------------------
class MemoryStore:
    """Backend‑agnostic memory persistence (spec 28)."""

    name: str = "abstract"

    def upsert(self, rec: MemoryRecord) -> MemoryRecord:  # pragma: no cover
        raise NotImplementedError

    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryRecord | None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:  # pragma: no cover
        raise NotImplementedError

    def query(
        self,
        *,
        scope: Scope | None = None,
        type_: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
        include_archived: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:  # pragma: no cover
        raise NotImplementedError

    def count(self, **kw: Any) -> int:  # pragma: no cover
        raise NotImplementedError

    def all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]:  # pragma: no cover
        raise NotImplementedError

    def touch(self, memory_id: str) -> None:  # pragma: no cover
        pass

    def health(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        pass

# --------------------------------------------------------------------------
# spec 26/71: local SQLite implementation with per‑type files
# --------------------------------------------------------------------------
_COLUMNS = (
    "memory_id",
    "content",
    "summary",
    "scope",
    "type",
    "owner_id",
    "agent_id",
    "project_id",
    "task_id",
    "session_id",
    "tags",
    "confidence",
    "importance",
    "relevance",
    "source_type",
    "source",
    "provenance",
    "created_at",
    "updated_at",
    "accessed_at",
    "expires_at",
    "version",
    "parent_version",
    "device_id",
    "sync_status",
    "deleted",
    "archived",
    "trusted",
    "embedding_pending",
    "canonical",
    "verified_at",
    "verified_by",
)

class LocalMemoryStore(MemoryStore):
    """SQLite‑backed local store (spec 26) with a separate file per ``MemoryType``.
    Legacy single‑file mode is still supported via the ``db_path`` argument.
    """

    name = "local_sqlite"

    def __init__(self, db_path: str | Path | None = None) -> None:
        # Legacy mode – a single database file.
        self._legacy = bool(db_path)
        self._lock = threading.RLock()
        self._conns: dict[str, sqlite3.Connection] = {}
        self._paths: dict[str, Path] = {}
        if self._legacy:
            path = Path(db_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._conns["_legacy"] = conn
            self._paths["_legacy"] = path
            self._configure_conn(conn)
            self._migrate_conn(conn)
        else:
            # Create one connection per MemoryType.
            for mtype in MemoryType:
                path = default_db_path(mtype.value)
                path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(path), check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._conns[mtype.value] = conn
                self._paths[mtype.value] = path
                self._configure_conn(conn)
                self._migrate_conn(conn)
        # Store the latest schema version for health reporting.
        self._schema_version = SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def _configure_conn(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-8000")
        cur.execute("PRAGMA busy_timeout=5000")
        conn.commit()

    def _migrate_conn(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at REAL)"
        )
        cur.execute("SELECT MAX(version) FROM schema_version")
        row = cur.fetchone()
        current = row[0] if row and row[0] is not None else 0
        if current < 1:
            typed = {
                "confidence": "REAL",
                "relevance": "REAL",
                "created_at": "REAL",
                "updated_at": "REAL",
                "accessed_at": "REAL",
                "expires_at": "REAL",
                "version": "INTEGER",
                "parent_version": "INTEGER",
                "deleted": "INTEGER",
                "archived": "INTEGER",
                "trusted": "INTEGER",
                "embedding_pending": "INTEGER",
                "canonical": "INTEGER",
                "verified_at": "REAL",
            }
            cols_def = ", ".join(f"{c} {typed.get(c, 'TEXT')}" for c in _COLUMNS)
            cur.execute(f"CREATE TABLE IF NOT EXISTS memories ({cols_def}, PRIMARY KEY (memory_id))")
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
            cur.execute("INSERT OR REPLACE INTO schema_version VALUES (1, ?)", (time.time(),))
            # Migration log table for future use.
            cur.execute(
                "CREATE TABLE IF NOT EXISTS migration_log (id INTEGER PRIMARY KEY AUTOINCREMENT, applied_at REAL NOT NULL, description TEXT)"
            )
            cur.execute(
                "INSERT INTO migration_log (applied_at, description) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM migration_log WHERE description = ?)",
                (time.time(), "initial schema + migration_log", "initial schema + migration_log"),
            )
            conn.commit()
            self._schema_version = 1

    def _conn_for_type(self, mem_type: str | None) -> sqlite3.Connection:
        if self._legacy:
            return self._conns["_legacy"]
        if mem_type and mem_type in self._conns:
            return self._conns[mem_type]
        # Fallback to any connection (first one).
        return next(iter(self._conns.values()))

    # ------------------------------------------------------------------
    # Record ↔ dict helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        d = dict(row)
        for k in ("tags", "provenance"):
            try:
                d[k] = json.loads(d.get(k) or ("[]" if k == "tags" else "{}"))
            except Exception:  # noqa: BLE001
                d[k] = [] if k == "tags" else {}
        for k in (
            "deleted",
            "archived",
            "trusted",
            "embedding_pending",
            "canonical",
        ):
            d[k] = bool(d.get(k))
        return MemoryRecord.from_dict(d)

    @staticmethod
    def _record_to_params(rec: MemoryRecord) -> dict[str, Any]:
        d = rec.to_dict()
        return {
            "memory_id": d["memory_id"],
            "content": d.get("content", ""),
            "summary": d.get("summary", ""),
            "scope": d.get("scope"),
            "type": d.get("type"),
            "owner_id": d.get("owner_id", ""),
            "agent_id": d.get("agent_id", ""),
            "project_id": d.get("project_id", ""),
            "task_id": d.get("task_id", ""),
            "session_id": d.get("session_id", ""),
            "tags": json.dumps(d.get("tags") or []),
            "confidence": float(d.get("confidence") or 0.0),
            "importance": d.get("importance"),
            "relevance": float(d.get("relevance") or 0.0),
            "source_type": d.get("source_type"),
            "source": d.get("source", ""),
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

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def upsert(self, rec: MemoryRecord) -> MemoryRecord:
        """spec 34: idempotent – same ``memory_id`` updates in place."""
        params = self._record_to_params(rec)
        placeholders = ", ".join(f":{c}" for c in _COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "memory_id")
        conn = self._conn_for_type(getattr(rec.type, "value", None) if isinstance(rec.type, MemoryType) else rec.type)
        with self._lock:
            conn.execute(
                f"INSERT INTO memories ({', '.join(_COLUMNS)}) VALUES ({placeholders}) ON CONFLICT(memory_id) DO UPDATE SET {updates}",
                params,
            )
            conn.commit()
        return rec

    def mark_synced(self, memory_ids: list[str], status: SyncStatus) -> None:
        """Update sync_status for given memory_ids.

        Used by sync engine to mark records as SYNCED or CONFLICT.
        """
        for conn in self._conns.values():
            cur = conn.cursor()
            cur.execute(
                "UPDATE memories SET sync_status=?, updated_at=? WHERE memory_id IN (" + ",".join(["?" for _ in memory_ids]) + ")",
                (status.value, time.time(), *memory_ids),
            )
            conn.commit()

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        """spec 18: soft delete by default; hard delete when requested."""
        for conn in self._conns.values():
            cur = conn.cursor()
            if hard:
                cur.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
            else:
                cur.execute(
                    "UPDATE memories SET deleted=1, updated_at=?, sync_status=? WHERE memory_id=?",
                    (time.time(), SyncStatus.PENDING.value, memory_id),
                )
            conn.commit()
            if cur.rowcount > 0:
                return True
        return False


    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryRecord | None:
        for conn in self._conns.values():
            sql = "SELECT * FROM memories WHERE memory_id=?"
            if not include_deleted:
                sql += " AND deleted=0"
            row = conn.execute(sql, (memory_id,)).fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def query(
        self,
        *,
        scope: Scope | None = None,
        type_: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
        include_archived: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        where: list[str] = []
        args: list[Any] = []
        if not include_deleted:
            where.append("deleted=0")
        if not include_archived:
            where.append("archived=0")
        if scope is not None:
            where.append("scope=?")
            args.append(getattr(scope, "value", scope))
        if type_ is not None:
            where.append("type=?")
            args.append(getattr(type_, "value", type_))
        if agent_id is not None:
            where.append("agent_id=?")
            args.append(agent_id)
        if project_id is not None:
            where.append("project_id=?")
            args.append(project_id)
        if task_id is not None:
            where.append("task_id=?")
            args.append(task_id)
        if keyword:
            where.append("(LOWER(content) LIKE ? OR LOWER(summary) LIKE ?)")
            like = f"%{keyword.lower()}%"
            args.extend([like, like])
        if tags:
            for t in tags:
                where.append("tags LIKE ?")
                args.append(f'%"{t}"%')
        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        args.extend([int(limit), int(offset)])
        results: list[MemoryRecord] = []
        # If a specific type is requested, query only that connection.
        if type_:
            conn = self._conn_for_type(type_)
            rows = conn.execute(sql, args).fetchall()
            results.extend(self._row_to_record(r) for r in rows)
        else:
            for conn in self._conns.values():
                rows = conn.execute(sql, args).fetchall()
                results.extend(self._row_to_record(r) for r in rows)
        return results

    def count(self, **kw: Any) -> int:
        where: list[str] = []
        args: list[Any] = []
        if not kw.get("include_deleted"):
            where.append("deleted=0")
        if not kw.get("include_archived"):
            where.append("archived=0")
        if kw.get("sync_status") is not None:
            where.append("sync_status=?")
            args.append(kw["sync_status"])
        if kw.get("scope") is not None:
            where.append("scope=?")
            args.append(getattr(kw["scope"], "value", kw["scope"]))
        sql = "SELECT COUNT(*) FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        total = 0
        for conn in self._conns.values():
            total += int(conn.execute(sql, args).fetchone()[0])
        return total

    def all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]:
        sql = (
            "SELECT * FROM memories WHERE deleted=0 AND archived=0 AND embedding_pending=1 ORDER BY updated_at DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        results: list[MemoryRecord] = []
        for conn in self._conns.values():
            rows = conn.execute(sql).fetchall()
            results.extend(self._row_to_record(r) for r in rows)
        return results

    # ------------------------------------------------------------------
    # Diagnostics / health
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        try:
            total = active = pending = 0
            for conn in self._conns.values():
                cur_total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                cur_active = conn.execute("SELECT COUNT(*) FROM memories WHERE deleted=0").fetchone()[0]
                cur_pending = conn.execute("SELECT COUNT(*) FROM memories WHERE sync_status='PENDING'").fetchone()[0]
                total += cur_total
                active += cur_active
                pending += cur_pending
            size = sum(p.stat().st_size for p in self._paths.values() if p.exists())
            return {
                "store": self.name,
                "online": True,
                "paths": [str(p) for p in self._paths.values()],
                "schema_version": self._schema_version,
                "total": total,
                "active": active,
                "pending_sync": pending,
                "size_bytes": size,
            }
        except Exception as exc:  # noqa: BLE001
            return {"store": self.name, "online": False, "error": str(exc)}

    def close(self) -> None:
        for conn in self._conns.values():
            try:
                conn.commit()
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def purge_expired(self) -> dict[str, int]:
        """Delete or archive records that exceed their layer's retention policy.

        Returns a dict mapping memory type (str) to number of records removed.
        """
        from .layers import LAYER_REGISTRY
        now = time.time()
        removed_counts: dict[str, int] = {}
        for mtype in MemoryType:
            layer = LAYER_REGISTRY.get(mtype)
            if not layer or layer.retention_seconds is None:
                continue
            cutoff = now - layer.retention_seconds
            conn = self._conns[mtype.value]
            cur = conn.cursor()
            cur.execute(
                "SELECT memory_id FROM memories WHERE type = ? AND updated_at < ? AND deleted = 0",
                (mtype.value, cutoff),
            )
            ids = [row[0] for row in cur.fetchall()]
            count = 0
            for mem_id in ids:
                self.delete(mem_id, hard=False)
                count += 1
            if count:
                removed_counts[mtype.value] = count
        return removed_counts

__all__ = ["MemoryStore", "LocalMemoryStore", "default_db_path", "DEFAULT_MEMORY_DIR", "SCHEMA_VERSION"]
