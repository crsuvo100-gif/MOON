"""
Planner — task decomposition for coordinator agent.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.llm_service import ChatMessage, LLMService
from app.brain.prompt_manager import PromptManager

logger = logging.getLogger("moontm.planner")


class Planner:
    def __init__(self, llm: LLMService, prompts: PromptManager) -> None:
        self._llm = llm
        self._prompts = prompts

    async def plan(self, task_prompt: str) -> Optional[str]:
        messages = [
            ChatMessage(role="system", content=self._prompts.planning(task_prompt)),
            ChatMessage(role="user", content=task_prompt),
        ]
        result = await self._llm.complete(messages, max_tokens=800)
        return result.content
