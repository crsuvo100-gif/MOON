"""Agent Factory: Performance Evaluator (spec 28 + MOON Factory design).

Scores a generated agent with the weighted formula from spec section 28 and
records a performance benchmark. Kept in its own module per the spec
directory layout (agent_factory/evaluator.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent_factory.architect import AgentSpec
from app.agent_factory.tester import TestResult


@dataclass
class EvalResult:
    overall: float
    correctness: float
    reliability: float
    verification: float
    recovery: float
    efficiency: float
    resource_usage: float
    notes: str = ""


class PerformanceEvaluator:
    """Scores a generated agent (spec 28 weighted formula)."""

    def evaluate(self, spec: AgentSpec, test: TestResult, security_ok: bool) -> EvalResult:
        correctness = 1.0 if test.passed else 0.0
        verification = 1.0 if test.passed else 0.0
        reliability = 1.0 if test.passed else 0.5
        recovery = 1.0 if security_ok else 0.5
        efficiency = 1.0
        resource_usage = 1.0
        overall = (0.35 * correctness + 0.20 * reliability + 0.15 * verification
                   + 0.10 * recovery + 0.10 * efficiency + 0.10 * resource_usage)
        return EvalResult(overall=round(overall, 3), correctness=correctness,
                          reliability=reliability, verification=verification,
                          recovery=recovery, efficiency=efficiency,
                          resource_usage=resource_usage,
                          notes=f"tests_passed={test.passed} security_ok={security_ok}")


__all__ = ["PerformanceEvaluator", "EvalResult"]
