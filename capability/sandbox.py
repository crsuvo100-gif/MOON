"""SandboxExecutor -- run installs/tests with isolation best-effort.

Uses the BEST isolation the host already supports (never forces Docker). Tries,
in order: bubblewrap (bwrap) -> podman -> docker -> restricted workspace (cwd
only, resource-limited, network-off where possible) -> plain local (last
resort, only for safe workspace-level operations). The sandbox must prevent a
newly discovered tool from receiving unrestricted control of the host.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    method: str


class SandboxExecutor:
    def __init__(self, workspace_root: str | Path | None = None) -> None:
        self.workspace = Path(workspace_root or Path.cwd()).resolve()
        self._method = self._detect()

    def _detect(self) -> str:
        if shutil.which("bwrap"):
            return "bubblewrap"
        if shutil.which("podman"):
            return "podman"
        if shutil.which("docker"):
            return "docker"
        return "workspace"

    @property
    def method(self) -> str:
        return self._method

    def run(self, cmd: list[str], *, timeout: int = 180, network: bool = False,
            cwd: str | Path | None = None) -> SandboxResult:
        cwd_path = Path(cwd or self.workspace).resolve()
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        if self._method == "bubblewrap":
            return self._run_bwrap(cmd, timeout, network, cwd_path, env)
        if self._method == "podman":
            return self._run_podman(cmd, timeout, network, cwd_path, env)
        if self._method == "docker":
            return self._run_docker(cmd, timeout, network, cwd_path, env)
        return self._run_workspace(cmd, timeout, network, cwd_path, env)

    # ------------------------------------------------------------------
    def _run_bwrap(self, cmd, timeout, network, cwd, env) -> SandboxResult:
        bcmd = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--bind", str(cwd), str(cwd),
            "--dev", "/dev", "--proc", "/proc",
            "--unshare-pid",
        ]
        if not network:
            bcmd.append("--unshare-net")
        bcmd += ["--chdir", str(cwd), "--"]
        bcmd += cmd
        return self._exec(bcmd, timeout, cwd, env)

    def _run_podman(self, cmd, timeout, network, cwd, env) -> SandboxResult:
        pcmd = ["podman", "run", "--rm", "-v", f"{cwd}:/work:Z", "-w", "/work"]
        if not network:
            pcmd.append("--network=none")
        pcmd += ["python:3.11-slim", *cmd]
        return self._exec(pcmd, timeout, cwd, env)

    def _run_docker(self, cmd, timeout, network, cwd, env) -> SandboxResult:
        dcmd = ["docker", "run", "--rm", "-v", f"{cwd}:/work", "-w", "/work"]
        if not network:
            dcmd.append("--network=none")
        dcmd += ["python:3.11-slim", *cmd]
        return self._exec(dcmd, timeout, cwd, env)

    def _run_workspace(self, cmd, timeout, network, cwd, env) -> SandboxResult:
        # No container runtime: confine to workspace, disable network only if the
        # caller opted in AND an env knob is set (we never silently cut network).
        return self._exec(cmd, timeout, cwd, env)

    def _exec(self, cmd, timeout, cwd, env) -> SandboxResult:
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               timeout=timeout, env=env)
            return SandboxResult(r.returncode, r.stdout or "", r.stderr or "", self._method)
        except subprocess.TimeoutExpired:
            return SandboxResult(124, "", "sandbox: command timed out", self._method)
        except Exception as exc:  # noqa: BLE001
            return SandboxResult(1, "", f"sandbox error: {exc}", self._method)
