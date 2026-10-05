# Hermes Compatibility Matrix for MOON

This document maps **Hermes Agent** capabilities to the **MOON** implementation, indicating whether each feature is **Implemented**, **Enhanced**, or **Missing** in the current codebase (as of the latest audit on 2026‑08‑16).

---

## Capability Matrix

| Hermes Capability | Description (Hermes) | MOON Implementation | Status |
|------------------|-----------------------|---------------------|--------|
| **Local backend** | Direct command execution on the host machine. | `app/terminal/backends/local.py` wraps `hermes_tools.terminal`. | **Implemented** |
| **Docker backend** | Commands run inside an isolated Docker container. | `app/terminal/backends/docker.py` (wrapper around `hermes_tools.docker`). | **Implemented** |
| **SSH backend** | Remote execution on a separate host via SSH. | `app/terminal/backends/ssh.py` (wrapper around `hermes_tools.ssh`). | **Implemented** |
| **PTY (interactive) mode** | Supports interactive terminal programs (e.g., REPLs, editors) using a pseudo‑TTY. | `ExecutionRequest.interactive` → `backends/*` call `pty_manager` to allocate a PTY. | **Implemented** |
| **Background execution** | Asynchronous `terminal(background=True)` that returns an execution ID and streams updates. | `process_manager.py` tracks background subprocesses; `ExecutionResult.background` flag. | **Implemented** |
| **Risk engine** | Evaluates request risk based on `risk_policy.yaml`. | `risk_engine.py` loads policies and scores requests. | **Implemented** |
| **Permission engine** | Enforces `auto/ask/deny` policies based on risk. | `permission_engine.py` consults user policy and prompts when needed. | **Implemented** |
| **Verification engine** | Post‑execution checks (file existence, port open, HTTP health). | `verification_engine.py` runs verification dicts attached to a request. | **Implemented** |
| **Event bus** | Pub/Sub system for all components and UI. | `event_bus.py` provides simple in‑process broker. | **Implemented** |
| **Stateful UI (Textual TUI)** | Interactive UI built on `agent‑terminal‑tui` skill. | `ui.py` + `ui_state.py` render panels and react to events. | **Implemented** |
| **FastAPI HTTP API** | `/api/execute`, `/api/history`, `/api/processes`, WS events. | `api.py` exposes endpoints using FastAPI. | **Implemented** |
| **Tool‑level logging** | Hermes‑style logs (`hermes_logging`) forwarded automatically. | `event_bus` forwards `hermes_logging` events; no duplicate instrumentation. | **Implemented** |
| **Sandbox isolation** | Optional sandbox mode that disables host‑side side‑effects. | Configurable via `terminal.backend` (Docker, SSH, Singularity, Modal, etc.). | **Implemented** |
| **Session persistence** | Tracks cwd, env, PTY fds across commands. | `session_manager.py` persists session state in SQLite. | **Implemented** |
| **Process cleanup** | Background process lifecycle management, auto‑kill on timeout. | `process_manager.py` with timeout handling and `cleanup` thread. | **Implemented** |
| **Recovery / fallback** | Automatic retry with alternative backend on failure. | `recovery_engine.py` selects fallback backend per policy. | **Implemented** |
| **Docker security hardening** | Default container runs with caps dropped, read‑only FS, limited PIDs. | Docker backend applies `--cap-drop ALL`, `--no-new-privileges`, etc. (see `Dockerfile`). | **Implemented** |
| **SSH key management** | Uses `TERMINAL_SSH_KEY` env var; integrates with SSH‑agent if present. | Backend reads env vars and falls back to agent. | **Implemented** |
| **PTY streaming** | Real‑time stdout/stderr streaming over PTY for interactive apps. | `backends/local.py` streams via Hermes notifications when `interactive=True`. | **Implemented** |
| **Background notifications** | `notify_on_complete` or pattern‑based notifications for long‑running jobs. | `process_manager` emits `execution.completed` events; UI subscribes. | **Implemented** |
| **Multi‑backend selection** | Ability to switch backends at runtime via config. | `backend_manager.py` resolves config value each request. | **Implemented** |
| **Policy‑driven risk overrides** | Customizable risk thresholds per command category. | `risk_policy.yaml` is extensible without code changes. | **Implemented** |
| **Hermes‑compatible logs** | Logs conform to Hermes log schema for downstream analysis. | `event_bus` emits structured log entries (`level`, `msg`, `source`). | **Implemented** |
| **Command verification hooks** | Optional user‑defined verification steps after execution. | `verification_engine.py` reads `verification` dict; users can plug custom checks. | **Implemented** |
| **Docker image selection** | Configurable Docker image per session. | `terminal.backend.docker_image` config key used by Docker backend. | **Implemented** |
| **SSH persistent shell** | `persistent_shell` flag keeps remote shell state. | SSH backend respects `persistent_shell` in config. | **Implemented** |
| **Background PTY support** | Running interactive programs in background (e.g., `tmux`). | Not directly needed – background PTY not supported (Hermes skips dangerous‑command check for Docker/SSH only). | **Missing** |

---

## Notes

* The **background PTY** row is the only missing feature. Hermes allows background execution for non‑interactive commands, but interactive PTY sessions must run in the foreground (see Hermes capability matrix where Docker/SSH backends skip the dangerous‑command check for background PTY). MOON currently follows this model and does **not** provide a safe background PTY implementation.
* All other capabilities listed in the Hermes documentation (local, Docker, SSH, PTY, background, risk/permission, verification, event bus, API, UI) are fully present in MOON, either as a direct implementation or an enhancement (e.g., additional risk policies, verification hooks).
* The matrix is generated from the **Hermes audit** (`references/terminal_whole_project_audit.md`) and the MOON source code (`app/terminal/*`).

---

*Optional PDF*: `pandoc docs/hermes_compatibility.md -o docs/hermes_compatibility.pdf` (install `pandoc` locally if desired).
