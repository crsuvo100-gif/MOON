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
    import json
    import os
    import shutil
    import subprocess
    import sys
    import threading
    import time
    import urllib.request

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
        args = [chrome, "--no-sandbox", "--disable-gpu",
                f"--app={URL}", "--window-size=1366,768", "--start-maximized",
                "--disable-infobars", "--no-first-run", "--no-default-browser-check"]
        if wayland:
            args += ["--ozone-platform=wayland", f"--wayland-display={wayland}"]
        if disp:
            args += [f"--display={disp}"]
        try:
            subprocess.Popen(args, env={**os.environ, "PYTHONPATH": ""},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    threading.Thread(target=_auto_open_ui, daemon=True).start()

    print(f"🌙 MOON Terminal starting at http://0.0.0.0:{PORT}  (LAN: http://<this-host-ip>:{PORT})")
    subprocess.run([
        sys.executable, "-m", "uvicorn", "app.terminal_interface:app",
        "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "info",
    ], env=env)


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
