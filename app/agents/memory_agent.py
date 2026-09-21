"""Memory agent: specializes in indexing + recalling knowledge."""

from __future__ import annotations

from app.agents.base import BaseAgent


class MemoryAgent(BaseAgent):
    def __init__(self, main_brain=None) -> None:
        super().__init__("memory", main_brain=main_brain)

    async def run(self, task: str, context: str = "") -> str:
        # Memory agent leans on the main brain's recall for answers.
        if self.brain.main_brain is not None:
            return await self.brain.refine_with_main(context or task, task)
        return await super().run(task, context)
