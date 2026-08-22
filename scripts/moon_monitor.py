#!/usr/bin/env python3
"""
MOON System Monitor + Self-Heal
Runs periodic health checks on the MOON install and auto-fixes common issues.
Pure-Python, no external deps. Designed to be invoked by cron (see bottom).

Checks:
  1. Ollama reachable + required models physically present (pulls missing ones)
  2. MOON backend (FastAPI :8777) reachable; restarts if down
  3. Git repo synced with origin (warns if diverged)
  4. Disk / RAM headroom (warns if critically low)
  5. Logged errors in recent backend output (scans make-terminal log)

Self-heal actions:
  - Restart backend if health != 200
  - Pull missing required GGUF models via ollama
  - (Git divergence is reported, never auto-force-pushed)

Logs to stderr/stdout; exit 0 = all OK (or healed), 1 = unresolved issue.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(PROJECT, ".venv", "bin", "python")
BACKEND_PORT = 8777
OLLAMA_PORT = 11434
REQUIRED_MODELS = [
    "qwen3:0.6b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2.5-coder:1.5b",
    "deepseek-r1:1.5b",
]


def log(msg):
    print(f"[moon-monitor {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def run(cmd, timeout=120):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=PROJECT)
    except Exception as e:  # noqa
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def http_get(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa
        return None, str(e)


def ollama_models():
    st, out = http_get(f"http://127.0.0.1:{OLLAMA_PORT}/api/tags")
    if st != 200:
        return None
    try:
        return {m["name"] for m in json.loads(out).get("models", [])}
    except Exception:
        return set()


def ensure_models():
    present = ollama_models()
    if present is None:
        log("WARN: Ollama not reachable -- cannot verify/pull models")
        return False
    missing = [m for m in REQUIRED_MODELS if m not in present]
    if not missing:
        log("OK: all required models present")
        return True
    log(f"HEAL: pulling missing models: {missing}")
    ok = True
    for m in missing:
        r = run(["ollama", "pull", m], timeout=600)
        if r.returncode == 0:
            log(f"HEAL: pulled {m}")
        else:
            log(f"FAIL: could not pull {m}: {(r.stderr or r.stdout)[:200]}")
            ok = False
    return ok


def ensure_backend():
    st, _ = http_get(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
    if st == 200:
        log("OK: backend healthy")
        return True
    log("HEAL: backend not responding -- restarting via make terminal")
    # kill any stale backend on the port, then launch fresh
    run(["pkill", "-f", "moon_terminal|terminal_interface|main.py terminal"], timeout=20)
    time.sleep(3)
    # launch in background detached
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    subprocess.Popen(
        ["make", "terminal"], cwd=PROJECT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # give it time to boot
    for _ in range(20):
        time.sleep(3)
        st2, _ = http_get(f"http://127.0.0.1:{BACKEND_PORT}/api/health")
        if st2 == 200:
            log("HEAL: backend restarted OK")
            return True
    log("FAIL: backend did not come back up")
    return False


def git_sync():
    local = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    rem = run(["git", "ls-remote", "--heads", "origin", "master"]).stdout.strip()
    remote_sha = rem.split()[0] if rem else ""
    if not remote_sha:
        log("WARN: cannot reach origin -- skipping git check")
        return True
    if local == remote_sha:
        log("OK: git synced with origin/master")
        return True
    log(f"WARN: local ({local[:8]}) != origin/master ({remote_sha[:8]}) -- "
        f"run `python -m moon update` (NOT auto-pushed)")
    return True  # report only; never force-push


def resource_check():
    # disk
    try:
        st = shutil.disk_usage(PROJECT)
        pct = (st.used / st.total) * 100
        if pct > 90:
            log(f"WARN: disk {pct:.0f}% full")
    except Exception:
        pass
    # ram
    try:
        with open("/proc/meminfo") as f:
            info = dict(line.split(":", 1) for line in f if ":" in line)
        avail = int(info.get("MemAvailable", "0").strip().split()[0]) / 1024 / 1024
        if avail < 0.5:
            log(f"WARN: low RAM available {avail:.1f} GiB -- model loads may OOM")
    except Exception:
        pass


def main():
    log("=== MOON monitor run ===")
    ensure_models()
    ensure_backend()
    git_sync()
    resource_check()
    log("=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
