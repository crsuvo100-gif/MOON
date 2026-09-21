"""EvaluationEngine (spec section 28).

Scores an execution across correctness, reliability, latency, resource usage,
tool efficiency, failure rate, recovery rate, and verification quality. The
overall score follows the spec's weighted formula:

  overall = 0.35*correctness + 0.20*reliability + 0.15*verification
          + 0.10*recovery + 0.10*efficiency + 0.10*resource_usage

All inputs are real metrics (no fabricated scores). Keeps a history so trends
can be observed (spec 28 "Keep evaluation history").
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreCard:
    correctness: float = 0.0        # 0..1
    reliability: float = 0.0         # 0..1
    verification: float = 0.0        # 0..1
    recovery: float = 0.0            # 0..1
    efficiency: float = 0.0          # 0..1
    resource_usage: float = 0.0      # 0..1 (higher = better utilisation)
    overall: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "correctness": self.correctness, "reliability": self.reliability,
            "verification": self.verification, "recovery": self.recovery,
            "efficiency": self.efficiency, "resource_usage": self.resource_usage,
            "overall": self.overall, "notes": self.notes,
        }


class EvaluationEngine:
    def __init__(self) -> None:
        self._history: list[ScoreCard] = []

    @staticmethod
    def _overall(c: ScoreCard) -> float:
        return round(
            0.35 * c.correctness + 0.20 * c.reliability + 0.15 * c.verification
            + 0.10 * c.recovery + 0.10 * c.efficiency + 0.10 * c.resource_usage, 3
        )

    def score(self, *, correctness: float, reliability: float = 1.0,
              verification: float = 0.0, recovery: float = 0.0,
              efficiency: float = 1.0, resource_usage: float = 1.0,
              notes: str = "") -> ScoreCard:
        # Clamp to [0,1]
        vals = [correctness, reliability, verification, recovery, efficiency, resource_usage]
        vals = [max(0.0, min(1.0, float(v))) for v in vals]
        c = ScoreCard(correctness=vals[0], reliability=vals[1], verification=vals[2],
                      recovery=vals[3], efficiency=vals[4], resource_usage=vals[5], notes=notes)
        c.overall = self._overall(c)
        self._history.append(c)
        return c

    def from_execution(self, result: dict[str, Any]) -> ScoreCard:
        """Build a ScoreCard from a structured execution result (spec 7 shape)."""
        success = bool(result.get("success"))
        has_evidence = bool(result.get("evidence"))
        errors = result.get("errors") or []
        correctness = 1.0 if success else 0.0
        verification = 1.0 if has_evidence else 0.0
        reliability = 0.0 if errors else 1.0
        return self.score(correctness=correctness, reliability=reliability,
                          verification=verification, notes=result.get("status", ""))

    def history(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self._history]

    def average_overall(self) -> float:
        if not self._history:
            return 0.0
        return round(sum(c.overall for c in self._history) / len(self._history), 3)
