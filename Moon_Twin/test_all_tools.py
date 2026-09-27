import sys, json, traceback, asyncio
sys.path.insert(0, '.')
from agent.engine import default_engine

async def test_all():
    failed = []
    ok = []
    for name in sorted(default_engine._tool_handlers.keys()):
        handler = default_engine._tool_handlers[name]
        try:
            r = await handler({})
            s = str(r)
            if len(s) > 120:
                s = s[:120] + '...'
            ok.append((name, s))
        except Exception as e:
            failed.append((name, type(e).__name__, str(e)[:120]))
    return ok, failed

ok, failed = asyncio.run(test_all())
print(f"OK ({len(ok)}):")
for n, s in ok:
    print(f"  OK  {n:30s} -> {s}")

print(f"\nFAILED ({len(failed)}):")
for n, e, s in failed:
    print(f"  FAIL {n:30s} [{e}] {s}")
