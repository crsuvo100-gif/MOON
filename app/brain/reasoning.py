"""ReasoningEngine -- lightweight reasoning helper over the LLM."""

from __future__ import annotations

from typing import Any


class ReasoningEngine:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def reason(self, query: str) -> str:
        if self._llm is None:
            return query
        return query
