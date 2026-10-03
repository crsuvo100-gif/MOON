"""Unit tests for the Base Agent runtime (spec 7)."""

from __future__ import annotations

from app.agents.base_runtime import BaseAgent, AgentResult, OrchestratorAgent


class _Echo(BaseAgent):
    agent_id = "echo"
    agent_version = "1.0.0"

    def capabilities(self):
        return ["echo"]

    def _run(self, task, **kw):
        return AgentResult(success=True, status="done", result=f"echo:{task}",
                           agent_id=self.agent_id, agent_version=self.agent_version)


def test_base_agent_structured_result():
    a = _Echo()
    r = a.execute("hello")
    assert r.success is True
    assert r.status == "done"
    assert r.result == "echo:hello"
    d = r.to_dict()
    for k in ("success", "status", "result", "evidence", "errors", "warnings",
              "metrics", "agent_id", "agent_version", "execution_id"):
        assert k in d


def test_validate_empty_rejected():
    a = _Echo()
    ok, reason = a.validate_input("")
    assert ok is False
    r = a.execute("")
    assert r.success is False


def test_metadata_interface():
    a = _Echo()
    m = a.metadata()
    assert m["id"] == "echo"
    assert m["capabilities"] == ["echo"]
    assert a.health()["status"] == "active"


def test_orchestrator_agent_instantiable():
    oa = OrchestratorAgent()
    assert oa.agent_id == "master_orchestrator"
    assert oa.capabilities()
