"""
ReasoningEngine — chain-of-thought via LLM.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.llm_service import ChatMessage, LLMService
from app.brain.prompt_manager import PromptManager

logger = logging.getLogger("moontm.reasoning")


class ReasoningEngine:
    def __init__(self, llm: LLMService, prompts: PromptManager) -> None:
        self._llm = llm
        self._prompts = prompts

    async def reason(self, query: str, max_tokens: int = 600) -> str:
        messages = [
            ChatMessage(role="system", content="Reason step by step. Show analysis, intermediate steps, and a clear conclusion."),
            ChatMessage(role="user", content=query),
        ]
        result = await self._llm.complete(
            messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        if result.content:
            return result.content
        logger.warning("ReasoningEngine: empty result for query: %s", query[:80])
        return query  # fallback to echo
