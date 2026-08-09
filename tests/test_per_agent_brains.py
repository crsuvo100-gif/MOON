"""Tests for expanded agent roster + per-agent brains + advanced workflow."""

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
        assert len(orch._agents) >= 22
        assert len(orch._agent_brains) == len(orch._agents)
        for brain in orch._agent_brains.values():
            assert brain.main_brain is orch
        for name in ("coding", "math", "security", "fact_checker", "router", "coordinator"):
            assert name in orch._agents
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_agent_registry_personas_present():
    from app.brain.agent_registry import persona_for, build_agents

    tools = ["web_search", "browser", "api_requests", "file_manager", "ocr", "pdf_reader", "image_processing"]
    agents = build_agents(tools)
    assert len(agents) >= 22
    for name in agents:
        assert len(persona_for(name)) > 20
    assert agents["research"].allowed_tools
    assert agents["review"].allowed_tools == []


def test_fast_path_and_parallel_helpers():
    o = asyncio.new_event_loop()
    try:
        orch = o.run_until_complete(_make_orch())
        assert orch._is_simple_query("What is the capital of France?")
        assert not orch._is_simple_query("write a 500 line program that does x and y and z and also compiles")
        subs = orch._split_subtasks("Summarize the report and also translate it to Spanish")
        assert len(subs) == 2
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_agent_brain_persists_episode():
    from app.brain.agent_brain import AgentBrain

    o = asyncio.new_event_loop()
    try:
        brain = AgentBrain("test_agent_persist", main_brain=None)
        o.run_until_complete(brain.setup())
        before = len(brain._store.episodes())
        o.run_until_complete(brain.remember({"goal": "g", "outcome": "o", "success": True}))
        after = len(brain._store.episodes())
        assert after == before + 1
    finally:
        o.close()
