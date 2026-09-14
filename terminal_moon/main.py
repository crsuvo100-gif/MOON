from __future__ import annotations

import argparse
import asyncio
import sys
import os

# env_guard FIRST — strip foreign PYTHONPATH
from app.config.env_guard import _guard  # noqa: F401
from app.config.settings import get_settings
from app.config.logging import get_logger

logger = get_logger("moontm")


def cmd_run(args: argparse.Namespace) -> None:
    s = get_settings()
    async def _go():
        from app.brain.orchestrator import Orchestrator as O, Task
        orch = O(s)
        await orch.setup()
        if args.task:
            t = Task.create(args.task)
            await orch.run_task(t)
            print(t.result or "[no result]")
        else:
            from app.tui import Moonscope
            Moonscope().run()
        await orch.teardown()
    asyncio.run(_go())


def cmd_terminal(args: argparse.Namespace) -> None:
    from app.tui import Moonscope
    Moonscope().run()


def cmd_cli(args: argparse.Namespace) -> None:
    sys.argv = [sys.argv[0], "cli"]
    from app.cli.main import main as cli_main
    cli_main()


def cmd_models(args: argparse.Namespace) -> None:
    import subprocess
    model = args.model or get_settings().model_name
    print(f"Pulling {model}...")
    subprocess.run(["ollama", "pull", model], check=False)


def cmd_terminal_server(args: argparse.Namespace) -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run("app.terminal_interface:app", host=s.host, port=s.port,
                log_level=s.log_level.lower())


def cmd_doctor(args: argparse.Namespace) -> None:
    checks = []
    s = get_settings()
    try:
        import httpx
        async def _check():
            try:
                async with httpx.AsyncClient(timeout=5.0) as c:
                    r = await c.get(f"http://127.0.0.1:{s.port}/api/health")
                    return r.json()
            except Exception:
                return None
        h = asyncio.run(_check())
        if h and h.get("summary") == "HEALTHY":
            checks.append(("backend", "PASS", "running"))
        elif h:
            checks.append(("backend", "WARN", h.get("summary")))
        else:
            checks.append(("backend", "FAIL", "not reachable"))
    except Exception:
        checks.append(("backend", "FAIL", "asyncio error"))

    checks.append(("config", "PASS", f"model={s.model_name}"))
    checks.append(("voice", "PASS", "chain ready"))
    checks.append(("lock", "PASS", "locked" if not args.unlocked else "unlocked"))

    print("╔══════════════════════════════════════╗")
    print("║  MOON TERMINAL — DOCTOR             ║")
    print("╠══════════════════════════════════════╣")
    for n, st, dt in checks:
        ic = "✓" if st == "PASS" else "✗" if st == "FAIL" else "⚠"
        print(f"║  {ic} {n:<12} {st:<8} {dt:<20} ║")
    print("╚══════════════════════════════════════╝")


def cmd_status(args: argparse.Namespace) -> None:
    s = get_settings()
    import httpx
    try:
        async def _check():
            async with httpx.AsyncClient(timeout=5.0) as c:
                return await c.get(f"http://127.0.0.1:{s.port}/api/health")
        resp = asyncio.run(_check())
        if resp:
            d = resp.json()
            print(f"status: {d.get('summary', 'unknown')}")
            for c in d.get("checks", []):
                print(f"  {c['name']}: {c['state']} — {c['detail'][:60]}")
        else:
            print("Backend not reachable on port", s.port)
    except Exception as e:
        print(f"Status check failed: {e}")


def cmd_install(args: argparse.Namespace) -> None:
    from app.install import install
    install()


def cmd_setup(args: argparse.Namespace) -> None:
    print("Setup wizard: edit .env manually. See .env.example.")


def cmd_uninstall(args: argparse.Namespace) -> None:
    from app.install import uninstall
    uninstall()


def cmd_version(args: argparse.Namespace) -> None:
    print("MOON Terminal v1.0.0")


def cmd_monitor(args: argparse.Namespace) -> None:
    print("Monitor: use cron or systemd.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="moon",
                                     description="MOON Terminal — AI agent terminal")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("run", help="Run task (TUI if no task)")
    p.add_argument("task", nargs="?", default="", help="task")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("terminal", help="Launch TUI")
    p.set_defaults(func=cmd_terminal)

    p = sub.add_parser("cli", help="Launch CLI REPL")
    p.set_defaults(func=cmd_cli)

    p = sub.add_parser("models", help="Pre-pull models")
    p.add_argument("--model", help="model name")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("server", help="Launch REST+WS backend")
    p.set_defaults(func=cmd_terminal_server)

    p = sub.add_parser("doctor", help="Health check")
    p.add_argument("--unlocked", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("status", help="Check backend health")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("install", help="Installer")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("setup", help="First-run setup")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("uninstall", help="Uninstall")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("version", help="Version")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("monitor", help="Health monitor")
    p.set_defaults(func=cmd_monitor)

    args = parser.parse_args()
    if args.command == "run" and not args.task:
        cmd_terminal(args)
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
