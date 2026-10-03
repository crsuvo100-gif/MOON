"""Boot probe: prove which multi-brain subsystems are ACTIVE (not None)."""
import asyncio, sys, time

async def main():
    from app.brain.orchestrator import Orchestrator
    from app.config.settings import get_settings

    o = Orchestrator(get_settings())
    t0 = time.time()
    try:
        await o.setup()
    except Exception as e:
        print(f"SETUP FAILED: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return 1

    checks = [
        ("main brain (llm)",        "_llm"),
        ("agent model manager",     "_agent_models"),
        ("memory manager",          "_memory"),
        ("tool manager",            "_tools"),
        ("planner",                 "_planner"),
        ("validator",               "_validator"),
        ("advanced memory",         "_advanced_memory"),
        ("advanced agents",         "_advanced_agents"),
        ("advanced brain",          "_advanced_brain"),
        ("cognitive loop",          "_cognitive_loop"),
        ("agent workflow",          "_agent_workflow"),
        ("skill orchestrator",      "_skill_orchestrator"),
        ("context orchestrator",    "_context_orchestrator"),
        ("professional orchestrator","_professional_orchestrator"),
    ]
    print(f"\n=== SUBSYSTEM STATE (setup took {time.time()-t0:.1f}s) ===")
    active = 0
    for label, attr in checks:
        v = getattr(o, attr, None)
        state = "ACTIVE" if v is not None else "None  "
        if v is not None: active += 1
        print(f"  [{state}] {label:28s} {type(v).__name__ if v is not None else ''}")
    print(f"\n{active}/{len(checks)} subsystems ACTIVE")
    print(f"agents registered: {len(getattr(o,'_agents',{}) or {})}")
    print(f"agent brains:      {len(getattr(o,'_agent_brains',{}) or {})}")
    reg = getattr(getattr(o,'_tools',None), '_registry', None)
    print(f"tools registered:  {len(getattr(reg,'tool_names',[]) or [])}")

    # Real inference through the main brain
    print("\n=== LIVE INFERENCE (quick_reply) ===")
    try:
        ans = await o.quick_reply("Reply with exactly: MOON MULTIBRAIN ONLINE")
        print(f"  answer: {ans!r}")
    except Exception as e:
        print(f"  inference failed: {type(e).__name__}: {e}")

    await o.teardown()
    return 0 if active >= 10 else 1

sys.exit(asyncio.run(main()))
