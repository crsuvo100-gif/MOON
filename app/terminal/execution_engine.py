"""Core execution engine for MOON terminal.

It coordinates:
- Risk analysis (RiskEngine)
- Permission handling (PermissionEngine)
- Backend selection (BackendManager)
- Execution (backend.run)
- Verification (VerificationEngine)
- Event emission (event_bus)

All heavy imports are performed lazily to avoid import‑time failures.
"""

from __future__ import annotations

import uuid
import time
from pathlib import Path
from typing import Any, Dict

# Pydantic models defined in app/terminal/models.py
from .models import ExecutionRequest, ExecutionResult
from .process_manager import process_manager
from .output_engine import OutputEngine

# Lazy imports – imported inside methods to keep module import lightweight

class ExecutionEngine:
    """Orchestrates a single execution request.

    The flow is:
    1. Risk evaluation
    2. Permission check (may raise PermissionRequired)
    3. Select backend via BackendManager
    4. Optional session handling – apply cwd, env, shell from a SessionManager if a `session_id` is provided.
    5. Run command (foreground or background)
    5. Verify result (optional)
    6. Emit events throughout the process
    """

    def __init__(self):
        # Import heavy modules lazily
        from .risk_engine import RiskEngine
        from .permission_engine import PermissionEngine
        from .verification_engine import VerificationEngine
        from .backend_manager import BackendManager
        from .event_bus import get_bus
        from .session_manager import SessionManager

        self.risk_engine = RiskEngine()
        self.permission_engine = PermissionEngine()
        self.verification_engine = VerificationEngine()
        self.backend_manager = BackendManager()
        self.bus = get_bus()
        # Session manager for optional session context
        self.session_manager = SessionManager()

    def _emit(self, topic: str, payload: Dict[str, Any]):
        try:
            self.bus.emit(topic, payload)
        except Exception:
            # Defensive – never crash the engine because of a bad listener
            pass

    def execute(self, req: ExecutionRequest, session_id: str | None = None) -> ExecutionResult:
        start_ts = time.time()
        execution_id = str(uuid.uuid4())
        self._emit("terminal.execution.started", {"execution_id": execution_id, "request": req.dict()})

        # ---------- Risk evaluation ----------
        risk_level = self.risk_engine.evaluate(req)
        self._emit("terminal.risk.evaluated", {"execution_id": execution_id, "risk": risk_level})

        # ---------- Permission handling ----------
        try:
            self.permission_engine.check(req, risk_level)
        except PermissionEngine.PermissionRequired as e:
            # Emit permission required event and re‑raise for UI handling
            self._emit("terminal.permission.required", {"execution_id": execution_id, "command": req.command, "risk": risk_level, "reason": str(e)})
            raise
        except PermissionEngine.Denied as e:
            self._emit("terminal.execution.denied", {"execution_id": execution_id, "reason": str(e)})
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

        # ---------- Backend selection ----------
        backend = self.backend_manager.get_backend(req.backend)
        if backend is None:
            err = f"Unknown backend '{req.backend}'"
            self._emit("terminal.execution.failed", {"execution_id": execution_id, "error": err})
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

        # ---------- Run the command ----------
        try:
            # Apply session defaults if a session_id is provided
            if session_id:
                sess = self.session_manager.get_session(session_id)
                if sess:
                    # Prefer session cwd and env when not explicitly set in request
                    if req.cwd is None:
                        req.cwd = sess.cwd
                    if not req.env:
                        req.env = sess.env

            # Ignore background flag for simplicity – treat as foreground execution
            req.background = False
            resp = backend.run(req)
        except Exception as exc:
            # Unexpected backend failure
            self._emit("terminal.execution.failed", {"execution_id": execution_id, "error": str(exc)})
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
                error=str(exc),
            )

        # ---------- Verification ----------
        verified, ver_result = self.verification_engine.verify(req.dict(), resp)
        status = "success" if resp.get("exit_code", 1) == 0 and verified else "failed"

        result = ExecutionResult(
            execution_id=execution_id,
            command=req.command,
            backend=req.backend,
            cwd=req.cwd or Path.cwd(),
            status=status,
            exit_code=resp.get("exit_code"),
            stdout=resp.get("stdout"),
            stderr=resp.get("stderr"),
            pid=resp.get("pid"),
            duration=time.time() - start_ts,
            verified=verified,
            verification_result=ver_result,
            error=None if status == "success" else "Verification failed",
        )

        self._emit("terminal.execution.completed", {"execution_id": execution_id, "result": result.dict()})
        return result

# End of execution_engine.py
