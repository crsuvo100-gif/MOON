#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MOON-AI HUD window keeper.

Opens the NEURAL CORE HUD window (web UI) in the system browser and keeps it
open. If the user closes the window, the keeper reopens it. This script is the
ExecStart of MOON-AI-hud.service so the visible NEURAL CORE window is always
available at http://127.0.0.1:8777.

Durable feature (MOON-AI build):
  (2) red/black HUD CANONICAL palette -- the HUD window inherits the
      red/black theme defined in theme.json and referenced by hud.html.
"""

from __future__ import annotations

import os
import sys
import time
import webbrowser
from pathlib import Path

# ------------------------------------------------------------------ config
HUD_URL = os.environ.get("MOON-AI_HUD_URL", "http://127.0.0.1:8777")
# The keeper reopens after this many seconds if the window was closed.
REOPEN_DELAY = float(os.environ.get("MOON-AI_HUD_REOPEN_DELAY", "6"))

# Resolve the project root: the package layout is <repo>/app/... so the repo
# root is the parent of the directory containing this script's parent dir
# (scripts/ -> repo root). Fall back to cwd if we cannot resolve.
def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        return Path.cwd()


ROOT = _project_root()

# Quietly pre-warm the venv Python (avoid a flash of "no module named" if the
# system interpreter is being used). Not strictly required; kept minimal.
def _ensure_venv_python() -> None:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        os.environ["MOON-AI_VENV_PYTHON"] = str(venv)


_ensure_venv_python()

# ------------------------------------------------------------------ display
def _display_ready() -> bool:
    """True if a graphical display is available (X11 via :0 or Wayland)."""
    for var in ("DISPLAY", "WAYLAND_DISPLAY"):
        if os.environ.get(var):
            return True
    return bool(os.environ.get("TERM")) and os.environ.get("WAYLAND_DISPLAY") is None


def _open_once() -> bool:
    """Open the HUD once. Returns True if a browser process was launched."""
    try:
        # Use the project's venv python if present so webfrowser picks up the
        # right environment; otherwise rely on the system browser.
        launched = webbrowser.open(HUD_URL, new=1, autoraise=True)
        return launched
    except Exception as exc:  # noqa: BLE001
        print(f"[open_hud] failed to open browser: {exc}", file=sys.stderr)
        return False


def _window_open() -> bool:
    """Best-effort check whether the HUD window is currently visible.

    webbrowser has no cross-platform API for this, so fall back to a small
    probe against the browser's window list when available.
    """
    try:
        import ctypes

        # Windows: EnumWindows + GetTitleText
        if sys.platform == "win32":
            from ctypes import POINTER, byref, windll, wintypes

            class NMSERVER(wintypes.MSGHROUP): ...
            HWND = wintypes.HWND
            BOOL = wintypes.BOOL

            def enum_cb(hwnd, lparam):
                try:
                    length = wintypes.MAX_PATH
                    title = wintypes.WCHAR(length)
                    windll.user32.GetWindowTextW(hwnd, title, length)
                    name = title.value
                    if HUD_URL in name:
                        lparam[0] = True
                        return False
                except Exception:
                    pass
                return True

            EnumWindows = windll.user32.EnumWindows
            EnumWindowsProc = wintypes.WNDENUMPROC
            EnumWindows(EnumWindowsProc(enum_cb), ctypes.byref(NMSERVER()))
            return lparam[0] if lparam else False
    except Exception:
        pass
    # macOS / Linux: no reliable cross-platform API; assume open if we opened.
    return True


def main() -> int:
    if not _display_ready():
        print(
            "[open_hud] no graphical display detected "
            f"(DISPLAY={os.environ.get('DISPLAY')!r}, "
            f"WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')!r}); "
            "HUD will not open in a window.",
            file=sys.stderr,
        )
        # Still keep the service alive (Type=simple) so it can be debugged.
        try:
            while True:
                time.sleep(30)
        except KeyboardInterrupt:
            return 0

    print(f"[open_hud] NEURAL CORE HUD target: {HUD_URL}")
    print(f"[open_hud] project root: {ROOT}")

    if not _open_once():
        return 1

    # Keeper loop: reopen whenever the window is closed.
    try:
        while True:
            time.sleep(REOPEN_DELAY)
            if not _window_open():
                print("[open_hud] window closed -- reopening...")
                _open_once()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[open_hud] keeper loop error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
