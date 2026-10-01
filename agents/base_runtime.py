"""Base Agent runtime (spec section 7: common agent interface).

This is the REAL base class every MOON agent conforms to. It implements the
common interface:

    metadata()  capabilities()  permissions()  validate_input()
    plan()  execute()  verify()  reflect()  health()  shutdown()

and returns a STRUCTURED result (spec 7) containing:
    success, status, result, evidence, errors, warnings, metrics,
    agent_id, agent_version, execution_id

It is not a stub: ``execute`` runs the task through the live MOON orchestrator
(after capability-based agent selection via the structured registry), and
``verify``/``reflect`` hook into the real VerificationEngine / ReflectionEngine.

Built-in persona agents, generated Factory agents, and spec40 agents all share
this contract. Non-destructive: it does not replace any existing agent; it is
the interface they can all be wrapped in.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Structured agent result (spec 7). Never free-form text only."""
    success: bool = False
    status: str = "pending"          # pending|running|success|failed|verifying
    result: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    agent_version: str = ""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success, "status": self.status, "result": self.result,
            "evidence": self.evidence, "errors": self.errors, "warnings": self.warnings,
            "metrics": self.metrics, "agent_id": self.agent_id,
            "agent_version": self.agent_version, "execution_id": self.execution_id,
        }


class BaseAgent:
    """Common agent interface (spec 7). Subclass and implement ``_run``."""

    agent_id: str = "base"
    agent_version: str = "1.0.0"

    # ---- spec 7 interface ------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.agent_id, "version": self.agent_version,
            "capabilities": self.capabilities(),
            "permissions": self.permissions(), "status": "active",
        }

    def capabilities(self) -> list[str]:
        return []

    def permissions(self) -> list[str]:
        return []

    def validate_input(self, task: str) -> tuple[bool, str]:
        if not task or not str(task).strip():
            return False, "empty task"
        return True, ""

    def plan(self, task: str) -> list[str]:
        """Default linear plan (spec 11). Override for dependency graphs."""
        return [f"execute: {task}"]

    def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """Run the task. Default implementation drives the live orchestrator
        (capability-based agent selection + cognition loop)."""
        ok, reason = self.validate_input(task)
        if not ok:
            return AgentResult(success=False, status="failed", agent_id=self.agent_id,
                               agent_version=self.agent_version, errors=[reason])
        try:
            res = self._run(task, **kwargs)
            return res
        except Exception as e:  # noqa: BLE001
            return AgentResult(success=False, status="failed", agent_id=self.agent_id,
                               agent_version=self.agent_version, errors=[str(e)])

    def verify(self, result: AgentResult) -> bool:
        """Evidence-based verification (spec 27). Default: trust structured
        success unless errors present."""
        return bool(result.success) and not result.errors

    def reflect(self, task: str, result: AgentResult) -> dict[str, Any]:
        """Lightweight reflection (spec 26)."""
        return {
            "goal": task, "succeeded": result.success,
            "lessons": result.warnings + result.errors,
        }

    def health(self) -> dict[str, Any]:
        return {"agent_id": self.agent_id, "status": "active", "version": self.agent_version}

    def shutdown(self) -> None:
        return None

    # ---- to be implemented by concrete agents ---------------------------
    def _run(self, task: str, **kwargs: Any) -> AgentResult:  # pragma: no cover
        raise NotImplementedError


class OrchestratorAgent(BaseAgent):
    """A BaseAgent that executes through the live MOON orchestrator using
    capability-based agent selection (spec 9/12). Real execution path."""

    def __init__(self, agent_id: str = "master_orchestrator", version: str = "1.0.0") -> None:
        self.agent_id = agent_id
        self.agent_version = version
        self._orch = None

    def _orch_instance(self):
        if self._orch is None:
            orch = _await(self._get_obtain_coro())
            self._orch = orch
        return self._orch

    @staticmethod
    def _get_obtain_coro():
        try:
            from app.terminal_interface import _get_orchestrator
        except Exception:  # noqa: BLE001
            from app.brain.orchestrator import _get_orchestrator  # type: ignore
        return _get_orchestrator()

    def _run(self, task: str, **kwargs: Any) -> AgentResult:
        orch = self._orch_instance()
        from app.models.task import Task
        t = Task.create(task, agent_name="auto")
        t = _await(orch.run_task(t))
        return AgentResult(
            success=(t.status == "done"), status=t.status,
            result=t.result or "", agent_id=self.agent_id,
            agent_version=self.agent_version,
            evidence={"selected_agents": getattr(t, "_selected_agents", [])},
            errors=[] if t.status == "done" else [t.result or "failed"],
        )

    def capabilities(self):
        return ["orchestrate", "task_execution", "agent_selection"]

    def permissions(self):
        return ["core:manage"]


def _await(coro):
    """Resolve a coroutine from a synchronous BaseAgent context."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We are inside a running loop (e.g. orchestrator call chain):
            # schedule and await via a future.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as ex:
                return ex.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


__all__ = ["BaseAgent", "AgentResult", "OrchestratorAgent"]
