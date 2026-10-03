"""Security boundary tests (spec 18, 47, 48, 49, 50)."""

from __future__ import annotations

from app.agent_factory.reviewer import SecurityReviewer
from app.agent_factory.architect import AgentSpec
from app.agent_factory.builder import BuildArtifact


def _spec(cap, risk="low", perms=None):
    return AgentSpec(agent_id="x", name="x", version="1.0.0", description="",
                     capabilities=[cap], required_tools=[], permissions=perms or [],
                     risk_level=risk, dependencies=[])


def test_forbidden_patterns_rejected():
    from app.agent_factory.reviewer import _FORBIDDEN
    patterns = [p for p, _ in _FORBIDDEN]
    # The static reviewer must flag dangerous dynamic execution / escape.
    assert any("eval" in p for p in patterns)
    assert any("exec" in p for p in patterns)
    assert any("os" in p for p in patterns)  # import os; ...system(


def test_critical_requires_admin_permission():
    spec = _spec("destroy", risk="critical", perms=["EXECUTE"])
    art = BuildArtifact(spec=spec, module_path="")
    rev = SecurityReviewer().review(art, spec)
    assert rev.approved is False
    assert any("critical" in v for v in rev.violations)


def test_low_risk_approved():
    spec = _spec("summarize", risk="low", perms=["READ"])
    art = BuildArtifact(spec=spec, module_path="")
    rev = SecurityReviewer().review(art, spec)
    assert rev.approved is True
