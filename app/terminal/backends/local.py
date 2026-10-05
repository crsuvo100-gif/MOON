"""Local backend implementation using Hermes' terminal tool.

It supports:
* foreground execution (default)
* background execution with optional streaming via Hermes notifications
* PTY (interactive) execution when request.interactive=True
* environment and cwd handling
"""

import uuid
import time
from pathlib import Path
from typing import Optional

# hermes_tools is imported lazily inside methods to avoid import errors during test collection
from ..models import ExecutionRequest, ExecutionResult
import subprocess, shlex
from typing import Dict

class LocalBackend:
    def __init__(self):
        from ..event_bus import get_bus
        self.bus = get_bus()

    def run(self, request: ExecutionRequest) -> Dict:
        """Execute ``request.command`` using ``subprocess.run``.

        This method implements the concrete backend API expected by
        ``ExecutionEngine``.  It returns a dictionary with the keys used by the
        engine: ``exit_code``, ``stdout``, ``stderr`` and ``pid``.
        """
        cwd = request.cwd or Path.cwd()
        cmd = request.command
        if request.shell:
            cmd = f"/bin/sh -c {cmd}"
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=request.timeout,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "pid": getattr(proc, "pid", None),
        }


    def _run_background(self, req: ExecutionRequest) -> ExecutionResult:
        start = time.time()
        # For background execution we reuse subprocess.run (synchronous) for now
        cwd = req.cwd or Path.cwd()
        command = req.command
        if req.shell:
            command = f"/bin/sh -c {command}"
        proc = subprocess.run(
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=req.timeout,
        )
        resp = {
            "exit_code": proc.returncode,
            "output": proc.stdout,
            "error": proc.stderr,
            "pid": getattr(proc, "pid", None),
        }
        duration = time.time() - start
        execution_id = str(uuid.uuid4())
        # Emit start event
        self.bus.publish("execution.started", {"execution_id": execution_id, "command": req.command})
        return ExecutionResult(
            execution_id=execution_id,
            command=req.command,
            backend="local",
            cwd=cwd,
            status="success" if resp["exit_code"] == 0 else "failed",
            exit_code=resp["exit_code"],
            stdout=resp.get("output"),
            stderr=resp.get("error"),
            pid=resp.get("pid"),
            duration=duration,
            verified=False,
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.background:
            return self._run_background(request)
        # Interactive (PTY) execution – use PTY manager when requested
        if request.interactive:
            from ..pty_manager import PTYManager
            pty_mgr = PTYManager()
            return pty_mgr.run_interactive(request)
        # Foreground execution – reuse the ``run`` method which returns a dict
        resp = self.run(request)
        # Build ExecutionResult directly from the dict
        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            command=request.command,
            backend="local",
            cwd=request.cwd or Path.cwd(),
            status="success" if resp["exit_code"] == 0 else "failed",
            exit_code=resp["exit_code"],
            stdout=resp.get("stdout"),
            stderr=resp.get("stderr"),
            pid=resp.get("pid"),
            duration=0.0,  # duration not tracked for simple run; could be measured later
            verified=False,
        )
