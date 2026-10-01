"""Sandbox filesystem / limits / policies (spec 6: sandbox/).

These re-export the real SandboxExecutor behaviour. The real implementation
enforces temporary filesystem, CPU/memory/process limits, timeouts, network
policy and cleanup (spec 19). Where a finer-grained helper is not separately
exposed, the SandboxExecutor.run call is the authoritative enforcement point.
"""

from app.capability.sandbox import SandboxExecutor, SandboxResult  # noqa: F401

__all__ = ["SandboxExecutor", "SandboxResult"]
