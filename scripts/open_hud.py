#!/usr/bin/env python3
"""
MOON HUD window keeper.

Single, idempotent process that keeps EXACTLY ONE MOON HUD (Chrome --app window)
open on the local display. It never spawns a backend and never touches the
:8777 port, so it cannot cause the old double-bind crash-loop that made the
whole terminal appear to blink.

Design (anti-blink):
  * Detects an already-running HUD window via a lockfile holding the Chrome PID.
  * Only opens a new window when the previous one has actually died.
  * Launches Chrome detached (own session) so it survives this keeper restarting.
  * Loops forever; systemd Restart=on-failure keeps the keeper alive too.

This is the ONLY component responsible for the visible HUD window now.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(tempfile.gettempdir(), "moon_hud_open.lock")
HEALTH_URL = "http://127.0.0.1:8777/api/health"


def _which(name):
    return shutil.which(name)


def _detect_browser():
    for cand in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome", "microsoft-edge",
                 "microsoft-edge-stable"):
        p = _which(cand)
        if p:
            return p
    for p in ("/opt/google/chrome/chrome", "/usr/bin/google-chrome",
              "/usr/bin/chromium", "/snap/bin/chromium"):
        if os.path.exists(p):
            return p
    return None


def _detect_display():
    d = os.environ.get("DISPLAY")
    if d:
        return d, None
    w = os.environ.get("WAYLAND_DISPLAY")
    if w:
        return None, w
    return None, None


def _load_url():
    sp = os.path.join(PROJECT, "web", "moon_settings.json")
    try:
        with open(sp) as fh:
            s = json.load(fh)
        host = s.get("host", "127.0.0.1")
        port = int(s.get("port", 8777))
    except Exception:
        host, port = "127.0.0.1", 8777
    return f"http://{host}:{port}/"


def _hud_alive():
    """Return the live Chrome PID recorded in the lockfile, or None."""
    try:
        with open(LOCK) as fh:
            pid = fh.read().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            # Confirm it is actually a chrome process owning our HUD
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as cf:
                    cmd = cf.read().decode("utf-8", "replace")
                if "app=http" in cmd or "moon" in cmd.lower() or "chrome" in cmd.lower():
                    return pid
            except Exception:
                return pid  # proc exists; treat as alive
    except Exception:
        pass
    return None


def _wait_backend(timeout=60):
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2):
                return True
        except Exception:
            time.sleep(2)
    return False


def _display_size():
    """Native X11 resolution (W,H) so the HUD window is created at true size
    instead of a hard-coded 1920x1080 that the X server upscales (upscaled
    fullscreen blits are a classic flicker source on scaled panels)."""
    try:
        import re
        out = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if "*current" in line:
                m = re.search(r"(\d+)x(\d+)", line)
                if m:
                    return m.group(1), m.group(2)
    except Exception:
        pass
    return "1366", "768"


def open_hud():
    disp, wayland = _detect_display()
    if not (disp or wayland):
        return None  # no graphical display -> nothing to do (headless/SSH)
    chrome = _detect_browser()
    if not chrome:
        return None
    url = _load_url()
    # GPU-ACCELERATED rendering (fixes the dominant display-blink cause): the
    # old flags forced --disable-gpu, pushing Chrome onto the SwiftShader
    # software rasterizer. On a non-composited X11 desktop a full-screen,
    # canvas-heavy page rendered in software drops frames and strobes. We now
    # let Chrome use the real Intel GPU (ANGLE/GL via Mesa) + GPU compositing.
    args = [chrome, "--disable-setuid-sandbox",
            "--enable-gpu", "--ignore-gpu-blocklist",
            "--enable-gpu-compositing", "--enable-gpu-rasterization",
            "--use-gl=angle", "--use-angle=gl",
            f"--app={url}", "--start-maximized",
            "--disable-infobars", "--no-first-run", "--no-default-browser-check"]
    w, h = _display_size()
    args += [f"--window-size={w},{h}"]
    if wayland:
        args += ["--ozone-platform=wayland", f"--wayland-display={wayland}"]
    if disp:
        args += [f"--display={disp}"]
    try:
        proc = subprocess.Popen(args, env={**os.environ, "PYTHONPATH": ""},
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True)
    except Exception:
        return None
    try:
        with open(LOCK, "w") as fh:
            fh.write(str(proc.pid))
    except Exception:
        pass
    return proc.pid


def main():
    # Give the backend a moment to come up before the first open.
    _wait_backend(timeout=90)
    while True:
        if _hud_alive() is None:
            pid = open_hud()
            if pid:
                print(f"[moon-hud] opened HUD window (chrome pid {pid})",
                      flush=True)
            else:
                # No browser / no display yet -- retry shortly.
                time.sleep(10)
                continue
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
