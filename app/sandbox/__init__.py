"""MOON Sandbox package (spec section 6: sandbox/, section 19).

Compatibility layer re-exporting the real SandboxExecutor from app.capability.sandbox.
Non-destructive: implementation is not duplicated or replaced.
"""

from __future__ import annotations

from app.capability.sandbox import SandboxExecutor, SandboxResult  # noqa: F401


class SandboxManager:
    """Thin spec-aligned facade over the real SandboxExecutor (spec 19)."""

    def __init__(self, workspace_root=None) -> None:
        self._exec = SandboxExecutor(workspace_root=workspace_root)

    def run(self, cmd, *, timeout=180, network=False, cwd=None):
        return self._exec.run(cmd, timeout=timeout, network=network, cwd=cwd)


# Spec-aligned submodule re-exports (real logic lives in app.capability.sandbox).
__all__ = ["SandboxExecutor", "SandboxResult", "SandboxManager"]
