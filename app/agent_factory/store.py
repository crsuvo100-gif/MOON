"""Agent Factory SQLite store (spec section 39, subset).

Initial low-resource deployment uses SQLite; the interface is intentionally
small so it can be swapped for PostgreSQL later without touching the factory.

Lives at data/agents/agent_factory.db. Generated agent code lives under
data/agents/{staging,approved,quarantine}/ per spec section 14.
"""

from __future__ import annotations

import sqlite3
import threading
import time
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
                CREATE TABLE IF NOT EXISTS agent_dependencies (
                    agent_id TEXT, dependency TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_tests (
                    agent_id TEXT, test_path TEXT, status TEXT, output TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_evaluations (
                    agent_id TEXT, version TEXT, overall REAL, correctness REAL,
                    reliability REAL, verification REAL, recovery REAL,
                    efficiency REAL, resource_usage REAL, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tools (
                    name TEXT PRIMARY KEY, version TEXT, source TEXT, executable TEXT,
                    capabilities TEXT, input_schema TEXT, output_schema TEXT,
                    permissions TEXT, risk_level TEXT, dependencies TEXT,
                    verification_method TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_versions (
                    name TEXT, version TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY, description TEXT, prerequisites TEXT,
                    required_tools TEXT, procedure TEXT, examples TEXT,
                    failure_modes TEXT, verification TEXT, success_criteria TEXT,
                    version TEXT, performance_score REAL
                );
                CREATE TABLE IF NOT EXISTS knowledge (
                    doc_id TEXT PRIMARY KEY, title TEXT, source TEXT, timestamp TEXT,
                    confidence REAL, verification_state TEXT, review_date TEXT
                );
                CREATE TABLE IF NOT EXISTS memories (
                    key TEXT PRIMARY KEY, kind TEXT, value TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, goal TEXT, risk TEXT,
                    required_capabilities TEXT, created_at TEXT, status TEXT
                );
                CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY, agent_id TEXT, task_id TEXT,
                    state TEXT, started_at TEXT, finished_at TEXT, result TEXT
                );
                CREATE TABLE IF NOT EXISTS improvement_proposals (
                    proposal_id TEXT PRIMARY KEY, observation TEXT, problem TEXT,
                    target_file TEXT, patch_text TEXT, sandbox_passed INTEGER,
                    regression_passed INTEGER, security_passed INTEGER, score REAL,
                    status TEXT, created_at TEXT, notes TEXT
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

    def add_improvement_proposal(self, p) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO improvement_proposals
                   (proposal_id,observation,problem,target_file,patch_text,
                    sandbox_passed,regression_passed,security_passed,score,status,created_at,notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p.proposal_id, p.observation, p.problem, p.target_file, p.patch_text,
                 1 if p.sandbox_passed else 0, 1 if p.regression_passed else 0,
                 1 if p.security_passed else 0, p.score, p.status, p.created_at, p.notes),
            )

    def add_task(self, task_id: str, goal: str, risk: str, caps: list[str], status: str = "created") -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?)",
                      (task_id, goal, risk, ",".join(caps),
                       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), status))

    def add_execution(self, execution_id: str, agent_id: str, task_id: str, state: str,
                      result: str = "") -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO executions VALUES (?,?,?,?,?,?,?)",
                      (execution_id, agent_id, task_id, state,
                       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "", result))

    def add_skill(self, skill_id: str, description: str = "", performance: float = 0.0) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO skills (skill_id,description,version,performance_score) VALUES (?,?,?,?)",
                      (skill_id, description, "1.0.0", performance))

    def register_tool(self, name: str, **kw) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO tools
                   (name,version,source,executable,capabilities,input_schema,output_schema,
                    permissions,risk_level,dependencies,verification_method)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (name, kw.get("version", "1.0.0"), kw.get("source", ""),
                 kw.get("executable", ""), kw.get("capabilities", ""),
                 kw.get("input_schema", ""), kw.get("output_schema", ""),
                 kw.get("permissions", ""), kw.get("risk_level", "low"),
                 kw.get("dependencies", ""), kw.get("verification_method", "")),
            )

    def record_evaluation(self, agent_id: str, version: str, sc) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO agent_evaluations
                   (agent_id,version,overall,correctness,reliability,verification,recovery,efficiency,resource_usage,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (agent_id, version, sc.overall, sc.correctness, sc.reliability,
                 sc.verification, sc.recovery, sc.efficiency, sc.resource_usage,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )

    def close(self) -> None:
        pass
