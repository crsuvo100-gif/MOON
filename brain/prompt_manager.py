"""PromptManager -- loads system/role prompts."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptManager:
    def __init__(self) -> None:
        self._dir = Path(__file__).resolve().parent.parent / "prompts" / "templates"

    def get(self, name: str, default: str = "") -> str:
        try:
            return (self._dir / f"{name}.md").read_text(encoding="utf-8")
        except Exception:
            return default

    def system_prompt(self) -> str:
        return self.get("moon_system", "You are MOON, a helpful autonomous AI assistant.")
