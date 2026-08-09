"""Planner -- decomposes a goal into sub-steps."""

from __future__ import annotations

from typing import Any


class Planner:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def plan(self, goal: str) -> list[str]:
        # Lightweight default plan; the LLM path is optional/best-effort.
        return [f"Analyze: {goal}", "Execute", "Validate"]
