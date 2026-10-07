"""Python executor for MOON terminal.

Provides specialized Python execution capabilities:
- Detect Python (python, python3)
- Virtual environment detection and activation
- Module execution (python -m)
- Script execution
- pip / dependency installation
- Import checking
- Test execution

Integrates with the terminal execution engine for risk/permission handling.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .models import ExecutionRequest, ExecutionResult
from .event_bus import get_bus


class PythonExecutor:
    """Specialized Python execution with environment awareness."""

    def __init__(self):
        self.bus = get_bus()
        self._detected_python: Optional[str] = None
        self._detected_pip: Optional[str] = None
        self._detect_python()

    def _detect_python(self):
        """Detect available Python interpreters."""
        for cmd in ("python3", "python"):
            path = shutil.which(cmd)
            if path:
                self._detected_python = path
                break
        if not self._detected_python:
            self._detected_python = sys.executable

        # Detect pip
        for cmd in ("pip3", "pip"):
            path = shutil.which(cmd)
            if path:
                self._detected_pip = path
                break

    @property
    def python_path(self) -> str:
        """Get the detected Python interpreter path."""
        return self._detected_python or sys.executable

    @property
    def pip_path(self) -> Optional[str]:
        """Get the detected pip path."""
        return self._detected_pip

    @property
    def version(self) -> str:
        """Get the Python version string."""
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    def get_virtual_env(self) -> Optional[str]:
        """Get the active virtual environment path, if any."""
        return os.environ.get("VIRTUAL_ENV")

    def is_virtual_env_active(self) -> bool:
        """Check if a virtual environment is currently active."""
        return self.get_virtual_env() is not None

    def find_virtual_envs(self, cwd: Optional[Path] = None) -> List[Path]:
        """Find virtual environments in the current directory tree."""
        cwd = cwd or Path.cwd()
        venvs = []
        for name in ("venv", ".venv", "env", ".env"):
            candidate = cwd / name
            if candidate.is_dir() and (candidate / "bin" / "python").exists():
                venvs.append(candidate)
        return venvs

    def execute_code(
        self,
        code: str,
        cwd: Optional[Path] = None,
        timeout: int = 30,
        on_output=None,
    ) -> ExecutionResult:
        """Execute Python code string."""
        cwd = cwd or Path.cwd()
        start_time = time.time()
        execution_id = str(uuid.uuid4())

        try:
            proc = subprocess.Popen(
                [self.python_path, "-c", code],
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout_parts: List[str] = []
            stderr_parts: List[str] = []

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
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                exit_code = -1

            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

            duration = time.time() - start_time
            status = "success" if exit_code == 0 else "failed"

            return ExecutionResult(
                execution_id=execution_id,
                command=f"python -c {code[:50]}",
                backend="local",
                cwd=cwd,
                status=status,
                exit_code=exit_code,
                stdout="".join(stdout_parts),
                stderr="".join(stderr_parts),
                pid=proc.pid,
                duration=duration,
                verified=False,
                verification_result=None,
                error=None,
            )

        except Exception as exc:
            return ExecutionResult(
                execution_id=execution_id,
                command=f"python -c {code[:50]}",
                backend="local",
                cwd=cwd,
                status="failed",
                exit_code=None,
                stdout=None,
                stderr=None,
                pid=None,
                duration=time.time() - start_time,
                verified=False,
                verification_result=None,
                error=str(exc),
            )

    def execute_module(
        self,
        module: str,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        timeout: int = 60,
    ) -> ExecutionResult:
        """Execute a Python module (python -m module)."""
        cmd = f"python -m {module}"
        if args:
            cmd += " " + " ".join(args)
        req = ExecutionRequest(
            command=cmd,
            cwd=cwd,
            env=None,
            backend="local",
            shell=True,
            timeout=timeout,
            background=False,
            interactive=False,
            permission_mode="ask",
            verification=None,
        )
        from .execution_engine import execution_engine
        return execution_engine.execute(req)

    def execute_script(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
        timeout: int = 60,
    ) -> ExecutionResult:
        """Execute a Python script file."""
        cmd = f"python {script_path}"
        if args:
            cmd += " " + " ".join(args)
        req = ExecutionRequest(
            command=cmd,
            cwd=cwd,
            env=None,
            backend="local",
            shell=True,
            timeout=timeout,
            background=False,
            interactive=False,
            permission_mode="ask",
            verification=None,
        )
        from .execution_engine import execution_engine
        return execution_engine.execute(req)

    def install_package(
        self,
        package: str,
        cwd: Optional[Path] = None,
        timeout: int = 120,
    ) -> ExecutionResult:
        """Install a Python package via pip."""
        cmd = f"python -m pip install {package}"
        req = ExecutionRequest(
            command=cmd,
            cwd=cwd,
            env=None,
            backend="local",
            shell=True,
            timeout=timeout,
            background=False,
            interactive=False,
            permission_mode="ask",
            verification=None,
        )
        from .execution_engine import execution_engine
        return execution_engine.execute(req)

    def check_import(self, module: str, cwd: Optional[Path] = None) -> bool:
        """Check if a Python module can be imported."""
        try:
            result = subprocess.run(
                [self.python_path, "-c", f"import {module}"],
                cwd=str(cwd or Path.cwd()),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_installed_packages(self, cwd: Optional[Path] = None) -> List[str]:
        """Get list of installed Python packages."""
        try:
            result = subprocess.run(
                [self.python_path, "-m", "pip", "list", "--format=freeze"],
                cwd=str(cwd or Path.cwd()),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            pass
        return []

    def run_tests(
        self,
        test_path: Optional[Path] = None,
        cwd: Optional[Path] = None,
        timeout: int = 120,
    ) -> ExecutionResult:
        """Run Python tests via pytest."""
        cmd = "python -m pytest"
        if test_path:
            cmd += f" {test_path}"
        cmd += " -v"
        req = ExecutionRequest(
            command=cmd,
            cwd=cwd,
            env=None,
            backend="local",
            shell=True,
            timeout=timeout,
            background=False,
            interactive=False,
            permission_mode="auto",
            verification=None,
        )
        from .execution_engine import execution_engine
        return execution_engine.execute(req)


# Module-level singleton
python_executor = PythonExecutor()
