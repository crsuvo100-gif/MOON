"""live_smoke_pipeline.py -- end-to-end smoke of the orchestrator."""

import asyncio
import sys

from app.brain.orchestrator import Orchestrator
from app.config.settings import get_settings
from app.models.task import Task


async def main() -> int:
    o = Orchestrator(get_settings())
    await o.setup()
    res = await o.run_task(Task.create("What is 7 * 6? Reply with just the number."))
    print("RESULT:", res.result)
    await o.teardown()
    return 0 if res.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
