"""Deep functional audit of Moon's working subsystems (tools, memory, agent-tool
use, learning loop). Real execution, real output — no fabrication.

Run: env -u PYTHONPATH .venv/bin/python scripts/moon_functional_audit.py
"""
from __future__ import annotations
import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from app.brain.orchestrator import Orchestrator
from app.config.settings import get_settings
from app.models.task import Task


async def main() -> None:
    o = Orchestrator(get_settings())
    await o.setup()
    # Unlock so the agent-tool path is exercised (MOON is locked by default).
    await o.run_task(Task.create("MOON love you 3000"))
    print(f"UNLOCKED={not o._lock.locked}")
    print(f"AGENT_BRAINS={len(o._agent_brains)}")
    names = sorted(o._tools._registry.tool_names)
    print(f"TOOLS={len(names)}")
    print("HAS_capability_manager=" + str("capability_manager" in names))
    print("HAS_global_connector=" + str("global_connector" in names))

    # 1) Direct real tool execution
    res = await o._tools.run("python_executor", {"code": "print(21*2)"}, agent=None)
    out = getattr(res, "output", None)
    print(f"TOOL_python_executor_output={out!r} success={getattr(res,'success',None)}")

    # 2) Agent uses a tool end-to-end (run a python task through the brain)
    t = Task.create("run this python code and tell me the result: print(6*7)", agent_name="auto")
    o._route_intent(t)
    r = await o.run_task(t)
    ans = r.result or ""
    print(f"AGENT_TOOL_USE agent={t.agent_name} len={len(ans)} answer={ans[:80]!r}")

    # 3) Memory persistence (learning loop): store + recall via the real API
    try:
        await o._memory.learn("AUDIT_MARKER_MOON_FUNCTIONAL memory write works")
        hits = await o._memory.recall("AUDIT_MARKER", limit=3)
        print(f"MEMORY_learn_ok recall_hits={len(hits)}")
        # episode record + save (the learning loop path)
        o._memory.episodic.record(goal="audit probe", outcome="ok", lesson="", success=True)
        o._memory.save_episodes()
        print("MEMORY_episode_saved=OK")
    except Exception as e:  # noqa: BLE001
        print(f"MEMORY_FAIL={e!r}")

    # 4) Consolidator (knowledge consolidation) does not crash
    try:
        if o._consolidator is not None:
            await o._consolidator.consolidate(prompt="audit probe", response="ok", lesson="", success=True, agent="manager")
            print("CONSOLIDATOR=OK")
        else:
            print("CONSOLIDATOR=disabled")
    except Exception as e:  # noqa: BLE001
        print(f"CONSOLIDATOR_FAIL={e!r}")

    # 5) Global connector list (real subsystem)
    try:
        ct = o._tools._registry.get("global_connector")
        if ct:
            lst = await ct.execute(action="list")
            print(f"CONNECTOR_list={str(lst)[:80]!r}")
        else:
            print("CONNECTOR=not_registered")
    except Exception as e:  # noqa: BLE001
        print(f"CONNECTOR_FAIL={e!r}")

    print("FUNCTIONAL_AUDIT_DONE")
    await o.teardown()


if __name__ == "__main__":
    asyncio.run(main())
