import asyncio, sys, os
sys.path.insert(0, '.')
from app.config.settings import get_settings
from app.brain.orchestrator import Orchestrator

async def main():
    o = Orchestrator(get_settings())
    await o.setup()
    notice = o._lock.observe('MOON love you 3000')
    print('UNLOCK_NOTICE:', str(notice)[:120])
    res = await o._tools.run('system_info', {}, agent=None)
    text = str(res)
    print('TOOL_RESULT_HEAD:', text[:200].replace('\n', ' | '))
    ok = ('linux' in text.lower())
    print('SYSTEM_INFO_OK' if ok else 'SYSTEM_INFO_MISSING_LINUX')
    if not ok:
        sys.exit(1)
    await o.teardown()

asyncio.run(main())
