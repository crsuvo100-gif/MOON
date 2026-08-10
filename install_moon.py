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
    # Drop PYTHONPATH AND VIRTUAL_ENV so pip/venv never target a foreign venv
    # (e.g. the Hermes agent environment on the dev host). We deliberately use
    # the venv we just created under .venv/ via sys.executable below.
    import os
    e = dict(os.environ)
    e.pop("PYTHONPATH", None)
    e.pop("VIRTUAL_ENV", None)
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
    """Best-effort install of MOON's FEMALE voice + optional dictation.

    Tries the right system package manager for the host OS (Debian/Ubuntu,
    Fedora/RHEL, Arch, macOS/brew) and falls back gracefully if none is
    available or the user lacks permission. The Python side (vosk/pyaudio)
    is optional for mic dictation and never blocks the core install.
    """
    import shutil

    pkg_cmd = None
    if shutil.which("apt-get"):
        pkg_cmd = "apt-get update && apt-get install -y espeak-ng sox"
    elif shutil.which("dnf"):
        pkg_cmd = "dnf install -y espeak-ng sox"
    elif shutil.which("yum"):
        pkg_cmd = "yum install -y espeak-ng sox"
    elif shutil.which("pacman"):
        pkg_cmd = "pacman -S --noconfirm espeak-ng sox"
    elif shutil.which("brew"):
        pkg_cmd = "brew install espeak sox"
    if pkg_cmd:
        _run(["bash", "-c", pkg_cmd])
    else:
        print("No supported system package manager found; skipping espeak-ng/sox "
              "system install. Install them manually for TTS: https://github.com/espeak-ng/espeak-ng")
    # Optional offline dictation (vosk). Pulled on demand; not required to run.
    py = ROOT / ".venv" / "bin" / "python"
    _run([str(py), "-m", "pip", "install", "vosk", "pyaudio"])
    print("Voice stack: espeak-ng+sox for TTS (system, best-effort); "
          "vosk+pyaudio optional for mic dictation.")


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
