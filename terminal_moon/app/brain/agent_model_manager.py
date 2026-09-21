"""
Agent model manager — per-agent model routing + pre-pull (optional).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.llm_service import LLMService

logger = logging.getLogger("moontm.agent_models")


class AgentModelManager:
    """Optional per-agent model routing. Falls back to main LLM on failure."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._models: dict[str, LLMService] = {}

    async def get_llm(self, agent_name: str) -> Optional[LLMService]:
        if agent_name in self._models:
            return self._models[agent_name]
        return None

    async def prefetch_all(self, agents: list[str]) -> None:
        for name in agents:
            try:
                # Placeholder: in a full implementation this pre-pulls the model
                logger.info("AgentModelManager: would pre-pull model for %s", name)
            except Exception as exc:
                logger.warning("AgentModelManager prefetch failed for %s: %s", name, exc)
