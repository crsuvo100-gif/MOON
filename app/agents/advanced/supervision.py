"""Multi-agent execution modes, task graph, and supervision (spec 29, 30, 31).

MOON must run multi-agent work in the SIMPLEST mode that satisfies the task
(spec 29), never execute a task before its dependencies are done (spec 30), and
supervise every running agent so a stuck one is detected and acted on rather
than hanging the request forever (spec 31).

This module is additive and pure-Python: it defines the orchestration policy and
the supervision state machine. It does not replace ``Orchestrator.run_task`` --
the orchestrator calls in here to pick a mode, order the work, and watch it.

    ExecutionMode.SEQUENTIAL        A -> B -> C
    ExecutionMode.PARALLEL          A | B | C  -> aggregate
    ExecutionMode.DEPENDENCY_GRAPH  A -> (B|C) -> D
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    DEPENDENCY_GRAPH = "dependency_graph"


@dataclass
class SubTask:
    """A unit of delegated work (spec 5 / 30)."""

    id: str
    objective: str
    agent: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"        # pending|running|done|failed|skipped
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration(self) -> float:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "objective": self.objective, "agent": self.agent,
                "depends_on": self.depends_on, "status": self.status,
                "result": self.result[:400], "error": self.error,
                "duration": round(self.duration, 3)}


class TaskGraph:
    """Dependency-aware task graph (spec 30)."""

    def __init__(self, tasks: list[SubTask]) -> None:
        self._tasks: dict[str, SubTask] = {t.id: t for t in tasks}
        self._validate()

    def _validate(self) -> None:
        for t in self._tasks.values():
            for dep in t.depends_on:
                if dep not in self._tasks:
                    raise ValueError(f"task '{t.id}' depends on unknown '{dep}'")
        # cycle detection (spec 30: never execute before dependencies complete)
        seen: dict[str, int] = {}

        def visit(nid: str) -> None:
            state = seen.get(nid, 0)
            if state == 1:
                raise ValueError(f"dependency cycle detected at '{nid}'")
            if state == 2:
                return
            seen[nid] = 1
            for dep in self._tasks[nid].depends_on:
                visit(dep)
            seen[nid] = 2

        for nid in self._tasks:
            visit(nid)

    def all_tasks(self) -> list[SubTask]:
        return list(self._tasks.values())

    def ready(self) -> list[SubTask]:
        """Tasks whose dependencies have all completed successfully."""
        out = []
        for t in self._tasks.values():
            if t.status != "pending":
                continue
            deps = [self._tasks[d] for d in t.depends_on]
            if all(d.status == "done" for d in deps):
                out.append(t)
        return out

    def blocked_by_failure(self) -> list[SubTask]:
        """Pending tasks that can never run because a dependency failed."""
        out = []
        for t in self._tasks.values():
            if t.status != "pending":
                continue
            deps = [self._tasks[d] for d in t.depends_on]
            if any(d.status in ("failed", "skipped") for d in deps):
                out.append(t)
        return out

    def is_complete(self) -> bool:
        return all(t.status in ("done", "failed", "skipped") for t in self._tasks.values())

    def progress(self) -> float:
        if not self._tasks:
            return 1.0
        done = sum(1 for t in self._tasks.values() if t.status in ("done", "failed", "skipped"))
        return done / len(self._tasks)

    def execution_order(self) -> list[str]:
        """Topological order (spec 30)."""
        order: list[str] = []
        seen: set[str] = set()

        def visit(nid: str) -> None:
            if nid in seen:
                return
            for dep in self._tasks[nid].depends_on:
                visit(dep)
            seen.add(nid)
            order.append(nid)

        for nid in self._tasks:
            visit(nid)
        return order


def choose_mode(tasks: list[SubTask]) -> ExecutionMode:
    """Pick the SIMPLEST mode that satisfies the task (spec 29)."""
    if not tasks:
        return ExecutionMode.SEQUENTIAL
    if any(t.depends_on for t in tasks):
        return ExecutionMode.DEPENDENCY_GRAPH
    if len(tasks) == 1:
        return ExecutionMode.SEQUENTIAL
    return ExecutionMode.PARALLEL


# --------------------------------------------------------------------------
# §31 Supervision
# --------------------------------------------------------------------------
@dataclass
class AgentWatch:
    """Live supervision record for one running agent (spec 31)."""

    agent: str
    task_id: str
    started_at: float = field(default_factory=time.time)
    last_progress: float = field(default_factory=time.time)
    progress: str = "starting"
    tool_calls: int = 0
    errors: int = 0
    cancelled: bool = False

    def beat(self, note: str = "") -> None:
        self.last_progress = time.time()
        if note:
            self.progress = note

    def idle_for(self) -> float:
        return time.time() - self.last_progress

    def to_dict(self) -> dict[str, Any]:
        return {"agent": self.agent, "task_id": self.task_id,
                "elapsed": round(time.time() - self.started_at, 2),
                "idle": round(self.idle_for(), 2), "progress": self.progress,
                "tool_calls": self.tool_calls, "errors": self.errors,
                "cancelled": self.cancelled}


class Supervisor:
    """Monitors task/agent/tool state and acts on a stuck agent (spec 31).

    Decision ladder (spec 31 steps 1-4, bounded by spec 51):
        detect -> stop/cancel if safe -> retry or reassign -> update plan.
    ``max_retries`` prevents the "never retry forever" failure (spec 36).
    """

    def __init__(self, *, idle_timeout: float = 120.0, max_retries: int = 2) -> None:
        self._idle_timeout = idle_timeout
        self._max_retries = max_retries
        self._watches: dict[str, AgentWatch] = {}
        self._retries: dict[str, int] = {}
        self._events: list[dict[str, Any]] = []

    # -- lifecycle --------------------------------------------------------
    def start(self, agent: str, task_id: str) -> AgentWatch:
        w = AgentWatch(agent=agent, task_id=task_id)
        self._watches[task_id] = w
        self._log("agent.started", agent=agent, task_id=task_id)
        return w

    def beat(self, task_id: str, note: str = "", tool: bool = False) -> None:
        w = self._watches.get(task_id)
        if w is None:
            return
        w.beat(note)
        if tool:
            w.tool_calls += 1
            self._log("agent.tool_started", agent=w.agent, task_id=task_id, detail=note)

    def finish(self, task_id: str, *, failed: bool = False, detail: str = "") -> None:
        w = self._watches.pop(task_id, None)
        if w is None:
            return
        if failed:
            w.errors += 1
        self._log("agent.failed" if failed else "agent.result",
                  agent=w.agent, task_id=task_id, detail=detail)

    def cancel(self, task_id: str) -> bool:
        w = self._watches.get(task_id)
        if w is None:
            return False
        w.cancelled = True
        self._log("agent.cancelled", agent=w.agent, task_id=task_id)
        return True

    # -- detection --------------------------------------------------------
    def stuck(self) -> list[AgentWatch]:
        return [w for w in self._watches.values()
                if not w.cancelled and w.idle_for() > self._idle_timeout]

    def decide(self, task_id: str) -> dict[str, Any]:
        """Spec 31/36 decision for a stuck agent: bounded, never infinite."""
        w = self._watches.get(task_id)
        if w is None:
            return {"action": "none", "reason": "not supervised"}
        if w.cancelled:
            return {"action": "none", "reason": "already cancelled"}
        if w.idle_for() <= self._idle_timeout:
            return {"action": "wait", "reason": f"idle {w.idle_for():.1f}s < timeout"}

        n = self._retries.get(task_id, 0)
        if n >= self._max_retries:
            self.cancel(task_id)
            self._log("agent.failed", agent=w.agent, task_id=task_id,
                      detail="retry budget exhausted -> escalate to user")
            return {"action": "ask_user",
                    "reason": f"stuck after {n} retries; escalating instead of looping",
                    "agent": w.agent}

        self._retries[task_id] = n + 1
        self._log("agent.progress", agent=w.agent, task_id=task_id,
                  detail=f"stuck -> retry {n + 1}/{self._max_retries}")
        return {"action": "retry" if n == 0 else "reassign",
                "reason": f"idle {w.idle_for():.1f}s > {self._idle_timeout}s",
                "attempt": n + 1, "agent": w.agent}

    # -- observability ----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "running": [w.to_dict() for w in self._watches.values()],
            "stuck": [w.to_dict() for w in self.stuck()],
            "retries": dict(self._retries),
            "events": self._events[-40:],
        }

    def _log(self, event: str, **kw: Any) -> None:
        self._events.append({"event": event, "at": time.time(), **kw})


# --------------------------------------------------------------------------
# Executor: runs a task graph under supervision
# --------------------------------------------------------------------------
async def execute_graph(
    graph: TaskGraph,
    *,
    run_task: Callable[[SubTask], Awaitable[str]],
    supervisor: Supervisor | None = None,
    max_concurrency: int = 1,
    mode: ExecutionMode | None = None,
) -> dict[str, Any]:
    """Execute a task graph in the chosen mode, honoring dependencies (29/30/31).

    ``run_task`` performs the actual agent call. ``max_concurrency`` enforces
    the spec-32/33 resource policy. Failures skip dependents rather than
    executing them against missing inputs.
    """
    mode = mode or choose_mode(graph.all_tasks())
    sup = supervisor or Supervisor()
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _run(sub: SubTask) -> None:
        async with sem:
            sub.status = "running"
            sub.started_at = time.time()
            sup.start(sub.agent or sub.id, sub.id)
            try:
                sup.beat(sub.id, note="executing")
                sub.result = await run_task(sub)
                sub.status = "done"
                sup.finish(sub.id, detail=sub.result[:120])
            except Exception as exc:  # noqa: BLE001
                sub.status = "failed"
                sub.error = f"{type(exc).__name__}: {exc}"
                sup.finish(sub.id, failed=True, detail=sub.error)
            finally:
                sub.finished_at = time.time()

    if mode == ExecutionMode.SEQUENTIAL:
        for sub in graph.all_tasks():
            if sub.depends_on:
                await _await_deps(graph, sub)
            if sub.status == "pending":
                await _run(sub)
    else:
        while not graph.is_complete():
            for sub in graph.blocked_by_failure():
                sub.status = "skipped"
                logger.warning("task '%s' skipped: dependency failed", sub.id)
            ready = graph.ready()
            if not ready:
                if not graph.is_complete():
                    logger.warning("task graph stalled with no ready nodes")
                break
            await asyncio.gather(*(_run(s) for s in ready))

    return {
        "mode": mode.value,
        "complete": graph.is_complete(),
        "progress": round(graph.progress(), 3),
        "tasks": [t.to_dict() for t in graph.all_tasks()],
        "supervision": sup.snapshot(),
    }


async def _await_deps(graph: TaskGraph, sub: SubTask) -> None:
    """Sequential mode still respects dependencies (spec 30)."""
    for dep_id in sub.depends_on:
        dep = next((t for t in graph.all_tasks() if t.id == dep_id), None)
        if dep is not None and dep.status in ("failed", "skipped"):
            sub.status = "skipped"


__all__ = [
    "ExecutionMode", "SubTask", "TaskGraph", "Supervisor", "AgentWatch",
    "choose_mode", "execute_graph",
]
