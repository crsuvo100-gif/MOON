"""Core execution engine for MOON terminal.

Orchestrates the full execution pipeline:
1. State machine transition (IDLE → PLANNING → ...)
2. Risk analysis (RiskEngine)
3. Permission handling (PermissionEngine)
4. Backend selection (BackendManager)
5. Execution (backend.run with streaming)
6. Verification (VerificationEngine)
7. Recovery (RecoveryEngine) on failure
8. History recording (HistoryManager)
9. Event emission (event_bus)

Supports foreground, background, and interactive (PTY) execution.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import ExecutionRequest, ExecutionResult
from .state_machine import ExecutionState, StateMachine
from .event_bus import get_bus
from .history_manager import history_manager
from .environment_manager import environment_manager


class ExecutionEngine:
    """Orchestrates a single execution request through the full pipeline."""

    def __init__(self):
        from .risk_engine import RiskEngine
        from .permission_engine import PermissionEngine
        from .verification_engine import VerificationEngine
        from .backend_manager import BackendManager
        from .recovery_engine import recovery_engine
        from .session_manager import SessionManager

        self.risk_engine = RiskEngine()
        self.permission_engine = PermissionEngine()
        self.verification_engine = VerificationEngine()
        self.backend_manager = BackendManager()
        self.recovery_engine = recovery_engine
        self.bus = get_bus()
        self.session_manager = SessionManager()

    def _emit(self, topic: str, payload: Dict[str, Any]):
        try:
            self.bus.emit(topic, payload)
        except Exception:
            pass

    def execute(
        self,
        req: ExecutionRequest,
        session_id: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a request through the full pipeline.

        Args:
            req: The execution request
            session_id: Optional session ID for context
            on_output: Optional callback for streaming output

        Returns:
            ExecutionResult with full execution details
        """
        start_ts = time.time()
        execution_id = str(uuid.uuid4())
        sm = StateMachine(execution_id)

        # Apply session defaults
        if session_id:
            sess = self.session_manager.get_session(session_id)
            if sess:
                if req.cwd is None:
                    req.cwd = sess.cwd
                if not req.env:
                    req.env = sess.env

        self._emit("terminal.execution.started", {
            "execution_id": execution_id,
            "command": req.command,
            "backend": req.backend,
        })

        # ── Risk evaluation ──
        sm.transition_to(ExecutionState.PLANNING, "evaluating risk")
        risk_level = self.risk_engine.evaluate(req)
        self._emit("terminal.risk.evaluated", {
            "execution_id": execution_id,
            "risk": risk_level,
        })

        # ── Permission handling ──
        sm.transition_to(ExecutionState.WAITING_PERMISSION, "checking permissions")
        try:
            self.permission_engine.check(req, risk_level)
        except PermissionEngine.PermissionRequired as e:
            self._emit("terminal.permission.required", {
                "execution_id": execution_id,
                "command": req.command,
                "risk": risk_level,
                "reason": str(e),
            })
            sm.transition_to(ExecutionState.DENIED, "permission required")
            return ExecutionResult(
                execution_id=execution_id,
                command=req.command,
                backend=req.backend,
                cwd=req.cwd or Path.cwd(),
                status="denied",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=time.time() - start_ts,
                verified=False,
                verification_result=None,
                error=f"Permission required: {e}",
            )
        except PermissionEngine.Denied as e:
            self._emit("terminal.execution.denied", {
                "execution_id": execution_id,
                "reason": str(e),
            })
            sm.transition_to(ExecutionState.DENIED, "permission denied")
            return ExecutionResult(
                execution_id=execution_id,
                command=req.command,
                backend=req.backend,
                cwd=req.cwd or Path.cwd(),
                status="denied",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=time.time() - start_ts,
                verified=False,
                verification_result=None,
                error=str(e),
            )

        # ── Backend selection ──
        backend = self.backend_manager.get_backend(req.backend)
        if backend is None:
            err = f"Unknown backend '{req.backend}'"
            self._emit("terminal.execution.failed", {
                "execution_id": execution_id,
                "error": err,
            })
            sm.transition_to(ExecutionState.FAILED, err)
            return ExecutionResult(
                execution_id=execution_id,
                command=req.command,
                backend=req.backend,
                cwd=req.cwd or Path.cwd(),
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=time.time() - start_ts,
                verified=False,
                verification_result=None,
                error=err,
            )

        # ── Execute ──
        sm.transition_to(ExecutionState.STARTING, "starting execution")
        sm.transition_to(ExecutionState.RUNNING, "executing command")

        try:
            if req.background:
                # Background execution
                if hasattr(backend, 'start_background'):
                    bg_id = backend.start_background(req, on_output=on_output)
                    duration = time.time() - start_ts
                    result = ExecutionResult(
                        execution_id=bg_id,
                        command=req.command,
                        backend=req.backend,
                        cwd=req.cwd or Path.cwd(),
                        status="success",
                        exit_code=None,
                        stdout=None,
                        stderr=None,
                        pid=None,
                        duration=duration,
                        verified=False,
                        verification_result=None,
                        error=None,
                    )
                    history_manager.add_entry(
                        command=req.command,
                        cwd=str(req.cwd or Path.cwd()),
                        backend=req.backend,
                        status="success",
                        duration=duration,
                        session_id=session_id,
                    )
                    self._emit("terminal.execution.completed", {
                        "execution_id": bg_id,
                        "result": result.dict(),
                    })
                    sm.transition_to(ExecutionState.COMPLETED, "background started")
                    return result
                else:
                    # Backend doesn't support background, fall back to foreground
                    req.background = False

            if req.interactive:
                # Interactive (PTY) execution
                from .pty_manager import PTYManager
                pty_mgr = PTYManager()
                result = pty_mgr.run_interactive(req, on_output=on_output)
                result.execution_id = execution_id
            else:
                # Foreground execution with optional streaming
                resp = backend.run(req, on_output=on_output)
                exit_code = resp.get("exit_code", -1)
                status = "success" if exit_code == 0 else "failed"
                if resp.get("timed_out"):
                    status = "timed_out"

                result = ExecutionResult(
                    execution_id=execution_id,
                    command=req.command,
                    backend=req.backend,
                    cwd=req.cwd or Path.cwd(),
                    status=status,
                    exit_code=exit_code,
                    stdout=resp.get("stdout"),
                    stderr=resp.get("stderr"),
                    pid=resp.get("pid"),
                    duration=time.time() - start_ts,
                    verified=False,
                    verification_result=None,
                    error=None,
                )

        except Exception as exc:
            self._emit("terminal.execution.failed", {
                "execution_id": execution_id,
                "error": str(exc),
            })
            sm.transition_to(ExecutionState.FAILED, str(exc))
            duration = time.time() - start_ts
            history_manager.add_entry(
                command=req.command,
                cwd=str(req.cwd or Path.cwd()),
                backend=req.backend,
                status="failed",
                duration=duration,
                session_id=session_id,
            )
            return ExecutionResult(
                execution_id=execution_id,
                command=req.command,
                backend=req.backend,
                cwd=req.cwd or Path.cwd(),
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=duration,
                verified=False,
                verification_result=None,
                error=str(exc),
            )

        # ── Verification ──
        if result.status == "success" and req.verification:
            sm.transition_to(ExecutionState.VERIFYING, "verifying result")
            verified, ver_result = self.verification_engine.verify(req.dict(), result.dict())
            result.verified = verified
            result.verification_result = ver_result
            if not verified:
                result.status = "failed"
                result.error = "Verification failed"

        # ── Recovery on failure ──
        if result.status == "failed":
            sm.transition_to(ExecutionState.RECOVERING, "attempting recovery")
            failure_type, description = self.recovery_engine.analyze_failure(req, result)
            actions = self.recovery_engine.plan_recovery(failure_type, req, result)

            for action in actions:
                if action.value == "ask_user":
                    break  # Stop and ask user
                # Use a simple executor that doesn't trigger recovery again
                def _simple_execute(r: ExecutionRequest) -> ExecutionResult:
                    backend = self.backend_manager.get_backend(r.backend)
                    resp = backend.run(r, on_output=on_output)
                    exit_code = resp.get("exit_code", -1)
                    status = "success" if exit_code == 0 else "failed"
                    if resp.get("timed_out"):
                        status = "timed_out"
                    return ExecutionResult(
                        execution_id=str(uuid.uuid4()),
                        command=r.command,
                        backend=r.backend,
                        cwd=r.cwd or Path.cwd(),
                        status=status,
                        exit_code=exit_code,
                        stdout=resp.get("stdout"),
                        stderr=resp.get("stderr"),
                        pid=resp.get("pid"),
                        duration=0.0,
                        verified=False,
                        verification_result=None,
                        error=None,
                    )
                recovery_result = self.recovery_engine.execute_recovery(
                    action, req, result, _simple_execute
                )
                if recovery_result and recovery_result.status == "success":
                    result = recovery_result
                    break

        # ── Finalize ──
        duration = time.time() - start_ts
        result.duration = duration

        if result.status == "success":
            sm.transition_to(ExecutionState.COMPLETED, "execution completed")
        elif result.status == "timed_out":
            sm.transition_to(ExecutionState.TIMED_OUT, "execution timed out")
        else:
            sm.transition_to(ExecutionState.FAILED, "execution failed")

        # Record history
        history_manager.add_entry(
            command=req.command,
            cwd=str(req.cwd or Path.cwd()),
            backend=req.backend,
            status=result.status,
            exit_code=result.exit_code,
            duration=duration,
            session_id=session_id,
        )

        self._emit("terminal.execution.completed", {
            "execution_id": execution_id,
            "result": result.dict(),
        })

        return result

    def execute_streaming(
        self,
        req: ExecutionRequest,
        session_id: Optional[str] = None,
    ) -> tuple[str, Callable[[Callable[[str], None]], ExecutionResult]]:
        """Execute with streaming, returning (execution_id, subscribe_fn).

        The subscribe_fn takes an on_output callback and starts execution.
        This allows the caller to set up the callback before execution starts.
        """
        execution_id = str(uuid.uuid4())
        callback_holder: List[Optional[Callable[[str], None]]] = [None]

        def _on_output(text: str):
            if callback_holder[0]:
                try:
                    callback_holder[0](text)
                except Exception:
                    pass

        def _subscribe(on_output: Callable[[str], None]):
            callback_holder[0] = on_output
            result = self.execute(req, session_id, on_output=_on_output)
            return result

        return execution_id, _subscribe


# Module-level singleton
execution_engine = ExecutionEngine()
