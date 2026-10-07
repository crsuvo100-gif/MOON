"""Terminal interface — unified API for the MOON terminal system.

This is the main entry point for UI, agent, and API consumers.
It wires together all terminal subsystems:
- ExecutionEngine (execution pipeline)
- SessionManager (persistent sessions)
- ProcessManager (background processes)
- PTYManager (interactive terminals)
- EnvironmentManager (shell/env detection)
- HistoryManager (execution history)
- VerificationEngine (post-execution verification)
- RecoveryEngine (failure recovery)
- EventBus (typed events)
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

from .models import ExecutionRequest, ExecutionResult
from .execution_engine import execution_engine
from .session_manager import SessionManager, Session
from .process_manager import process_manager, ProcessInfo
from .pty_manager import pty_manager
from .environment_manager import environment_manager
from .history_manager import history_manager, HistoryEntry
from .event_bus import get_bus, Event
from .state_machine import ExecutionState


class TerminalInterface:
    """Unified terminal API for MOON.

    Usage:
        terminal = TerminalInterface()

        # Execute a command
        result = terminal.execute("ls -la")

        # Create a persistent session
        session = terminal.create_session(shell="zsh")

        # Execute in a session
        result = terminal.execute("git status", session_id=session.session_id)

        # Start a background process
        exec_id = terminal.start_background("python -m http.server 8080")

        # Start an interactive PTY session
        pty_id = terminal.start_pty("python3")

        # Send input to PTY
        terminal.send_input(pty_id, "print('hello')\\n")

        # List processes
        procs = terminal.list_processes()

        # Get execution history
        history = terminal.get_history(count=20)
    """

    def __init__(self):
        self.engine = execution_engine
        self.sessions = SessionManager()
        self.processes = process_manager
        self.ptys = pty_manager
        self.env = environment_manager
        self.history = history_manager
        self.bus = get_bus()

    # ── Execution ──

    def execute(
        self,
        command: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        backend: Literal["local", "docker", "ssh"] = "local",
        shell: bool = False,
        timeout: int = 60,
        background: bool = False,
        interactive: bool = False,
        permission_mode: Literal["auto", "ask", "deny"] = "ask",
        verification: Optional[Dict] = None,
        session_id: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a command through the full pipeline."""
        req = ExecutionRequest(
            command=command,
            cwd=cwd,
            env=env,
            backend=backend,
            shell=shell,
            timeout=timeout,
            background=background,
            interactive=interactive,
            permission_mode=permission_mode,
            verification=verification,
        )
        return self.engine.execute(req, session_id=session_id, on_output=on_output)

    def execute_streaming(
        self,
        command: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        backend: Literal["local", "docker", "ssh"] = "local",
        shell: bool = False,
        timeout: int = 60,
        permission_mode: Literal["auto", "ask", "deny"] = "ask",
        verification: Optional[Dict] = None,
        session_id: Optional[str] = None,
    ) -> tuple[str, Callable[[Callable[[str], None]], ExecutionResult]]:
        """Execute with streaming output.

        Returns (execution_id, subscribe_fn). Call subscribe_fn with an
        on_output callback to start execution and receive streaming output.
        """
        req = ExecutionRequest(
            command=command,
            cwd=cwd,
            env=env,
            backend=backend,
            shell=shell,
            timeout=timeout,
            background=False,
            interactive=False,
            permission_mode=permission_mode,
            verification=verification,
        )
        return self.engine.execute_streaming(req, session_id=session_id)

    # ── Sessions ──

    def create_session(
        self,
        shell: Optional[str] = None,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        name: str = "",
    ) -> Session:
        """Create a new terminal session."""
        if shell is None:
            shell = self.env.detect_default_shell()
        session = self.sessions.create_session(shell=shell, cwd=cwd, env=env)
        if name:
            self.sessions.rename_session(session.session_id, name)
            session.name = name
        self.bus.emit("terminal.session.created", {
            "session_id": session.session_id,
            "shell": shell,
            "cwd": str(session.cwd),
        })
        return session

    def list_sessions(self) -> List[Session]:
        """List all sessions."""
        return self.sessions.list_sessions()

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get_session(session_id)

    def close_session(self, session_id: str):
        """Close a session."""
        self.sessions.close_session(session_id)
        self.bus.emit("terminal.session.closed", {"session_id": session_id})

    def rename_session(self, session_id: str, name: str):
        """Rename a session."""
        self.sessions.rename_session(session_id, name)

    # ── Background Processes ──

    def start_background(
        self,
        command: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        backend: Literal["local", "docker", "ssh"] = "local",
        shell: bool = False,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Start a background process. Returns execution_id."""
        req = ExecutionRequest(
            command=command,
            cwd=cwd,
            env=env,
            backend=backend,
            shell=shell,
            timeout=None,
            background=True,
            interactive=False,
            permission_mode="auto",
            verification=None,
        )
        backend_obj = self.engine.backend_manager.get_backend(backend)  # type: ignore[arg-type]
        if hasattr(backend_obj, 'start_background'):
            exec_id = backend_obj.start_background(req, on_output=on_output)
            self.bus.emit("terminal.process.started", {
                "execution_id": exec_id,
                "command": command,
                "backend": backend,
            })
            return exec_id
        else:
            # Fallback: use process_manager
            exec_id = self.processes.start_process(req)
            self.bus.emit("terminal.process.started", {
                "execution_id": exec_id,
                "command": command,
                "backend": backend,
            })
            return exec_id

    def list_processes(self) -> List[ProcessInfo]:
        """List all tracked processes."""
        return self.processes.list_processes()

    def get_process(self, execution_id: str) -> Optional[ProcessInfo]:
        """Get process info by execution_id."""
        return self.processes.get_process(execution_id)

    def stop_process(self, execution_id: str):
        """Stop a process."""
        self.processes.stop_process(execution_id)
        self.bus.emit("terminal.process.stopped", {"execution_id": execution_id})

    def kill_process(self, execution_id: str):
        """Kill a process."""
        self.processes.kill_process(execution_id)
        self.bus.emit("terminal.process.stopped", {"execution_id": execution_id})

    def get_process_logs(self, execution_id: str) -> Dict[str, str]:
        """Get logs for a background process."""
        backend_obj = self.engine.backend_manager.get_backend("local")
        if hasattr(backend_obj, 'get_background_logs'):
            return backend_obj.get_background_logs(execution_id)
        proc = self.processes.get_process(execution_id)
        if proc:
            return {"stdout": proc.stdout or "", "stderr": proc.stderr or ""}
        return {"stdout": "", "stderr": ""}

    # ── PTY / Interactive ──

    def start_pty(
        self,
        command: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Start an interactive PTY session. Returns execution_id."""
        req = ExecutionRequest(
            command=command,
            cwd=cwd,
            env=env,
            backend="local",
            shell=False,
            timeout=None,
            background=False,
            interactive=True,
            permission_mode="auto",
            verification=None,
        )
        exec_id = self.ptys.start_session(req, on_output=on_output)
        self.bus.emit("terminal.pty.started", {
            "execution_id": exec_id,
            "command": command,
        })
        return exec_id

    def send_input(self, execution_id: str, data: str) -> bool:
        """Send input to a PTY session."""
        return self.ptys.send_input(execution_id, data)

    def resize_pty(self, execution_id: str, rows: int, cols: int) -> bool:
        """Resize a PTY session."""
        return self.ptys.resize_pty(execution_id, rows, cols)

    def stop_pty(self, execution_id: str) -> bool:
        """Stop a PTY session."""
        result = self.ptys.stop_session(execution_id)
        if result:
            self.bus.emit("terminal.pty.stopped", {"execution_id": execution_id})
        return result

    def list_ptys(self) -> List[str]:
        """List active PTY session IDs."""
        return self.ptys.list_sessions()

    # ── Environment ──

    def get_available_shells(self) -> Dict[str, str]:
        """Get available shells on the system."""
        return self.env.available_shells

    def get_default_shell(self) -> str:
        """Get the default shell."""
        return self.env.detect_default_shell()

    def get_environment(self, redacted: bool = True) -> Dict[str, str]:
        """Get current environment variables."""
        if redacted:
            return self.env.get_redacted_environment()
        return self.env.get_environment()

    def get_os_info(self) -> Dict[str, str]:
        """Get OS information."""
        return self.env.get_os_info()

    def get_git_state(self, cwd: Optional[Path] = None) -> Dict[str, str]:
        """Get git repository state."""
        return self.env.get_git_state(cwd)

    # ── History ──

    def get_history(self, count: int = 20) -> List[HistoryEntry]:
        """Get recent execution history."""
        return self.history.get_recent(count)

    def search_history(self, query: str) -> List[HistoryEntry]:
        """Search execution history."""
        return self.history.search(query)

    def clear_history(self):
        """Clear execution history."""
        self.history.clear()

    # ── Verification ──

    def verify_execution(
        self,
        command: str,
        result: ExecutionResult,
        verification_spec: Dict,
    ) -> tuple[bool, Optional[Dict]]:
        """Verify an execution result."""
        req_dict = {"command": command, "verification": verification_spec}
        return self.engine.verification_engine.verify(req_dict, result.dict())

    # ── Events ──

    def subscribe(self, event: str, callback: Callable[[Any], None]):
        """Subscribe to terminal events."""
        self.bus.subscribe(event, callback)

    def unsubscribe(self, event: str, callback: Callable[[Any], None]):
        """Unsubscribe from terminal events."""
        # Note: event_bus doesn't have unsubscribe, but we can add it
        pass

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """Get overall terminal system status."""
        return {
            "shells": self.env.available_shells,
            "default_shell": self.env.detect_default_shell(),
            "sessions": len(self.sessions.list_sessions()),
            "processes": len(self.processes.list_processes()),
            "ptys": len(self.ptys.list_sessions()),
            "history_entries": len(self.history),
            "pty_available": self.ptys.is_available(),
            "os": self.env.get_os_info(),
        }


# Module-level singleton
terminal_interface = TerminalInterface()
