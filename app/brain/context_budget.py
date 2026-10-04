"""Context Budget Enforcer (spec 49).

Every Agent Brain must have context limits. Before inference, calculate:
    SYSTEM TOKENS + TASK TOKENS + RELEVANT MEMORY + TOOL RESULTS + OUTPUT RESERVE

If too large:
1. remove low-priority context
2. summarize
3. retrieve selectively
4. compress
5. retry

Never blindly exceed model context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContextBudget:
    """Token budget for a single inference call (spec 49)."""
    model_context_limit: int = 8192
    system_tokens: int = 0
    task_tokens: int = 0
    memory_tokens: int = 0
    tool_result_tokens: int = 0
    output_reserve: int = 1024
    # Overhead per message (role, content markers, etc.)
    overhead_per_message: int = 10

    @property
    def total_used(self) -> int:
        return (
            self.system_tokens
            + self.task_tokens
            + self.memory_tokens
            + self.tool_result_tokens
            + self.output_reserve
        )

    @property
    def remaining(self) -> int:
        return self.model_context_limit - self.total_used

    @property
    def is_within_budget(self) -> bool:
        return self.total_used <= self.model_context_limit

    @property
    def utilization(self) -> float:
        if self.model_context_limit == 0:
            return 1.0
        return self.total_used / self.model_context_limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_context_limit": self.model_context_limit,
            "system_tokens": self.system_tokens,
            "task_tokens": self.task_tokens,
            "memory_tokens": self.memory_tokens,
            "tool_result_tokens": self.tool_result_tokens,
            "output_reserve": self.output_reserve,
            "total_used": self.total_used,
            "remaining": self.remaining,
            "is_within_budget": self.is_within_budget,
            "utilization": round(self.utilization, 3),
        }


class ContextBudgetEnforcer:
    """Enforces context budgets and applies compression strategies (spec 49).

    Strategies applied in order:
    1. Remove low-priority context (old tool results, low-importance memory)
    2. Summarize (compress conversation history)
    3. Retrieve selectively (reduce memory retrieval count)
    4. Compress (truncate individual messages)
    5. Retry (with reduced context)
    """

    def __init__(
        self,
        *,
        max_utilization: float = 0.95,
        compression_threshold: float = 0.8,
    ) -> None:
        self._max_utilization = max_utilization
        self._compression_threshold = compression_threshold

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses a simple heuristic: ~4 characters per token for English text.
        This is intentionally conservative (overestimates) to avoid overflow.
        """
        if not text:
            return 0
        # Conservative: 3.5 chars/token to avoid underestimating
        return max(1, int(len(text) / 3.5))

    def build_budget(
        self,
        *,
        model_context_limit: int,
        system_prompt: str,
        task: str,
        memory_items: list[str] | None = None,
        tool_results: list[str] | None = None,
        output_reserve: int = 1024,
    ) -> ContextBudget:
        """Build a context budget from components."""
        memory_items = memory_items or []
        tool_results = tool_results or []

        return ContextBudget(
            model_context_limit=model_context_limit,
            system_tokens=self.estimate_tokens(system_prompt),
            task_tokens=self.estimate_tokens(task),
            memory_tokens=sum(self.estimate_tokens(m) for m in memory_items),
            tool_result_tokens=sum(self.estimate_tokens(t) for t in tool_results),
            output_reserve=output_reserve,
        )

    def enforce(
        self,
        budget: ContextBudget,
        *,
        memory_items: list[str] | None = None,
        tool_results: list[str] | None = None,
    ) -> tuple[ContextBudget, list[str], list[str], list[str]]:
        """Enforce budget, returning adjusted budget + filtered items.

        Returns:
            (adjusted_budget, kept_memory, kept_tool_results, actions_taken)
        """
        memory_items = list(memory_items or [])
        tool_results = list(tool_results or [])
        actions: list[str] = []

        # Check if we're within budget (below compression threshold)
        if budget.is_within_budget and budget.utilization <= self._compression_threshold:
            return budget, memory_items, tool_results, actions

        # Strategy 1: Remove low-priority context (oldest tool results first)
        # Stop at max_utilization so compression has items to work with
        while (
            tool_results
            and budget.utilization > self._max_utilization
        ):
            removed = tool_results.pop(0)
            budget.tool_result_tokens -= self.estimate_tokens(removed)
            actions.append(f"removed_tool_result ({self.estimate_tokens(removed)} tokens)")

        # Strategy 2: Reduce memory items (keep most recent/important)
        while (
            memory_items
            and budget.utilization > self._max_utilization
        ):
            removed = memory_items.pop(0)
            budget.memory_tokens -= self.estimate_tokens(removed)
            actions.append(f"removed_memory_item ({self.estimate_tokens(removed)} tokens)")

        # Strategy 3: Compress remaining tool results (truncate to 50%)
        if budget.utilization > self._compression_threshold and tool_results:
            for i, tr in enumerate(tool_results):
                if len(tr) > 200:
                    compressed = tr[: len(tr) // 2] + "...[truncated]"
                    budget.tool_result_tokens += self.estimate_tokens(compressed) - self.estimate_tokens(tr)
                    tool_results[i] = compressed
            actions.append("compressed_tool_results")

        # Strategy 4: Compress memory items (truncate to 50%)
        if budget.utilization > self._compression_threshold and memory_items:
            for i, mem in enumerate(memory_items):
                if len(mem) > 200:
                    compressed = mem[: len(mem) // 2] + "...[truncated]"
                    budget.memory_tokens += self.estimate_tokens(compressed) - self.estimate_tokens(mem)
                    memory_items[i] = compressed
            actions.append("compressed_memory_items")

        # Strategy 5: Reduce output reserve as last resort
        if budget.utilization > self._compression_threshold:
            old_reserve = budget.output_reserve
            budget.output_reserve = max(256, budget.output_reserve // 2)
            actions.append(
                f"reduced_output_reserve ({old_reserve} -> {budget.output_reserve})"
            )

        return budget, memory_items, tool_results, actions

    def can_fit(
        self,
        *,
        model_context_limit: int,
        system_prompt: str,
        task: str,
        memory_items: list[str] | None = None,
        tool_results: list[str] | None = None,
        output_reserve: int = 1024,
    ) -> bool:
        """Check if the given context fits within the model's context limit."""
        budget = self.build_budget(
            model_context_limit=model_context_limit,
            system_prompt=system_prompt,
            task=task,
            memory_items=memory_items,
            tool_results=tool_results,
            output_reserve=output_reserve,
        )
        return budget.is_within_budget


# Module-level singleton
_ENFORCER: ContextBudgetEnforcer | None = None


def get_enforcer() -> ContextBudgetEnforcer:
    global _ENFORCER
    if _ENFORCER is None:
        _ENFORCER = ContextBudgetEnforcer()
    return _ENFORCER


__all__ = [
    "ContextBudget", "ContextBudgetEnforcer", "get_enforcer",
]
