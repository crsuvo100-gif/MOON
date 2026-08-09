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
    logger.info("Starting MOON at http://localhost:8000/brain")
    subprocess.run([
        sys.executable, "-m", "uvicorn", _APP_MODULE,
        "--host", "127.0.0.1", "--port", "8000", "--log-level", "info",
    ])


async def _prefetch_models():
    from app.brain.orchestrator import Orchestrator
    from app.config.settings import get_settings
    from app.brain.agent_model_manager import AgentModelManager
    import json

    settings = get_settings()
    mgr = AgentModelManager(
        base_url=settings.model_base_url, api_key=settings.model_api_key,
        default_model=settings.model_name, temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens, timeout=settings.model_timeout,
    )
    results = await mgr.prefetch_all()
    print(json.dumps(results, indent=2))
    ready = [m for m, ok in results.items() if ok]
    print(f"\n{len(ready)}/{len(results)} models ready: " + ", ".join(ready))


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
    models_p = sub.add_parser("models", help="Pre-pull all per-agent preferred models so agents are ready")
    args = ap.parse_args()
    if args.cmd == "start":
        _start_http()
    elif args.cmd == "run":
        asyncio.run(_run(args.task, args.agent))
    elif args.cmd == "models":
        asyncio.run(_prefetch_models())
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
