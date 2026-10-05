"""Cloud memory store backed by PostgreSQL via asyncpg.

Replaces the in-memory stub with a real, persistent, async PostgreSQL
implementation. The store satisfies the same :class:`MemoryStore` interface
as the local SQLite store, so it can be used as a drop-in replacement when
``MOON_MEMORY_BACKEND=cloud`` and ``MOON_DATABASE_URL`` is set.

The asyncpg driver runs in a dedicated background event-loop thread; all
public methods are synchronous and bridge to that loop, so no caller
changes are required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Any

import asyncpg

from .record import MemoryRecord, MemoryType, Scope, SyncStatus
from .store import MemoryStore

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Column definitions – mirrors LocalMemoryStore._COLUMNS
# ---------------------------------------------------------------------------
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

# Columns that are JSONB in PostgreSQL
_JSONB_COLUMNS = {"tags", "provenance"}

# Columns that are REAL (float) in PostgreSQL
_REAL_COLUMNS = {
    "confidence", "relevance", "created_at", "updated_at",
    "accessed_at", "expires_at", "verified_at",
}

# Columns that are INTEGER in PostgreSQL
_INT_COLUMNS = {"version", "parent_version"}

# Columns that are BOOLEAN in PostgreSQL
_BOOL_COLUMNS = {"deleted", "archived", "trusted", "embedding_pending", "canonical"}


class CloudMemoryStore(MemoryStore):
    """PostgreSQL-backed cloud memory store using asyncpg.

    Parameters
    ----------
    dsn:
        PostgreSQL connection string. Defaults to ``MOON_DATABASE_URL``.
    """

    name = "cloud_postgres"

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.getenv("MOON_DATABASE_URL", "")
        if not self._dsn:
            raise RuntimeError(
                "CloudMemoryStore requires MOON_DATABASE_URL to be set"
            )
        self._loop = asyncio.new_event_loop()
        self._pool: asyncpg.Pool | None = None
        self._lock = threading.RLock()
        self._schema_version = _SCHEMA_VERSION
        self._thread = threading.Thread(
            target=self._run_loop, name="cloud-memory-loop", daemon=True
        )
        self._thread.start()
        # Initialise pool and schema synchronously so the store is ready.
        self._run_async(self._init())

    # ------------------------------------------------------------------
    # Event-loop management
    # ------------------------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro: Any) -> Any:
        """Run a coroutine on the background loop and block for the result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _init(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
        await self._migrate()

    async def _migrate(self) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            row = await conn.fetchrow(
                "SELECT MAX(version) AS v FROM schema_version"
            )
            current = row["v"] if row and row["v"] is not None else 0
            if current < 1:
                await self._create_schema(conn)
                await conn.execute(
                    "INSERT INTO schema_version VALUES ($1, $2)",
                    _SCHEMA_VERSION,
                    time.time(),
                )

    async def _create_schema(self, conn: asyncpg.Connection) -> None:
        # Build column definitions
        col_defs: list[str] = []
        for col in _COLUMNS:
            if col == "memory_id":
                col_defs.append("memory_id TEXT PRIMARY KEY")
            elif col in _JSONB_COLUMNS:
                col_defs.append(f"{col} JSONB NOT NULL DEFAULT '[]'::jsonb")
            elif col in _REAL_COLUMNS:
                col_defs.append(f"{col} DOUBLE PRECISION")
            elif col in _INT_COLUMNS:
                col_defs.append(f"{col} INTEGER")
            elif col in _BOOL_COLUMNS:
                col_defs.append(f"{col} BOOLEAN NOT NULL DEFAULT FALSE")
            else:
                col_defs.append(f"{col} TEXT NOT NULL DEFAULT ''")

        cols_sql = ", ".join(col_defs)
        await conn.execute(f"CREATE TABLE IF NOT EXISTS memories ({cols_sql})")

        # Indexes
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS ix_mem_scope ON memories(scope)",
            "CREATE INDEX IF NOT EXISTS ix_mem_type ON memories(type)",
            "CREATE INDEX IF NOT EXISTS ix_mem_agent ON memories(agent_id)",
            "CREATE INDEX IF NOT EXISTS ix_mem_project ON memories(project_id)",
            "CREATE INDEX IF NOT EXISTS ix_mem_task ON memories(task_id)",
            "CREATE INDEX IF NOT EXISTS ix_mem_sync ON memories(sync_status)",
            "CREATE INDEX IF NOT EXISTS ix_mem_deleted ON memories(deleted)",
            "CREATE INDEX IF NOT EXISTS ix_mem_archived ON memories(archived)",
        ):
            await conn.execute(idx_sql)

    # ------------------------------------------------------------------
    # Record <-> dict helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _record_to_params(rec: MemoryRecord) -> dict[str, Any]:
        d = rec.to_dict()
        params: dict[str, Any] = {}
        for col in _COLUMNS:
            val = d.get(col, "")
            if col in _JSONB_COLUMNS:
                params[col] = json.dumps(val or ([] if col == "tags" else {}))
            elif col in _REAL_COLUMNS:
                params[col] = float(val) if val is not None else None
            elif col in _INT_COLUMNS:
                params[col] = int(val) if val is not None else None
            elif col in _BOOL_COLUMNS:
                params[col] = bool(val)
            else:
                params[col] = str(val) if val is not None else ""
        return params

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> MemoryRecord:
        d = dict(row)
        for k in ("tags", "provenance"):
            v = d.get(k)
            if isinstance(v, str):
                try:
                    d[k] = json.loads(v)
                except Exception:
                    d[k] = [] if k == "tags" else {}
            elif v is None:
                d[k] = [] if k == "tags" else {}
        for k in _BOOL_COLUMNS:
            d[k] = bool(d.get(k, False))
        for k in _REAL_COLUMNS:
            if d.get(k) is not None:
                d[k] = float(d[k])
        for k in _INT_COLUMNS:
            if d.get(k) is not None:
                d[k] = int(d[k])
        return MemoryRecord.from_dict(d)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def upsert(self, rec: MemoryRecord) -> MemoryRecord:
        return self._run_async(self._upsert(rec))

    async def _upsert(self, rec: MemoryRecord) -> MemoryRecord:
        assert self._pool is not None
        now = time.time()
        rec.updated_at = now
        rec.accessed_at = now
        rec.sync_status = SyncStatus.SYNCED
        params = self._record_to_params(rec)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(f"${i+1}" for i in range(len(_COLUMNS)))
        updates = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in _COLUMNS if c != "memory_id"
        )
        sql = (
            f"INSERT INTO memories ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT (memory_id) DO UPDATE SET {updates}"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(sql, *[params[c] for c in _COLUMNS])
        return rec

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        return self._run_async(self._delete(memory_id, hard=hard))

    async def _delete(self, memory_id: str, *, hard: bool = False) -> bool:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            if hard:
                result = await conn.execute(
                    "DELETE FROM memories WHERE memory_id = $1", memory_id
                )
                return result != "DELETE 0"
            else:
                result = await conn.execute(
                    """
                    UPDATE memories
                    SET deleted = TRUE, updated_at = $2, sync_status = $3
                    WHERE memory_id = $1 AND deleted = FALSE
                    """,
                    memory_id,
                    time.time(),
                    SyncStatus.PENDING.value,
                )
                return result != "UPDATE 0"

    def touch(self, memory_id: str) -> None:
        self._run_async(self._touch(memory_id))

    async def _touch(self, memory_id: str) -> None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memories SET accessed_at = $2 WHERE memory_id = $1",
                memory_id,
                time.time(),
            )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get(
        self, memory_id: str, *, include_deleted: bool = False
    ) -> MemoryRecord | None:
        return self._run_async(self._get(memory_id, include_deleted=include_deleted))

    async def _get(
        self, memory_id: str, *, include_deleted: bool = False
    ) -> MemoryRecord | None:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            if include_deleted:
                row = await conn.fetchrow(
                    "SELECT * FROM memories WHERE memory_id = $1", memory_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM memories WHERE memory_id = $1 AND deleted = FALSE",
                    memory_id,
                )
            return self._row_to_record(row) if row else None

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
        return self._run_async(
            self._query(
                scope=scope,
                type_=type_,
                agent_id=agent_id,
                project_id=project_id,
                task_id=task_id,
                tags=tags,
                keyword=keyword,
                include_archived=include_archived,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            )
        )

    async def _query(
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
        assert self._pool is not None
        conditions: list[str] = []
        params: list[Any] = []
        pidx = 1

        if not include_deleted:
            conditions.append("deleted = FALSE")
        if not include_archived:
            conditions.append("archived = FALSE")
        if scope is not None:
            conditions.append(f"scope = ${pidx}")
            params.append(scope.value if isinstance(scope, Scope) else scope)
            pidx += 1
        if type_ is not None:
            conditions.append(f"type = ${pidx}")
            params.append(type_)
            pidx += 1
        if agent_id is not None:
            conditions.append(f"agent_id = ${pidx}")
            params.append(agent_id)
            pidx += 1
        if project_id is not None:
            conditions.append(f"project_id = ${pidx}")
            params.append(project_id)
            pidx += 1
        if task_id is not None:
            conditions.append(f"task_id = ${pidx}")
            params.append(task_id)
            pidx += 1
        if tags:
            # All specified tags must be present in the JSONB array
            conditions.append(f"tags @> ${pidx}::jsonb")
            params.append(json.dumps(tags))
            pidx += 1
        if keyword:
            kw = keyword.lower()
            conditions.append(
                f"(LOWER(content) LIKE ${pidx} OR LOWER(summary) LIKE ${pidx})"
            )
            params.append(f"%{kw}%")
            pidx += 1

        where = " AND ".join(conditions) if conditions else "TRUE"
        sql = (
            f"SELECT * FROM memories WHERE {where} "
            f"ORDER BY updated_at DESC LIMIT ${pidx} OFFSET ${pidx + 1}"
        )
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [self._row_to_record(r) for r in rows]

    def count(self, **kw: Any) -> int:
        return self._run_async(self._count(**kw))

    async def _count(self, **kw: Any) -> int:
        # Reuse query logic but only need the count
        conditions: list[str] = []
        params: list[Any] = []
        pidx = 1

        include_deleted = kw.get("include_deleted", False)
        include_archived = kw.get("include_archived", False)
        scope = kw.get("scope")
        type_ = kw.get("type_")
        agent_id = kw.get("agent_id")
        project_id = kw.get("project_id")
        task_id = kw.get("task_id")
        tags = kw.get("tags")
        keyword = kw.get("keyword")

        if not include_deleted:
            conditions.append("deleted = FALSE")
        if not include_archived:
            conditions.append("archived = FALSE")
        if scope is not None:
            conditions.append(f"scope = ${pidx}")
            params.append(scope.value if isinstance(scope, Scope) else scope)
            pidx += 1
        if type_ is not None:
            conditions.append(f"type = ${pidx}")
            params.append(type_)
            pidx += 1
        if agent_id is not None:
            conditions.append(f"agent_id = ${pidx}")
            params.append(agent_id)
            pidx += 1
        if project_id is not None:
            conditions.append(f"project_id = ${pidx}")
            params.append(project_id)
            pidx += 1
        if task_id is not None:
            conditions.append(f"task_id = ${pidx}")
            params.append(task_id)
            pidx += 1
        if tags:
            conditions.append(f"tags @> ${pidx}::jsonb")
            params.append(json.dumps(tags))
            pidx += 1
        if keyword:
            kw = keyword.lower()
            conditions.append(
                f"(LOWER(content) LIKE ${pidx} OR LOWER(summary) LIKE ${pidx})"
            )
            params.append(f"%{kw}%")
            pidx += 1

        where = " AND ".join(conditions) if conditions else "TRUE"
        sql = f"SELECT COUNT(*) AS cnt FROM memories WHERE {where}"

        assert self._pool is not None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
            return row["cnt"] if row else 0

    def all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]:
        return self._run_async(self._all_for_embedding(limit=limit))

    async def _all_for_embedding(self, *, limit: int = 0) -> list[MemoryRecord]:
        assert self._pool is not None
        sql = (
            "SELECT * FROM memories WHERE deleted = FALSE AND archived = FALSE "
            "ORDER BY updated_at DESC"
        )
        params: list[Any] = []
        if limit:
            sql += " LIMIT $1"
            params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [self._row_to_record(r) for r in rows]

    # ------------------------------------------------------------------
    # Diagnostics / health
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return self._run_async(self._health())

    async def _health(self) -> dict[str, Any]:
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM memories")
            active = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE deleted = FALSE"
            )
            pending = await conn.fetchval(
                "SELECT COUNT(*) FROM memories WHERE sync_status = $1",
                SyncStatus.PENDING.value,
            )
            return {
                "store": self.name,
                "online": True,
                "schema_version": self._schema_version,
                "total": total or 0,
                "active": active or 0,
                "pending_sync": pending or 0,
            }

    def close(self) -> None:
        if self._pool is not None:
            self._run_async(self._close())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


__all__ = ["CloudMemoryStore"]
