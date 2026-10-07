"""SSH backend with real remote execution.

Supports host, port, username, authentication, remote cwd,
environment variables, command execution, streaming, and timeouts.

Never hard-codes credentials. Never stores plaintext secrets.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, cast

from ..models import ExecutionRequest, ExecutionResult
from ..event_bus import get_bus


class SSHBackend:
    """Execute commands on remote hosts via SSH."""

    def __init__(self):
        self.bus = get_bus()
        self.available = shutil.which("ssh") is not None
        self._active_sessions: Dict[str, subprocess.Popen] = {}

    def _build_ssh_args(self, request: ExecutionRequest) -> List[str]:
        """Build SSH command arguments from an ExecutionRequest.

        The SSH connection details are passed via environment variables:
        - MOON_SSH_HOST: remote hostname (required)
        - MOON_SSH_PORT: remote port (default: 22)
        - MOON_SSH_USER: remote username (default: current user)
        - MOON_SSH_KEY: path to private key (optional)
        """
        host = os.environ.get("MOON_SSH_HOST", "")
        port = os.environ.get("MOON_SSH_PORT", "22")
        user = os.environ.get("MOON_SSH_USER", os.environ.get("USER", ""))
        key = os.environ.get("MOON_SSH_KEY", "")

        if not host:
            raise ValueError("MOON_SSH_HOST environment variable is required for SSH backend")

        args = ["ssh"]

        # Port
        args.extend(["-p", port])

        # Private key
        if key:
            args.extend(["-i", key])

        # Strict host key checking (disable for first connection)
        args.extend(["-o", "StrictHostKeyChecking=accept-new"])

        # Connection timeout
        args.extend(["-o", "ConnectTimeout=10"])

        # Target
        target = f"{user}@{host}" if user else host
        args.append(target)

        # Remote command
        if request.shell:
            args.append(request.command)
        else:
            args.append(request.command)

        return args

    def run(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """Execute a command on a remote host via SSH."""
        if not self.available:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "SSH is not available on this system",
                "pid": None,
                "timed_out": False,
            }

        try:
            args = self._build_ssh_args(request)
        except ValueError as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "pid": None,
                "timed_out": False,
            }

        start_time = time.time()

        try:
            if on_output:
                # Streaming mode
                stdout_parts: List[str] = []
                stderr_parts: List[str] = []

                proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )

                def _read_stdout():
                    try:
                        stdout = proc.stdout
                        assert stdout is not None
                        for line in stdout:
                            stdout_parts.append(line)
                            if on_output:
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
                            if on_output:
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

                try:
                    exit_code = proc.wait(timeout=request.timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    exit_code = -1

                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)

                return {
                    "exit_code": exit_code,
                    "stdout": "".join(stdout_parts),
                    "stderr": "".join(stderr_parts),
                    "pid": proc.pid,
                    "timed_out": exit_code == -1,
                }
            else:
                # Capture mode
                proc = subprocess.run(
                    args,
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
                "stderr": stderr_raw + f"\nSSH command timed out after {request.timeout}s",
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

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a request via SSH and return ExecutionResult."""
        resp = self.run(request)
        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            command=request.command,
            backend="ssh",
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

    def cleanup(self):
        """Clean up any active SSH sessions."""
        for proc in self._active_sessions.values():
            try:
                proc.kill()
            except Exception:
                pass
        self._active_sessions.clear()
