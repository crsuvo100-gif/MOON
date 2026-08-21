"""Integration glue: makes the spec runtime modules (app/runtime/*) functional
inside MOON's live orchestrator instead of being orphaned (spec sections 9, 10,
12, 28, 30, 41, 46).

Design (NON-DESTRUCTIVE):
  * This module NEVER replaces the orchestrator's working logic. It AUGMENTS it:
    - TaskAnalyzer (spec 10) enriches a Task with a structured GoalSpec.
    - AgentRouter (spec 12) refines agent selection by capability match.
    - ModelRouter (spec 30) recommends a model for a step.
    - Autonomy (spec 46) gates high-risk actions (create agent / install tool).
    - EvaluationEngine (spec 28) scores a completed result and records history.
    - EventBus (spec 41) emits real lifecycle events.
  * Every call is wrapped so a missing dependency or failure degrades cleanly
    (spec 59) and never breaks the existing task flow.

The orchestrator imports :func:`augment_task_analyzer`, :func:`route_agent`,
:func:`choose_model`, :func:`gate_action`, :func:`record_evaluation`,
:func:`emit` and uses them at safe integration points.
"""

from __future__ import annotations

from typing import Any

from app.runtime.task_analyzer import GoalSpec, TaskAnalyzer
from app.runtime.agent_router import AgentRouter
from app.runtime.model_router import ModelRouter
from app.runtime.autonomy import Autonomy
from app.runtime.evaluation import EvaluationEngine
from app.runtime.event_bus import bus as _bus


# Module-level singletons reused across tasks (stateful: performance history,
# evaluation history, autonomy level).
_ANALYZER = TaskAnalyzer()
_ROUTER = AgentRouter()
_MODEL = ModelRouter()
_AUTONOMY = Autonomy()
_EVAL = EvaluationEngine()


def analyze_task(request: str) -> GoalSpec:
    """Enrich a user request into a structured GoalSpec (spec 10)."""
    return _ANALYZER.analyze(request)


def route_agent(spec: GoalSpec, known_agents: list[str], default: str) -> str:
    """Refine agent selection by capability/policy (spec 12). Falls back to the
    orchestrator's existing choice when the router finds no candidate."""
    try:
        sel = _ROUTER.select(spec)
        if sel and (sel in known_agents or not known_agents):
            return sel
    except Exception:  # noqa: BLE001
        pass
    return default


def choose_model(*, complexity: str = "low", coding: bool = False,
                 reasoning: bool = False, privacy: bool = False) -> dict[str, Any]:
    """Recommend a model for a step (spec 30)."""
    try:
        return _MODEL.to_dict(_MODEL.select(
            complexity=complexity, coding=coding, reasoning=reasoning, privacy=privacy))
    except Exception:  # noqa: BLE001
        return {"model": "local-default", "note": "model router degraded"}


def set_autonomy(level: int) -> None:
    _AUTONOMY.set_level(level)


def autonomy_level() -> int:
    return int(_AUTONOMY.to_dict()["level"])


def gate_action(action: str, *, high_risk: bool = False) -> tuple[bool, str]:
    """Gate a potentially dangerous action (spec 46 / 47)."""
    return _AUTONOMY.allows(action, high_risk=high_risk)


def record_outcome(agent_name: str, success: bool) -> None:
    """Feed execution outcomes back to the router (spec 12 performance)."""
    try:
        _ROUTER.record_outcome(agent_name, success)
    except Exception:  # noqa: BLE001
        pass


def record_evaluation(*, correctness: float, reliability: float = 1.0,
                      verification: float = 1.0, recovery: float = 1.0,
                      efficiency: float = 1.0, resource_usage: float = 1.0,
                      agent_id: str = "", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a completed execution (spec 28) and persist to history."""
    try:
        card = _EVAL.score(
            correctness=correctness, reliability=reliability,
            verification=verification, recovery=recovery,
            efficiency=efficiency, resource_usage=resource_usage)
        if agent_id:
            card.agent_id = agent_id
        if metadata:
            card.metadata = metadata
        return card.to_dict()
    except Exception as e:  # noqa: BLE001
        return {"overall": correctness, "error": str(e)}


def evaluation_summary() -> dict[str, Any]:
    try:
        return {"average_overall": _EVAL.average_overall(), "history_len": len(_EVAL.history())}
    except Exception:  # noqa: BLE001
        return {"average_overall": 0.0, "history_len": 0}


def emit(event: str, *, execution_id: str = "", agent_id: str = "", detail: str = "") -> None:
    """Publish a lifecycle event on the bus (spec 41)."""
    try:
        _bus.publish(event, execution_id=execution_id, agent_id=agent_id, detail=detail)
    except Exception:  # noqa: BLE001
        pass


def router_explain(spec: GoalSpec) -> dict[str, Any]:
    try:
        return _ROUTER.explain(spec)
    except Exception:  # noqa: BLE001
        return {}


__all__ = [
    "analyze_task", "route_agent", "choose_model", "set_autonomy", "autonomy_level",
    "gate_action", "record_outcome", "record_evaluation", "evaluation_summary",
    "emit", "router_explain", "GoalSpec",
]
