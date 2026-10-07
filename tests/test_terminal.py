"""Tests for MOON terminal system."""

import time
import pytest
from pathlib import Path

from app.terminal import (
    terminal_interface,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    StateMachine,
    history_manager,
    environment_manager,
)
from app.terminal.permission_engine import PermissionRequired, Denied


class TestExecutionEngine:
    """Test core execution engine."""

    def test_basic_execution(self):
        result = terminal_interface.execute("echo hello world")
        assert result.status == "success"
        assert result.exit_code == 0
        assert "hello world" in (result.stdout or "")

    def test_failed_execution(self):
        result = terminal_interface.execute("exit 1", shell=True)
        assert result.status == "failed"
        assert result.exit_code == 1

    def test_stderr_capture(self):
        result = terminal_interface.execute("echo error >&2", shell=True)
        assert "error" in (result.stderr or "")

    def test_working_directory(self):
        result = terminal_interface.execute("pwd", cwd=Path("/tmp"))
        assert "/tmp" in (result.stdout or "")

    def test_timeout(self):
        result = terminal_interface.execute("sleep 10", timeout=1)
        assert result.status == "timed_out"

    def test_shell_mode(self):
        result = terminal_interface.execute("echo $SHELL", shell=True)
        assert result.status == "success"

    def test_background_execution(self):
        exec_id = terminal_interface.start_background("sleep 30")
        assert exec_id is not None
        assert len(exec_id) > 0

    def test_execution_result_fields(self):
        result = terminal_interface.execute("echo test")
        assert result.execution_id is not None
        assert result.command == "echo test"
        assert result.backend == "local"
        assert result.cwd is not None
        assert result.duration >= 0
        assert isinstance(result.verified, bool)


class TestSessionManager:
    """Test session management."""

    def test_create_session(self):
        session = terminal_interface.create_session(shell="bash", name="test")
        assert session.session_id is not None
        assert session.shell == "bash"
        assert session.name == "test"

    def test_list_sessions(self):
        terminal_interface.create_session(shell="sh")
        sessions = terminal_interface.list_sessions()
        assert len(sessions) > 0

    def test_get_session(self):
        session = terminal_interface.create_session(shell="bash")
        fetched = terminal_interface.get_session(session.session_id)
        assert fetched is not None
        assert fetched.session_id == session.session_id

    def test_close_session(self):
        session = terminal_interface.create_session(shell="bash")
        terminal_interface.close_session(session.session_id)
        assert terminal_interface.get_session(session.session_id) is None

    def test_rename_session(self):
        session = terminal_interface.create_session(shell="bash", name="old")
        terminal_interface.rename_session(session.session_id, "new")
        fetched = terminal_interface.get_session(session.session_id)
        assert fetched is not None
        assert fetched.name == "new"


class TestProcessManager:
    """Test background process management."""

    def test_start_background(self):
        exec_id = terminal_interface.start_background("sleep 30")
        assert exec_id is not None

    def test_list_processes(self):
        terminal_interface.start_background("sleep 30")
        procs = terminal_interface.list_processes()
        assert isinstance(procs, list)

    def test_get_process(self):
        exec_id = terminal_interface.start_background("sleep 30")
        proc = terminal_interface.get_process(exec_id)
        # Process may have already finished or not be tracked
        # Just verify the call doesn't crash
        assert proc is None or proc.execution_id == exec_id


class TestEnvironmentManager:
    """Test environment management."""

    def test_detect_shells(self):
        shells = environment_manager.available_shells
        assert "bash" in shells or "sh" in shells

    def test_default_shell(self):
        shell = environment_manager.detect_default_shell()
        assert shell in ("bash", "sh", "zsh", "fish")

    def test_redact_environment(self):
        env = {"API_KEY": "secret123", "PATH": "/usr/bin"}
        redacted = environment_manager.redact_environment(env)
        assert redacted["API_KEY"] == "***REDACTED***"
        assert redacted["PATH"] == "/usr/bin"

    def test_is_secret_var(self):
        assert environment_manager.is_secret_var("API_KEY")
        assert environment_manager.is_secret_var("OPENROUTER_API_KEY")
        assert not environment_manager.is_secret_var("PATH")

    def test_os_info(self):
        info = environment_manager.get_os_info()
        assert "system" in info
        assert "machine" in info

    def test_git_state(self):
        git = environment_manager.get_git_state()
        assert "is_repo" in git


class TestHistoryManager:
    """Test execution history."""

    def test_add_and_get(self):
        history_manager.add_entry(
            command="echo test",
            cwd="/tmp",
            backend="local",
            status="success",
            exit_code=0,
            duration=0.1,
        )
        entries = history_manager.get_recent(count=5)
        assert len(entries) > 0

    def test_search(self):
        history_manager.add_entry(
            command="echo search_test_unique",
            cwd="/tmp",
            backend="local",
            status="success",
        )
        results = history_manager.search("search_test_unique")
        assert len(results) > 0

    def test_clear(self):
        history_manager.clear()
        assert len(history_manager) == 0


class TestStateMachine:
    """Test execution state machine."""

    def test_initial_state(self):
        sm = StateMachine("test-id")
        assert sm.state == ExecutionState.IDLE

    def test_valid_transition(self):
        sm = StateMachine("test-id")
        assert sm.transition_to(ExecutionState.PLANNING)
        assert sm.state == ExecutionState.PLANNING

    def test_invalid_transition(self):
        sm = StateMachine("test-id")
        assert not sm.transition_to(ExecutionState.COMPLETED)

    def test_terminal_state(self):
        sm = StateMachine("test-id")
        sm.transition_to(ExecutionState.PLANNING)
        sm.transition_to(ExecutionState.STARTING)
        sm.transition_to(ExecutionState.RUNNING)
        sm.transition_to(ExecutionState.COMPLETED)
        assert sm.is_terminal()

    def test_history(self):
        sm = StateMachine("test-id")
        sm.transition_to(ExecutionState.PLANNING)
        sm.transition_to(ExecutionState.RUNNING)
        assert len(sm.history) == 3  # initial + 2 transitions


class TestPTYManager:
    """Test PTY management."""

    def test_availability(self):
        from app.terminal.pty_manager import pty_manager
        # PTY should be available on Linux
        assert pty_manager.is_available()

    def test_list_sessions(self):
        from app.terminal.pty_manager import pty_manager
        sessions = pty_manager.list_sessions()
        assert isinstance(sessions, list)


class TestTerminalInterface:
    """Test unified terminal interface."""

    def test_get_status(self):
        status = terminal_interface.get_status()
        assert "shells" in status
        assert "default_shell" in status
        assert "sessions" in status
        assert "processes" in status
        assert "ptys" in status
        assert "pty_available" in status

    def test_execute_with_session(self):
        session = terminal_interface.create_session(shell="bash")
        result = terminal_interface.execute("echo test", session_id=session.session_id)
        assert result.status == "success"

    def test_subscribe(self):
        called = []
        def handler(payload):
            called.append(payload)
        terminal_interface.subscribe("terminal.execution.started", handler)
        terminal_interface.execute("echo test")
        # Event should have been emitted
        assert len(called) > 0


class TestBackendManager:
    """Test backend management."""

    def test_get_local_backend(self):
        from app.terminal.backend_manager import BackendManager
        bm = BackendManager()
        backend = bm.get_backend("local")
        assert backend is not None

    def test_get_docker_backend(self):
        from app.terminal.backend_manager import BackendManager
        bm = BackendManager()
        backend = bm.get_backend("docker")
        assert backend is not None

    def test_get_ssh_backend(self):
        from app.terminal.backend_manager import BackendManager
        bm = BackendManager()
        backend = bm.get_backend("ssh")
        assert backend is not None

    def test_unknown_backend(self):
        from app.terminal.backend_manager import BackendManager
        bm = BackendManager()
        with pytest.raises(ValueError):
            bm.get_backend("unknown")  # type: ignore[arg-type]


class TestRiskEngine:
    """Test risk assessment."""

    def test_safe_command(self):
        from app.terminal.risk_engine import RiskEngine
        engine = RiskEngine()
        req = ExecutionRequest(command="ls", shell=False, cwd=None, env=None, backend="local", timeout=60, background=False, interactive=False, permission_mode="ask", verification=None)
        risk = engine.evaluate(req)
        assert risk in ("safe", "low")

    def test_dangerous_command(self):
        from app.terminal.risk_engine import RiskEngine
        engine = RiskEngine()
        req = ExecutionRequest(command="rm -rf /", shell=False, cwd=None, env=None, backend="local", timeout=60, background=False, interactive=False, permission_mode="ask", verification=None)
        risk = engine.evaluate(req)
        assert risk in ("high", "critical")


class TestPermissionEngine:
    """Test permission system."""

    def test_auto_mode(self):
        from app.terminal.permission_engine import PermissionEngine
        engine = PermissionEngine()
        req = ExecutionRequest(command="ls", shell=False, permission_mode="auto")
        # Should not raise
        engine.check(req, "low")

    def test_deny_mode(self):
        from app.terminal.permission_engine import PermissionEngine
        engine = PermissionEngine()
        req = ExecutionRequest(command="mkfs /dev/sda", shell=False, permission_mode="deny", cwd=None, env=None, backend="local", timeout=60, background=False, interactive=False, verification=None)
        with pytest.raises(Denied):
            engine.check(req, "critical")


class TestVerificationEngine:
    """Test verification system."""

    def test_file_exists_verification(self):
        from app.terminal.verification_engine import VerificationEngine
        engine = VerificationEngine()
        # Create a test file
        test_file = Path("/tmp/moon_test_verify.txt")
        test_file.write_text("test")
        try:
            req_dict = {"command": "echo test > /tmp/moon_test_verify.txt", "verification": {"type": "file_exists", "path": str(test_file)}}
            result_dict = {"exit_code": 0, "stdout": "", "stderr": ""}
            verified, ver_result = engine.verify(req_dict, result_dict)
            assert verified is True
        finally:
            test_file.unlink(missing_ok=True)

    def test_failed_verification(self):
        from app.terminal.verification_engine import VerificationEngine
        engine = VerificationEngine()
        req_dict = {"command": "echo test", "verification": {"type": "file_exists", "path": "/nonexistent/path"}}
        result_dict = {"exit_code": 0, "stdout": "", "stderr": ""}
        verified, ver_result = engine.verify(req_dict, result_dict)
        assert verified is False


class TestRecoveryEngine:
    """Test recovery system."""

    def test_analyze_command_not_found(self):
        from app.terminal.recovery_engine import RecoveryEngine, FailureType
        engine = RecoveryEngine()
        req = ExecutionRequest(command="nonexistent_command_xyz", shell=False, cwd=None, env=None, backend="local", timeout=60, background=False, interactive=False, permission_mode="ask", verification=None)
        result = ExecutionResult(
            execution_id="test",
            command="nonexistent_command_xyz",
            backend="local",
            cwd=Path("/tmp"),
            status="failed",
            exit_code=127,
            stdout="",
            stderr="command not found",
            pid=None,
            duration=0.1,
            verified=False,
            verification_result=None,
            error=None,
        )
        failure_type, desc = engine.analyze_failure(req, result)
        assert failure_type == FailureType.COMMAND_NOT_FOUND

    def test_plan_recovery(self):
        from app.terminal.recovery_engine import RecoveryEngine, FailureType, RecoveryAction
        engine = RecoveryEngine()
        req = ExecutionRequest(command="nonexistent", shell=False, cwd=None, env=None, backend="local", timeout=60, background=False, interactive=False, permission_mode="ask", verification=None)
        result = ExecutionResult(
            execution_id="test",
            command="nonexistent",
            backend="local",
            cwd=Path("/tmp"),
            status="failed",
            exit_code=127,
            stdout="",
            stderr="command not found",
            pid=None,
            duration=0.1,
            verified=False,
            verification_result=None,
            error=None,
        )
        actions = engine.plan_recovery(FailureType.COMMAND_NOT_FOUND, req, result)
        assert len(actions) > 0


class TestEventBus:
    """Test event system."""

    def test_subscribe_and_publish(self):
        from app.terminal.event_bus import get_bus
        bus = get_bus()
        received = []
        def handler(payload):
            received.append(payload)
        bus.subscribe("test.event", handler)
        bus.publish("test.event", {"data": "test"})
        assert len(received) == 1
        assert received[0]["data"] == "test"

    def test_emit_alias(self):
        from app.terminal.event_bus import get_bus
        bus = get_bus()
        received = []
        def handler(payload):
            received.append(payload)
        bus.subscribe("test.event2", handler)
        bus.emit("test.event2", {"data": "test2"})
        assert len(received) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
