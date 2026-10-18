#!/usr/bin/env python3
"""
install_ollama.py -- Install / health-check the OLLAMA backend service.

Designed to be best-effort and idempotent: every step reports status and
returns 0 unless a genuine, unrecoverable failure occurs.

Notes on this environment:
  * OLLAMA is installed via the host package (`/usr/local/bin/ollama`), owned by
    the `ollama` system user / systemd unit.  MOON's OLLAMA integration shell-outs
    to the `ollama` CLI (it does *not* call the HTTP API), so the model state the
    CLI sees (`ollama list`) is the authoritative one for the MOON runtime.
  * `sudo` is password-protected, so any "use sudo" attempt is best-effort at
    most and is never required for MOON to run.

Usage:
    make install          # runs: python3 scripts/install_ollama.py
    python3 scripts/install_ollama.py   # no arguments
"""

import os
import shutil
import subprocess
import sys

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
# Default model shipped by MOON; override via .env OLLAMA_MODEL_DEFAULT or env.
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL_DEFAULT", "qwen2.5:1.5b")


def _run(cmd, check=False):
    """Run a command, capture stdout/stderr, return CompletedProcess."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=300
    )


def _curl_ok(host):
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://{host}/api/version"],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() == "200"
    except Exception:
        return False


def ensure_binary():
    """Return True if the `ollama` CLI is on PATH."""
    path = shutil.which("ollama")
    if path:
        print(f"[OK] ollama CLI on PATH: {path}")
        return True
    print(f"[WARN] ollama CLI NOT on PATH. Install: apt install ollama (Debian) "
          f"or https://ollama.com/download")
    return False


def ensure_running():
    """Ensure the ollama system service is active. Best effort; sudo may be needed."""
    r = _run(["systemctl", "is-active", "ollama"])
    if r.stdout.strip() == "active":
        print("[OK] ollama systemd service active")
        return True
    print(f"[INFO] ollama service not active (systemctl: {r.stdout.strip()!r}); "
          f"attempting start (needs sudo)...")
    s = _run(["sudo", "systemctl", "start", "ollama"])
    if s.returncode == 0:
        print("[OK] ollama service started with sudo")
        return True
    print("[WARN] Could not auto-start ollama (password-less sudo not available). "
          "Start it manually: sudo systemctl start ollama")
    return False


def ensure_on_path():
    """Ensure the ollama binary is on PATH (idempotent symlink to /usr/local/bin)."""
    if shutil.which("ollama"):
        return True
    target = "/usr/local/bin/ollama"
    if not os.path.exists(target):
        print(f"[WARN] {target} missing; cannot link into PATH")
        return False
    link = "/usr/local/bin/ollama"
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(target, link)
        print(f"[OK] symlink {link} -> {target}")
    except OSError as e:
        print(f"[WARN] could not symlink ollama into /usr/local/bin: {e}")
        return False
    return True


def ensure_model(model=DEFAULT_MODEL):
    """Pull the default model best-effort; report if already present."""
    r = _run(["ollama", "list"])
    if model in r.stdout:
        print(f"[OK] model already present: {model}")
        return True
    print(f"[INFO] model '{model}' not present; pulling (best effort)...")
    p = _run(["ollama", "pull", model], check=True)
    if p.returncode == 0:
        print(f"[OK] model pulled: {model}")
        return True
    print(f"[WARN] ollama pull '{model}' failed: {p.stderr or p.stdout}")
    return False


def main():
    print("== MOON OLLAMA BACKEND SERVICE INSTALL ==")
    binary_ok = ensure_binary()
    running_ok = ensure_running()
    path_ok = ensure_on_path()
    model_ok = ensure_model(os.environ.get("OLLAMA_MODEL_DEFAULT", DEFAULT_MODEL))
    print("== END ==")
    # Exit 0: this is best-effort infra; a warning above is not a hard failure.
    # Only hard-fail when the CLI itself is missing.
    sys.exit(0 if binary_ok else 1)


if __name__ == "__main__":
    main()
