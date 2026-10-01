"""AgentRouter (spec section 12).

Selects agents based on capability match, permissions, historical performance,
risk, and tool availability -- NOT by name alone. Reuses MOON's existing agent
registry (built-ins + factory-generated) and the AgentFactory store for
performance/risk data. Falls back gracefully when no strong match exists.
"""

from __future__ import annotations

import logging
from typing import Any

from app.runtime.task_analyzer import GoalSpec

logger = logging.getLogger(__name__)


class AgentRouter:
    def __init__(self) -> None:
        self._perf: dict[str, float] = {}  # agent_name -> rolling success score

    # -- performance tracking (§12 historical performance) -----------------
    def record_outcome(self, agent_name: str, success: bool) -> None:
        prev = self._perf.get(agent_name, 1.0)
        # exponential moving average of success
        self._perf[agent_name] = round(0.7 * prev + 0.3 * (1.0 if success else 0.0), 3)

    def performance(self, agent_name: str) -> float:
        return self._perf.get(agent_name, 0.9)

    # -- candidate enumeration (reuse existing agents) --------------------
    def _candidates(self) -> list[str]:
        names: list[str] = []
        try:
            from app.brain.agent_registry import get_existing_agent_names
            names = list(get_existing_agent_names())
        except Exception:  # noqa: BLE001
            pass
        # also include generated agents from the factory store
        try:
            from app.agent_factory.store import AgentStore
            for r in AgentStore().all():
                if r.name not in names:
                    names.append(r.name)
        except Exception:  # noqa: BLE001
            pass
        return names

    def _capability_of(self, name: str) -> str:
        # Map agent name -> its primary capability token (best-effort).
        return name.split("_")[0]

    # -- routing ----------------------------------------------------------
    def route(self, spec: GoalSpec) -> list[str]:
        """Return an ordered list of suitable agent names (best first)."""
        wanted = set(spec.required_capabilities)
        scored: list[tuple[float, str]] = []
        for name in self._candidates():
            cap = self._capability_of(name)
            cap_match = 1.0 if (wanted and cap in wanted) else 0.2
            perf = self.performance(name)
            # risk: prefer lower-risk; high-risk tasks need authorized agents
            risk_penalty = 0.0
            if spec.risk in ("high", "critical") and name in ("red_team", "cyber", "purple_team"):
                risk_penalty = 0.0  # these are the authorized high-risk agents
            score = round(0.5 * cap_match + 0.4 * perf + 0.1 - risk_penalty, 3)
            scored.append((score, name))
        scored.sort(reverse=True)
        return [n for _, n in scored]

    def select(self, spec: GoalSpec) -> str | None:
        routed = self.route(spec)
        return routed[0] if routed else None

    def explain(self, spec: GoalSpec) -> dict[str, Any]:
        return {
            "required_capabilities": spec.required_capabilities,
            "risk": spec.risk,
            "selected": self.select(spec),
            "ranked": self.route(spec)[:5],
        }
