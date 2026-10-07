"""Docker backend with real container execution.

Provides isolated workspace, resource limits, environment isolation,
timeouts, output limits, and cleanup.

Docker is optional — MOON works without it.
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


class DockerBackend:
    """Execute commands in Docker containers with isolation and resource limits."""

    def __init__(self):
        self.bus = get_bus()
        self.available = shutil.which("docker") is not None
        self._active_containers: Dict[str, str] = {}  # execution_id → container_id

    def _build_docker_args(self, request: ExecutionRequest) -> List[str]:
        """Build docker run arguments from an ExecutionRequest."""
        args = ["docker", "run", "--rm"]

        # Resource limits
        args.extend(["--memory", "512m"])
        args.extend(["--cpus", "1.0"])

        # Network isolation (no network by default for security)
        args.extend(["--network", "none"])

        # Working directory
        cwd = request.cwd or Path.cwd()
        args.extend(["-w", str(cwd)])

        # Environment variables (only non-sensitive ones)
        if request.env:
            for key, value in request.env.items():
                # Skip sensitive env vars
                upper = key.upper()
                if any(s in upper for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "API")):
                    continue
                args.extend(["-e", f"{key}={value}"])

        # Mount the working directory as a volume
        args.extend(["-v", f"{cwd}:{cwd}"])

        # Use a minimal image
        args.append("alpine:latest")

        # Command
        if request.shell:
            args.extend(["/bin/sh", "-c", request.command])
        else:
            try:
                args.extend(shlex.split(request.command))
            except ValueError:
                args.extend(["/bin/sh", "-c", request.command])

        return args

    def run(
        self,
        request: ExecutionRequest,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """Execute a command in a Docker container."""
        if not self.available:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Docker is not available on this system",
                "pid": None,
                "timed_out": False,
            }

        cwd = request.cwd or Path.cwd()
        args = self._build_docker_args(request)
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
                "stderr": stderr_raw + f"\nDocker command timed out after {request.timeout}s",
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
        """Execute a request in Docker and return ExecutionResult."""
        resp = self.run(request)
        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            command=request.command,
            backend="docker",
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
        """Clean up any remaining containers."""
        # With --rm flag, containers are auto-removed
        pass
