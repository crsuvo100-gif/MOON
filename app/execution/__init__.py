"""Execution subsystem (spec sections 31, 32).

An asynchronous job system with persistence so the runtime can recover after
restart (spec 31). Execution states: CREATED, PLANNED, RUNNING, WAITING,
RETRYING, VERIFYING, SUCCESS, FAILED, CANCELLED, ROLLED_BACK (spec 31).

Storage is a SQLite-backed queue so state survives process restart (spec 31).
State machine transitions are validated; illegal transitions are rejected with
a machine-readable error (spec 55). Resource manager (spec 32) exposes a
lightweight CPU/RAM snapshot.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ExecState(str, Enum):
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    RETRYING = "RETRYING"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"


_ALLOWED = {
    ExecState.CREATED: {ExecState.PLANNED, ExecState.RUNNING, ExecState.CANCELLED},
    ExecState.PLANNED: {ExecState.RUNNING, ExecState.WAITING, ExecState.CANCELLED},
    ExecState.RUNNING: {ExecState.VERIFYING, ExecState.RETRYING, ExecState.FAILED, ExecState.CANCELLED},
    ExecState.WAITING: {ExecState.RUNNING, ExecState.CANCELLED},
    ExecState.RETRYING: {ExecState.RUNNING, ExecState.FAILED, ExecState.CANCELLED},
    ExecState.VERIFYING: {ExecState.SUCCESS, ExecState.FAILED, ExecState.ROLLED_BACK},
    ExecState.SUCCESS: {ExecState.ROLLED_BACK},
    ExecState.FAILED: {ExecState.RETRYING, ExecState.ROLLED_BACK, ExecState.CANCELLED},
    ExecState.CANCELLED: set(),
    ExecState.ROLLED_BACK: set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Job:
    execution_id: str
    agent_id: str = ""
    task: str = ""
    state: ExecState = ExecState.CREATED
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    history: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id, "agent_id": self.agent_id,
            "task": self.task, "state": self.state.value,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "history": self.history, "result": self.result,
        }


class ExecutionManager:
    """Persistent async job system (spec 31)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db = str(db_path or Path(os.environ.get("MOON_DATA_DIR", "data")) / "executions.db")
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        with self._lock, sqlite3.connect(self._db) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS executions (
                    execution_id TEXT PRIMARY KEY,
                    agent_id TEXT, task TEXT, state TEXT,
                    created_at TEXT, updated_at TEXT,
                    history TEXT, result TEXT)""")
        self._jobs: dict[str, Job] = {}
        self._load()

    def _load(self) -> None:
        try:
            with self._lock, sqlite3.connect(self._db) as c:
                for row in c.execute("SELECT execution_id,agent_id,task,state,created_at,updated_at,history,result FROM executions"):
                    import json
                    self._jobs[row[0]] = Job(
                        execution_id=row[0], agent_id=row[1] or "", task=row[2] or "",
                        state=ExecState(row[3]), created_at=row[4], updated_at=row[5],
                        history=json.loads(row[6] or "[]"), result=json.loads(row[7] or "{}"))
        except Exception:  # noqa: BLE001
            pass

    def create(self, execution_id: str, agent_id: str = "", task: str = "") -> Job:
        job = Job(execution_id=execution_id, agent_id=agent_id, task=task)
        self._persist(job)
        self._jobs[execution_id] = job
        return job

    def get(self, execution_id: str) -> Job | None:
        return self._jobs.get(execution_id)

    def transition(self, execution_id: str, to: ExecState, *, result: dict[str, Any] | None = None) -> Job:
        job = self._jobs.get(execution_id)
        if job is None:
            raise KeyError(f"unknown execution {execution_id}")
        if to not in _ALLOWED.get(job.state, set()):
            raise ValueError(f"illegal transition {job.state.value} -> {to.value}")
        job.state = to
        job.updated_at = _now()
        if result is not None:
            job.result = result
        job.history.append({"at": job.updated_at, "to": to.value})
        self._persist(job)
        return job

    def _persist(self, job: Job) -> None:
        import json
        with self._lock, sqlite3.connect(self._db) as c:
            c.execute(
                """INSERT OR REPLACE INTO executions
                   (execution_id,agent_id,task,state,created_at,updated_at,history,result)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (job.execution_id, job.agent_id, job.task, job.state.value,
                 job.created_at, job.updated_at, json.dumps(job.history), json.dumps(job.result)))

    def all(self) -> list[Job]:
        return list(self._jobs.values())


class ResourceManager:
    """Lightweight resource monitor (spec 32)."""

    @staticmethod
    def snapshot() -> dict[str, Any]:
        try:
            import psutil  # type: ignore
            return {
                "cpu_pct": psutil.cpu_percent(interval=0.1),
                "ram_pct": psutil.virtual_memory().percent,
                "process_count": len(psutil.pids()),
            }
        except Exception:  # noqa: BLE001
            # Clean degradation: report what the stdlib can (spec 59).
            load = os.getloadavg()
            return {"cpu_loadavg": list(load), "note": "psutil unavailable"}


__all__ = ["ExecState", "Job", "ExecutionManager", "ResourceManager"]
