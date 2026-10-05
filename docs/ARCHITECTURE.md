# MOON Terminal Architecture

## Overview
The terminal subsystem sits between the **MOON AI Brain** (the orchestrator) and the user/operator.  It consists of a set of well‑defined components that are wired together via an **event bus**.

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
   Backend Manager            │                     │
  ┌─────┼──────┐               │           ┌─────────┼─────────┐
  │     │      │               │           │         │         │
  ▼     ▼      ▼               ▼           ▼         ▼         ▼
Local  Docker  SSH          PTY Manager  RiskEngine  PermissionEngine
Backend Backend Backend      (interactive) (risk calc) (policy enforcement)
```

## Core Interfaces
### ExecutionRequest (app/terminal/models.py)
```python
class ExecutionRequest(BaseModel):
    command: str                       # raw command string
    cwd: Optional[Path] = None
    env: Optional[Mapping[str, str]] = None
    backend: Literal["local", "docker", "ssh"] = "local"
    shell: bool = False               # run via /bin/sh – allows pipelines
    timeout: Optional[int] = 60
    background: bool = False
    interactive: bool = False         # requires PTY
    permission_mode: Literal["auto", "ask", "deny"] = "ask"
    verification: Optional[Dict] = None
```

### ExecutionResult
```python
class ExecutionResult(BaseModel):
    execution_id: str
    command: str
    backend: str
    cwd: Path
    status: Literal["success", "failed", "cancelled", "timed_out", "denied"]
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    pid: Optional[int] = None
    duration: float
    verified: bool = False
    verification_result: Optional[Dict] = None
    error: Optional[str] = None
```

## Modules
| Module | Responsibility |
|--------|----------------|
| `backend_manager.py` | Resolve backend name → concrete backend class and forward `execute`. |
| `backends/local.py` | Wraps `hermes_tools.terminal` for local execution; supports PTY, background, streaming. |
| `backends/docker.py` | Optional wrapper around `hermes_tools.docker`. |
| `backends/ssh.py` | Optional wrapper around `hermes_tools.ssh`. |
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

## Data Flow Example
1. **User types** `!git status` in the UI.
2. UI sends a raw request to **Orchestrator** → **IntentDetector** identifies a *direct‑shell* intent.
3. Planner creates an **ExecutionRequest** with `backend="local"`, `shell=True`, `permission_mode="ask"`.
4. **RiskEngine** scores the command as *LOW*.
5. **PermissionEngine** auto‑approves (policy `auto_low`).
6. **BackendManager → LocalBackend** runs the command via Hermes `terminal` (background=False).
7. **VerificationEngine** runs a `git status`‑specific check (ensures repo is clean).
8. **Result** is stored in **ExecutionHistory** and emitted as `execution.completed`.
9. UI receives the event, updates its state to **SUCCESS**, and displays the formatted output.

---

## Extensibility
* Adding a new backend only requires implementing the same `Backend` interface (`execute(request)`).
* New risk categories can be added to `risk_policy.yaml` without code changes – the engine loads the YAML at start‑up.
* UI panels are decoupled via the event bus; adding a new panel just subscribes to relevant events.

---

## Compatibility with Hermes
* All actual command execution uses **Hermes tools** (`hermes_tools.terminal`, `hermes_tools.docker`, `hermes_tools.ssh`).
* The event bus forwards Hermes logs (`hermes_logging`) so no duplicate instrumentation is needed.
* The design mirrors Hermes’ capability matrix, extending it with explicit **risk/permission** and a **stateful UI**.

---

## Next Implementation Steps
1. Add `app/terminal/models.py` with the two Pydantic classes above.
2. Implement `backend_manager.py` and the `LocalBackend` stub.
3. Write unit tests for a simple foreground command (`echo hello`).
4. Build the event bus and verify that a publish/subscribe round‑trip works.
5. Progressively add PTY, background, risk, permission, verification, UI, and API.
"