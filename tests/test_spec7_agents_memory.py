"""Spec 55 coverage gaps + spec 7 agent roster completeness.

Covers the two §55 test categories that had no test at all:
    15. Memory isolation   -- each agent's private memory is its own file
    16. Shared memory      -- global memory is controlled, not blanket-exposed
plus the spec-7 specialist roster (all 10 named agents must exist).
"""

from __future__ import annotations

import asyncio

from app.brain.agent_brain import _AgentBrainStore
from app.brain.agent_registry import build_agents


# ------------------------------------------------------- §7 agent roster
def test_all_ten_spec7_specialists_exist() -> None:
    agents = build_agents([])
    # the spec's 10 named specialists -> MOON agent ids
    spec7 = {
        "Coding Agent": "coding",
        "Research Agent": "research",
        "System Agent": "infra",
        "Web Agent": "browser",
        "Git/GitHub Agent": "github_sync",
        "Security Agent": "security",
        "Testing/QA Agent": "qa",
        "Memory Agent": "memory",
        "Data/File Agent": "data_file",
        "Automation Agent": "automation",
    }
    missing = [label for label, aid in spec7.items() if aid not in agents]
    assert not missing, f"missing spec-7 specialists: {missing}"


def test_new_agents_have_scoped_tools_not_everything() -> None:
    """spec 34: an agent should not automatically receive every tool."""
    tools = ["file_manager", "pdf_reader", "ocr", "database", "python_executor",
             "terminal", "system_command", "docker", "git", "web_search", "browser"]
    agents = build_agents(tools)
    data_tools = set(agents["data_file"].allowed_tools)
    auto_tools = set(agents["automation"].allowed_tools)
    assert "file_manager" in data_tools
    assert "browser" not in data_tools and "web_search" not in data_tools
    assert "terminal" in auto_tools
    assert data_tools != auto_tools, "the two agents must have distinct scopes"
    assert len(data_tools) < len(tools), "scope must be narrower than all tools"


def test_agent_count_is_at_least_41() -> None:
    """39 personas + the 2 spec-7 additions (factory agents may add more)."""
    agents = build_agents([])
    assert len(agents) >= 41, f"expected >=41 agents, got {len(agents)}"
    assert "data_file" in agents and "automation" in agents


# -------------------------------------------------- §55.15 memory isolation
def _episode_store(agent: str) -> _AgentBrainStore:
    """Build a store and populate its in-memory episode list (the real API:
    ``append`` is async and only then is ``episodes()`` non-empty)."""
    s = _AgentBrainStore(agent)
    asyncio.run(s.append({"goal": f"probe-{agent}", "outcome": "ok"}))
    return s


def test_private_memory_is_isolated_per_agent() -> None:
    """Each agent gets its OWN durable store; one agent cannot read another's."""
    a = _AgentBrainStore("coding_probe")
    b = _AgentBrainStore("research_probe")
    asyncio.run(a.append({"goal": "fix bug", "outcome": "patched"}))
    asyncio.run(b.append({"goal": "read paper", "outcome": "summarized"}))

    a_eps = a.episodes()
    b_eps = b.episodes()
    assert any("fix bug" in str(e) for e in a_eps)
    assert not any("fix bug" in str(e) for e in b_eps), "coding memory leaked into research"
    assert any("read paper" in str(e) for e in b_eps)
    assert not any("read paper" in str(e) for e in a_eps), "research memory leaked into coding"


def test_private_memory_paths_differ() -> None:
    a = _AgentBrainStore("agent_one")
    b = _AgentBrainStore("agent_two")
    assert a._path != b._path
    assert "agent_one" in str(a._path) and "agent_two" in str(b._path)


def test_private_memory_survives_reload() -> None:
    """Private memory is durable across store instances (same agent name)."""
    import uuid as _uuid

    agent = f"durable_probe_{_uuid.uuid4().hex[:8]}"
    s1 = _AgentBrainStore(agent)
    asyncio.run(s1.append({"goal": "persist me", "outcome": "ok"}))
    assert s1._path.exists(), "append did not write the JSONL file"
    s2 = _AgentBrainStore(agent)
    asyncio.run(s2.load())
    assert any("persist me" in str(e) for e in s2.episodes())
    try:
        s1._path.unlink()
    except OSError:
        pass


# ---------------------------------------------------- §55.16 shared memory
def test_global_memory_is_controlled_not_blanket() -> None:
    """spec 23: global memory is retrieved on demand, not exposed wholesale."""
    from app.memory.advanced.orchestrator import AdvancedMemoryOrchestrator

    methods = [m for m in dir(AdvancedMemoryOrchestrator) if not m.startswith("__")]
    # controlled retrieval exists...
    assert any(m in methods for m in ("before_task", "search", "recall", "unified_search")), \
        f"no controlled retrieval surface: {methods[:20]}"
    # ...and there is no 'give me everything' accessor handed to agents.
    blanket = [m for m in methods if m in ("everything", "dump", "expose_all")]
    assert not blanket, f"blanket global-memory accessor found: {blanket}"


def test_global_memory_retrieval_is_query_scoped() -> None:
    """A query returns only what matches, not the entire store."""
    from app.memory.enhanced_long_term import EnhancedLongTermMemory
    from app.brain.memory_manager import MemoryManager

    async def _run() -> None:
        ltm = EnhancedLongTermMemory()
        await ltm.setup()
        await ltm.store({"content": "MOON uses qwen models for local inference"}, importance=0.9)
        await ltm.store({"content": "The cafeteria menu changes on Fridays"}, importance=0.9)
        mm = MemoryManager(long_term=ltm)
        hits = await mm.recall("qwen", limit=5)
        joined = " ".join(hits).lower()
        assert "qwen" in joined, f"relevant memory not retrieved: {hits}"
        # an unrelated query must not surface the unrelated fact
        other = await mm.recall("cafeteria", limit=5)
        assert not any("qwen" in h.lower() for h in other), \
            f"query-scoping leaked unrelated memory: {other}"

    asyncio.run(_run())
