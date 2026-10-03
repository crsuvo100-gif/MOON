"""Tests for the newly integrated spec subsystems (verification, execution,
learning) and the runtime integration glue that wires them into the
orchestrator. Real behavior, no mocks for the unit-level parts."""

from __future__ import annotations

from app.execution import ExecutionManager, ExecState
from app.verification import Verifier
from app.learning import Learner, FailureClassifier, Reflector
from app.runtime.integration import (
    analyze_task, route_agent, choose_model, gate_action,
    record_evaluation, emit, record_outcome,
)
from app.runtime.task_analyzer import GoalSpec


def test_verifier_evidence_based():
    v = Verifier()
    assert v.file_exists("/nonexistent/path").passed is False
    assert v.file_exists("tests/runtime/test_gap_closures.py").passed is True
    assert v.http_ok(200).passed is True
    assert v.http_ok(500).passed is False
    assert v.state_match(1, 1).passed is True
    assert v.state_match(1, 2).passed is False
    r = v.result_ok({"success": True, "evidence": {"x": 1}})
    assert r.passed is True
    r2 = v.result_ok({"success": False, "errors": ["boom"]})
    assert r2.passed is False and "boom" in r2.issues


def test_execution_state_machine(tmp_path):
    em = ExecutionManager(db_path=tmp_path / "exec.db")
    em.create("e1", agent_id="a", task="t")
    em.transition("e1", ExecState.RUNNING)
    em.transition("e1", ExecState.VERIFYING)
    em.transition("e1", ExecState.SUCCESS)
    j = em.get("e1")
    assert j.state == ExecState.SUCCESS
    # illegal transition must be rejected (spec 55 machine-readable error)
    try:
        em.transition("e1", ExecState.RUNNING)
        assert False, "illegal transition allowed"
    except ValueError:
        pass
    # persistence across a new manager instance
    em2 = ExecutionManager(db_path=tmp_path / "exec.db")
    assert em2.get("e1").state == ExecState.SUCCESS


def test_learning_mastery_and_reflection(tmp_path):
    l = Learner(store_path=tmp_path / "mastery.json")
    before = l.mastery("python")
    l.observe("python", success=True)
    assert l.mastery("python") > before
    l.observe("python", success=False)
    assert l.mastery("python") < 1.0
    kind = FailureClassifier.classify("connection refused timeout")
    assert kind in ("network", "timeout")
    rec = Reflector().reflect(goal="g", succeeded=False, failure_kind="timeout", improvement="retry")
    assert "goal" in rec and rec["succeeded"] is False


def test_runtime_integration_modules():
    spec = analyze_task("analyze my python project for unused imports")
    assert isinstance(spec, GoalSpec) and spec.goal
    known = ["coding", "research", "coordinator", "planning"]
    sel = route_agent(spec, known, "coordinator")
    assert sel in known
    rec = choose_model(coding=True)
    assert rec.get("name")
    allowed, why = gate_action("install_tool", high_risk=True)
    assert isinstance(allowed, bool)
    card = record_evaluation(correctness=0.9, verification=1.0)
    assert 0.0 <= card["overall"] <= 1.0
    emit("TASK_CREATED", execution_id="x", detail="test")
    record_outcome("coding", True)
