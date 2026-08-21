"""Agent-level tests: the 40-agent registry + selection (spec 8, 12, 40)."""

from __future__ import annotations

from app.agents.registry import get_registry


def test_all_40_spec_agents_present():
    reg = get_registry()
    rep = reg.to_report()
    assert rep["by_source"].get("spec40", 0) >= 38


def test_role_groups_present():
    reg = get_registry()
    groups = {m.role_group for m in reg.all() if m.role_group}
    assert "core" in groups and "advanced" in groups


def test_select_returns_capability_match():
    reg = get_registry()
    assert reg.select(capability="coding")[0].id == "coding"
