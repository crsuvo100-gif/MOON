"""
MOON Terminal installer — bootstrap: venv, deps, default model, print usage.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def install() -> None:
    root = Path(__file__).resolve().parent
    print(f"MOON Terminal installer — root: {root}")

    # venv
    venv = root / ".venv"
    if not venv.exists():
        print("Creating .venv...")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    else:
        print(".venv exists — skipping create.")

    # pip upgrade
    pip = venv / "bin" / "pip"
    if os.name == "nt":
        pip = venv / "Scripts" / "pip.exe"
    print("Upgrading pip...")
    subprocess.run([str(pip), "install", "--upgrade", "pip"], check=True)

    # deps
    print("Installing dependencies...")
    subprocess.run([str(pip), "install", "-e", str(root)], check=True)

    # default model
    model = os.environ.get("MOON_MODEL", "qwen2.5:1.5b")
    print(f"Default model: {model} (pull with 'moon models' or 'ollama pull {model}')")

    # print usage
    print("""
╔══════════════════════════════════════════════════════╗
║  MOON TERMINAL — INSTALLED                          ║
╠══════════════════════════════════════════════════════╣
║  3 entry points:                                    ║
║                                                     ║
║  1. Browser:   http://127.0.0.1:8777               ║
║  2. Terminal:  ./venv/bin/python main.py terminal   ║
║  3. CLI:       ./venv/bin/python main.py cli        ║
║                                                     ║
║  Unlock phrase: "MOON love you 3000"                ║
║                                                     ║
║  Start server:                                      ║
║    ./venv/bin/uvicorn app.terminal_interface:app    ║
║    --port 8777 --host 127.0.0.1                    ║
╚══════════════════════════════════════════════════════╝
""")


def uninstall() -> None:
    root = Path(__file__).resolve().parent
    print(f"Uninstalling MOON Terminal from {root}")
    print("Remove .venv/ and any systemd/user service entries manually.")
    print("No auto-start wiring to clean up in this version.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()
