"""Tests for expanded agent roster + per-agent brains + advanced workflow."""

import pytest

pytestmark = pytest.mark.live  # requires a live model backend (Ollama)

import asyncio


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
        # Every agent has its OWN brain wired to the main MOON brain.
        assert len(orch._agents) >= 36
        assert len(orch._agent_brains) == len(orch._agents)
        for name, brain in orch._agent_brains.items():
            assert brain.main_brain is orch, f"{name} brain not connected to main"
            assert hasattr(brain, "refine_with_main")
            assert hasattr(brain, "remember")
        for name in ("coding", "math", "security", "fact_checker", "router", "coordinator"):
            assert name in orch._agents
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_agent_registry_personas_present():
    from app.brain.agent_registry import build_agents, persona_for

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


def test_two_phase_parse_logic():
    """Unit-test the critique/verify parsing without hitting the LLM."""
    from app.brain.agent_brain import AgentBrain

    o = asyncio.new_event_loop()
    try:
        brain = AgentBrain("test_parse", main_brain=None)

        # Simulate main-brain verdicts via a fake main_brain
        class FakeMain:
            def __init__(self, replies):
                self._q = list(replies)

            async def refine(self, prompt, **kw):
                return self._q.pop(0)

        # Case 1: verdict ok -> draft unchanged
        brain.main_brain = FakeMain(['{"verdict": "ok", "answer": "draft answer"}'])
        out = o.run_until_complete(brain.refine_with_main("draft answer", "task"))
        assert out == "draft answer", out

        # Case 2: verdict corrected (JSON) -> returns corrected text
        brain.main_brain = FakeMain(['{"verdict": "corrected", "answer": "the right answer"}'])
        out = o.run_until_complete(brain.refine_with_main("wrong", "task"))
        assert "right answer" in out, out

        # Case 3: free-form prose correction (heuristic fallback)
        brain.main_brain = FakeMain(["The draft is wrong. Corrected Answer: 56"])
        out = o.run_until_complete(brain.refine_with_main("7*8 = 54", "multiply"))
        assert out == "56", out
    finally:
        o.close()


def test_every_agent_has_durable_brain_file():
    import asyncio


    o = asyncio.new_event_loop()
    try:
        orch = o.run_until_complete(_make_orch())
        for name in orch._agent_brains:
            assert orch._agent_brains[name]._store._path.parent.exists()
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_majority_answer_logic():
    from app.brain.orchestrator import Orchestrator
    # exact majority
    assert Orchestrator._majority_answer(["Paris", "Paris", "London"]) == "Paris"
    # consensus by token overlap
    out = Orchestrator._majority_answer([
        "The capital of France is Paris.",
        "France's capital city is Paris.",
        "Berlin is the capital of Germany.",
    ])
    assert "Paris" in out, out


def test_pick_llm_routing():
    o = asyncio.new_event_loop()
    try:
        orch = o.run_until_complete(_make_orch())
        # Strong model IS configured (unlocked) -> factual/cyber prompts route to
        # the strong model, everything else to the default.
        assert orch._pick_llm("what is 2+2?") is orch._llm_strong, "factual -> strong"
        assert orch._pick_llm("scan this host for exploits") is orch._llm_strong, "cyber-critical -> strong"
        assert orch._pick_llm("write me a haiku about the moon") is orch._llm, "creative -> default"
        o.run_until_complete(orch.teardown())
    finally:
        o.close()


def test_per_agent_model_manager_binding():
    from app.brain.agent_model_manager import AgentModelManager
    from app.config.settings import get_settings

    s = get_settings()
    mgr = AgentModelManager(
        base_url=s.model_base_url, api_key=s.model_api_key,
        default_model=s.model_name, temperature=0.7, max_tokens=512,
    )
    # Specialists have a preferred (non-default) model; general agents fall back.
    assert mgr._preferred("math") != s.model_name, "math should prefer its own model"
    assert mgr._preferred("coding") != s.model_name, "coding should prefer coder model"
    # Every agent now gets a function-suited model; the manager runs
    # orchestration/planning so it is bound to a DISTINCT (reasoning) model
    # rather than the global default, and unmapped/coordination agents resolve
    # to a real string (default or own).
    assert mgr._preferred("manager") != s.model_name, "manager should use its own model"
    assert bool(mgr._preferred("manager")), "manager model must resolve to a non-empty id"
    # Resolution covers the FULL registered agent roster, not just AGENT_MODELS.
    from app.brain.agent_registry import AGENT_DEFS
    for a in AGENT_DEFS:
        res = mgr._preferred(a)
        assert isinstance(res, str) and res, f"agent {a} must resolve to a model"


def test_agent_brain_binds_own_model():
    """Each agent's brain is wired to its OWN model when a manager is supplied."""
    from app.brain.agent_brain import AgentBrain
    from app.brain.agent_model_manager import AgentModelManager
    from app.config.settings import get_settings

    s = get_settings()
    amm = AgentModelManager(
        base_url=s.model_base_url, api_key=s.model_api_key,
        default_model=s.model_name, temperature=0.7, max_tokens=512,
    )
    o = asyncio.new_event_loop()
    try:
        brain = AgentBrain("coding", main_brain=None, agent_models=amm)
        o.run_until_complete(brain.setup())
        # The agent is bound to a model instance (its own, or the default on
        # graceful fallback when Ollama is absent).
        assert brain._llm is not None, "agent brain must bind a model"
    finally:
        o.close()


def test_agent_brain_draft_uses_own_model():
    """An agent's draft is generated by its OWN model, not just a template."""
    from app.brain.agent_brain import AgentBrain

    o = asyncio.new_event_loop()
    try:
        brain = AgentBrain("research", main_brain=None, agent_models=None)

        class FakeLLM:
            async def complete(self, messages):
                from app.services.llm_service import CompletionResult
                return CompletionResult(content="AGENT-OWN-MODEL-ANSWER", has_tool_calls=False)

        brain._llm = FakeLLM()

        async def run():
            await brain.setup()
            return await brain.draft("summarize X")

        out = o.run_until_complete(run())
        assert "AGENT-OWN-MODEL-ANSWER" in out
    finally:
        o.close()

