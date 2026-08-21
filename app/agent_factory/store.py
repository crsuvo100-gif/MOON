"""Agent Factory SQLite store (spec section 39, subset).

Initial low-resource deployment uses SQLite; the interface is intentionally
small so it can be swapped for PostgreSQL later without touching the factory.

Lives at data/agents/agent_factory.db. Generated agent code lives under
data/agents/{staging,approved,quarantine}/ per spec section 14.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.agent_factory.models import AgentFactoryRecord, AuditEvent

_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "agents"


def data_root() -> Path:
    return _DATA_ROOT


def _staging_dir() -> Path:
    d = _DATA_ROOT / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _approved_dir() -> Path:
    d = _DATA_ROOT / "approved"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _quarantine_dir() -> Path:
    d = _DATA_ROOT / "quarantine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def stage_for(status: str) -> Path:
    """Map a status to its on-disk directory (spec 14)."""
    s = (status or "staging").lower()
    if s in ("approved", "active"):
        return _approved_dir()
    if s == "quarantined":
        return _quarantine_dir()
    return _staging_dir()


class AgentStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db = Path(db_path) if db_path else (_DATA_ROOT / "agent_factory.db")
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db))
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT,
                    version TEXT,
                    status TEXT,
                    stage TEXT,
                    risk_level TEXT,
                    description TEXT,
                    permissions TEXT,
                    required_tools TEXT,
                    capabilities TEXT,
                    module_path TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    previous_version TEXT,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_versions (
                    agent_id TEXT,
                    version TEXT,
                    module_path TEXT,
                    created_at TEXT,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_capabilities (
                    agent_id TEXT, capability TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_permissions (
                    agent_id TEXT, permission TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_executions (
                    execution_id TEXT PRIMARY KEY,
                    agent_id TEXT,
                    status TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    result TEXT
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    action TEXT,
                    agent_id TEXT,
                    actor TEXT,
                    execution_id TEXT,
                    detail TEXT
                );
                """
            )

    # -- writes ----------------------------------------------------------
    def upsert_agent(self, rec: AgentFactoryRecord) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """
                INSERT INTO agents
                (agent_id,name,version,status,stage,risk_level,description,
                 permissions,required_tools,capabilities,module_path,created_at,updated_at,previous_version,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name=excluded.name, version=excluded.version, status=excluded.status,
                    stage=excluded.stage, risk_level=excluded.risk_level,
                    description=excluded.description, permissions=excluded.permissions,
                    required_tools=excluded.required_tools, capabilities=excluded.capabilities,
                    module_path=excluded.module_path, updated_at=excluded.updated_at,
                    previous_version=excluded.previous_version, notes=excluded.notes
                """,
                (
                    rec.agent_id, rec.name, rec.version, rec.status, rec.stage,
                    rec.risk_level, rec.description, rec.permissions, rec.required_tools,
                    rec.capabilities, rec.module_path, rec.created_at, rec.updated_at,
                    rec.previous_version, rec.notes,
                ),
            )

    def add_version(self, agent_id: str, version: str, module_path: str, notes: str = "") -> None:
        from datetime import datetime
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO agent_versions (agent_id,version,module_path,created_at,notes) VALUES (?,?,?,?,?)",
                (agent_id, version, module_path, datetime.utcnow().isoformat() + "Z", notes),
            )

    def audit(self, ev: AuditEvent) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO audit_events (timestamp,action,agent_id,actor,execution_id,detail) VALUES (?,?,?,?,?,?)",
                (ev.timestamp, ev.action, ev.agent_id, ev.actor, ev.execution_id, ev.detail),
            )

    def record_execution(self, execution_id: str, agent_id: str, status: str,
                         result: str = "", started_at: str = "", finished_at: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO agent_executions VALUES (?,?,?,?,?,?)",
                (execution_id, agent_id, status, started_at, finished_at, result),
            )

    # -- reads -----------------------------------------------------------
    def get(self, agent_id: str) -> AgentFactoryRecord | None:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
            return AgentFactoryRecord(**dict(row)) if row else None

    def all(self) -> list[AgentFactoryRecord]:
        with self._lock, self._conn() as c:
            return [AgentFactoryRecord(**dict(r)) for r in c.execute("SELECT * FROM agents").fetchall()]

    def list_versions(self, agent_id: str) -> list[dict[str, Any]]:
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT version,module_path,created_at,notes FROM agent_versions WHERE agent_id=? ORDER BY created_at",
                (agent_id,)).fetchall()]

    def recent_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]

    def close(self) -> None:
        pass
