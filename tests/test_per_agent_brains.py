"""Tests for per-agent brains + galaxy wiring (reconstruction scan fixes)."""

import asyncio

import pytest


async def _make_orch():
    from app.brain.orchestrator import Orchestrator
    from app.config.settings import get_settings

    o = Orchestrator(get_settings())
    await o.setup()
    return o


def test_per_agent_brains_connected():
    o = asyncio.new_event_loop()
    try:
        orch = o.run_until_complete(_make_orch())
        # 11 agents, each with its own connected AgentBrain
        assert len(orch._agents) == 11
        assert len(orch._agent_brains) == 11
        # each brain is wired to the main brain for two-phase validation
        for brain in orch._agent_brains.values():
            assert brain.main_brain is orch
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_agent_brain_persists_episode(tmp_path):
    import sys

    sys.path.insert(0, ".")
    from app.brain.agent_brain import AgentBrain

    o = asyncio.new_event_loop()
    try:
        brain = AgentBrain("test_agent", main_brain=None)
        o.run_until_complete(brain.setup())
        o.run_until_complete(brain.remember({"goal": "g", "outcome": "o", "success": True}))
        store = brain._store
        assert len(store.episodes()) == 1
    finally:
        o.close()
