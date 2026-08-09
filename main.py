"""MOON CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio

from app.brain.orchestrator import Orchestrator
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)

_APP_MODULE = "app.api.main:" + "app"


def _start_http() -> None:
    import subprocess
    import sys
    settings = get_settings()
    logger.info("Starting MOON at http://localhost:8000/brain")
    subprocess.run([
        sys.executable, "-m", "uvicorn", _APP_MODULE,
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "info",
    ])


async def _run(task, agent):
    o = Orchestrator(get_settings())
    await o.setup()
    from app.models.task import Task
    res = await o.run_task(Task.create(task, agent_name=agent))
    print(res.result)
    await o.teardown()


def main() -> None:
    ap = argparse.ArgumentParser(prog="moon", description="Standalone AI Agent")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="Run the web backend + Neural Brain Command Center")
    run_p = sub.add_parser("run", help="Run a single task")
    run_p.add_argument("task", nargs="?", default="Say hello.")
    run_p.add_argument("--agent", default="auto")
    args = ap.parse_args()
    if args.cmd == "start":
        _start_http()
    elif args.cmd == "run":
        asyncio.run(_run(args.task, args.agent))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
