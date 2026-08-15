#!/usr/bin/env python3
"""
moon_launcher.py -- run MOON anywhere with one cross-platform command.

Pure-Python, OS-agnostic launcher for MOON. It:
  1. Ensures her model backend (Ollama) is reachable on OLLAMA_HOST, starting
     the service when possible (systemd on Linux with root/sudo; background
     ``ollama serve`` on macOS/Windows).
  2. Boots MOON's terminal interface (default), dashboard, or runs a one-shot
     task via main.py.

Usage:
    python3 scripts/moon_launcher.py                 # terminal UI on 127.0.0.1:8777
    python3 scripts/moon_launcher.py dashboard       # Flask+SocketIO dashboard :5000
    python3 scripts/moon_launcher.py run "hi Moon"   # one-shot task
    OLLAMA_HOST=127.0.0.1:11434 python3 scripts/moon_launcher.py

No build step required beyond a ready Python venv (see DEPLOY.md).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")


def log(msg: str) -> None:
    print(f"🌙 {msg}")


def ollama_up() -> bool:
    import urllib.request
    url = f"http://{OLLAMA_HOST}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def start_ollama() -> None:
    """Best-effort start of Ollama depending on platform."""
    if platform.system() == "Linux" and shutil.which("systemctl") is not None:
        cmd = ["systemctl", "start", "ollama"]
        if os.geteuid() != 0:
            cmd = ["sudo", *cmd]
        subprocess.run(cmd, check=False)
    else:
        # macOS / Windows / non-systemd: background serve
        exe = shutil.which("ollama")
        if exe:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)


def ensure_ollama() -> None:
    if ollama_up():
        log(f"Ollama backend already reachable at {OLLAMA_HOST}")
        return
    log(f"Ollama not reachable at {OLLAMA_HOST} -- attempting to start")
    start_ollama()
    for _ in range(10):
        if ollama_up():
            break
        time.sleep(1)
    if ollama_up():
        log("Ollama backend is up")
    else:
        log("⚠️  Ollama still down -- start it manually (e.g. 'ollama serve')")


def main(argv: list[str]) -> int:
    os.chdir(ROOT)
    mode = argv[1] if len(argv) > 1 else "terminal"

    ensure_ollama()

    # Decontaminate PYTHONPATH so MOON's venv is used (see app/config/env_guard.py)
    os.environ.pop("PYTHONPATH", None)
    venv_python = os.path.join(ROOT, ".venv", "bin", "python")
    if platform.system() == "Windows":
        venv_python = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        log(f"No .venv found at {venv_python}")
        log("Create one: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")
        return 1

    if mode in ("terminal", "serve", "start"):
        log("MOON Terminal starting at http://127.0.0.1:8777")
        return subprocess.call([venv_python, "main.py", "start"])
    if mode == "dashboard":
        log("MOON Dashboard starting at http://127.0.0.1:5000")
        return subprocess.call([venv_python, "main.py", "dashboard"])
    if mode == "run":
        task = " ".join(argv[2:]) if len(argv) > 2 else "Say hello."
        log(f"MOON running: {task}")
        return subprocess.call([venv_python, "main.py", "run", task])
    log("Usage: moon_launcher.py [terminal|dashboard|run <task>]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
