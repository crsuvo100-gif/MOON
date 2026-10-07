"""Local backend with real streaming, background, and PTY support.

Uses subprocess.Popen for streaming output and background execution.
Uses PTYManager for interactive terminal sessions.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, cast

from ..models import ExecutionRequest, ExecutionResult
from ..event_bus import get_bus
from ..output_engine import OutputEngine


class LocalBackend:
    """Execute commands on the local machine with full streaming and background support."""

    def __init__(self):
        self.bus = get_bus()
        self.output_engine = OutputEngine()
        self._background_processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def run(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """Execute a command and return a dict with exit_code, stdout, stderr, pid.

        If on_output is provided, output is streamed via the callback.
        Otherwise, output is captured and returned in the dict.
        """
        cwd = request.cwd or Path.cwd()
        env = {**os.environ, **(request.env or {})}

        # Build command
        if request.shell:
            cmd = ["/bin/sh", "-c", request.command]
        else:
            try:
                cmd = shlex.split(request.command)
            except ValueError:
                cmd = ["/bin/sh", "-c", request.command]

        start_time = time.time()

        if on_output:
            # Streaming mode
            return self._run_streaming(cmd, cwd, env, request, on_output)
        else:
            # Capture mode
            return self._run_capture(cmd, cwd, env, request)

    def _run_streaming(
        self,
        cmd: List[str],
        cwd: Path,
        env: Dict[str, str],
        request: ExecutionRequest,
        on_output: Callable[[str], None],
    ) -> Dict:
        """Run with streaming output via callback."""
        stdout_parts: List[str] = []
        stderr_parts: List[str] = []
        exit_code = None
        pid = None
        timed_out = False

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            pid = proc.pid

            # Read stdout and stderr in separate threads
            def _read_stdout():
                try:
                    stdout = proc.stdout
                    assert stdout is not None
                    for line in stdout:
                        stdout_parts.append(line)
                        try:
                            on_output(line)
                        except Exception:
                            pass
                except Exception:
                    pass

            def _read_stderr():
                try:
                    stderr = proc.stderr
                    assert stderr is not None
                    for line in stderr:
                        stderr_parts.append(line)
                        try:
                            on_output(line)
                        except Exception:
                            pass
                except Exception:
                    pass

            stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            # Wait with timeout
            try:
                exit_code = proc.wait(timeout=request.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                proc.wait()
                exit_code = -1

            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

        except Exception as exc:
            return {
                "exit_code": -1,
                "stdout": "".join(stdout_parts),
                "stderr": "".join(stderr_parts) + f"\nError: {exc}",
                "pid": pid,
                "timed_out": timed_out,
            }

        return {
            "exit_code": exit_code,
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "pid": pid,
            "timed_out": timed_out,
        }

    def _run_capture(
        self,
        cmd: List[str],
        cwd: Path,
        env: Dict[str, str],
        request: ExecutionRequest,
    ) -> Dict:
        """Run and capture all output (non-streaming)."""
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=request.timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "pid": None,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as e:
            stdout_str = cast(str, e.stdout or "")
            stderr_raw = cast(str, e.stderr or "")
            return {
                "exit_code": -1,
                "stdout": stdout_str,
                "stderr": stderr_raw + f"\nCommand timed out after {request.timeout}s",
                "pid": None,
                "timed_out": True,
            }
        except Exception as exc:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "pid": None,
                "timed_out": False,
            }

    def start_background(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Start a background process and return execution_id immediately."""
        execution_id = str(uuid.uuid4())
        cwd = request.cwd or Path.cwd()
        env = {**os.environ, **(request.env or {})}

        if request.shell:
            cmd = ["/bin/sh", "-c", request.command]
        else:
            try:
                cmd = shlex.split(request.command)
            except ValueError:
                cmd = ["/bin/sh", "-c", request.command]

        # Open log files
        log_dir = Path(".moon_logs")
        log_dir.mkdir(exist_ok=True)
        stdout_log = open(log_dir / f"{execution_id}.stdout", "w")
        stderr_log = open(log_dir / f"{execution_id}.stderr", "w")

        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=stdout_log,
            stderr=stderr_log,
            text=True,
        )

        with self._lock:
            self._background_processes[execution_id] = proc

        self.bus.emit("terminal.process.started", {
            "execution_id": execution_id,
            "command": request.command,
            "pid": proc.pid,
            "backend": "local",
        })

        # Monitor thread
        def _monitor():
            exit_code = proc.wait()
            stdout_log.close()
            stderr_log.close()
            with self._lock:
                self._background_processes.pop(execution_id, None)
            self.bus.emit("terminal.process.stopped", {
                "execution_id": execution_id,
                "exit_code": exit_code,
                "command": request.command,
            })

        threading.Thread(target=_monitor, daemon=True).start()

        return execution_id

    def stop_background(self, execution_id: str) -> bool:
        """Stop a background process."""
        with self._lock:
            proc = self._background_processes.get(execution_id)
        if not proc:
            return False
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return True

    def get_background_status(self, execution_id: str) -> Optional[Dict]:
        """Get status of a background process."""
        with self._lock:
            proc = self._background_processes.get(execution_id)
        if not proc:
            return None
        return {
            "execution_id": execution_id,
            "pid": proc.pid,
            "running": proc.poll() is None,
            "exit_code": proc.poll(),
        }

    def get_background_logs(self, execution_id: str) -> Dict[str, str]:
        """Get logs for a background process."""
        log_dir = Path(".moon_logs")
        stdout_file = log_dir / f"{execution_id}.stdout"
        stderr_file = log_dir / f"{execution_id}.stderr"
        stdout = stdout_file.read_text() if stdout_file.exists() else ""
        stderr = stderr_file.read_text() if stderr_file.exists() else ""
        return {"stdout": stdout, "stderr": stderr}

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a request and return ExecutionResult."""
        if request.interactive:
            from ..pty_manager import PTYManager
            pty_mgr = PTYManager()
            return pty_mgr.run_interactive(request)

        if request.background:
            execution_id = self.start_background(request)
            return ExecutionResult(
                execution_id=execution_id,
                command=request.command,
                backend="local",
                cwd=request.cwd or Path.cwd(),
                status="success",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=0.0,
                verified=False,
                verification_result=None,
                error=None,
            )

        resp = self.run(request)
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
            duration=0.0,
            verified=False,
            verification_result=None,
            error=None,
        )
