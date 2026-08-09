"""planner.py -- decomposes a goal into an ordered plan of sub-steps.

Real LLM-driven planning with a safe offline fallback. Used by the
coordinator / task-decomposition path.
"""

from __future__ import annotations

import json
import re

from app.services.llm_service import ChatMessage


class Planner:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def plan(self, goal: str) -> list[str]:
        if self._llm is not None:
            try:
                resp = await self._llm.complete(
                    [ChatMessage(role="user", content=(
                        "Break the following goal into a concise, ordered list of "
                        "actionable sub-steps (each one line, no numbering symbols). "
                        "Keep it under 8 steps. Goal: " + goal
                    ))],
                    max_tokens=300, temperature=0.2,
                )
                steps = [s.strip("0123456789. )-") for s in (resp.content or "").splitlines()]
                steps = [s for s in steps if s]
                if steps:
                    return steps
            except Exception:  # noqa: BLE001
                pass
        # offline fallback: a sensible generic skeleton
        return [f"Analyze: {goal}", "Identify sub-tasks", "Execute", "Validate result"]
