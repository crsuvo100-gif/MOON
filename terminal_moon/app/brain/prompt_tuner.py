"""
Prompt tuner — records failure-mode lessons for agent personas.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("moontm.tuner")


class PromptTuner:
    """Stores failure-mode lessons (simple in-memory, persisted elsewhere)."""

    def __init__(self) -> None:
        self._lessons: dict[str, list[str]] = {}

    def record_lesson(self, agent: str, lesson: str) -> None:
        self._lessons.setdefault(agent, []).append(lesson)
        logger.debug("PromptTuner: recorded lesson for %s: %s", agent, lesson[:80])
