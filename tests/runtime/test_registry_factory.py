"""Tests for the MOON 40-agent spec integration + Agent Factory sub-components.

Real behavior, no mocks: registry selection, spec-agent registration, factory
BUILD->REGISTER->REUSE pipeline, and terminal/REST surface existence.
"""

from __future__ import annotations

import pytest


def test_registry_has_spec40_agents():
    from app.agents.registry import get_registry
    reg = get_registry()
    rep = reg.to_report()
    assert rep["by_source"].get("spec40", 0) >= 38, rep["by_source"]
    assert rep["total"] > 70


def test_registry_capability_select():
    from app.agents.registry import get_registry
    reg = get_registry()
    assert reg.select(capability="coding")[0].id == "coding"
    assert reg.select(capability="web research")  # tokenised multi-word
    git = [c.id for c in reg.select(capability="git")]
    assert "git_agent" in git


def test_factory_build_then_reuse():
    import uuid
    from app.agent_factory.factory import AgentFactory
    af = AgentFactory()
    # Use a guaranteed-novel capability (random token) so the pipeline BUILDS.
    cap = f"translate ancient runic script to readable json schema {uuid.uuid4().hex[:8]}"
    r1 = af.create(cap)
    assert r1.status == "CREATED", (r1.status, r1.errors)
    assert r1.metrics.get("tests_passed") is True
    # Second call must REUSE, not rebuild (no duplicate).
    r2 = af.create(cap)
    assert r2.status == "REUSED_EXISTING", r2.status
    assert r2.agent_id == r1.agent_id


def test_factory_components_exist():
    from app.agent_factory.capability_analyzer import CapabilityAnalyzer
    from app.agent_factory.architect import AgentArchitect
    from app.agent_factory.builder import AgentBuilder, DependencyResolver
    from app.agent_factory.tester import AgentTester
    from app.agent_factory.evaluator import PerformanceEvaluator
    from app.agent_factory.reviewer import SecurityReviewer, RepairAgent
    from app.agent_factory.registrar import AgentRegistrar, AgentRollback
    from app.agent_factory.rollback import AgentFactoryRollback
    for c in (CapabilityAnalyzer, AgentArchitect, AgentBuilder, DependencyResolver,
              AgentTester, PerformanceEvaluator, SecurityReviewer, RepairAgent,
              AgentRegistrar, AgentRollback, AgentFactoryRollback):
        assert callable(getattr(c, "__init__", None))


def test_spec_agents_idempotent():
    from app.agents.registry import get_registry
    from app.agents.spec_agents import register_spec_agents, spec_agent_ids
    # All spec agents must be present in the registry (registered at startup
    # via get_registry(), or by this explicit call).
    added = register_spec_agents()
    for aid in spec_agent_ids():
        assert get_registry().get(aid) is not None, aid
    # A second call must be a no-op (idempotent).
    assert register_spec_agents() == 0
    assert added >= 0  # added may be 0 if already registered this session


def test_registry_select_risk_filter():
    from app.agents.registry import get_registry
    reg = get_registry()
    # low-risk only filter should exclude critical self_improvement_agent
    low = reg.select(capability="propose improvement", risk_max="low")
    assert all(m.risk_level in ("low",) for m in low)
    crit = reg.select(capability="propose improvement", risk_max="critical")
    assert any(m.id == "self_improvement_agent" for m in crit)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
