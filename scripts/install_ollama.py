#!/usr/bin/env python3
"""
install_ollama.py -- make MOON's model backend (Ollama) run on ANY OS.

Pure-Python, cross-platform installer for the Ollama service that powers MOON's
local models. No shell scripts. Detects the platform and uses the right
mechanism:

  * Linux   -> systemd unit (creates the unprivileged ``ollama`` user, enables
               CUDA automatically when an NVIDIA GPU is present, sets
               OLLAMA_DEBUG=1 and a stable OLLAMA_HOST).
  * macOS   -> Homebrew service (``brew services``), or direct ``ollama serve``
               if Homebrew is absent.
  * Windows -> winget install + start ``ollama serve`` in the background.

Idempotent and safe to re-run. Privileged steps are performed via ``sudo`` on
POSIX when not already root; on Windows they run in an elevated context if the
caller has admin. Designed to be invoked by ``make install`` or directly:

    python3 scripts/install_ollama.py

Environment overrides:
    MOON_OLLAMA_USER   service account name   (default: ollama)
    OLLAMA_HOST        listen address         (default: 127.0.0.1:11434)
    OLLAMA_INSTALL_DIR home for the user      (default: /usr/share/ollama)
    SKIP_OLLAMA_USER   set to 1 to skip user/group management
    DRY_RUN            set to 1 to print actions without executing them
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

OLLAMA_USER = os.environ.get("MOON_OLLAMA_USER", "ollama")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
INSTALL_DIR = os.environ.get("OLLAMA_INSTALL_DIR", "/usr/share/ollama")
UNIT_PATH = "/etc/systemd/system/ollama.service"
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"


def log(msg: str) -> None:
    print(f"[install_ollama] {msg}")


def run(cmd, **kw):
    """Run a command; honor DRY_RUN for non-mutating visibility."""
    printable = " ".join(str(c) for c in cmd)
    if DRY_RUN:
        log(f"(dry-run) would run: {printable}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    log(f"run: {printable}")
    return subprocess.run(cmd, **kw)


def sudo_cmd(cmd):
    """Prefix with sudo unless we are already root (POSIX only)."""
    if os.name != "posix" or os.geteuid() == 0:
        return cmd
    return ["sudo", *cmd]


def has_nvidia() -> bool:
    """Detect an NVIDIA GPU via nvidia-smi."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, timeout=10)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def ensure_ollama_binary() -> None:
    if shutil.which("ollama") is not None:
        log("ollama binary present")
        return
    log("ollama binary NOT found on PATH.")
    sysname = platform.system()
    if sysname == "Darwin":
        log("Install with: brew install ollama")
    elif sysname == "Windows":
        log("Install with: winget install Ollama.Ollama")
    else:
        log("Install with: curl -fsSL https://ollama.com/install.sh | sh")
    sys.exit(1)


def linux_install() -> None:
    log("platform=Linux (systemd)")
    ensure_ollama_binary()

    # --- service user (idempotent) ---
    if os.environ.get("SKIP_OLLAMA_USER", "") != "1":
        try:
            subprocess.run(["id", OLLAMA_USER], check=True, capture_output=True)
            log(f"user '{OLLAMA_USER}' already exists -- skipping")
        except subprocess.CalledProcessError:
            log(f"creating system user '{OLLAMA_USER}'")
            run(sudo_cmd([
                "useradd", "-r", "-s", "/bin/false", "-U", "-m",
                "-d", INSTALL_DIR, OLLAMA_USER,
            ]), check=True)
        # add invoking user to the ollama group for socket access
        invoker = os.environ.get("SUDO_USER") or os.environ.get("USER")
        if invoker and invoker != OLLAMA_USER:
            groups = subprocess.run(
                ["id", "-nG", invoker], capture_output=True, text=True
            ).stdout.split()
            if OLLAMA_USER not in groups:
                log(f"adding '{invoker}' to group '{OLLAMA_USER}'")
                run(sudo_cmd(["usermod", "-a", "-G", OLLAMA_USER, invoker]), check=True)
            else:
                log(f"'{invoker}' already in group '{OLLAMA_USER}'")

    # --- GPU detection ---
    gpu_lines = ""
    if has_nvidia():
        log("NVIDIA GPU detected -> enabling CUDA")
        gpu_lines = (
            'Environment="CUDA_VISIBLE_DEVICES=all"\n'
            'Environment="OLLAMA_CUDA=1"\n'
        )
    else:
        log("no NVIDIA GPU -> CPU mode")

    # --- write unit ---
    unit = f"""[Unit]
Description=Ollama Service (MOON model backend)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ollama serve
User={OLLAMA_USER}
Group={OLLAMA_USER}
Restart=always
RestartSec=3
Environment="OLLAMA_HOST={OLLAMA_HOST}"
Environment="OLLAMA_DEBUG=1"
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin"
{gpu_lines}
[Install]
WantedBy=multi-user.target
"""
    log(f"writing {UNIT_PATH}")
    if DRY_RUN:
        log("(dry-run) unit content:\n" + unit)
    else:
        run(sudo_cmd(["tee", UNIT_PATH]), input=unit.encode(), check=True,
            stdout=subprocess.DEVNULL)

    # --- reload / enable / restart ---
    run(sudo_cmd(["systemctl", "daemon-reload"]), check=True)
    run(sudo_cmd(["systemctl", "enable", "ollama"]), check=True)
    run(sudo_cmd(["systemctl", "restart", "ollama"]), check=True)
    import time
    time.sleep(2)
    try:
        subprocess.run(sudo_cmd(["systemctl", "is-active", "--quiet", "ollama"]),
                       check=True)
        log("ollama ACTIVE")
    except subprocess.CalledProcessError:
        log("WARNING: ollama not active -- check 'systemctl status ollama'")


def macos_install() -> None:
    log("platform=macOS")
    ensure_ollama_binary()
    if shutil.which("brew") is not None:
        log("installing/starting via Homebrew service")
        run(["brew", "services", "start", "ollama"], check=False)
    else:
        log("Homebrew not found; starting 'ollama serve' in background")
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"ollama should be listening on {OLLAMA_HOST}")


def windows_install() -> None:
    log("platform=Windows")
    if shutil.which("ollama") is None:
        log("installing Ollama via winget")
        run(["winget", "install", "--id", "Ollama.Ollama", "-e", "--silent"],
            check=False)
    else:
        log("ollama binary present")
    log("starting 'ollama serve' in background")
    subprocess.Popen(["ollama", "serve"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log(f"ollama should be listening on {OLLAMA_HOST}")


def main() -> None:
    sysname = platform.system()
    log(f"Ollama installer | user={OLLAMA_USER} host={OLLAMA_HOST} dir={INSTALL_DIR}")
    if sysname == "Linux":
        linux_install()
    elif sysname == "Darwin":
        macos_install()
    elif sysname == "Windows":
        windows_install()
    else:
        log(f"unsupported platform: {sysname}")
        sys.exit(1)
    log(f"done. MOON's model backend target: {OLLAMA_HOST}")


if __name__ == "__main__":
    main()
