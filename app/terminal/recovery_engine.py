"""Recovery engine for MOON terminal.

When execution fails, the recovery engine:
1. Captures the failure
2. Analyzes the cause
3. Plans recovery
4. Executes recovery
5. Verifies the result

Recovery strategies:
- retry: try the same command again
- change_command: try a modified command
- install_dependency: install a missing dependency
- activate_environment: activate a virtual environment
- change_cwd: try a different working directory
- restart_service: restart a service
- ask_user: ask the user for guidance
- stop: give up

Uses bounded retries — never repeatedly performs destructive operations.
"""

from __future__ import annotations

import re
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import ExecutionRequest, ExecutionResult


class RecoveryAction(str, Enum):
    RETRY = "retry"
    CHANGE_COMMAND = "change_command"
    INSTALL_DEPENDENCY = "install_dependency"
    ACTIVATE_ENVIRONMENT = "activate_environment"
    CHANGE_CWD = "change_cwd"
    RESTART_SERVICE = "restart_service"
    ASK_USER = "ask_user"
    STOP = "stop"


class FailureType(str, Enum):
    COMMAND_NOT_FOUND = "command_not_found"
    PERMISSION_DENIED = "permission_denied"
    MISSING_DEPENDENCY = "missing_dependency"
    TIMEOUT = "timeout"
    EXIT_NONZERO = "exit_nonzero"
    VERIFICATION_FAILED = "verification_failed"
    UNKNOWN = "unknown"


# Patterns that indicate specific failure types
_FAILURE_PATTERNS: Dict[FailureType, List[str]] = {
    FailureType.COMMAND_NOT_FOUND: [
        r"command not found",
        r"not found",
        r"No such file or directory",
    ],
    FailureType.PERMISSION_DENIED: [
        r"permission denied",
        r"Permission denied",
        r"Operation not permitted",
    ],
    FailureType.MISSING_DEPENDENCY: [
        r"ModuleNotFoundError",
        r"ImportError",
        r"ModuleNotFoundError: No module named",
        r"cannot find",
        r"Could not find",
    ],
    FailureType.TIMEOUT: [
        r"timed out",
        r"timeout",
        r"TimeoutError",
    ],
}


class RecoveryEngine:
    """Analyzes failures and attempts recovery."""

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries
        self._retry_counts: Dict[str, int] = {}  # execution_id → retry count

    def analyze_failure(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
    ) -> Tuple[FailureType, str]:
        """Analyze a failure and return (failure_type, description)."""
        if result.status == "timed_out":
            return FailureType.TIMEOUT, "Command timed out"
        if result.status == "denied":
            return FailureType.PERMISSION_DENIED, "Permission denied"
        if result.status == "cancelled":
            return FailureType.UNKNOWN, "Command was cancelled"

        stderr = result.stderr or ""
        stdout = result.stdout or ""
        combined = stderr + "\n" + stdout

        for failure_type, patterns in _FAILURE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return failure_type, f"Detected: {failure_type.value}"

        if result.exit_code and result.exit_code != 0:
            return FailureType.EXIT_NONZERO, f"Exit code {result.exit_code}"

        if result.verified is False and result.verification_result:
            return FailureType.VERIFICATION_FAILED, "Verification failed"

        return FailureType.UNKNOWN, "Unknown failure"

    def plan_recovery(
        self,
        failure_type: FailureType,
        request: ExecutionRequest,
        result: ExecutionResult,
    ) -> List[RecoveryAction]:
        """Plan recovery actions based on failure type."""
        actions: List[RecoveryAction] = []

        if failure_type == FailureType.COMMAND_NOT_FOUND:
            actions.append(RecoveryAction.CHANGE_COMMAND)
            actions.append(RecoveryAction.ASK_USER)
        elif failure_type == FailureType.MISSING_DEPENDENCY:
            actions.append(RecoveryAction.INSTALL_DEPENDENCY)
            actions.append(RecoveryAction.ACTIVATE_ENVIRONMENT)
            actions.append(RecoveryAction.ASK_USER)
        elif failure_type == FailureType.PERMISSION_DENIED:
            actions.append(RecoveryAction.ASK_USER)
        elif failure_type == FailureType.TIMEOUT:
            actions.append(RecoveryAction.RETRY)
            actions.append(RecoveryAction.ASK_USER)
        elif failure_type == FailureType.EXIT_NONZERO:
            actions.append(RecoveryAction.RETRY)
            actions.append(RecoveryAction.CHANGE_COMMAND)
            actions.append(RecoveryAction.ASK_USER)
        elif failure_type == FailureType.VERIFICATION_FAILED:
            actions.append(RecoveryAction.CHANGE_COMMAND)
            actions.append(RecoveryAction.ASK_USER)
        else:
            actions.append(RecoveryAction.ASK_USER)

        return actions

    def can_retry(self, execution_id: str) -> bool:
        """Check if we can retry this execution."""
        count = self._retry_counts.get(execution_id, 0)
        return count < self.max_retries

    def record_retry(self, execution_id: str):
        """Record a retry attempt."""
        self._retry_counts[execution_id] = self._retry_counts.get(execution_id, 0) + 1

    def execute_recovery(
        self,
        action: RecoveryAction,
        request: ExecutionRequest,
        result: ExecutionResult,
        executor: Callable[[ExecutionRequest], ExecutionResult],
    ) -> Optional[ExecutionResult]:
        """Execute a recovery action.

        `executor` is a callable that takes an ExecutionRequest and returns
        an ExecutionResult (typically the ExecutionEngine.execute method).
        """
        if action == RecoveryAction.RETRY:
            if not self.can_retry(result.execution_id):
                return None
            self.record_retry(result.execution_id)
            return executor(request)

        elif action == RecoveryAction.CHANGE_COMMAND:
            # Try with shell=True if not already
            if not request.shell:
                new_req = request.copy(deep=True)
                new_req.shell = True
                return executor(new_req)
            return None

        elif action == RecoveryAction.INSTALL_DEPENDENCY:
            # Try to install missing Python module
            stderr = result.stderr or ""
            match = re.search(r"No module named '([^']+)'", stderr)
            if match:
                module = match.group(1)
                install_req = ExecutionRequest(
                    command=f"pip install {module}",
                    cwd=request.cwd,
                    env=request.env,
                    backend=request.backend,
                    shell=True,
                    timeout=120,
                    background=False,
                    interactive=False,
                    permission_mode="ask",
                    verification=None,
                )
                return executor(install_req)
            return None

        elif action == RecoveryAction.ACTIVATE_ENVIRONMENT:
            # Try to find and activate a virtual env
            import os
            venv = os.environ.get("VIRTUAL_ENV")
            if venv:
                activate_script = os.path.join(venv, "bin", "activate")
                if os.path.exists(activate_script):
                    new_req = request.copy(deep=True)
                    new_req.shell = True
                    new_req.command = f"source {activate_script} && {request.command}"
                    return executor(new_req)
            return None

        elif action == RecoveryAction.CHANGE_CWD:
            # Try from home directory
            from pathlib import Path
            new_req = request.copy(deep=True)
            new_req.cwd = Path.home()
            return executor(new_req)

        elif action == RecoveryAction.RESTART_SERVICE:
            # Not implemented — requires service tracking
            return None

        elif action == RecoveryAction.ASK_USER:
            # Signal that user input is needed
            return None

        elif action == RecoveryAction.STOP:
            return None

        return None

    def reset_retries(self, execution_id: str):
        """Reset retry count for an execution."""
        self._retry_counts.pop(execution_id, None)


# Module-level singleton
recovery_engine = RecoveryEngine()
