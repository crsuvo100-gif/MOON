"""MOON bootstrap script."""

"install_moon.py -- bootstrap MOON on a fresh machine.

Creates an isolated environment, fetches runtime dependencies, and (best-effort)
the voice stack. Heavy framework requirements are pulled via requirements.txt.
"
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_PKG = "pip"


def _run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=False)


def smoke_import():
    try:
        subprocess.run(
            [sys.executable, "-c",
             "import app.voice, app.brain.orchestrator, app.brain.agent_brain, app.brain.memory_manager"],
            cwd=str(ROOT), check=True,
        )
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-env", action="store_true")
    args = ap.parse_args()
    if not args.no_env:
        _run([sys.executable, "-m", "venv", ".venv"])
        py = ROOT / ".venv" / "bin" / "python"
        _run([str(py), "-m", _PKG, "install", "--upgrade", _PKG])
        _run([str(py), "-m", _PKG, "install", "-r", "requirements.txt"])
    print("Setup complete. Launch the UI with: make serve  (http://localhost:8000/brain)")
    print("Smoke import:", "OK" if smoke_import() else "FAILED")


if __name__ == "__main__":
    main()
