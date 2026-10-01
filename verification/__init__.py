"""Verification subsystem (spec section 27).

MOON must never accept "Done." as success -- it requires evidence. This
package provides a reusable Verifier that checks structured results produced
by agents/tools against concrete evidence requirements (spec 27 examples):
test pass, file exists, HTTP+schema, version check, expected==actual state.

Reuses MOON's existing ``app.brain.validator`` output-validation where present
and adds evidence-based checks on top. Non-destructive: this is a new package,
no existing module is touched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VerificationResult:
    """Outcome of a verification pass (structured, never free-form only)."""

    passed: bool
    method: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "method": self.method,
            "detail": self.detail,
            "evidence": self.evidence,
            "issues": self.issues,
        }


class Verifier:
    """Evidence-based verification (spec 27). All checks return a structured
    :class:`VerificationResult`; no check silently returns 'success'."""

    def file_exists(self, path: str) -> VerificationResult:
        ok = bool(path) and os.path.exists(path)
        return VerificationResult(
            passed=ok, method="FILE_EXISTS", detail=f"path={path}",
            evidence={"exists": ok},
            issues=[] if ok else [f"expected file missing: {path}"],
        )

    def http_ok(self, status_code: int) -> VerificationResult:
        ok = 200 <= status_code < 300
        return VerificationResult(
            passed=ok, method="HTTP_STATUS", detail=f"status={status_code}",
            evidence={"status_code": status_code},
            issues=[] if ok else [f"unexpected HTTP status {status_code}"],
        )

    def version_present(self, version: str | None) -> VerificationResult:
        ok = bool(version)
        return VerificationResult(
            passed=ok, method="VERSION_CHECK", detail=f"version={version}",
            evidence={"version": version or ""},
            issues=[] if ok else ["no version reported"],
        )

    def state_match(self, expected: Any, actual: Any) -> VerificationResult:
        ok = expected == actual
        return VerificationResult(
            passed=ok, method="STATE_MATCH",
            detail=f"expected={expected!r} actual={actual!r}",
            evidence={"expected": expected, "actual": actual},
            issues=[] if ok else ["expected state != actual state"],
        )

    def result_ok(self, result: dict[str, Any] | None) -> VerificationResult:
        """Verify a structured result (spec 7) carries success + evidence."""
        if not isinstance(result, dict):
            return VerificationResult(
                passed=False, method="RESULT_SCHEMA",
                issues=["result is not a structured dict"])
        ok = bool(result.get("success")) and bool(result.get("evidence") or result.get("result"))
        issues: list[str] = []
        if not result.get("success"):
            err = result.get("errors")
            if isinstance(err, (list, tuple)):
                err = "; ".join(str(e) for e in err) or "reported failure"
            issues.append(err or "reported failure")
        if not (result.get("evidence") or result.get("result")):
            issues.append("no evidence/result attached")
        return VerificationResult(
            passed=ok, method="RESULT_SCHEMA",
            evidence={"success": result.get("success"),
                      "has_evidence": bool(result.get("evidence") or result.get("result"))},
            issues=issues,
        )


__all__ = ["Verifier", "VerificationResult"]
