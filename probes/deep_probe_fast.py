import asyncio, sys
sys.path.insert(0, '.')
from app.config.settings import get_settings
from app.brain.orchestrator import Orchestrator
from app.tools.registry import ToolRegistry
from app.tools.system_info_tool import SystemInfoTool
from app.brain.tool_manager import ToolManager

async def main():
    o = Orchestrator(get_settings())
    # Rebuild the orchestrator's tool runner directly (fast; no heavy KB re-index).
    reg = ToolRegistry()
    reg.register(SystemInfoTool())
    o._tools = ToolManager(reg)
    o._tools._tool_timeout = getattr(o._settings, 'tool_timeout', 60)

    notice = o._lock.observe('MOON love you 3000')
    print('UNLOCK_NOTICE:', str(notice)[:120])

    res = await o._tools.run('system_info', {}, agent=None)
    text = str(res)
    print('TOOL_RESULT_HEAD:', text[:160].replace('\n', ' | '))
    ok = ('linux' in text.lower())
    print('SYSTEM_INFO_OK' if ok else 'SYSTEM_INFO_MISSING_LINUX')
    if not ok:
        sys.exit(1)
    await o.teardown()

asyncio.run(main())
