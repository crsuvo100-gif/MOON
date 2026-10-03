"""Task model -- the unit of work MOON executes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Task:
    prompt: str
    agent_name: str = "auto"
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    status: str = "pending"
    result: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0

    # --- optional spec enrichment slots (populated by the orchestrator's
    # additive runtime glue; declared here so the structured analysis is part
    # of the task contract rather than an ad-hoc dynamic attribute).
    # spec 10  -> structured GoalSpec from TaskAnalyzer
    _goal_spec: Any = None
    # spec 30  -> ModelRouter recommendation for the step
    _model_recommendation: Any = None
    # spec 12  -> capability-ranked agent candidates from the Agent Registry
    _selected_agents: list[str] = field(default_factory=list)
    # spec 26/27/28 -> aggregated + conflict-checked multi-agent result
    _aggregated: Any = None

    @classmethod
    def create(cls, prompt: str, agent_name: str = "auto") -> Task:
        return cls(prompt=prompt, agent_name=agent_name)

    def mark_running(self) -> None:
        self.status = "running"

    def mark_done(self) -> None:
        # Idempotent terminal marker used by the fast-path / parallel fan-out
        # before returning the result (Task.complete() already sets "completed";
        # this mirrors mark_running for symmetry and avoids AttributeError).
        if self.status not in ("completed", "failed"):
            self.status = "done"

    def complete(self, result: str, *, data: dict[str, Any] | None = None, tokens_used: int = 0) -> None:
        self.status = "completed"
        self.result = result
        if data is not None:
            self.data.update(data)
        self.tokens_used = tokens_used

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.result = error
