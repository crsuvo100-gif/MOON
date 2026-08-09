"""Base agent: wraps an AgentBrain with a run loop."""

from __future__ import annotations

import logging

from app.brain.agent_brain import AgentBrain

logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, name: str, main_brain=None) -> None:
        self.name = name
        self.brain = AgentBrain(name, main_brain=main_brain)

    async def setup(self) -> None:
        await self.brain.setup()

    async def run(self, task: str, context: str = "") -> str:
        return await self.brain.run(task, context)

    async def teardown(self) -> None:
        await self.brain.teardown()
