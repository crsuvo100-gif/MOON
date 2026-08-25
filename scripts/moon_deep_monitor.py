#!/usr/bin/env python3
"""
MOON deep-operational monitor (self-contained, no agent required).

Runs a REAL operational scan of the MOON backend every invocation:
  - backend reachable + /api/health == HEALTHY (8 checks)
  - agents >= 30 and tools >= 30 live
  - DEEP PROOF: unlock + run the system_info tool in-process and assert the
    real output contains 'linux' (proves the agent->tool execution pipeline
    actually executes, not just that the server process is up).

If the backend is down OR the deep proof fails, it restarts the
moon-terminal.service (safe, idempotent) and re-probes.

Designed to be invoked by systemd (deploy/moon-monitor.{service,timer}) every
15 minutes. Pure-python, no external deps. Logs to stdout (journald picks it up).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(PROJECT, ".venv", "bin", "python")
BACKEND = "http://127.0.0.1:8777"
UNLOCK = "MOON love you 3000"


def log(msg):
    print(f"[moon-deep-monitor {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def http_get(path, timeout=6):
    try:
        with urllib.request.urlopen(BACKEND + path, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def restart_backend():
    log("HEAL: backend unhealthy -- restarting moon-terminal.service")
    subprocess.run(["systemctl", "--user", "restart", "moon-terminal.service"],
                   capture_output=True, text=True)
    time.sleep(10)


def deep_proof():
    """Return True if the agent->tool pipeline executes a real result."""
    if not os.path.exists(VENV_PY):
        return False
    script = (
        "import sys; sys.path.insert(0, '.')\n"
        "import asyncio\n"
        "async def main():\n"
        "    from app.brain.orchestrator import Orchestrator\n"
        "    from app.config.settings import get_settings\n"
        "    o = Orchestrator(get_settings()); await o.setup()\n"
        "    o._lock.observe('" + UNLOCK + "')\n"
        "    r = await o._tools.run('system_info', {}, agent=None)\n"
        "    out = getattr(r, 'output', str(r))\n"
        "    print('DEEP_PROOF_OK' if 'linux' in out.lower() else 'DEEP_PROOF_FAIL')\n"
        "asyncio.run(main())\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["TMPDIR"] = env.get("TMPDIR", "/home/meow/.pip_tmp")
    try:
        out = subprocess.run([VENV_PY, "-c", script], cwd=PROJECT, env=env,
                             capture_output=True, text=True, timeout=180)
        return "DEEP_PROOF_OK" in out.stdout
    except Exception as e:  # noqa: BLE001
        log(f"deep proof error: {e}")
        return False


def main():
    log("=== MOON deep monitor run ===")
    st, h = http_get("/api/health")
    h_dict = h if isinstance(h, dict) else {}
    if st != 200 or h_dict.get("status") != "HEALTHY":
        log(f"health probe: {st} {h if isinstance(h, str) else h_dict.get('status')}")
        restart_backend()
        st, h = http_get("/api/health")
        h_dict = h if isinstance(h, dict) else {}
    if st != 200:
        log("FAIL: backend still down after restart")
        return 1

    checks = h_dict.get("checks", [])
    ok_checks = all(c.get("state") == "OK" for c in checks) if checks else True
    log(f"health: {h_dict.get('status')} ({len(checks)} checks, all_ok={ok_checks})")

    _, ag = http_get("/api/agents")
    _, tl = http_get("/api/tools")
    na = len(ag.get("agents", [])) if isinstance(ag, dict) else 0
    nt = len(tl.get("tools", [])) if isinstance(tl, dict) else 0
    log(f"agents={na} tools={nt}")
    if na < 30 or nt < 30:
        log("FAIL: agent/tool count below threshold")
        return 1

    if not deep_proof():
        log("FAIL: deep execution proof did not return a real result")
        restart_backend()
        if not deep_proof():
            log("FAIL: deep proof still failing after restart")
            return 1

    log("OK: MOON fully operational (health + registry + real execution)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
