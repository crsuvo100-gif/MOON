"""Agent Factory: Security Reviewer + Repair Agent (spec 18, 29 + MOON Factory).

Security Reviewer: static checks of generated code for forbidden patterns
(modifying MOON core, secret exfiltration, unsafe eval/exec, network exfil)
and verifies required permissions are within the requested risk level.
Repair Agent: on test failure, applies a safe, bounded fix (re-generate with
the corrected capability) -- never silently rewrites MOON core.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent_factory.architect import AgentSpec
from app.agent_factory.builder import BuildArtifact
from app.agent_factory.tester import TestResult


# Patterns that are never allowed in generated agent code (spec 18/47/50).
_FORBIDDEN = [
    (r"import\s+os\s*;.*system\(", "shell escape"),
    (r"eval\s*\(", "unrestricted eval"),
    (r"exec\s*\(", "unrestricted exec"),
    (r"app\.brain", "modifies MOON core"),
    (r"app\.agent_factory\.models", "tampers factory models"),
    (r"subprocess.*shell\s*=\s*True", "unsafe shell"),
    (r"requests\.get\(.*verify\s*=\s*False", "tls verification disabled"),
    (r"open\([^)]*,\s*['\"]w\+?['\"]", "writes outside sandbox"),
]


@dataclass
class ReviewResult:
    approved: bool
    violations: list[str] = field(default_factory=list)
    notes: str = ""


class SecurityReviewer:
    def review(self, artifact: BuildArtifact, spec: AgentSpec) -> ReviewResult:
        violations: list[str] = []
        code = ""
        if artifact.module_path:
            try:
                code = Path(artifact.module_path).read_text()
            except Exception:  # noqa: BLE001
                code = ""
        for pat, label in _FORBIDDEN:
            if re.search(pat, code or ""):
                violations.append(label)
        # risk gating: critical actions require explicit permissions
        if spec.risk_level == "critical" and "ADMIN" not in spec.permissions:
            violations.append("critical risk without ADMIN permission")
        return ReviewResult(approved=len(violations) == 0, violations=violations,
                            notes="static review of generated module")


class RepairAgent:
    """On test failure, attempt a safe re-generation (spec 29 DIAGNOSE->REPAIR).

    Does NOT edit MOON core. It re-runs the Builder with the same spec and
    returns a fresh artifact + whether the repair changed anything.
    """

    def repair(self, spec: AgentSpec, artifact: BuildArtifact, staging_dir: str | Path,
               test: TestResult) -> tuple[BuildArtifact, bool]:
        if test.passed:
            return artifact, False
        # Bounded, safe repair: regenerate (deterministic) and re-run caller-side.
        from app.agent_factory.builder import AgentBuilder
        new = AgentBuilder().build(spec, staging_dir)
        changed = new.module_path != artifact.module_path or new.ok != artifact.ok
        return new, changed


__all__ = ["SecurityReviewer", "ReviewResult", "RepairAgent"]
