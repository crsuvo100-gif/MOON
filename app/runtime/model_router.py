"""ModelRouter (spec section 30).

Chooses the appropriate model based on task complexity, coding/reasoning
requirement, latency, cost, local/remote availability, and privacy. Reuses
MOON's existing settings (local default model + optional stronger local model)
and the LLMService backends. Never hard-codes a single model across the system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ModelChoice:
    name: str
    base_url: str
    reason: str
    is_remote: bool = False


class ModelRouter:
    def __init__(self) -> None:
        self._s = get_settings()

    def select(self, *, complexity: str = "low", coding: bool = False,
               reasoning: bool = False, privacy: bool = False,
               latency_sensitive: bool = False) -> ModelChoice:
        """complexity: low|medium|high. Returns the best-fit ModelChoice."""
        local = self._s.model_name
        local_url = self._s.model_base_url
        strong = getattr(self._s, "strong_model_name", "") or ""
        strong_url = getattr(self._s, "strong_model_base_url", "") or local_url

        # Privacy: prefer a local model (no data leaves the host).
        if privacy and local:
            return ModelChoice(local, local_url, "privacy: local model", is_remote=False)

        # High complexity or heavy reasoning/coding -> stronger local model if set.
        if (complexity == "high" or (coding and reasoning)) and strong:
            return ModelChoice(strong, strong_url, "high complexity / coding+reasoning", is_remote=False)

        # Latency sensitive -> default local (no network round-trip).
        if latency_sensitive and local:
            return ModelChoice(local, local_url, "latency-sensitive: local", is_remote=False)

        # Medium complexity -> local default.
        if complexity in ("low", "medium") and local:
            return ModelChoice(local, local_url, "routine: local default", is_remote=False)

        # Fallback to any configured remote fallback (OpenAI/OpenRouter/HF).
        for attr in ("openai_model", "openrouter_model", "huggingface_model"):
            name = getattr(self._s, attr, "")
            if name:
                url = getattr(self._s, attr.replace("_model", "_base_url"), "")
                return ModelChoice(name, url, f"fallback: {attr}", is_remote=True)
        # Ultimate fallback
        return ModelChoice(local or "local", local_url or "", "default", is_remote=False)

    def to_dict(self, choice: ModelChoice) -> dict[str, Any]:
        return {"name": choice.name, "base_url": choice.base_url,
                "reason": choice.reason, "is_remote": choice.is_remote}
