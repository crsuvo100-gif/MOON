#!/usr/bin/env python3
"""
MOON Uninstaller -- native, standalone, non-destructive by default.

Mirrors the "uninstall" step of agent installers (e.g. Hermes) but is built
ONLY for MOON and shares NO code with any other project. It reverses exactly
what MOON's installer creates:

    * systemd user units: moon-terminal / moon-hud / moon-watchdog (+ .timer)
    * the launcher symlink: ~/.local/bin/moon
    * the desktop entry:   ~/.local/share/applications/moon-terminal.desktop

By DEFAULT this leaves your project files, .venv and runtime DATA (agent DBs,
memory, knowledge, backups) intact -- it only removes the auto-start wiring
and installed entry points, so you can reinstall cleanly.

Use  --purge  to ALSO remove the virtualenv (.venv) and runtime data dirs.
Use  --yes    to skip the confirmation prompt (for scripted/one-click use).

This is purely additive: it does not touch files it did not create and never
force-deletes anything outside MOON's own install artifacts.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# --- where MOON was installed (resolved at runtime, not hard-coded) ----------
# The launcher knows the real install dir; prefer it. Otherwise fall back to
# the directory this script lives in, then the working copy.
def _detect_install_root() -> Path:
    launcher = Path(os.path.expanduser("~/.local/bin/moon"))
    if launcher.is_file():
        try:
            for line in launcher.read_text().splitlines():
                line = line.strip()
                if line.startswith("cd ") and "MOON" in line:
                    cand = Path(line[3:].strip().strip('"').strip("'"))
                    if cand.is_dir():
                        return cand
        except Exception:
            pass
    here = Path(__file__).resolve().parent
    if (here / "main.py").exists():
        return here
    return Path.cwd()


ROOT = _detect_install_root()
SYSTEMD_DIR = Path(os.path.expanduser("~/.config/systemd/user"))
BIN = Path(os.path.expanduser("~/.local/bin/moon"))
DESKTOP = Path(os.path.expanduser("~/.local/share/applications/moon-terminal.desktop"))

# All unit names MOON's installer/setup may have deployed over time.
UNIT_NAMES = [
    "moon-terminal.service",
    "moon-hud.service",
    "moon-watchdog.service",
    "moon-watchdog.timer",
    "moon-monitor.service",
    "moon-monitor.timer",
]


def _c(code, s):
    if sys.stdout.isatty():
        return f"\033[{code}m{s}\033[0m"
    return s


def info(s):  print(_c("36", f"[MOON] {s}"))
def ok(s):    print(_c("32", f"[ OK ] {s}"))
def warn(s):  print(_c("33", f"[!! ] {s}"))
def head(s):  print("\n" + _c("35", "=== " + s + " ==="))


def _run(cmd, check=False):
    return subprocess.run(cmd, capture_output=True, text=True)


def _unit_points_to_root(unit_path: Path, root: Path) -> bool:
    """True if a systemd unit file references the target install root."""
    try:
        txt = unit_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    root_str = str(root)
    # units reference the root via WorkingDirectory= or ExecStart= paths
    return root_str in txt


def stop_and_disable_units():
    if not (SYSTEMD_DIR / "moon-terminal.service").exists() and \
       shutil.which("systemctl") is None:
        return
    for unit in UNIT_NAMES:
        p = SYSTEMD_DIR / unit
        if not p.exists():
            continue
        # SAFETY: only touch units that actually belong to this MOON install.
        # If --root was given and the unit points elsewhere, skip it so we
        # never remove another installation's wiring.
        if ROOT not in (p, ) and not _unit_points_to_root(p, ROOT):
            warn(f"skipping {unit}: not owned by {ROOT} (points elsewhere)")
            continue
        info(f"Stopping + disabling {unit} ...")
        _run(["systemctl", "--user", "stop", unit], check=False)
        _run(["systemctl", "--user", "disable", unit], check=False)
        try:
            p.unlink()
            ok(f"removed unit file: {unit}")
        except FileNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            warn(f"could not remove {unit}: {exc}")
    _run(["systemctl", "--user", "daemon-reload"], check=False)
    ok("systemd daemon-reload done")


def _path_points_to_root(path: Path, root: Path) -> bool:
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return str(root) in txt


def remove_launcher():
    if not (BIN.exists() or BIN.is_symlink()):
        info(f"launcher not present: {BIN} (skip)")
        return
    # SAFETY: only remove if it launches THIS MOON install.
    if not _path_points_to_root(BIN, ROOT):
        warn(f"skipping launcher {BIN}: not owned by {ROOT}")
        return
    try:
        BIN.unlink()
        ok(f"removed launcher: {BIN}")
    except Exception as exc:  # noqa: BLE001
        warn(f"could not remove launcher {BIN}: {exc}")


def remove_desktop():
    if not DESKTOP.exists():
        info("desktop entry not present (skip)")
        return
    if not _path_points_to_root(DESKTOP, ROOT):
        warn(f"skipping desktop entry {DESKTOP}: not owned by {ROOT}")
        return
    try:
        DESKTOP.unlink()
        ok(f"removed desktop entry: {DESKTOP}")
        _run(["update-desktop-database", str(DESKTOP.parent)], check=False)
    except Exception as exc:  # noqa: BLE001
        warn(f"could not remove desktop entry {DESKTOP}: {exc}")


def purge(ask_yes: bool):
    head("Purge runtime artifacts (--purge)")
    venv = ROOT / ".venv"
    data_dirs = [ROOT / "data", ROOT / "backups", ROOT / "app" / "logs",
                 ROOT / "memory", ROOT / "connections"]
    if venv.is_dir():
        info(f"Removing virtualenv: {venv}")
        shutil.rmtree(venv, ignore_errors=True)
        ok("virtualenv removed")
    else:
        info("no .venv found (skip)")
    for d in data_dirs:
        if d.is_dir():
            info(f"Removing data dir: {d}")
            shutil.rmtree(d, ignore_errors=True)
            ok(f"removed {d}")
    # Also drop the generated .env so a fresh setup is clean.
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            env_file.unlink()
            ok("removed generated .env (re-run `moon setup` to regenerate)")
        except Exception:
            pass


def main():
    global ROOT
    ap = argparse.ArgumentParser(description="MOON uninstaller (native, safe by default)")
    ap.add_argument("--yes", action="store_true", help="skip confirmation prompt")
    ap.add_argument("--purge", action="store_true",
                    help="ALSO remove .venv + runtime data (agent DBs, memory, backups)")
    ap.add_argument("--root", default=str(ROOT),
                    help=f"MOON install dir (auto-detected: {ROOT})")
    args = ap.parse_args()

    ROOT = Path(args.root).expanduser().resolve()

    head("MOON Uninstall")
    info(f"Install root: {ROOT}")
    print("This will remove MOON's auto-start wiring (systemd units, launcher, desktop entry).")
    if args.purge:
        warn("PURGE enabled: .venv and runtime data will also be deleted.")
    else:
        info("Project files / .venv / runtime DATA will be KEPT (safe reinstall).")

    if not args.yes:
        ans = input(_c("36", "  ? Proceed with uninstall? [y/N]: ")).strip().lower()
        if ans not in ("y", "yes"):
            info("Aborted. Nothing changed.")
            return 0

    stop_and_disable_units()
    remove_launcher()
    remove_desktop()

    if args.purge:
        purge(args.yes)

    head("Done")
    if args.purge:
        ok("MOON uninstalled (including venv + data). Reinstall with: git clone ... && ./install.sh")
    else:
        ok("MOON auto-start wiring removed. Project + data kept.")
        info("To reinstall quickly:  cd " + str(ROOT) + " && ./install.sh")
        info("Or just run the backend again:  cd " + str(ROOT) + " && moon terminal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
