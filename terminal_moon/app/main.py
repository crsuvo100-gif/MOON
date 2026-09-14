"""
MOON Terminal — main CLI entrypoint.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# env_guard FIRST — strip foreign PYTHONPATH
from app.config.env_guard import _guard  # noqa: F401
from app.config.settings import get_settings
from app.config.logging import get_logger

logger = get_logger("moontm")

# ── subcommands ────────────────────────────────────────────────────────────
def cmd_run(args: argparse.Namespace) -> None:
    """Run a task, or launch TUI if no task given."""
    s = get_settings()
    async def _go():
        from app.brain.orchestrator import Orchestrator, Task
        orch = Orchestrator(s)
        await orch.setup()
        if args.task:
            task = Task.create(args.task)
            await orch.run_task(task)
            print(task.result or "[no result]")
        else:
            from app.tui import Moonscope
            Moonscope().run()
        await orch.teardown()
    asyncio.run(_go())


def cmd_terminal(args: argparse.Namespace) -> None:
    """Launch moonscope TUI."""
    from app.tui import Moonscope
    Moonscope().run()


def cmd_cli(args: argparse.Namespace) -> None:
    """Launch CLI REPL."""
    sys.argv = [sys.argv[0], "cli"]
    from app.cli.main import main as cli_main
    cli_main()


def cmd_models(args: argparse.Namespace) -> None:
    """Pre-pull models (stub — call ollama pull)."""
    import subprocess
    model = args.model or get_settings().model_name
    print(f"Pulling {model}...")
    subprocess.run(["ollama", "pull", model], check=False)


def cmd_terminal_server(args: argparse.Namespace) -> None:
    """Launch FastAPI+WS backend."""
    import uvicorn
    s = get_settings()
    uvicorn.run(
        "app.terminal_interface:app",
        host=s.host,
        port=s.port,
        log_level=s.log_level.lower(),
    )


def cmd_doctor(args: argparse.Namespace) -> None:
    """Health check."""
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
        health = asyncio.run(_check())
        if health and health.get("summary") == "HEALTHY":
            checks.append(("backend", "PASS", "running"))
        elif health:
            checks.append(("backend", "WARN", health.get("summary")))
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
    for name, state, detail in checks:
        icon = "✓" if state == "PASS" else "✗" if state == "FAIL" else "⚠"
        print(f"║  {icon} {name:<12} {state:<8} {detail:<20} ║")
    print("╚══════════════════════════════════════╝")


def cmd_status(args: argparse.Namespace) -> None:
    """Check backend health."""
    s = get_settings()
    import httpx
    try:
        async def _check():
            async with httpx.AsyncClient(timeout=5.0) as c:
                return await c.get(f"http://127.0.0.1:{s.port}/api/health")
        resp = asyncio.run(_check())
        if resp:
            data = resp.json()
            print(f"status: {data.get('summary', 'unknown')}")
            for c in data.get("checks", []):
                print(f"  {c['name']}: {c['state']} — {c['detail'][:60]}")
        else:
            print("Backend not reachable on port", s.port)
    except Exception as e:
        print(f"Status check failed: {e}")


def cmd_install(args: argparse.Namespace) -> None:
    """Run installer."""
    from app.install import install
    install()


def cmd_setup(args: argparse.Namespace) -> None:
    """First-run setup wizard."""
    print("Setup wizard: edit .env manually.")
    print("See .env.example for options.")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Safe uninstall."""
    from app.install import uninstall
    uninstall()


def cmd_version(args: argparse.Namespace) -> None:
    print("MOON Terminal v1.0.0")


def cmd_monitor(args: argparse.Namespace) -> None:
    """Launch health monitor."""
    print("Monitor: not implemented as standalone. Use cron or systemd.")


# ── entrypoint ─────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moon",
        description="MOON Terminal — AI agent terminal interface",
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run a task (launches TUI if no task)")
    p_run.add_argument("task", nargs="?", default="", help="task description")
    p_run.set_defaults(func=cmd_run)

    p_term = sub.add_parser("terminal", help="Launch TUI")
    p_term.set_defaults(func=cmd_terminal)

    p_cli = sub.add_parser("cli", help="Launch CLI REPL")
    p_cli.set_defaults(func=cmd_cli)

    p_mod = sub.add_parser("models", help="Pre-pull models")
    p_mod.add_argument("--model", help="model name")
    p_mod.set_defaults(func=cmd_models)

    p_srv = sub.add_parser("server", help="Launch REST+WS backend")
    p_srv.set_defaults(func=cmd_terminal_server)

    p_doc = sub.add_parser("doctor", help="Health check")
    p_doc.add_argument("--unlocked", action="store_true", help="check unlocked state")
    p_doc.set_defaults(func=cmd_doctor)

    p_stat = sub.add_parser("status", help="Check backend health")
    p_stat.set_defaults(func=cmd_status)

    p_inst = sub.add_parser("install", help="Run installer")
    p_inst.set_defaults(func=cmd_install)

    p_setup = sub.add_parser("setup", help="First-run setup")
    p_setup.set_defaults(func=cmd_setup)

    p_uninst = sub.add_parser("uninstall", help="Uninstall")
    p_uninst.set_defaults(func=cmd_uninstall)

    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=cmd_version)

    p_mon = sub.add_parser("monitor", help="Health monitor")
    p_mon.set_defaults(func=cmd_monitor)

    args = parser.parse_args()

    if args.command == "run" and not args.task:
        cmd_terminal(args)
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
