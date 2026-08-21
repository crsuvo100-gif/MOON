"""GoalManager (spec section 9).

Manages the lifecycle of a goal: create an execution id, capture the structured
GoalSpec, check memory + knowledge for relevant prior context, and record the
final outcome. Reuses MOON's existing memory/knowledge layers when available;
degrades gracefully (reports missing context) instead of failing (spec 59).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.runtime.task_analyzer import GoalSpec, TaskAnalyzer


@dataclass
class Goal:
    execution_id: str
    spec: GoalSpec
    created_at: str
    memory_hits: list[str] = field(default_factory=list)
    knowledge_hits: list[str] = field(default_factory=list)
    status: str = "created"
    result: str = ""


class GoalManager:
    def __init__(self, analyzer: TaskAnalyzer | None = None) -> None:
        self.analyzer = analyzer or TaskAnalyzer()
        self._goals: dict[str, Goal] = {}

    def create(self, request: str) -> Goal:
        spec = self.analyzer.analyze(request)
        gid = uuid.uuid4().hex[:12]
        goal = Goal(execution_id=gid, spec=spec,
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._goals[gid] = goal
        self._search_context(goal)
        return goal

    def _search_context(self, goal: Goal) -> None:
        # Reuse existing memory/knowledge if importable; never fail if absent.
        try:
            from app.memory.memory_manager import MemoryManager
            mm = MemoryManager()
            hits = mm.search(goal.spec.goal, k=3)
            goal.memory_hits = [str(h)[:120] for h in (hits or [])]
        except Exception:  # noqa: BLE001
            goal.memory_hits = []
        try:
            from app.knowledge.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            res = kb.search(goal.spec.goal, k=3)
            goal.knowledge_hits = [str(r)[:120] for r in (res or [])]
        except Exception:  # noqa: BLE001
            goal.knowledge_hits = []

    def complete(self, execution_id: str, result: str) -> Goal | None:
        g = self._goals.get(execution_id)
        if g:
            g.status = "completed"
            g.result = result
        return g

    def get(self, execution_id: str) -> Goal | None:
        return self._goals.get(execution_id)

    def all(self) -> list[Goal]:
        return list(self._goals.values())

    def to_report(self, goal: Goal) -> dict[str, Any]:
        return {
            "execution_id": goal.execution_id,
            "goal": goal.spec.goal,
            "risk": goal.spec.risk,
            "required_capabilities": goal.spec.required_capabilities,
            "memory_hits": len(goal.memory_hits),
            "knowledge_hits": len(goal.knowledge_hits),
            "status": goal.status,
        }
