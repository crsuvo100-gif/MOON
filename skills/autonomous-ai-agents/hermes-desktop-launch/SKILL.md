---
name: hermes-desktop-launch
description: "Launch Hermes desktop: serve first, fix fallback, verify."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, desktop, electron, launch, backend, serve]
    category: desktop
    related_skills: [hermes-agent, local-service-operations]
---

# Hermes Desktop Launch

## Overview
Launch the Hermes Electron desktop app (`hermes desktop`) and its required local backend (`hermes serve`). The desktop app is a GUI client that connects to a local Hermes backend; it does NOT work standalone.

## When to Use
- The user asks to run, launch, or open the Hermes desktop app.
- The desktop app fails to start, crashes, or falls back to a cloud URL.
- You need to verify the desktop + backend stack is healthy.

## Prerequisites
- Node.js >= 18 and npm (for Electron runtime; the app bundles its own Electron)
- `hermes serve` capability (Python venv with Hermes installed)
- X11 session with `$DISPLAY` set (Linux); GPU may need to be disabled on remote/X11-forwarded displays

## The Core Rule: Serve First, Then Desktop

The desktop app resolves a backend in this order:
1. Local backend on `127.0.0.1:9119` (or auto-assigned port when `--port 0` is used)
2. Falls back to cloud URL `https://hermes.hermes-agent.nousresearch.com/v1` if no local backend is found

**The cloud fallback is the failure mode, not a feature.** That hostname does not resolve in most environments, producing `ERR_NAME_NOT_RESOLVED`. When you see that error in the Electron console, the fix is ALWAYS to start a local backend first — not to debug DNS.

## Launch Sequence

### Step 1 — Start the local backend

```bash
hermes serve --host 127.0.0.1 --port 9119
```

This runs the headless Hermes gateway (JSON-RPC + WebSocket). It prints `HERMES_BACKEND_READY port=9119` when ready. Use `--port 0` for auto-assigned port; the desktop app discovers it.

### Step 2 — Launch the desktop app

```bash
# From the Hermes source root (e.g. ~/.hermes/hermes-agent):
python -m hermes_cli.main desktop [--skip-build]
```

`--skip-build` skips the npm build step and launches the existing unpacked app from `apps/desktop/release/linux-unpacked/`. Use it when the app has already been built.

Other useful flags:
- `--source` — launch via `electron .` against `apps/desktop/dist` (dev mode)
- `--build-only` — build but don't launch
- `--cwd DIR` — set initial project directory for chat sessions
- `--force-build` — rebuild even if content stamp matches

### Step 3 — Verify

Check the backend health endpoint:

```bash
curl -s http://127.0.0.1:9119/api/status
```

Look for:
- `dashboard.status: "ok"` — the backend is serving
- `storage.status: "ok"` — storage layer healthy
- `active_sessions >= 1` — the desktop session is connected
- `overall` may be `"degraded"` when messaging platforms (Telegram/Discord/etc.) are not configured — this is NORMAL for desktop-only use, not a failure

Check the desktop process is alive:

```bash
ps aux | grep "Hermes.*--disable-gpu" | grep -v grep
```

## Diagnosing Failures

### Symptom: `ERR_NAME_NOT_RESOLVED` for `hermes.hermes-agent.nousresearch.com`

**Cause:** The desktop app could not find a local backend and fell back to the cloud URL, which doesn't resolve.

**Fix:**
1. Start `hermes serve` on `127.0.0.1:9119` (or port 0)
2. Re-launch `hermes desktop --skip-build`
3. The desktop should now connect to localhost instead of the cloud URL

### Symptom: GPU process crashes / `GPU process isn't usable. Goodbye.`

**Cause:** Hardware GPU acceleration failing on the current display setup (common on X11-forwarded or remote displays).

**Fix:** The desktop app auto-detects remote displays and disables GPU (`HERMES_DESKTOP_DISABLE_GPU`). If it doesn't, launch Electron with `--disable-gpu --disable-software-rasterizer`. The packaged desktop launch already passes these flags.

### Symptom: Desktop launches but shows onboarding/provider screen

**Cause:** The backend has no inference provider configured. The desktop app's onboarding flow requires a configured model/provider before chat works.

**Fix:** Configure a provider in the desktop app's Settings -> Providers, or configure one via the CLI first (`hermes model` or `hermes setup`), then relaunch the desktop.

### Symptom: `hermes serve` exits immediately

**Cause:** Port already in use, or missing venv/dependencies.

**Fix:**
1. Check for existing serve process: `ps aux | grep "hermes_cli.main serve"`
2. Kill it if stale: `pkill -f "hermes_cli.main serve"` (or use `fuser -k 9119/tcp`)
3. Restart: `hermes serve --host 127.0.0.1 --port 9119`

### Symptom: Desktop times out connecting but `hermes serve` process is running

**Cause:** The serve process survived a gateway restart/shutdown and is listening on its port but not answering HTTP — a zombie. The desktop log (`~/.hermes/logs/desktop.log`) shows `Timed out connecting to Hermes backend after 60000ms` while `ps` shows the serve process still alive. This is distinct from "serve exits immediately" — the process is present but unresponsive.

**Diagnosis path:**
1. Confirm serve is alive: `ps aux | grep "hermes_cli.main serve" | grep -v grep`
2. Find its actual port (when launched with `--port 0`): `ss -tlnp | grep <pid>` — look for the `127.0.0.1:<port>` LISTEN line
3. Test responsiveness: `curl --max-time 5 http://127.0.0.1:<port>/api/status` — a timeout (curl exit 28) or hang means the process is a zombie
4. Check desktop.log for the timeout: `grep "Timed out" ~/.hermes/logs/desktop.log | tail -5`

**Fix:**
1. Kill the stuck serve: `hermes serve --stop` — this kills the zombie AND auto-restarts a fresh instance on a new port
2. Find the new port from desktop.log: look for `HERMES_BACKEND_READY port=<port>` in recent entries, or `ss -tlnp | grep <new_pid>`
3. Verify the new instance is responsive: `curl --max-time 5 http://127.0.0.1:<port>/api/status` — expect `overall: ok`, `dashboard: ok`, `storage: ok`, `active_sessions >= 1`
4. If the desktop did not auto-reconnect, relaunch: `hermes desktop --skip-build`

**Key log files:**
- `~/.hermes/logs/desktop.log` — desktop-side errors, timeout messages, backend ready events
- `~/.hermes/logs/gateway.log` — serve/gateway lifecycle, startup/shutdown timestamps
- `~/.hermes/logs/gui.log` — WebSocket send failures, disconnect reasons (backend-side view of desktop connections)

## Stopping

```bash
hermes serve --stop
```

Alternatively, kill the Electron process and the serve process:

```bash
pkill -f "Hermes.*--disable-gpu"
pkill -f "hermes_cli.main serve"
```

## Health Snapshot (copy-paste verification)

```bash
# Backend health
curl -s http://127.0.0.1:9119/api/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Overall: {d.get('overall')}\")
print(f\"Dashboard: {d['components']['dashboard']['status']}\")
print(f\"Storage: {d['components']['storage']['status']}\")
print(f\"Active sessions: {d.get('active_sessions')}\")
print(f\"Profiles: {d.get('profiles')}\")
"

# Desktop process
pgrep -a "Hermes.*--disable-gpu" || echo "no desktop process"
```

## Pitfalls

1. **Launching desktop without serve.** The #1 failure. Always start `hermes serve` first. The desktop does not bundle its own backend.

2. **Treating `overall: "degraded"` as a failure.** For desktop-only use (no Telegram/Discord/etc.), `gateway.state: "stopped"` is expected. The relevant indicators are `dashboard: ok` and `storage: ok`.

3. **Rebuilding unnecessarily.** If the unpacked app exists in `apps/desktop/release/linux-unpacked/`, use `--skip-build`. Rebuilding takes time and requires npm/Node modules.

4. **Running from the wrong directory.** `hermes desktop` should be invoked from the Hermes source root (`~/.hermes/hermes-agent`) so it finds `apps/desktop/`. The `python -m hermes_cli.main desktop` form from anywhere works if `HERMES_HOME` is set correctly.

5. **Port conflict.** If `hermes serve` picks port 0 (auto-assign), the desktop discovers the actual port. If you hardcode `--port 9119` and something else is on 9119, serve fails. Check with `ss -tlnp | grep 9119` or `lsof -i :9119`.

## Reference

- `hermes desktop --help` — full flag reference
- `hermes serve --help` — backend flags
- `hermes doctor` — dependency and config health check
- `hermes status --all` — component status overview
- `references/diagnostics.md` — failure-mode matrix, port-discovery for `--port 0`, log-file guide, /api/status interpretation
