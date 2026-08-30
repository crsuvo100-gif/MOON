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
    o = Orchestrator(get_settings())
    await o.setup()
    from app.models.task import Task
    res = await o.run_task(Task.create(task, agent_name=agent))
    print(res.result)
    await o.teardown()


async def _run_terminal() -> None:
    import json
    import os
    import shutil
    import subprocess
    import sys
    import tempfile
    import threading
    import time
    import urllib.request

    # Phase 26 startup readiness: make sure the local model backend is up before
    # the API starts, so the Orchestrator has a model to bind to. Best-effort and
    # non-destructive -- safe when Ollama is already running or unavailable.
    _ensure_ollama()

    # The project venv is 3.13, but a global PYTHONPATH may point at an
    # incompatible (3.11) site-packages and shadow pydantic_core at import time.
    # Drop PYTHONPATH for the child so MOON's own dependencies win. (Non-destructive:
    # only affects this subprocess, never mutates the parent environment.)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    # --- Load persisted UI settings (host/port/display/browser/aspect/avatar) ---
    settings = {}
    try:
        sp = os.path.join(os.path.dirname(__file__), "..", "web", "moon_settings.json")
        if os.path.exists(sp):
            settings = json.load(open(sp))
    except Exception:
        settings = {}
    PORT = int(settings.get("port", 8777))
    HOST = settings.get("host", "127.0.0.1")
    URL = f"http://{HOST}:{PORT}/"

    def _which(name):
        return shutil.which(name)

    def _detect_browser():
        # 1) explicit override from settings
        b = settings.get("browser", "")
        if b and os.path.exists(b):
            return b
        # 2) common names, in preference order
        for cand in ("google-chrome", "google-chrome-stable", "chromium",
                     "chromium-browser", "chrome", "microsoft-edge",
                     "microsoft-edge-stable"):
            p = _which(cand)
            if p:
                return p
        # 3) well-known absolute paths
        for p in ("/opt/google/chrome/chrome", "/usr/bin/google-chrome",
                  "/usr/bin/chromium", "/snap/bin/chromium"):
            if os.path.exists(p):
                return p
        return None

    def _detect_display():
        d = settings.get("display", "")
        if d:
            return d, None
        if os.environ.get("WAYLAND_DISPLAY"):
            return None, os.environ["WAYLAND_DISPLAY"]
        if os.environ.get("DISPLAY"):
            return os.environ["DISPLAY"], None
        return None, None

    # --- Auto-open the MOON HUD on MOON's own boot (any display) ---
    # Detects X11 / Wayland / headless and picks a suitable browser; on
    # headless/SSH sessions with no display it simply skips (never crashes).
    def _auto_open_ui():
        if not settings.get("autostart", True):
            return
        # Idempotency guard: only ever open ONE MOON HUD window per host.
        # A lockfile records the last-open PID/window so restarts/relaunches
        # never stack duplicate Chrome windows.
        lock = os.path.join(tempfile.gettempdir(), "moon_hud_open.lock")
        try:
            if os.path.exists(lock):
                # a window was already opened recently for this host -> skip
                try:
                    with open(lock) as fh:
                        data = fh.read().strip()
                    # if the recorded pid is still alive, assume its window is up
                    if data and os.path.exists(f"/proc/{data}"):
                        return
                except Exception:
                    pass
        except Exception:
            pass
        for _ in range(30):                      # wait for backend (max ~30s)
            try:
                with urllib.request.urlopen(URL, timeout=2):
                    break
            except Exception:
                time.sleep(1)
        else:
            return
        disp, wayland = _detect_display()
        if not (disp or wayland):
            return                          # no graphical display -> skip quietly
        chrome = _detect_browser()
        if not chrome:
            return
        args = [chrome, "--disable-setuid-sandbox", "--disable-gpu",
                f"--app={URL}", "--window-size=1920,1080", "--start-maximized",
                "--disable-infobars", "--no-first-run", "--no-default-browser-check"]
        if wayland:
            args += ["--ozone-platform=wayland", f"--wayland-display={wayland}"]
        if disp:
            args += [f"--display={disp}"]
        try:
            proc = subprocess.Popen(args, env={**os.environ, "PYTHONPATH": ""},
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # record this opener's pid so a second invocation won't duplicate
            try:
                with open(lock, "w") as fh:
                    fh.write(str(proc.pid))
            except Exception:
                pass
        except Exception:
            pass

    # NOTE: the visible HUD window is NOT auto-opened on boot anymore.
    # autostart=false in moon_settings.json + moon-hud.service disabled means:
    # the backend (systemd moon-terminal.service) runs, but NO browser window
    # appears until the operator explicitly runs `moon terminal` (or opens
    # http://127.0.0.1:8777/ manually). The _auto_open_ui() definition below
    # is retained for manual `python main.py start` use outside systemd.
    if settings.get("autostart", False):
        _auto_open_ui()

    # --- Guard against double-binding :PORT (root cause of the HUD "blink") ---
    # If another MOON backend already owns the port (e.g. moon.service is up),
    # launching a 2nd uvicorn fails to bind and systemd restarts us in a tight
    # crash-loop. That makes the HUD WebSocket drop/reconnect every few seconds
    # and the whole terminal appears to blink. So: if the port is taken, just
    # attach the HUD to the existing backend and exit cleanly (no loop).
    def _port_busy(port):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
        finally:
            s.close()

    if _port_busy(PORT):
        print(f"\U0001F319 MOON backend already listening on :{PORT} "
              f"-- attaching HUD only (not spawning a 2nd backend).")
        # The backend is already up: open (or focus) the visible HUD window
        # instead of just exiting. open_hud() is idempotent (one window, GPU
        # accelerated) and never touches :8777, so it's safe to call here.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from scripts.open_hud import open_hud
            pid = open_hud()
            if pid:
                print(f"\U0001F319 HUD window opened (chrome pid {pid}). "
                      f"Open http://{HOST}:{PORT}/ if no window appears.")
            else:
                print(f"\U0001F319 No display/browser detected -- open "
                      f"http://{HOST}:{PORT}/ manually in your browser.")
        except Exception as e:  # noqa: BLE001
            print(f"\U0001F319 Could not auto-open HUD ({e}); "
                  f"open http://{HOST}:{PORT}/ manually.")
        return 0

    print(f"🌙 MOON Terminal starting at http://0.0.0.0:{PORT}  (LAN: http://<this-host-ip>:{PORT})")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "app.terminal_interface:app",
        "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "info",
    ], env=env)
    return 0


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


def _cmd_monitor() -> int:
    """Run the health monitor + self-heal script."""
    import subprocess

    project = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(project, "scripts", "moon_monitor.py")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    py = os.path.join(project, ".venv", "bin", "python")
    if not os.path.exists(py):
        py = sys.executable
    r = subprocess.run([py, script], cwd=project, env=env)
    return r.returncode


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
        import app.terminal_interface  # noqa: F401
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
    from app.runtime.backup import backup
    d = backup()
    print(f"BACKUP COMPLETE -> {d}")
    return 0


def _cmd_restore() -> int:
    import sys as _sys
    if len(_sys.argv) < 2:
        print("usage: python -m moon restore <snapshot-dir>")
        return 2
    from app.runtime.backup import restore
    snap = _sys.argv[-1]
    restored = restore(Path(snap))
    print(f"RESTORE COMPLETE -> restored: {', '.join(restored) or 'nothing'}")
    return 0


def _cmd_setup() -> int:
    """First-run setup wizard (interactive config -> .env -> installer).

    Native to MOON (mirrors the 'setup' step of agent installers) and shares
    no code with any other project. Delegates to setup_wizard.py.
    """
    import importlib.util
    import os

    spec = importlib.util.spec_from_file_location(
        "setup_wizard", str(Path("setup_wizard.py").resolve()))
    if spec is None or spec.loader is None:
        print("setup_wizard.py not found in project root")
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main() or 0


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
    """Delegate to the existing Python bootstrap installer (install_moon.py)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("install_moon", str(Path("install_moon.py").resolve()))
    if spec is None or spec.loader is None:
        print("install_moon.py not found in project root")
        return 2
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()
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
    sub.add_parser("start", help="Launch MOON's terminal interface (animated avatar UI)")
    run_p = sub.add_parser("run", help="Run a single task")
    run_p.add_argument("task", nargs="?", default="Say hello.")
    run_p.add_argument("--agent", default="auto")
    sub.add_parser("models", help="Pre-pull all per-agent preferred models so agents are ready")
    sub.add_parser("terminal", help="Launch MOON's own terminal interface (animated avatar UI)")
    sub.add_parser("tui", help="Launch MOON's curses text-mode terminal UI (headless/SSH)")
    sub.add_parser("shell", help="Launch MOON's TTS/textual shell terminal (voice + shell + CLI)")
    # NEW Python-first operational commands (additive)
    sub.add_parser("doctor", help="Health check: Python/deps/config/DB/agents/tools/model/git")
    sub.add_parser("status", help="Check the running MOON backend health endpoint")
    sub.add_parser("backup", help="Snapshot runtime data into backups/ (cross-platform)")
    sub.add_parser("restore", help="Restore a backups/moon_<timestamp> snapshot")
    sub.add_parser("install", help="Run the Python bootstrap installer (venv + deps + models)")
    sub.add_parser("setup", help="First-run setup wizard (configure .env, then install)")
    sub.add_parser("uninstall", help="Remove MOON auto-start wiring (launcher, services, desktop)")
    sub.add_parser("update", help="Safe update: git pull --ff-only + pip install -e . --upgrade")
    sub.add_parser("version", help="Print MOON version")
    sub.add_parser("monitor", help="Run health monitor + self-heal (backend, models, git sync)")
    args = ap.parse_args()
    _ensure_default_peer()
    if args.cmd == "monitor":
        raise SystemExit(_cmd_monitor())
    elif args.cmd == "start":
        _run_terminal()
    elif args.cmd == "run":
        asyncio.run(_run(args.task, args.agent))
    elif args.cmd == "models":
        asyncio.run(_prefetch_models())
    elif args.cmd == "tui":
        from app.tui import main as tui_main
        raise SystemExit(tui_main())
    elif args.cmd == "shell":
        from app.tui import main as tui_main
        raise SystemExit(tui_main())
    elif args.cmd == "terminal":
        _run_terminal()
    elif args.cmd == "doctor":
        raise SystemExit(_cmd_doctor())
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
    elif args.cmd == "version":
        _cmd_version()
    else:
        # No subcommand (or unknown) -> Moon Terminal is the DEFAULT interface.
        _run_terminal()


if __name__ == "__main__":
    main()
