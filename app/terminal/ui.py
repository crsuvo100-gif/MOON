"""Professional MOON Terminal UI.

A full-featured terminal interface with:
- Terminal frame (header, session bar, output, input, status bar)
- State display (idle, executing, permission, verifying, recovering, success, error)
- Live output streaming
- Command input with history
- Process panel
- Session panel
- Permission dialog
- Event-driven updates

Usage:
    python -m app.terminal.ui
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Tab,
    TabbedContent,
    Tabs,
)
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.binding import Binding
from textual import events

from .event_bus import Event, subscribe, publish, get_bus
from .state_machine import ExecutionState
from .terminal_interface import terminal_interface
from .models import ExecutionResult


# ── State display text ──

_STATE_DISPLAY: Dict[ExecutionState, tuple[str, str]] = {
    ExecutionState.IDLE: ("● READY", "#00ff88"),
    ExecutionState.PLANNING: ("◌ PLANNING", "#ffaa00"),
    ExecutionState.WAITING_PERMISSION: ("⚠ PERMISSION REQUIRED", "#ffaa00"),
    ExecutionState.STARTING: ("● STARTING", "#ffaa00"),
    ExecutionState.RUNNING: ("● EXECUTING", "#00ff88"),
    ExecutionState.VERIFYING: ("◌ VERIFYING", "#ffaa00"),
    ExecutionState.RECOVERING: ("↻ RECOVERING", "#ffaa00"),
    ExecutionState.COMPLETED: ("✓ COMPLETED", "#00ff88"),
    ExecutionState.FAILED: ("× FAILED", "#ff4444"),
    ExecutionState.CANCELLED: ("× CANCELLED", "#ff4444"),
    ExecutionState.TIMED_OUT: ("× TIMED OUT", "#ff4444"),
    ExecutionState.DENIED: ("× DENIED", "#ff4444"),
}


class StatusBar(Static):
    """Bottom status bar showing system info."""

    cpu_usage = reactive("CPU --%")
    ram_usage = reactive("RAM --MB")
    process_count = reactive("PROCESS 0")
    session_status = reactive("SESSION ACTIVE")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._update_text()

    def _update_text(self):
        self.update(
            f" {self.cpu_usage}  {self.ram_usage}  {self.process_count}  {self.session_status} "
        )

    def watch_cpu_usage(self, value):
        self._update_text()

    def watch_ram_usage(self, value):
        self._update_text()

    def watch_process_count(self, value):
        self._update_text()

    def watch_session_status(self, value):
        self._update_text()


class OutputDisplay(Static):
    """Main output display area."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._lines: List[str] = []
        self._max_lines = 1000

    def add_line(self, text: str, css_class: str = ""):
        """Add a line to the output."""
        if css_class:
            self._lines.append(f"[{css_class}]{text}[/{css_class}]")
        else:
            self._lines.append(text)
        # Trim to max lines
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines:]
        self.update("\n".join(self._lines))

    def add_text(self, text: str):
        """Add raw text (may contain newlines)."""
        for line in text.splitlines():
            self.add_line(line)

    def clear(self):
        """Clear all output."""
        self._lines.clear()
        self.update("")

    def scroll_to_bottom(self):
        """Scroll to bottom of output."""
        pass  # Textual handles this automatically


class ProcessPanel(Static):
    """Side panel showing running processes."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._processes: List[Dict] = []

    def update_processes(self, processes: List[Dict]):
        """Update the process list."""
        self._processes = processes
        if not processes:
            self.update("No running processes")
            return
        lines = ["RUNNING PROCESSES", ""]
        for proc in processes:
            pid = proc.get("pid", "?")
            name = proc.get("command", "unknown")[:20]
            status = proc.get("status", "?")
            lines.append(f"  PID {pid}  {name}  {status}")
        self.update("\n".join(lines))


class SessionPanel(Static):
    """Side panel showing terminal sessions."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._sessions: List[Dict] = []

    def update_sessions(self, sessions: List[Dict]):
        """Update the session list."""
        self._sessions = sessions
        if not sessions:
            self.update("No active sessions")
            return
        lines = ["SESSIONS", ""]
        for sess in sessions:
            name = sess.get("name", sess.get("session_id", "?")[:8])
            shell = sess.get("shell", "?")
            cwd = sess.get("cwd", "?")
            active = "●" if sess.get("active") else "○"
            lines.append(f"  {active} {name}  {shell}  {cwd}")
        self.update("\n".join(lines))


class PermissionDialog(Container):
    """Modal dialog for permission requests."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._command = ""
        self._risk = ""
        self._effect = ""

    def compose(self) -> ComposeResult:
        yield Label("⚠ MOON PERMISSION REQUIRED", id="perm-title")
        yield Label("", id="perm-command")
        yield Label("", id="perm-risk")
        yield Label("", id="perm-effect")
        with Horizontal(id="perm-buttons"):
            yield Button("ALLOW", id="perm-allow", variant="success")
            yield Button("DENY", id="perm-deny", variant="error")

    def set_permission_request(self, command: str, risk: str, effect: str = ""):
        """Set the permission request details."""
        self._command = command
        self._risk = risk
        self._effect = effect
        try:
            self.query_one("#perm-command", Label).update(f"Command: {command}")
            self.query_one("#perm-risk", Label).update(f"Risk: {risk}")
            self.query_one("#perm-effect", Label).update(f"Effect: {effect}")
        except NoMatches:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button presses."""
        if event.button.id == "perm-allow":
            self.app._handle_permission_response(True)
        elif event.button.id == "perm-deny":
            self.app._handle_permission_response(False)


class TerminalFrame(Container):
    """Main terminal frame with all components."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_state = ExecutionState.IDLE
        self._output_lines: List[str] = []
        self._history: List[str] = []
        self._history_index = 0
        self._command = ""
        self._session_id: Optional[str] = None
        self._processes: List[Dict] = []
        self._sessions: List[Dict] = []
        self._permission_pending = False

    def compose(self) -> ComposeResult:
        # Header bar
        with Horizontal(id="header-bar"):
            yield Label(" MOON TERMINAL ", id="header-title")
            yield Label("● CONNECTED", id="header-status")

        # Session bar
        with Horizontal(id="session-bar"):
            yield Label("Local • SH • /home/meow/Projects/MOON", id="session-info")

        # Main content area
        with Horizontal(id="main-content"):
            # Session panel (left)
            yield SessionPanel(id="session-panel")

            # Output area (center)
            with Vertical(id="output-container"):
                yield OutputDisplay(id="output-text")

            # Process panel (right)
            yield ProcessPanel(id="process-panel")

        # Input area
        with Horizontal(id="input-container"):
            yield Label(" $ ", id="input-prompt")
            yield Input(placeholder="Enter command...", id="command-input")

        # Status bar
        yield StatusBar(id="status-bar")

    def on_mount(self):
        """Initialize the terminal frame."""
        # Subscribe to events
        self._subscribe_events()

        # Create default session
        try:
            session = terminal_interface.create_session(
                shell=terminal_interface.get_default_shell(),
                cwd=Path.cwd(),
                name="moon-local",
            )
            self._session_id = session.session_id
            self._update_session_info()
        except Exception:
            pass

        # Show initial state
        self._set_state(ExecutionState.IDLE)

        # Focus input
        try:
            self.query_one("#command-input", Input).focus()
        except NoMatches:
            pass

    def _subscribe_events(self):
        """Subscribe to terminal events."""
        bus = get_bus()
        bus.subscribe("terminal.execution.started", self._on_execution_started)
        bus.subscribe("terminal.execution.completed", self._on_execution_completed)
        bus.subscribe("terminal.execution.failed", self._on_execution_failed)
        bus.subscribe("terminal.permission.required", self._on_permission_required)
        bus.subscribe("terminal.process.started", self._on_process_started)
        bus.subscribe("terminal.process.stopped", self._on_process_stopped)
        bus.subscribe("terminal.session.created", self._on_session_created)
        bus.subscribe("terminal.session.closed", self._on_session_closed)

    def _set_state(self, state: ExecutionState):
        """Update the display state."""
        self._current_state = state
        text, color = _STATE_DISPLAY.get(state, ("? UNKNOWN", "#888888"))
        try:
            self.query_one("#header-status", Label).update(f" {text} ")
        except NoMatches:
            pass

    def _update_session_info(self):
        """Update the session info display."""
        try:
            if self._session_id:
                session = terminal_interface.get_session(self._session_id)
                if session:
                    shell = session.shell.upper()
                    cwd = str(session.cwd)
                    name = session.name or session.session_id[:8]
                    info = f" {name} • {shell} • {cwd} "
                else:
                    info = " No session "
            else:
                info = " No session "
            self.query_one("#session-info", Label).update(info)
        except NoMatches:
            pass

    def _on_execution_started(self, payload: Any):
        """Handle execution started event."""
        if isinstance(payload, dict):
            command = payload.get("command", "")
            self._add_output(f"$ {command}", "command")
            self._set_state(ExecutionState.RUNNING)

    def _on_execution_completed(self, payload: Any):
        """Handle execution completed event."""
        if isinstance(payload, dict):
            result = payload.get("result", {})
            if isinstance(result, dict):
                status = result.get("status", "")
                exit_code = result.get("exit_code")
                duration = result.get("duration", 0)
                if status == "success":
                    self._set_state(ExecutionState.COMPLETED)
                    self._add_output(f"✓ Completed (exit {exit_code}, {duration:.2f}s)", "success")
                else:
                    self._set_state(ExecutionState.FAILED)
                    self._add_output(f"× Failed (exit {exit_code})", "error")

    def _on_execution_failed(self, payload: Any):
        """Handle execution failed event."""
        if isinstance(payload, dict):
            error = payload.get("error", "Unknown error")
            self._set_state(ExecutionState.FAILED)
            self._add_output(f"× Error: {error}", "error")

    def _on_permission_required(self, payload: Any):
        """Handle permission required event."""
        if isinstance(payload, dict):
            command = payload.get("command", "")
            risk = payload.get("risk", "HIGH")
            self._set_state(ExecutionState.WAITING_PERMISSION)
            self._add_output(f"⚠ Permission required for: {command}", "status")
            self._add_output(f"  Risk: {risk}", "status")
            self._permission_pending = True

    def _on_process_started(self, payload: Any):
        """Handle process started event."""
        if isinstance(payload, dict):
            self._add_output(f"● Process started: {payload.get('command', '')}", "system")
            self._update_processes()

    def _on_process_stopped(self, payload: Any):
        """Handle process stopped event."""
        if isinstance(payload, dict):
            self._add_output(f"○ Process stopped: {payload.get('execution_id', '')[:8]}", "system")
            self._update_processes()

    def _on_session_created(self, payload: Any):
        """Handle session created event."""
        if isinstance(payload, dict):
            self._add_output(f"● Session created: {payload.get('session_id', '')[:8]}", "system")
            self._update_sessions()

    def _on_session_closed(self, payload: Any):
        """Handle session closed event."""
        if isinstance(payload, dict):
            self._add_output(f"○ Session closed: {payload.get('session_id', '')[:8]}", "system")
            self._update_sessions()

    def _add_output(self, text: str, css_class: str = ""):
        """Add output text."""
        try:
            output = self.query_one("#output-text", OutputDisplay)
            output.add_line(text, css_class)
        except NoMatches:
            pass

    def _update_processes(self):
        """Update the process panel."""
        try:
            processes = terminal_interface.list_processes()
            panel = self.query_one("#process-panel", ProcessPanel)
            panel.update_processes([p.dict() for p in processes])
        except NoMatches:
            pass

    def _update_sessions(self):
        """Update the session panel."""
        try:
            sessions = terminal_interface.list_sessions()
            panel = self.query_one("#session-panel", SessionPanel)
            panel.update_sessions([s.to_dict() for s in sessions])
        except NoMatches:
            pass

    def on_input_submitted(self, event: Input.Submitted):
        """Handle command input."""
        if event.input.id == "command-input":
            command = event.input.value.strip()
            if command:
                self._history.append(command)
                self._history_index = len(self._history)
                self._execute_command(command)
                event.input.value = ""

    def on_key(self, event: events.Key):
        """Handle key presses."""
        if event.key == "ctrl+c":
            # Cancel current execution
            self._add_output("^C", "system")
        elif event.key == "ctrl+l":
            # Clear output
            try:
                self.query_one("#output-text", OutputDisplay).clear()
            except NoMatches:
                pass
        elif event.key == "up":
            # History up
            if self._history and self._history_index > 0:
                self._history_index -= 1
                try:
                    self.query_one("#command-input", Input).value = self._history[self._history_index]
                except NoMatches:
                    pass
        elif event.key == "down":
            # History down
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                try:
                    self.query_one("#command-input", Input).value = self._history[self._history_index]
                except NoMatches:
                    pass
            else:
                self._history_index = len(self._history)
                try:
                    self.query_one("#command-input", Input).value = ""
                except NoMatches:
                    pass

    def _execute_command(self, command: str):
        """Execute a command."""
        self._set_state(ExecutionState.RUNNING)
        self._add_output(f"$ {command}", "command")

        try:
            result = terminal_interface.execute(
                command=command,
                session_id=self._session_id,
                on_output=lambda text: self._add_output(text),
            )
            if result.status == "success":
                self._set_state(ExecutionState.COMPLETED)
                self._add_output(f"✓ Completed (exit {result.exit_code}, {result.duration:.2f}s)", "success")
            else:
                self._set_state(ExecutionState.FAILED)
                self._add_output(f"× Failed: {result.error or 'Unknown error'}", "error")
        except Exception as e:
            self._set_state(ExecutionState.FAILED)
            self._add_output(f"× Error: {e}", "error")

    def _handle_permission_response(self, allowed: bool):
        """Handle permission dialog response."""
        self._permission_pending = False
        if allowed:
            self._add_output("✓ Permission granted", "success")
        else:
            self._add_output("× Permission denied", "error")
            self._set_state(ExecutionState.DENIED)


class MoonTerminalApp(App):
    """Main MOON Terminal application."""

    CSS_PATH = "ui.css"
    BINDINGS = [
        Binding("ctrl+c", "cancel", "Cancel"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._terminal_frame: Optional[TerminalFrame] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TerminalFrame(id="terminal-frame")
        yield Footer()

    def on_mount(self):
        """Initialize the app."""
        try:
            self._terminal_frame = self.query_one("#terminal-frame", TerminalFrame)
        except NoMatches:
            pass

    def action_cancel(self):
        """Cancel current execution."""
        if self._terminal_frame:
            self._terminal_frame._add_output("^C", "system")

    def action_clear(self):
        """Clear output."""
        if self._terminal_frame:
            try:
                self._terminal_frame.query_one("#output-text", OutputDisplay).clear()
            except NoMatches:
                pass

    def _handle_permission_response(self, allowed: bool):
        """Handle permission dialog response."""
        if self._terminal_frame:
            self._terminal_frame._handle_permission_response(allowed)


def main():
    """Run the MOON Terminal UI."""
    app = MoonTerminalApp()
    app.run()


if __name__ == "__main__":
    main()
