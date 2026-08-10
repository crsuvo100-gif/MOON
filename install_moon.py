"""install_moon.py -- bootstrap MOON on a fresh machine.

Creates an isolated environment, fetches runtime dependencies, and (best-effort)
the voice stack. Heavy framework requirements are pulled via requirements.txt.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_PKG = "pip"


def _run(cmd, env=None):
    print("+", " ".join(cmd))
    # Drop PYTHONPATH so pip/venv never target a foreign venv (e.g. Hermes agent).
    import os
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    if env:
        e.update(env)
    subprocess.run(cmd, check=False, env=e)


def smoke_import():
    py = ROOT / ".venv" / "bin" / "python"
    try:
        subprocess.run(
            [str(py), "-c",
             "import app.voice, app.brain.orchestrator, app.brain.agent_brain, app.brain.memory_manager"],
            cwd=str(ROOT), check=True, env={**__import__("os").environ, "PYTHONPATH": ""},
        )
        return True
    except Exception:
        return False


def install_voice_stack():
    """Best-effort install of MOON's FEMALE voice + optional dictation."""
    # System TTS + SoX (already present on this host; install if missing).
    _run(["bash", "-c", "command -v espeak >/dev/null 2>&1 || (apt-get update && apt-get install -y espeak sox)"])
    # Optional offline dictation (vosk). Pulled on demand; not required to run.
    py = ROOT / ".venv" / "bin" / "python"
    _run([str(py), "-m", "pip", "install", "vosk", "pyaudio"])
    print("Voice stack: espeak+sox required (installed if missing); vosk+pyaudio optional for mic dictation.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-env", action="store_true")
    ap.add_argument("--no-voice", action="store_true", help="skip voice stack install")
    args = ap.parse_args()
    if not args.no_env:
        _run([sys.executable, "-m", "venv", ".venv"])  # _run already drops PYTHONPATH
        py = ROOT / ".venv" / "bin" / "python"
        _run([str(py), "-m", _PKG, "install", "--upgrade", _PKG])
        _run([str(py), "-m", _PKG, "install", "-r", "requirements.txt"])
    if not args.no_voice:
        try:
            install_voice_stack()
        except Exception as exc:  # noqa: BLE001
            print("Voice stack install skipped:", exc)
    print("Setup complete. Launch the UI with: make serve  (http://127.0.0.1:8777)")
    print("Female voice companion: make voice")
    print("Smoke import:", "OK" if smoke_import() else "FAILED")


if __name__ == "__main__":
    main()
