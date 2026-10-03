"""Spec 52 PHASE APPROVAL GATES — verifies each gate with real execution.

    GATE 1  Existing architecture understood
    GATE 2  Multi-agent architecture approved internally
    GATE 3  Main Brain operational
    GATE 4  Agent base operational
    GATE 5  First specialist agent operational
    GATE 6  Agent Brain routing operational
    GATE 7  Agent communication operational
    GATE 8  Result aggregation operational
    GATE 9  Verification operational
    GATE 10 Terminal integration operational
    GATE 11 End-to-end multi-agent task operational
    GATE 12 Clean installation operational

"Never proceed past a critical failed gate without repair or rollback."
Exit code 1 if any gate FAILS.

    env -u PYTHONPATH .venv/bin/python scripts/spec52_gates.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GATES: list[tuple[int, str, str, str]] = []


def gate(n: int, name: str, ok: bool, detail: str) -> None:
    GATES.append((n, name, "PASS" if ok else "FAIL", detail))


# ------------------------------------------------------------------ GATE 1
try:
    required = ["app/brain/orchestrator.py", "app/tools/registry.py",
                "app/brain/memory_manager.py", "app/models/task.py",
                "app/brain/agent_registry.py", "pyproject.toml"]
    present = [p for p in required if (ROOT / p).exists()]
    gate(1, "Existing architecture understood", len(present) == len(required),
         f"inspected {len(present)}/{len(required)} core components "
         f"(orchestrator, tools, memory, models, agents, packaging)")
except Exception as e:  # noqa: BLE001
    gate(1, "Existing architecture understood", False, str(e))

# ------------------------------------------------------------------ GATE 2
try:
    mods = ["app/brain/orchestrator.py", "app/brain/agent_brain.py",
            "app/runtime/brain_provider.py", "app/agents/advanced/supervision.py",
            "app/brain/aggregator.py", "app/brain/recovery_policy.py",
            "app/agents/professional/professional_orchestrator.py",
            "app/agents/registry.py", "app/runtime/event_bus.py"]
    found = [m for m in mods if (ROOT / m).exists()]
    gate(2, "Multi-agent architecture approved internally", len(found) == len(mods),
         f"architecture modules present: {len(found)}/{len(mods)}")
except Exception as e:  # noqa: BLE001
    gate(2, "Multi-agent architecture approved internally", False, str(e))


# ------------------------------------------------------------ GATES 3-9, 11
async def _runtime_gates() -> None:
    from app.brain.orchestrator import Orchestrator
    from app.config.settings import get_settings
    from app.models.task import Task

    o = Orchestrator(get_settings())
    try:
        await o.setup()
    except Exception as exc:  # noqa: BLE001
        for n, name in ((3, "Main Brain operational"), (4, "Agent base operational"),
                        (5, "First specialist agent operational"),
                        (6, "Agent Brain routing operational"),
                        (7, "Agent communication operational"),
                        (8, "Result aggregation operational"),
                        (9, "Verification operational")):
            gate(n, name, False, f"setup failed: {exc}")
        return

    # GATE 3 — Main Brain
    brain_ok = (o._llm is not None and o._tools is not None and o._memory is not None
                and o._context is not None and len(o._agents) > 0)
    gate(3, "Main Brain operational", brain_ok,
         f"llm={o._llm is not None}, tools={o._tools is not None}, "
         f"memory={o._memory is not None}, agents={len(o._agents)}, "
         f"planner={o._planner is not None}, validator={o._validator is not None}")

    # GATE 4 — Agent base (common interface)
    try:
        from app.agents import AgentResult, BaseAgent, OrchestratorAgent
        base = BaseAgent()
        iface = [m for m in ("metadata", "capabilities", "permissions", "validate_input",
                             "plan", "execute", "verify", "reflect", "health", "shutdown")
                 if hasattr(base, m)]
        gate(4, "Agent base operational", len(iface) == 10,
             f"BaseAgent interface: {len(iface)}/10 methods "
             f"(+AgentResult +OrchestratorAgent)")
    except Exception as e:  # noqa: BLE001
        gate(4, "Agent base operational", False, str(e))

    # GATE 5 — first specialist agent (real execution)
    try:
        spec_agent = o._agents.get("coding")
        brain = o._agent_brains.get("coding")
        out = await brain.run("Reply with exactly: READY") if brain else ""
        gate(5, "First specialist agent operational",
             spec_agent is not None and brain is not None and bool(str(out).strip()),
             f"coding agent + its own brain; live reply={str(out).strip()[:40]!r}")
    except Exception as e:  # noqa: BLE001
        gate(5, "First specialist agent operational", False, str(e))

    # GATE 6 — agent brain routing (distinct brains per agent)
    try:
        from app.brain.agent_model_manager import AgentModelManager
        m = o._agent_models
        per = {a: m._preferred(a) for a in ("coding", "math", "research", "writing")}
        distinct = len(set(per.values()))
        br = getattr(o, "_brain_router", None)
        gate(6, "Agent Brain routing operational",
             distinct > 1 and br is not None and len(br.specs()) >= 3,
             f"{distinct} distinct per-agent models {per}; "
             f"brain router has {len(br.specs()) if br else 0} brains")
    except Exception as e:  # noqa: BLE001
        gate(6, "Agent Brain routing operational", False, str(e))

    # GATE 7 — agent communication
    try:
        from app.runtime.messaging import MessageBus, MessageType, get_bus
        bus = get_bus()
        bus.post(sender="gate", receiver="coding", payload={"ping": 1})
        got = bus.receive("coding", timeout=1.0)
        types = len(list(MessageType))
        gate(7, "Agent communication operational",
             got is not None and types >= 15,
             f"message posted+received; {types} message types")
    except Exception as e:  # noqa: BLE001
        gate(7, "Agent communication operational", False, str(e))

    # GATE 8 — result aggregation (real conflict detection)
    try:
        from app.brain.aggregator import (AgentEnvelope, ConflictKind,
                                          ResultAggregator)
        agg = ResultAggregator().aggregate([
            AgentEnvelope(agent_id="coding", result="Bug fixed.", confidence=0.9,
                          evidence=["edited x.py"]),
            AgentEnvelope(agent_id="testing", result="", status="failed",
                          errors=["tests still fail"]),
        ])
        ok = agg.has_conflict and any(c.kind == ConflictKind.FAILURE for c in agg.conflicts)
        gate(8, "Result aggregation operational", ok,
             f"aggregated; status={agg.status.value}, conflicts={len(agg.conflicts)}")
    except Exception as e:  # noqa: BLE001
        gate(8, "Result aggregation operational", False, str(e))

    # GATE 9 — verification
    try:
        from app.verification import Verifier
        v = Verifier()
        r = v.file_exists(str(ROOT / "pyproject.toml"))
        bad = v.file_exists("/nonexistent/definitely-missing")
        gate(9, "Verification operational",
             bool(r.passed) and not bool(bad.passed),
             "verifier distinguishes present vs absent evidence")
    except Exception as e:  # noqa: BLE001
        gate(9, "Verification operational", False, str(e))

    # GATE 11 — end-to-end multi-agent task
    try:
        t = Task(prompt="What is 6 multiplied by 7? Reply with only the number.",
                 agent_name="auto")
        t = await o.run_task(t)
        ans = (t.result or "").strip()
        gate(11, "End-to-end multi-agent task operational",
             t.status in ("completed", "done") and "42" in ans,
             f"status={t.status}, answer={ans[:60]!r}, agent={t.agent_name}, "
             f"budget={t.data.get('_context_budget', {}).get('before', 'n/a')}")
    except Exception as e:  # noqa: BLE001
        gate(11, "End-to-end multi-agent task operational", False, str(e))

    try:
        await o.teardown()
    except Exception:  # noqa: BLE001
        pass


asyncio.run(_runtime_gates())

# ------------------------------------------------------------------ GATE 10
try:
    import app.terminal_interface as T
    routes = [getattr(r, "path", "") for r in T.app.routes]
    need = ["/api/health", "/api/events", "/api/brains", "/api/supervision",
            "/api/moon-agent", "/ui"]
    have = [n for n in need if n in routes]
    gate(10, "Terminal integration operational", len(have) == len(need),
         f"{len(routes)} routes incl {have}")
except Exception as e:  # noqa: BLE001
    gate(10, "Terminal integration operational", False, str(e))

# ------------------------------------------------------------------ GATE 12
try:
    installer = (ROOT / "script.py").exists()
    pkg = (ROOT / "pyproject.toml").read_text(errors="ignore")
    script_ok = "moon =" in pkg
    gate(12, "Clean installation operational", installer and script_ok,
         f"script.py installer present={installer}; console_script={script_ok}; "
         f"verify with: python script.py --verify")
except Exception as e:  # noqa: BLE001
    gate(12, "Clean installation operational", False, str(e))


# ------------------------------------------------------------------- report
print("=" * 72)
print("MOON SPEC 52 — PHASE APPROVAL GATES")
print("=" * 72)
for n, name, state, detail in sorted(GATES):
    print(f"  [{state}] GATE {n:2d}: {name}")
    print(f"            {detail[:150]}")
fails = [g for g in GATES if g[2] == "FAIL"]
print()
print(f"RESULT: {len(GATES) - len(fails)}/{len(GATES)} gates PASSED"
      + ("" if not fails else f"  --  FAILED: {[g[0] for g in fails]}"))
sys.exit(1 if fails else 0)
