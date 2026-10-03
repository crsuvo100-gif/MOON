"""Tests for spec 17/18/19/37 (brains), 29/30/31 (execution + supervision),
36 (recovery decisions) and the spec-24 protocol shape."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.advanced.supervision import (
    ExecutionMode,
    SubTask,
    Supervisor,
    TaskGraph,
    choose_mode,
    execute_graph,
)
from app.brain.aggregator import AgentEnvelope
from app.brain.recovery_policy import (
    FailureContext,
    RecoveryAction,
    RecoveryPolicy,
)
from app.runtime.brain_provider import (
    BrainHealth,
    BrainRouter,
    BrainSpec,
    OllamaProvider,
    OpenAICompatibleProvider,
    available_providers,
    provider_for,
)


# ------------------------------------------------------------------ §17 / §19
def test_providers_available() -> None:
    provs = available_providers()
    for expected in ("ollama", "openai_compatible", "huggingface", "remote"):
        assert expected in provs


def test_provider_for_infers_from_endpoint() -> None:
    assert isinstance(provider_for(BrainSpec("m", provider="ollama")), OllamaProvider)
    assert isinstance(
        provider_for(BrainSpec("m", base_url="http://127.0.0.1:11434/v1")), OllamaProvider)
    assert isinstance(
        provider_for(BrainSpec("m", base_url="https://api.openai.com/v1")),
        OpenAICompatibleProvider)
    # unknown provider string falls back to inference, never crashes
    assert provider_for(BrainSpec("m", provider="nonsense", base_url="")) is not None


def test_health_reports_all_spec19_fields() -> None:
    h = BrainHealth(available=True, provider="ollama", model="qwen3:0.6b",
                    endpoint="http://127.0.0.1:11434/v1", context_limit=8192,
                    latency_ms=3.2, is_remote=False, est_ram_mb=1200)
    d = h.to_dict()
    for field in ("available", "provider", "model", "context_limit", "latency_ms",
                  "error", "is_remote", "est_ram_mb", "needs_gpu"):
        assert field in d


def test_spec_never_leaks_api_key() -> None:
    spec = BrainSpec("m", api_key="sk-secret")
    assert "sk-secret" not in str(spec.to_dict())
    assert spec.to_dict()["has_api_key"] is True


def test_brain_spec_serialisation_hides_key() -> None:
    assert "api_key" not in BrainSpec("m", api_key="x").to_dict()


# ------------------------------------------------------------- §18 / §37
def test_router_selects_by_role_then_shape() -> None:
    r = BrainRouter({
        "default": BrainSpec("small", est_ram_mb=900),
        "coding": BrainSpec("coder", est_ram_mb=1500),
        "strong": BrainSpec("big", est_ram_mb=8000),
    })
    assert r.select(role="coding").model_id == "coder"
    assert r.select(role="missing", coding=True).model_id == "coder"
    assert r.select(role="missing", reasoning=True).model_id == "big"
    assert r.select(role="nope").model_id == "small"


def test_router_low_resource_prefers_smaller_brain() -> None:
    r = BrainRouter({
        "default": BrainSpec("small", est_ram_mb=900),
        "coding": BrainSpec("huge", est_ram_mb=9000),
    })
    assert r.select(role="coding", low_resource=True).model_id == "small"


def test_router_privacy_prefers_local() -> None:
    r = BrainRouter({
        "default": BrainSpec("cloud", is_remote=True),
        "local": BrainSpec("onprem", is_remote=False, est_ram_mb=2000),
    })
    assert r.select(role="default", privacy=True).model_id == "onprem"


def test_fallback_records_and_never_silent() -> None:
    """Spec 37: a fallback must be recorded, and unavailable brains reported."""
    # a brain pointing at a dead port is unavailable
    r = BrainRouter({
        "default": BrainSpec("m", base_url="http://127.0.0.1:1/v1"),
        "strong": BrainSpec("m", base_url="http://127.0.0.1:1/v1"),
    })
    spec, health = r.resolve_with_fallback(role="default", task_hint="probe")
    assert spec is None and health is not None and health.available is False
    # nothing healthy -> no fake success, and no bogus fallback recorded
    assert r.fallback_history() == []


# --------------------------------------------------------------- §29 / §30
def test_choose_mode_simplest() -> None:
    assert choose_mode([]) == ExecutionMode.SEQUENTIAL
    assert choose_mode([SubTask("a", "x")]) == ExecutionMode.SEQUENTIAL
    assert choose_mode([SubTask("a", "x"), SubTask("b", "y")]) == ExecutionMode.PARALLEL
    assert choose_mode([SubTask("a", "x"), SubTask("b", "y", depends_on=["a"])]) \
        == ExecutionMode.DEPENDENCY_GRAPH


def test_task_graph_topological_order() -> None:
    g = TaskGraph([
        SubTask("d", "deploy", depends_on=["b", "c"]),
        SubTask("b", "build", depends_on=["a"]),
        SubTask("c", "test", depends_on=["a"]),
        SubTask("a", "inspect"),
    ])
    order = g.execution_order()
    assert order.index("a") < order.index("b") < order.index("d")
    assert order.index("a") < order.index("c") < order.index("d")


def test_task_graph_rejects_cycle() -> None:
    with pytest.raises(ValueError):
        TaskGraph([SubTask("a", "x", depends_on=["b"]),
                   SubTask("b", "y", depends_on=["a"])])


def test_task_graph_rejects_unknown_dependency() -> None:
    with pytest.raises(ValueError):
        TaskGraph([SubTask("a", "x", depends_on=["ghost"])])


def test_ready_only_after_dependencies_done() -> None:
    g = TaskGraph([SubTask("a", "x"), SubTask("b", "y", depends_on=["a"])])
    assert [t.id for t in g.ready()] == ["a"]
    next(t for t in g.all_tasks() if t.id == "a").status = "done"
    assert [t.id for t in g.ready()] == ["b"]


def test_failed_dependency_skips_dependents() -> None:
    g = TaskGraph([SubTask("a", "x"), SubTask("b", "y", depends_on=["a"])])
    next(t for t in g.all_tasks() if t.id == "a").status = "failed"
    assert [t.id for t in g.blocked_by_failure()] == ["b"]


def test_execute_graph_parallel() -> None:
    async def _run(sub: SubTask) -> str:
        await asyncio.sleep(0)
        return f"done:{sub.id}"

    g = TaskGraph([SubTask("a", "x"), SubTask("b", "y"), SubTask("c", "z")])
    out = asyncio.run(execute_graph(g, run_task=_run, max_concurrency=2))
    assert out["mode"] == "parallel"
    assert out["complete"] is True
    assert out["progress"] == 1.0
    assert all(t["status"] == "done" for t in out["tasks"])


def test_execute_graph_dependency_order_respected() -> None:
    seen: list[str] = []

    async def _run(sub: SubTask) -> str:
        seen.append(sub.id)
        return "ok"

    g = TaskGraph([SubTask("a", "x"), SubTask("b", "y", depends_on=["a"]),
                   SubTask("c", "z", depends_on=["b"])])
    out = asyncio.run(execute_graph(g, run_task=_run, max_concurrency=3))
    assert out["mode"] == "dependency_graph"
    assert seen == ["a", "b", "c"]


def test_execute_graph_skips_dependents_of_failure() -> None:
    async def _run(sub: SubTask) -> str:
        if sub.id == "a":
            raise RuntimeError("boom")
        return "ok"

    g = TaskGraph([SubTask("a", "x"), SubTask("b", "y", depends_on=["a"])])
    out = asyncio.run(execute_graph(g, run_task=_run, max_concurrency=1))
    statuses = {t["id"]: t["status"] for t in out["tasks"]}
    assert statuses["a"] == "failed"
    assert statuses["b"] == "skipped"


def test_concurrency_limit_is_enforced() -> None:
    live = 0
    peak = 0

    async def _run(sub: SubTask) -> str:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.02)
        live -= 1
        return "ok"

    g = TaskGraph([SubTask(str(i), "x") for i in range(6)])
    asyncio.run(execute_graph(g, run_task=_run, max_concurrency=2))
    assert peak <= 2, f"concurrency limit breached: peak={peak}"


# ------------------------------------------------------------------ §31 / §36
def test_supervisor_detects_stuck() -> None:
    sup = Supervisor(idle_timeout=0.05, max_retries=2)
    sup.start("coding", "t1")
    assert sup.stuck() == []
    import time
    time.sleep(0.08)
    assert [w.task_id for w in sup.stuck()] == ["t1"]


def test_supervisor_decision_is_bounded_never_infinite() -> None:
    sup = Supervisor(idle_timeout=0.01, max_retries=2)
    sup.start("coding", "t1")
    import time
    time.sleep(0.03)
    first = sup.decide("t1")
    assert first["action"] == "retry"
    time.sleep(0.03)
    second = sup.decide("t1")
    assert second["action"] == "reassign"
    time.sleep(0.03)
    third = sup.decide("t1")
    assert third["action"] == "ask_user"  # escalated, NOT looping


def test_supervisor_tracks_tool_calls_and_cancel() -> None:
    sup = Supervisor()
    sup.start("coding", "t1")
    sup.beat("t1", note="run test", tool=True)
    sup.beat("t1", note="run lint", tool=True)
    snap = sup.snapshot()
    assert snap["running"][0]["tool_calls"] == 2
    assert sup.cancel("t1") is True
    assert sup.decide("t1")["action"] == "none"


def test_recovery_policy_brain_error_changes_brain() -> None:
    d = RecoveryPolicy().decide(FailureContext(
        agent="coding", task="x", error="ConnectError: connection refused"))
    assert d.action == RecoveryAction.CHANGE_BRAIN
    assert d.target_agent == "coding"          # agent stays (spec 37)


def test_recovery_policy_exhausted_escalates() -> None:
    d = RecoveryPolicy(max_attempts=3).decide(FailureContext(
        agent="coding", task="x", error="whatever", attempt=3))
    assert d.action == RecoveryAction.ASK_USER


def test_recovery_policy_high_risk_requires_human() -> None:
    d = RecoveryPolicy().decide(FailureContext(
        agent="cyber", task="exploit", error="denied", high_risk=True))
    assert d.action == RecoveryAction.ASK_USER


def test_recovery_policy_first_failure_retries_then_changes_agent() -> None:
    p = RecoveryPolicy()
    first = p.decide(FailureContext(agent="coding", task="x", error="bad output",
                                    other_agents=["debug"]))
    assert first.action == RecoveryAction.RETRY_SAME_AGENT
    second = p.decide(FailureContext(agent="coding", task="x", error="bad output",
                                     attempt=1, other_agents=["debug"]))
    assert second.action == RecoveryAction.CHANGE_AGENT
    assert second.target_agent == "debug"


def test_recovery_policy_composite_splits() -> None:
    d = RecoveryPolicy().decide(FailureContext(
        agent="coordinator", task="x", error="context length exceeded",
        task_is_composite=True))
    assert d.action == RecoveryAction.SPLIT_TASK


def test_recovery_policy_no_alternatives_escalates() -> None:
    d = RecoveryPolicy().decide(FailureContext(
        agent="solo", task="x", error="bad output", attempt=1, other_agents=[]))
    assert d.action == RecoveryAction.ASK_USER


# ---------------------------------------------------------------- §24 protocol
def test_envelope_has_full_spec24_field_set() -> None:
    d = AgentEnvelope(task_id="t", agent_id="coding_agent", status="completed",
                      objective="o", input="i", result="r", evidence=["e"],
                      artifacts=["a"], confidence=0.8, next_action="verification",
                      message_type="TASK_RESULT").to_dict()
    for field in ("task_id", "agent_id", "message_type", "timestamp", "status",
                  "objective", "input", "result", "evidence", "errors", "warnings",
                  "next_action", "confidence", "artifacts"):
        assert field in d, f"missing spec-24 field: {field}"
