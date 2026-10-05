# MOON Terminal Documentation

## Architecture Overview

The terminal subsystem sits between the **MOON AI Brain** (the orchestrator) and the user/operator. It consists of a set of well‑defined components wired together via an **event bus**.

```
                         ┌─────────────────────┐
                         │   MOON AI BRAIN    │
                         │ (Orchestrator)     │
                         └───────┬───────────┘
                                 │
                TOOL ROUTER →   │
                                 ▼
                      Execution Orchestrator
                                 │
        ┌───────────────────────┼─────────────────────┐
        │                       │                     │
        ▼                       ▼                     ▼
 Terminal Engine          Python Executor       Process Manager
        │                       │                     │
        ▼                       ▼                     ▼
   Backend Manager            │                │
  ┌─────┼──────┐               │          ┌─────────┼─────────┐
  │     │      │               │          │         │         │
  ▼     ▼      ▼               ▼          ▼         ▼         ▼
Local  Docker  SSH          PTY Manager  RiskEngine  PermissionEngine
Backend Backend Backend      (interactive) (risk calc) (policy enforcement)
```

### Core Interfaces

*`ExecutionRequest`* (in `app/terminal/models.py`)
```python
class ExecutionRequest(BaseModel):
    command: str
    cwd: Optional[Path] = None
    env: Optional[Mapping[str, str]] = None
    backend: Literal["local", "docker", "ssh"] = "local"
    shell: bool = False
    timeout: Optional[int] = 60
    background: bool = False
    interactive: bool = False   # PTY support
    permission_mode: Literal["auto", "ask", "deny"] = "ask"
    verification: Optional[Dict] = None
```

*`ExecutionResult`* – captures stdout, stderr, exit code, timing, verification flag, etc.

### Modules
| Module | Responsibility |
|--------|-----------------|
| `backend_manager.py` | Resolve backend name → concrete backend class and forward `execute`. |
| `backends/local.py` | Wraps `hermes_tools.terminal` for local execution; supports PTY, background, streaming. |
| `backends/docker.py` | Wrapper around `hermes_tools.docker`. |
| `backends/ssh.py` | Wrapper around `hermes_tools.ssh`. |
| `session_manager.py` | Create/list/attach/detach sessions; persists cwd, env, PTY fds. |
| `pty_manager.py` | Provides a PTY file descriptor using Hermes PTY support. |
| `process_manager.py` | Tracks background processes (PID, start‑time, status). |
| `risk_engine.py` | Loads `risk_policy.yaml`, computes a risk level for a request. |
| `permission_engine.py` | Enforces `auto/ask/deny` based on risk level and user policy. |
| `verification_engine.py` | Runs post‑execution checks (file exists, port open, HTTP health). |
| `recovery_engine.py` | Policy‑driven retries, fallback backend selection, dependency install. |
| `event_bus.py` | Simple pub/sub used by all components and the UI. |
| `ui_state.py` | Finite‑state machine representing UI states (idle, listening, planning, …). |
| `ui.py` | Textual UI built on the `agent-terminal-tui` skill; consumes events and renders panels. |
| `api.py` | FastAPI router exposing session/execute/process endpoints and a WebSocket for UI streaming. |
| `history.py` | Persists `ExecutionResult` rows to SQLite (`history.db`). |

### Data Flow Example
1. User types `!git status` in the UI.  
2. UI sends a raw request to the Orchestrator → IntentDetector identifies a *direct‑shell* intent.  
3. Planner creates an `ExecutionRequest` with `backend="local"`, `shell=True`, `permission_mode="ask"`.  
4. **RiskEngine** scores the command as *LOW*.  
5. **PermissionEngine** auto‑approves (policy `auto_low`).  
6. **BackendManager → LocalBackend** runs the command via Hermes `terminal` (background = False).  
7. **VerificationEngine** runs a `git status`‑specific check (ensures repo is clean).  
8. Result stored in **ExecutionHistory** and emitted as `execution.completed`.  
9. UI receives the event, updates its state to **SUCCESS**, and displays formatted output.

## Usage Guide

```bash
# Basic launch – opens the interactive TUI
python -m moon terminal

# Shortcut – the default `python -m moon` also starts the terminal
python -m moon
```

### Commands
| Command | Purpose |
|--------|---------|
| `!<cmd>` | Execute a shell command directly (e.g. `!ls -la`). |
| `!run "<task>"` | Run a named task (calls the planner). |
| `!bg <cmd>` | Run `<cmd>` in background; a UUID is returned and you can later query status. |
| `!kill <execution_id>` | Cancel a background process. |
| `!logs <execution_id>` | Retrieve stdout/stderr of a finished execution. |
| `!risk <cmd>` | Show the risk score that would be assigned. |
| `!verify <execution_id>` | Force verification checks on a completed execution. |

All commands are routed through the same event‑bus architecture, so custom plugins can add additional intents.

## API Reference

The terminal also exposes a JSON‑over‑HTTP API (used by the UI and external tools).

* **POST `/api/execute`** – Body: `ExecutionRequest`. Returns an `ExecutionResult` (or an execution ID for background runs).
* **GET `/api/history/{id}`** – Retrieve a stored `ExecutionResult`.
* **GET `/api/processes`** – List currently running background processes.
* **WebSocket `/ws/events`** – Stream `execution.*` and UI state events.

All API endpoints ultimately call the same backend implementations described above.

---

## Compatibility with Hermes
* All command execution uses **Hermes tools** (`hermes_tools.terminal`, `hermes_tools.docker`, `hermes_tools.ssh`).
* The design mirrors Hermes’ capability matrix, extending it with explicit **risk/permission** and a **stateful UI**.

---

*Optional PDF*: `pandoc docs/terminal.md -o docs/terminal.pdf` (install `pandoc` if desired).
