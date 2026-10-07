# MOON Terminal — Architecture & Usage

## Overview

MOON Terminal is a production-grade AI-agent execution subsystem that provides:
- Real terminal execution with streaming, background, and PTY support
- Persistent sessions with shell state
- Process management for background tasks
- Risk analysis and permission system
- Verification and recovery engines
- Professional terminal UI
- Full agent integration

## Architecture

```
MOON AI BRAIN
    │
TOOL ROUTER
    │
EXECUTION ORCHESTRATOR (ExecutionEngine)
    │
    ├── TERMINAL ENGINE (backends/local.py)
    │   └── LocalBackend (streaming, background, PTY)
    │
    ├── PYTHON EXECUTOR (python_executor.py)
    │   └── PythonExecutor (code, modules, scripts, pip)
    │
    └── PROCESS MANAGER (process_manager.py)
        └── ProcessManager (background process tracking)

BACKEND MANAGER
    ├── LocalBackend
    ├── DockerBackend
    └── SSHBackend

OUTPUT STREAM → VERIFICATION → RECOVERY → RESULT ENGINE → MOON AGENT → TERMINAL UI
```

## Components

### ExecutionEngine (`execution_engine.py`)
Orchestrates the full execution pipeline:
1. Risk evaluation
2. Permission check
3. Backend selection
4. Execution (foreground/background/interactive)
5. Verification
6. Recovery on failure
7. History recording
8. Event emission

### TerminalInterface (`terminal_interface.py`)
Unified API for all terminal operations:
- `execute()` — execute a command
- `create_session()` / `list_sessions()` / `close_session()` — session management
- `start_background()` / `list_processes()` / `stop_process()` — process management
- `start_pty()` / `send_input()` / `resize_pty()` — interactive terminal
- `get_history()` / `search_history()` — execution history
- `get_status()` — system status

### Backends (`backends/`)
- **LocalBackend** — local shell execution with streaming, background, PTY
- **DockerBackend** — container execution with isolation and resource limits
- **SSHBackend** — remote execution via SSH

### Session Manager (`session_manager.py`)
Persistent terminal sessions with:
- Shell detection (bash, sh, zsh, fish)
- Working directory tracking
- Environment variables
- Session state (active/inactive)

### Process Manager (`process_manager.py`)
Background process tracking:
- Start/stop/kill/restart
- Process status monitoring
- Output capture

### PTY Manager (`pty_manager.py`)
Interactive terminal support:
- Real PTY via `pty` module
- Interactive input/output
- Terminal resizing
- Session management

### Environment Manager (`environment_manager.py`)
Shell and environment management:
- Shell detection
- Environment variable handling
- Secret redaction
- Git state detection

### Risk Engine (`risk_engine.py`)
Command risk classification:
- SAFE / LOW / MEDIUM / HIGH / CRITICAL
- Pattern-based analysis
- Configurable rules

### Permission Engine (`permission_engine.py`)
Permission policies:
- AUTO / ASK / DENY modes
- YAML-based policy files
- Pattern matching

### Verification Engine (`verification_engine.py`)
Post-execution verification:
- File existence
- Process existence
- Port availability
- HTTP health check
- Python import
- Test suite
- Git status
- Custom verification

### Recovery Engine (`recovery_engine.py`)
Failure recovery:
- Retry
- Change command
- Install dependency
- Activate environment
- Change CWD
- Restart service
- Ask user
- Stop

### State Machine (`state_machine.py`)
Execution state tracking:
- IDLE → PLANNING → WAITING_PERMISSION → STARTING → RUNNING → VERIFYING → COMPLETED
- RECOVERING → FAILED / CANCELLED / TIMED_OUT / DENIED

### Event Bus (`event_bus.py`)
Typed event system:
- terminal.session.created/closed
- terminal.execution.started/completed/failed
- terminal.process.started/stopped
- terminal.permission.required
- terminal.verification.started/completed
- terminal.recovery.started/completed

### History Manager (`history_manager.py`)
Execution history with persistence:
- Recent commands
- Search
- Filter by status
- Session history

### Python Executor (`python_executor.py`)
Specialized Python execution:
- Code execution
- Module execution (python -m)
- Script execution
- pip install
- Import checking
- Test execution

### Security (`security.py`)
Security utilities:
- Command sanitization
- Secret redaction
- Path traversal protection

### Output Engine (`output_engine.py`)
Output buffering and streaming:
- In-memory buffering
- Persistent rotating logs
- Stream pagination

### Terminal UI (`ui.py`)
Professional terminal interface:
- Terminal frame (header, session bar, output, input, status bar)
- State display (idle, executing, permission, verifying, recovering, success, error)
- Live output streaming
- Command input with history
- Process panel
- Session panel
- Permission dialog

## Usage

### Basic Execution
```python
from app.terminal import terminal_interface

result = terminal_interface.execute("ls -la")
print(result.stdout)
```

### Session Management
```python
session = terminal_interface.create_session(shell="zsh", name="dev")
result = terminal_interface.execute("git status", session_id=session.session_id)
```

### Background Process
```python
exec_id = terminal_interface.start_background("python -m http.server 8080")
procs = terminal_interface.list_processes()
```

### Interactive PTY
```python
pty_id = terminal_interface.start_pty("python3")
terminal_interface.send_input(pty_id, "print('hello')\n")
terminal_interface.stop_pty(pty_id)
```

### Streaming Output
```python
exec_id, subscribe = terminal_interface.execute_streaming("npm install")
result = subscribe(lambda text: print(text, end=""))
```

### Python Execution
```python
from app.terminal.python_executor import python_executor

result = python_executor.execute_code("print('hello')")
python_executor.install_package("requests")
python_executor.run_tests()
```

## Testing
```bash
python -m pytest tests/test_terminal.py -v
```

## Configuration

### Permission Policy
Create `permission_policy.yaml` in the project root:
```yaml
- pattern: "*rm *"
  action: ask
- pattern: "*mkfs *"
  action: deny
- pattern: "*"
  action: allow
```

### SSH Backend
Set environment variables:
```bash
export MOON_SSH_HOST=remote.example.com
export MOON_SSH_PORT=22
export MOON_SSH_USER=myuser
export MOON_SSH_KEY=/path/to/key
```

## Entry Points

1. **Terminal UI**: `python -m app.terminal.ui`
2. **Python API**: `from app.terminal import terminal_interface`
3. **Agent Tool**: `TerminalTool` (registered in tool registry)
