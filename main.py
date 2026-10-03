"""MOON CLI entrypoint."""

from __future__ import annotations

# Decontaminate PYTHONPATH BEFORE any other imports (see app/config/env_guard.py).
import app.config.env_guard  # noqa: F401  (strips foreign-venv PYTHONPATH)

import argparse
import asyncio
import os
import sys

from pathlib import Path
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


def _ensure_ollama() -> None:
    """Best-effort: make sure MOON's local model backend (Ollama) is reachable
    before the terminal/API starts, so the Orchestrator's setup() has a model to
    bind to (Phase 26 startup readiness).

    Additive + non-destructive: if Ollama is already up it is a no-op; if it
    cannot be started we still launch MOON (it degrades to the cloud fallbacks /
    reports the backend as unavailable rather than crashing). Mirrors the
    long-standing logic in scripts/moon_launcher.py.
    """
    import os
    import platform
    import shutil
    import subprocess
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=3) as r:
            if r.status == 200:
                return
    except Exception:
        pass
    print(f"🌙 Ollama not reachable at {host} -- attempting to start")
    try:
        if platform.system() == "Linux" and shutil.which("systemctl") is not None:
            cmd = ["systemctl", "start", "ollama"]
            if os.geteuid() != 0:
                cmd = ["sudo", *cmd]
            subprocess.run(cmd, check=False)
        else:
            exe = shutil.which("ollama")
            if exe:
                subprocess.Popen([exe, "serve"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama autostart skipped: %s", exc)


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
    """Run a task through the full Orchestrator (advanced brain + agents + memory)."""
    from app.brain.orchestrator import Orchestrator
    from app.config.settings import get_settings as _gs
    from app.models.task import Task
    import asyncio as _asyncio
    import time as _time

    settings = _gs()
    orchestrator = Orchestrator(settings)
    try:
        await orchestrator.setup()
    except Exception as exc:
        print(f"[MOON: orchestrator setup failed: {exc}]")
        return

    # Create a task model
    t = Task(prompt=task, agent_name=agent or "auto")

    # Pick an agent
    agent_card = None
    if agent and agent in orchestrator._agents:
        agent_card = orchestrator._agents[agent]
    elif orchestrator._agents:
        agent_card = list(orchestrator._agents.values())[0]

    if agent_card is None:
        print("[MOON: no agents available]")
        return

    # Run the task through the full cognition loop
    try:
        result_task = await orchestrator.run_task(t)
        content = result_task.result or ""
        if content:
            print(f"RESULT: {content}")
        else:
            print("(no response from model)")
    except _asyncio.TimeoutError:
        print("[MOON: task timed out]")
    except Exception as exc:
        print(f"[MOON: task failed: {exc}]")
    finally:
        try:
            await orchestrator.teardown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# `moon terminal` -- launch the Hermes-style CLI terminal (REPL, voice, shell).
# This is the single user-facing surface: a readline-driven interactive session
# with integrated voice (espeak-ng + Kokoro/F5-TTS), shell commands, and the
# full MOON brain behind it. No browser or web UI involved.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# `_cmd_ui()` removed: the web UI (moon_terminal.html / Three.js 3D brain orb /
# avatar images / theme.json) has been stripped from app/terminal_interface.py.
# `moon ui` no longer exists as a subcommand -- use `moon` or `moon terminal`
# for the Hermes-style CLI REPL, or hit the REST+WebSocket API directly.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Python-first operational commands (spec 9/10/25/26). All additive -- the
# existing start/run/models/terminal/tui/shell subcommands and the
# default-terminal behaviour are preserved untouched.
# ---------------------------------------------------------------------------

def _cmd_version() -> None:
    try:
        import importlib.metadata as md
        ver = md.version("moon-ai-agent")
    except Exception:
        ver = "0.1.0"
    print(f"moon-ai-agent {ver}")


def _cmd_status() -> int:
    import urllib.request

    host = "127.0.0.1:8777"
    try:
        with urllib.request.urlopen("http://" + host + "/api/health", timeout=5) as r:
            body = r.read().decode("utf-8", "replace")
        print(f"MOON backend at {host}: HEALTHY")
        print(body)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"MOON backend at {host}: UNREACHABLE ({exc})")
        print("Start it with:  python -m moon  (or: python -m moon terminal)")
        return 1




def _cmd_doctor() -> int:
    """Real health check (spec 10). Reports PASS / WARN / FAIL per subsystem."""
    import importlib.util
    import platform

    checks: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str, warn: bool = False) -> None:
        state = "PASS" if ok else ("WARN" if warn else "FAIL")
        checks.append((name, state, detail))

    # 1. Python version
    py_ok = sys.version_info >= (3, 10)
    add("Python version", py_ok, f"{platform.python_version()} (need >=3.10)")

    # 2. Dependencies importable
    try:
        import fastapi, uvicorn, pydantic, pydantic_settings, openai, httpx  # noqa: F401
        add("Core dependencies", True, "fastapi/uvicorn/pydantic/openai/httpx importable")
    except Exception as exc:  # noqa: BLE001
        add("Core dependencies", False, f"missing: {exc}")

    # 3. Project package imports
    try:
        import app.brain.orchestrator  # noqa: F401
        add("Project imports", True, "app package imports clean")
    except Exception as exc:  # noqa: BLE001
        add("Project imports", False, f"import error: {exc}")

    # 4. Configuration / .env
    env_path = Path(".env")
    env_example = Path(".env.example")
    add(".env present", env_path.is_file(),
        ".env found" if env_path.is_file() else ".env missing (copy .env.example and fill secrets)",
        warn=not env_path.is_file())
    add(".env.example present", env_example.is_file(), "template exists")

    # 5. Required runtime directories (recreated on first run -> WARN if missing)
    for d in ("data", "data/agents", "data/memory", "data/knowledge", "app/logs"):
        p = Path(d)
        add(f"dir:{d}", p.is_dir(), "exists" if p.is_dir() else "missing (recreated on first run)",
            warn=not p.is_dir())

    # 6. Databases
    for db in ("data/agents/agent_factory.db", "data/executions.db"):
        p = Path(db)
        add(f"db:{db}", p.is_file(), "exists" if p.is_file() else "not created yet (will be on first run)",
            warn=not p.is_file())

    # 7. Model runtime (Ollama reachability, optional)
    import urllib.request
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    try:
        with urllib.request.urlopen(f"http://{host}/api/tags", timeout=3) as r:
            ok = r.status == 200
        add("Model runtime (Ollama)", ok, f"reachable at {host}" if ok else "not reachable", warn=not ok)
    except Exception:
        add("Model runtime (Ollama)", False, f"not reachable at {host} (install Ollama + pull models)", warn=True)

    # 8. Agents & tools (real import)
    try:
        from app.brain.orchestrator import Orchestrator
        from app.config.settings import get_settings
        o = Orchestrator(get_settings())
        try:
            asyncio.run(o.setup())
        except Exception as exc:  # noqa: BLE001
            add("Orchestrator setup", False, f"setup error: {exc}", warn=True)
        n_agents = len(getattr(o, "_agents", {}) or {})
        reg = getattr(getattr(o, "_tools", None), "_registry", None)
        n_tools = len(getattr(reg, "tool_names", []) or [])
        add("Agents loadable", n_agents > 0, f"{n_agents} agents registered")
        add("Tools loadable", n_tools > 0, f"{n_tools} tools registered")
    except Exception as exc:  # noqa: BLE001
        add("Agents/Tools", False, f"load error: {exc}")

    # 9. Git integrity
    try:
        import subprocess as _sp
        out = _sp.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
        add("Git repository", out.returncode == 0, "repo intact" if out.returncode == 0 else "not a git repo")
    except Exception:
        add("Git repository", False, "git unavailable", warn=True)

    # Report
    fails = [c for c in checks if c[1] == "FAIL"]
    warns = [c for c in checks if c[1] == "WARN"]
    for name, state, detail in checks:
        print(f"[{state}] {name}: {detail}")
    print("-" * 60)
    if fails:
        print(f"RESULT: FAIL ({len(fails)} failed, {len(warns)} warning)")
        return 1
    if warns:
        print(f"RESULT: WARN ({len(warns)} warning, 0 failed)")
        return 0
    print("RESULT: PASS")
    return 0


def _cmd_backup() -> int:
    """Snapshot runtime data into backups/ (pure-Python, stdlib only).

    Self-contained: no external backup module required.
    """
    import shutil
    import time as _time

    stamp = _time.strftime("%Y%m%d_%H%M%S")
    dest = Path("backups") / f"moon_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in ("data", "connections", ".env"):
        src = Path(item)
        if not src.exists():
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, dest / item, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest / item)
            copied.append(item)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not back up {item}: {exc}")
    print(f"BACKUP COMPLETE -> {dest}")
    print(f"  included: {', '.join(copied) or 'nothing'}")
    return 0


def _cmd_restore() -> int:
    """Restore a backups/moon_<timestamp> snapshot (pure-Python)."""
    import shutil
    import sys as _sys

    if len(_sys.argv) < 2:
        print("usage: python -m moon restore <snapshot-dir>")
        return 2
    snap = Path(_sys.argv[-1])
    if not snap.is_dir():
        print(f"snapshot not found: {snap}")
        return 2
    restored: list[str] = []
    for item in ("data", "connections", ".env"):
        src = snap / item
        if not src.exists():
            continue
        try:
            if src.is_dir():
                shutil.copytree(src, Path(item), dirs_exist_ok=True)
            else:
                shutil.copy2(src, Path(item))
            restored.append(item)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not restore {item}: {exc}")
    print(f"RESTORE COMPLETE -> restored: {', '.join(restored) or 'nothing'}")
    return 0


def _cmd_setup() -> int:
    """First-run setup wizard (interactive config -> .env -> installer).

    Delegates to script.py, the single consolidated installer that replaced
    install_moon.py / setup_wizard.py / install.sh (commit 7fd368a).
    """
    import importlib.util

    installer = Path("script.py")
    if not installer.is_file():
        print("script.py (installer) not found in project root")
        return 2
    spec = importlib.util.spec_from_file_location(
        "moon_installer", str(installer.resolve()))
    if spec is None or spec.loader is None:
        print("script.py could not be loaded")
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for entry in ("main", "run"):
        fn = getattr(mod, entry, None)
        if callable(fn):
            rc = fn()
            return rc if isinstance(rc, int) else 0
    # No main()/run(): execute the module body (top-level installer script).
    return 0


def _cmd_uninstall() -> int:
    """Native MOON uninstaller (safe by default -- removes auto-start wiring)."""
    import importlib.util
    import os

    spec = importlib.util.spec_from_file_location(
        "uninstall_moon", str(Path("uninstall_moon.py").resolve()))
    if spec is None or spec.loader is None:
        print("uninstall_moon.py not found in project root")
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main() or 0


def _cmd_install() -> int:
    """Run the consolidated Python installer (script.py).

    script.py replaced install.sh / install_moon.py / install_moon_full.py /
    setup_wizard.py / scripts/install_ollama.py in commit 7fd368a.
    """
    import importlib.util

    installer = Path("script.py")
    if not installer.is_file():
        print("script.py (installer) not found in project root")
        return 2
    spec = importlib.util.spec_from_file_location(
        "moon_installer", str(installer.resolve()))
    if spec is None or spec.loader is None:
        print("script.py could not be loaded")
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for entry in ("main", "run"):
        fn = getattr(mod, entry, None)
        if callable(fn):
            rc = fn()
            return rc if isinstance(rc, int) else 0
    return 0


def _cmd_update() -> int:
    """Safe update: pull latest source + update deps. Never destructive git."""
    import subprocess as _sp
    print("==> MOON update (safe: git pull + pip install -e .)")
    try:
        r = _sp.run(["git", "pull", "--ff-only"], check=False)
        if r.returncode != 0:
            print("WARN: git pull failed/non-fast-forward -- leaving local history intact.")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: git pull skipped: {exc}")
    try:
        _sp.run([sys.executable, "-m", "pip", "install", "-e", ".", "--upgrade"], check=False)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: dependency update skipped: {exc}")
    print("==> running doctor")
    return _cmd_doctor()


def main() -> None:
    ap = argparse.ArgumentParser(prog="moon", description="Standalone AI Agent")
    sub = ap.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run", help="Run a single task via LLM, or launch moonscope TUI if no task given")
    run_p.add_argument("task", nargs="?", default=None, help="Task to run (omit to launch moonscope TUI)")
    run_p.add_argument("--task", dest="task_flag", default=None, help="Task to run (omit to launch the terminal)")
    run_p.add_argument("--agent", default=None, help="Agent name to run the task with")
    sub.add_parser("models", help="Pre-pull all per-agent preferred models so agents are ready")
    # Single terminal interface: Hermes-style Textual TUI (moonscope).
    #   moon / moon terminal / moon run  ->  Hermes-style TUI (moonscope)
    #   moon cli  ->  readline REPL (fallback, Hermes-feature-rich)
    #   moon terminal-moon  ->  standalone MOON Terminal (terminal_moon/ sub-project)
    sub.add_parser("telegram", help="Launch MOON's Telegram bot listener (polling)")
    sub.add_parser("doctor", help="Health check: Python/deps/config/DB/agents/tools/model/git")
    sub.add_parser("status", help="Check the running MOON backend health endpoint")
    sub.add_parser("backup", help="Snapshot runtime data into backups/ (cross-platform)")
    sub.add_parser("restore", help="Restore a backups/moon_<timestamp> snapshot")
    sub.add_parser("install", help="Run the Python bootstrap installer (venv + deps + models)")
    sub.add_parser("setup", help="First-run setup wizard (configure .env, then install)")
    sub.add_parser("uninstall", help="Remove MOON auto-start wiring (launcher, services, desktop)")
    sub.add_parser("update", help="Safe update: git pull --ff-only + pip install -e . --upgrade")
    sub.add_parser("version", help="Print MOON version")

    args, remaining = ap.parse_known_args()
    _ensure_default_peer()
    if args.cmd == "run":
        task = args.task or args.task_flag
        if task:
            asyncio.run(_run(task, args.agent))
        else:
            print("No task given. Use: moon run \"<task>\" or moon <subcommand>")
            return
    elif args.cmd == "models":
        asyncio.run(_prefetch_models())
    elif args.cmd == "terminal":
        print("Terminal UI removed. Use: moon run \"<task>\" or moon api", file=sys.stderr)
        return 1
    elif args.cmd == "cli":
        print("CLI removed. Use: moon run \"<task>\" or moon api", file=sys.stderr)
        return 1
    elif args.cmd == "status":
        raise SystemExit(_cmd_status())
    elif args.cmd == "backup":
        raise SystemExit(_cmd_backup())
    elif args.cmd == "restore":
        raise SystemExit(_cmd_restore())
    elif args.cmd == "install":
        raise SystemExit(_cmd_install())
    elif args.cmd == "setup":
        raise SystemExit(_cmd_setup())
    elif args.cmd == "uninstall":
        raise SystemExit(_cmd_uninstall())
    elif args.cmd == "update":
        raise SystemExit(_cmd_update())
    elif args.cmd == "terminal-moon":
        print("[terminal-moon] terminal_moon/ sub-project has been removed. Use 'moon terminal' instead.", file=sys.stderr)
        raise SystemExit(1)
    elif args.cmd == "telegram":
        # Launch MOON's Telegram bot listener (polling mode).
        # Token is read from TELEGRAM_BOT_TOKEN env var (set via .env or
        # passed explicitly). Runs in-process as a foreground blocking service.
        from app.services.telegram_bot import main as _tg_main
        raise SystemExit(_tg_main())
    elif args.cmd == "version":
        _cmd_version()
    else:
        # No subcommand -> show help
        ap.print_help()


if __name__ == "__main__":
    main()
