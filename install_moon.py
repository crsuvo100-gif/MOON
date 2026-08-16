"""install_moon.py -- bootstrap MOON on a fresh machine.

Creates an isolated environment, fetches runtime dependencies, and (best-effort)
the voice stack. Heavy framework requirements are pulled via requirements.txt.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_PKG = "pip"

# Models Moon needs so every agent is ready out of the box (CPU-friendly sizes).
# Pulled best-effort; larger models can be added later on a capable host.
REQUIRED_MODELS = [
    "qwen3:0.6b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "qwen2.5-coder:1.5b",
    "deepseek-r1:1.5b",
]


def install_models():
    """Best-effort: ensure Ollama is up and pull the models Moon's agents use."""
    import shutil

    exe = shutil.which("ollama")
    if exe is None:
        print("ollama not found on PATH -- skipping model pull. Install Ollama "
              "(https://ollama.com) then run: ollama pull qwen3:0.6b")
        return
    # Start the service if needed.
    import urllib.request

    def _up():
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3):
                return True
        except Exception:
            return False

    if not _up():
        print("Starting ollama serve (background)...")
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(20):
            if _up():
                break
            time.sleep(1)
    for m in REQUIRED_MODELS:
        print(f"Pulling model: {m}")
        _run([exe, "pull", m])


def ensure_env_file():
    """Create .env from .env.example if absent (secrets never committed)."""
    import shutil

    env = ROOT / ".env"
    example = ROOT / ".env.example"
    if env.exists():
        print(".env present -- keeping existing local config")
        return
    if example.exists():
        shutil.copyfile(example, env)
        print(".env created from .env.example (fill API keys to enable cloud fallbacks)")
    else:
        print("No .env.example -- relying on built-in defaults")


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
    ap.add_argument("--no-models", action="store_true", help="skip Ollama model pull")
    args = ap.parse_args()
    if not args.no_env:
        _run([sys.executable, "-m", "venv", ".venv"])  # _run already drops PYTHONPATH
        py = ROOT / ".venv" / "bin" / "python"
        _run([str(py), "-m", _PKG, "install", "--upgrade", _PKG])
        _run([str(py), "-m", _PKG, "install", "-r", "requirements.txt"])
        ensure_env_file()
        if not args.no_models:
            try:
                install_models()
            except Exception as exc:  # noqa: BLE001
                print("Model pull skipped:", exc)
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
