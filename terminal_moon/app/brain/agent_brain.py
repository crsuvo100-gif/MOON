"""
AgentBrain — per-agent durable brain with two-phase validation gate.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.brain.memory_manager import MemoryManager
from app.services.llm_service import LLMService, ChatMessage

logger = logging.getLogger("moontm.agent_brain")


class AgentBrain:
    """Each agent gets its own durable memory + refinement gate."""

    def __init__(
        self,
        name: str,
        main_brain: "Orchestrator",  # noqa: F821  (forward ref)
        agent_models: Optional[Any] = None,
    ) -> None:
        self._name = name
        self._main = main_brain
        self._models = agent_models
        self._memory: Optional[MemoryManager] = None
        self._episodes: list[dict] = []
        self._logger = logging.getLogger(f"moontm.agent_brain.{name}")

    async def setup(self) -> None:
        # Wire a shared memory manager reference (or a dedicated one if needed)
        self._memory = self._main._memory
        self._logger.info("Agent brain '%s' wired to main memory", self._name)

    async def refine_with_main(self, final_text: str, task_prompt: str) -> str:
        """Two-phase gate: agent's brain refines the draft through the main brain."""
        if not self._main._llm:
            return final_text

        messages = [
            ChatMessage(role="system", content=(
                f"You are refining an answer produced by agent '{self._name}'. "
                f"The original answer:\n\n{final_text}\n\n"
                f"Task: {task_prompt}\n\n"
                "Improve clarity, accuracy, and completeness. Keep it concise."
            )),
            ChatMessage(role="user", content=f"Refined answer:\n{final_text}"),
        ]
        result = await self._main._llm.complete(messages, max_tokens=800)
        if result.content:
            self._logger.info("Refinement produced: %s chars", len(result.content))
            return result.content
        return final_text

    def remember(self, episode: dict) -> None:
        """Persist an episode into this agent's durable brain."""
        self._episodes.append(episode)
        self._logger.debug("Agent brain '%s' recorded episode: %s", self._name, episode.get("goal", "")[:60])
