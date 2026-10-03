---
name: local-service-operations
description: Use when checking or operating a local service or daemon.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [local-services, daemon, health-check, verification, linux]
    related_skills: [hermes-agent]
---

# Local Service Operations

## Overview
Use a verified, non-destructive workflow to determine whether a local service is running, reachable, and usable. Distinguish process state, socket reachability, and application health; they are separate facts.

## When to Use
- The user asks to run, connect to, check, or troubleshoot a local daemon or application service.
- A localhost port is known or discovered.
- The user wants a direct result rather than an unverified claim that a service is operational.

## Verification Workflow

1. Inspect the service process and record its command, user, and PID when visible.
2. Inspect listening sockets and record the precise bound address and port.
3. Make a small, non-destructive localhost request only when an HTTP endpoint is expected.
4. Interpret responses accurately:
   - A successful application health/API response confirms usability for that endpoint.
   - A TCP connection confirms reachability only.
   - An HTTP `404` at `/` means the listener is reachable, not that the service is broken or that a web UI exists.
5. Report verified facts separately from unknowns. Do not infer undocumented routes from a listener alone.

## Execution Style

Use reasonable defaults and verify results with real tools. Do not claim a service is “running” merely because a helper command or related dependency exists. Do not start, restart, reconfigure, or stop a service without explicit user direction.

## Verifying a local service's full API surface (not just health)

When auditing a local service that exposes a web API (FastAPI, Flask, etc.), go
beyond the health endpoint. A service can be "healthy" while its real functionality
is broken or missing.

### Procedure

1. **List all routes** — import the app and walk `app.routes`:
   ```python
   from app.terminal_interface import app
   for route in app.routes:
       if hasattr(route, 'methods') and hasattr(route, 'path'):
           print(f"  {route.path:40s} {sorted(route.methods)}")
   ```
   This reveals the FULL surface, including routes that may not be documented.

2. **Check WebSocket endpoints separately** — WS routes don't show up in the
   HTTP route list. Look for `app.websocket` decorators:
   ```python
   for route in app.routes:
       if hasattr(route, 'path') and 'ws' in str(getattr(route, 'path', '')):
           print(f"  WS: {route.path}")
   ```

3. **Probe the health endpoint** — confirms the service is reachable and its
   self-check passes. But health ≠ functional. A backend can report healthy
   while its task-execution path is broken.

4. **Probe a real functional endpoint** — find an endpoint that exercises the
   core logic (task execution, tool call, agent run) and call it. For MOON:
   `POST /api/agents/coordinator/run` with a deterministic prompt proves the
   full backend → orchestrator → LLM → response path works.

5. **Check authorization gates** — some routes may require a token/header. If
   a probe returns 401, check for `TERMINAL_TOKEN` env var or similar.

### Common pitfalls

- **Root-path 404 ≠ broken service.** Many FastAPI apps have no `/` route.
  Probe a documented endpoint (`/api/health`, `/api/brain-status`).
- **Health OK but task execution fails.** The health check may ping the model
  endpoint but not actually run a task. Always test the task-execution path
  separately.
- **WS endpoints are separate from HTTP routes.** A service with working HTTP
  may have broken WS (wrong path, auth mismatch, missing handler).
- **Don't assume two subprojects share a port.** MOON's moonscope backend runs
  on port 8777 (managed by `moon-terminal.service`). terminal_moon has its own
  backend that is NOT currently managed by systemd and may not be running.
- **Route handler double-send crash (Starlette/FastAPI).** A route handler that
  calls an internal method which uses the ASGI `send()` callable AND then returns
  a `Response` (e.g. `JSONResponse`) crashes with a "stream is already final" /
  double-send error — the body already triggered one send, and returning a
  `Response` triggers a second. Fix: split the method into a `_data` variant that
  returns a plain `dict` (no `send()` calls) and a thin send wrapper that calls
  `send()`; the route handler calls `_data` and wraps the result in
  `JSONResponse(content=data)`. Confirm the fix by hitting the endpoint — a clean
  JSON response means the double-send is resolved.

### MOON-specific notes

- moonscope backend: 34 REST routes + 3 WS endpoints on port 8777.
  Task execution: `POST /api/agents/{agent_id}/run`.
- terminal_moon backend: smaller API, no task-execution endpoint.
  TUI uses direct LLM, not the backend.
- See `references/moonscope-terminal-moon-audit.md` in
  `local-ai-agent-engineering` for the full route inventory and audit procedure.

## Discovering and Using a Local Python Application's CLI Surface

When you have installed a local Python application (e.g. a self-hosted agent, service, or tool) and need to find how to invoke it properly — its real subcommands, its default launch behavior, how to open its UI vs its backend, and how to run tasks from the terminal — follow this discovery workflow before guessing at commands.

### When this applies
- The app was installed from a Git repo into a project directory (e.g. `~/Projects/<app>`).
- There is a venv at `<project>/.venv` and a Python entry point (often `main.py`, or a `src/<pkg>/__main__.py`).
- A launcher was installed to `~/.local/bin/<app>` (or similar) that `cd`s into the project and execs the venv python.
- You need to know: what does `<app>` (no args) do? What opens the web UI? What runs a task? What is the backward-compatible alias?

### Discovery steps

1. **Read the launcher script first.** It is the fastest source of truth for how the app is meant to be started. Typical location: `~/.local/bin/<app>`. It usually does `cd "<project>" && exec <venv>/bin/python main.py "$@"`. The `"$@"` tells you every argument you pass is forwarded — so subcommands come from `main.py`'s argparse, not from the launcher itself.

2. **Read `main.py`'s argparse / subcommand map.** This is where the real surface lives. Look for `add_subparsers(dest="cmd")` and the `if/elif` dispatch block. That block is the authoritative list of subcommands and what each triggers. Do NOT assume the project's README or a skill describes the current surface — read the dispatch block; it is source-of-truth.

3. **Distinguish deep vs shallow package imports.** Many projects ship a shallow top-level package (e.g. `<app>/__init__.py`) whose only job is to delegate to `main.py` or to the real implementation under `app/` or `scripts/`. If you import the shim package and guess submodules like `<app>.launcher` or `<app>.voice` and get `ModuleNotFoundError`, that is a FALSE NEGATIVE — the real modules live elsewhere. Always inspect the actual layout with `find <root> -name "*.py"` scoped to `app/` or `src/` before reporting an import failure.

   Related: if the app uses a voice engine and one import name fails but another succeeds, confirm which engine is actually wired. For example, a project may install `kokoro-onnx` (underscore) as the active voice while a legacy `kokoro` (no underscore, Coqui XTTS-v2) import is absent by design — the absent import is not voice-broken; the wired engine is the one that matters.

4. **Run `<app> --help` and each candidate subcommand's `--help` (`<app> ui --help`, `<app> run --help`, etc.).** This confirms the live subcommand set and each subcommand's accepted flags. Use this to verify your mental model against the installed binary, not the repo you read earlier.

5. **Identify the default (no-args) behavior from the `else:` branch of the dispatch block.** That branch is what runs when the user types just `<app>`. Treat it as the primary interactive entry point by default — unless the project documents otherwise.

6. **Find the UI-opening path separately from the backend-starting path.** For apps with a web UI:
   - One subcommand/branch usually starts the backend server (e.g. uvicorn) — often `terminal`, `start`, or `server`.
   - Another subcommand opens the browser to the already-running backend (e.g. `ui`) — often using a window-keeper helper (lockfile-based, idempotent, avoids stacking duplicate windows).
   - If the caller's session is headless (no `DISPLAY`), the UI opener may still succeed if a HUD/browser window is already running — implementors frequently scan running browser processes for `--display=...` to recover the display. The caller should handle the "already open" case explicitly and print a distinct message (not a generic "no browser detected").

7. **Tie backgrounding to tool capability, not to assumptions.** When the caller is a headless/background process (e.g. a Hermes terminal session) and the app's UI opener needs a real display, the right behavior is: attempt to open; if no display/browser, print a clear message telling the user to run it from a graphical terminal — do NOT fake success or stack windows.

### Patterns observed in a working install (illustrative, not prescriptive)

- A `moon` CLI where `moon` (no args) launches a Jarvis-style TUI/shell, `moon ui` opens the web HUD (full avatar + function dock), `moon run "task"` runs a single task from CLI, and `moon terminal` remains a backward-compatible alias that starts the backend and opens the HUD.
- A shared lock-state file (e.g. `app/data/lock_state.json`) that lets the CLI, web backend, voice, and TUI share one unlock state — so an unlock in any surface persists for all. When adding such shared state, put the file path in `.gitignore` (runtime state, never committed) and use a stable project-relative path so both the long-running web process and short-lived CLI invocations read/write the same file.
- A window keeper (`open_hud.py`-style) that uses a lockfile + PID check for idempotency, returns a distinct sentinel when the HUD is already open, and lets the caller print the right message.

### Pitfalls

- **Assuming the default subcommand.** Do not assume `<app>` with no args starts the web backend. Read the `else:` branch.
- **Importing the wrong package path.** Importing the shallow shim and guessing submodules produces false negatives. Inspect real layout first.
- **Confusing UI-open with backend-start.** They are often separate subcommands with different responsibilities (one may be idempotent and window-only; the other binds a port). Do not merge them.
- **Faking success in headless context.** If no display is available and no existing HUD window is reachable, report that clearly rather than claiming the UI opened.
- **Stacking duplicate UI windows.** Any UI-opener must be idempotent (lockfile/PID guard) before it spawns a browser, especially when the backend is managed by systemd and the UI opener is invoked repeatedly.
- **Treating a HEAD~n diff as the full change.** When committing, only the staged files are committed; unstaged modified files remain behind. Always check `git status --short` AND `git diff --cached --stat` to know exactly what a commit will contain.

### Verification checklist

- [ ] Launcher script read (`~/.local/bin/<app>`)
- [ ] `main.py` dispatch block read (authoritative subcommand list)
- [ ] Default (no-args) behavior confirmed from the `else:` branch
- [ ] UI-open path and backend-start path distinguished
- [ ] `<app> --help` and key subcommand `--help` run against the INSTALLED app, not assumed from repo
- [ ] Import-path pitfall checked if any import failure encountered (inspect real `app/` or `src/` layout)
- [ ] Shared runtime state (if any) is in `.gitignore` and uses a stable project path
- [ ] UI opener is idempotent (lockfile/PID guard) before spawning
- [ ] Headless case handled: clear message, no fake success

## Session references

- `references/moon-install-and-cli-rewire-2026-09.md` — full session log for the 2026-09-01/02 MOON fresh install + CLI rewire + two follow-up fixes (shared lock_state, headless display fallback, "already open" message, desktop entry update). Useful as a worked example of the discovery workflow and pitfalls above.
