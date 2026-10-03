"""Tests for the additive MOON runtime subsystems (spec 3,9,10,12,28,30,41,46,57).

These verify the newly-added components are real and independently testable.
No existing MOON behavior is modified by these tests.
"""

from __future__ import annotations

from app.runtime import (
    AgentRouter, Autonomy, EvaluationEngine, EventBus, EventType,
    GoalManager, ModelRouter, SkillSystem, TaskAnalyzer,
)


def test_task_analyzer_risk_and_caps():
    ta = TaskAnalyzer()
    g = ta.analyze("Create a python agent to analyze code and fix bugs")
    assert g.risk in ("low", "medium", "high", "critical")
    assert "coding" in g.required_capabilities
    assert "create" in g.requirements


def test_goal_manager_creates_exec_id():
    gm = GoalManager()
    goal = gm.create("translate this sentence to French")
    assert goal.execution_id
    assert goal.spec.goal
    gm.complete(goal.execution_id, "bonjour")
    assert gm.get(goal.execution_id).status == "completed"


def test_agent_router_selects_by_capability():
    r = AgentRouter()
    spec = TaskAnalyzer().analyze("translate text between languages")
    selected = r.select(spec)
    assert selected is not None
    r.record_outcome(selected, True)
    assert r.performance(selected) >= 0.9


def test_model_router_privacy_and_high():
    mr = ModelRouter()
    priv = mr.select(privacy=True)
    assert priv.is_remote is False
    high = mr.select(complexity="high", coding=True, reasoning=True)
    assert high.name  # non-empty model id


def test_evaluation_scoring():
    ev = EvaluationEngine()
    sc = ev.from_execution({"success": True, "evidence": {"x": 1}, "status": "SUCCESS"})
    assert 0 <= sc.overall <= 1
    assert sc.overall > 0.5
    # failed execution scores low
    sc2 = ev.from_execution({"success": False, "errors": ["boom"], "status": "FAILED"})
    assert sc2.overall < sc.overall


def test_autonomy_gates_high_risk():
    au = Autonomy()
    ok, _ = au.allows("exec_tool")
    assert ok is True
    blocked, reason = au.allows("create_agent")
    # default level 3 blocks autonomous agent creation (spec 46)
    assert blocked is False and "autonomy level" in reason
    hr_ok, hr_reason = au.allows("delete", high_risk=True)
    assert hr_ok is False


def test_skill_system_discovers_corpus():
    ss = SkillSystem()
    assert len(ss.list_ids()) > 0
    sid = ss.list_ids()[0]
    ss.record_outcome(sid, True)
    assert ss.get(sid).performance_score > 0.9


def test_event_bus_publishes_and_surfaces():
    b = EventBus()
    captured = []
    b.subscribe(lambda e: captured.append(e))
    e = b.publish(EventType.AGENT_CREATED, agent_id="x", detail="made")
    assert e.type == "AGENT_CREATED"
    assert any(ev.agent_id == "x" for ev in captured)
