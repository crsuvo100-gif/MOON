"""MOON CLI entrypoint."""

from __future__ import annotations

# Decontaminate PYTHONPATH BEFORE any other imports (see app/config/env_guard.py).
import app.config.env_guard  # noqa: F401  (strips foreign-venv PYTHONPATH)

import argparse
import asyncio

from app.brain.orchestrator import Orchestrator
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)





def _ensure_default_peer() -> None:
    """Idempotently register MOON's own loopback peer so the global connector
    always shows a LIVE connection (verified via 'connect health'/'federate').

    This is additive: it only registers the peer if absent, and never clobbers a
    user-managed registry. The default registry file (connections/registry.json)
    already seeds this; this is a belt-and-suspenders for fresh clones.
    """
    try:
        from app.connector.gateway import ConnectionGateway

        gw = ConnectionGateway()
        if gw.get("moon_local") is None:
            from app.connector.gateway import ConnectionRecord

            from app.config.settings import get_settings

            s = get_settings()
            gw.register(ConnectionRecord(
                name="moon_local", kind="agent",
                url=s.model_base_url.rstrip("/"), model=s.model_name,
                scope="network.agent", permissions=("network.agent",),
                credential_ref="", enabled=True,
                metadata={"note": "Loopback peer: MOON's own Ollama-compatible endpoint (default live connection)."},
            ))
            print("🌙 Registered default loopback peer 'moon_local' (global connector)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("default peer registration skipped: %s", exc)


async def _prefetch_models():
    import json

    from app.brain.agent_model_manager import AgentModelManager
    from app.config.settings import get_settings

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


async def _run_dashboard():
    from app.dashboard import run_dashboard

    o = Orchestrator(get_settings())
    await o.setup()

    async def run_fn(prompt: str) -> str:
        from app.models.task import Task
        res = await o.run_task(Task.create(prompt, agent_name="auto"))
        return res.result or ""

    run_dashboard(run_fn)
    print("🌙 MOON dashboard running. Open http://127.0.0.1:5000  (Ctrl-C to stop)")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await o.teardown()


def _run_terminal() -> None:
    import subprocess
    import sys

    print("🌙 MOON Terminal starting at http://127.0.0.1:8777")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "app.terminal_interface:app",
        "--host", "127.0.0.1", "--port", "8777", "--log-level", "info",
    ])


def main() -> None:
    ap = argparse.ArgumentParser(prog="moon", description="Standalone AI Agent")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="Launch MOON's terminal interface (animated avatar UI)")
    run_p = sub.add_parser("run", help="Run a single task")
    run_p.add_argument("task", nargs="?", default="Say hello.")
    run_p.add_argument("--agent", default="auto")
    sub.add_parser("models", help="Pre-pull all per-agent preferred models so agents are ready")
    sub.add_parser("dashboard", help="Launch the MOON web dashboard (Flask+SocketIO UI)")
    sub.add_parser("terminal", help="Launch MOON's own terminal interface (animated avatar UI)")
    sub.add_parser("tui", help="Launch MOON's curses text-mode terminal UI (headless/SSH)")
    sub.add_parser("telegram", help="Run MOON as a Telegram bot (polling listener)")
    args = ap.parse_args()
    _ensure_default_peer()
    if args.cmd == "start":
        _run_terminal()
    elif args.cmd == "run":
        asyncio.run(_run(args.task, args.agent))
    elif args.cmd == "models":
        asyncio.run(_prefetch_models())
    elif args.cmd == "dashboard":
        asyncio.run(_run_dashboard())
    elif args.cmd == "tui":
        from app.tui import main as tui_main
        raise SystemExit(tui_main())
    elif args.cmd == "telegram":
        from app.services.telegram_bot import main as tg_main
        raise SystemExit(tg_main())
    elif args.cmd == "terminal":
        _run_terminal()
    else:
        # No subcommand (or unknown) -> Moon Terminal is the DEFAULT interface.
        _run_terminal()


if __name__ == "__main__":
    main()
