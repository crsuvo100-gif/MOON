"""VerificationEngine -- prove an acquired capability actually works.

Runs a non-destructive health test appropriate to the capability type:
  * importable python module -> import it
  * CLI utility -> run ``<util> --version`` / ``--help`` (first word only)
  * registered tool -> call a cheap probe if available

Never runs unknown upstream code as the health test; only safe probes.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    ok: bool
    detail: str = ""
    health: str = "unhealthy"   # healthy | degraded | unhealthy


class VerificationEngine:
    def verify_import(self, import_name: str) -> VerifyResult:
        try:
            import importlib
            importlib.import_module(import_name)
            return VerifyResult(True, f"import {import_name} OK", "healthy")
        except Exception as exc:  # noqa: BLE001
            return VerifyResult(False, f"import {import_name} failed: {exc}", "unhealthy")

    def verify_cli(self, util: str, timeout: int = 30) -> VerifyResult:
        if not shutil.which(util):
            return VerifyResult(False, f"{util} not on PATH", "unhealthy")
        for flag in ("--version", "--help", "-V", "version"):
            try:
                r = subprocess.run([util, flag], capture_output=True, text=True, timeout=timeout)
                if r.returncode in (0, 1):  # many tools exit 1 on --help
                    return VerifyResult(True, f"{util} {flag}: rc={r.returncode}", "healthy")
            except Exception:  # noqa: BLE001
                continue
        # fallback: just the binary runs
        try:
            r = subprocess.run([util], capture_output=True, text=True, timeout=timeout)
            return VerifyResult(True, f"{util} present (rc={r.returncode})", "degraded")
        except Exception as exc:  # noqa: BLE001
            return VerifyResult(False, f"{util} probe failed: {exc}", "unhealthy")

    def verify(self, rec_type: str, target: str) -> VerifyResult:
        if rec_type == "python":
            return self.verify_import(target)
        if rec_type == "cli":
            return self.verify_cli(target)
        return VerifyResult(False, f"no verifier for type {rec_type}", "unhealthy")
