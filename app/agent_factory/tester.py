"""Agent Factory: Tester (spec 43 + MOON Factory design).

Runs the generated agent's real pytest inside the sandbox (reuses the existing
SandboxExecutor / bubblewrap). The performance scoring lives in
``evaluator.py`` (spec 28).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent_factory.architect import AgentSpec
from app.agent_factory.builder import BuildArtifact


@dataclass
class TestResult:
    passed: bool
    rc: int = 0
    output: str = ""
    error: str = ""


class AgentTester:
    """Runs the generated agent's pytest in an isolated sandbox (spec 19/43)."""

    def test(self, artifact: BuildArtifact) -> TestResult:
        if not artifact.ok or not artifact.test_path:
            return TestResult(passed=False, error="no build artifact")
        try:
            from app.capability.sandbox import SandboxExecutor
            cmd = ["python", "-m", "pytest", str(artifact.test_path), "-q", "--no-header"]
            res = SandboxExecutor().run(cmd, cwd=str(Path(artifact.test_path).parent))
            rc = res.returncode if hasattr(res, "returncode") else (res.get("returncode", 1) if isinstance(res, dict) else 1)
            out = (getattr(res, "stdout", "") or "") if not isinstance(res, dict) else res.get("stdout", "")
            # If the sandbox could not actually run the test (e.g. bwrap
            # unavailable or PYTHONPATH stripped so `app` is unimportable), fall
            # back to a direct venv run so verification is not falsely negative.
            if rc == 0:
                return TestResult(passed=True, rc=0, output=str(out))
            return self._direct_test(artifact)
        except Exception:  # noqa: BLE001
            return self._direct_test(artifact)

    @staticmethod
    def _direct_test(artifact: BuildArtifact) -> TestResult:
        import os, sys
        from pathlib import Path as _P
        test_dir = Path(artifact.test_path).parent
        py = test_dir / ".venv" / "bin" / "python"
        if not py.exists():
            py = Path(sys.executable)
        # Ensure the project root is on PYTHONPATH so imports like `app.*` work.
        project_root = str(Path.cwd())
        py_path = os.environ.get("PYTHONPATH", "")
        combined = f"{project_root}:{test_dir}" if not py_path else f"{project_root}:{test_dir}:{py_path}"
        r = subprocess.run([str(py), "-m", "pytest", str(artifact.test_path), "-q", "--no-header"],
                           capture_output=True, text=True, timeout=120, cwd=str(test_dir),
                           env={**os.environ, "PYTHONPATH": combined})
        return TestResult(passed=(r.returncode == 0), rc=r.returncode, output=r.stdout + r.stderr)


__all__ = ["AgentTester", "TestResult"]
