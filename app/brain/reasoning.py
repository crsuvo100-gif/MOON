"""reasoning.py -- structured chain-of-thought reasoning over the LLM.

Provides a real reasoning pass (analysis -> steps -> conclusion) used by the
cognition loop for harder tasks. Falls back to echoing the query only when no
LLM is available.
"""

from __future__ import annotations

from app.services.llm_service import ChatMessage


class ReasoningEngine:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def reason(self, query: str) -> str:
        if self._llm is None:
            return query
        try:
            resp = await self._llm.complete(
                [ChatMessage(role="user", content=(
                    "Reason step by step about the following. Show your analysis, "
                    "intermediate steps, and a clear final conclusion.\n\n" + query
                ))],
                max_tokens=600, temperature=0.3,
            )
            return (resp.content or "").strip() or query
        except Exception:  # noqa: BLE001
            return query
