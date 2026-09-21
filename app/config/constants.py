"""Shared constants and enums for MOON."""

from __future__ import annotations

from enum import Enum


class MemoryScope(str, Enum):
    SHORT_TERM = "short_term"
    WORKING = "working"
    EPISODIC = "episodic"
    LONG_TERM = "long_term"
    SEMANTIC = "semantic"


# The phrase that unlocks MOON's Security Lock Mode.
UNLOCK_PHRASE = "MOON love you 3000"

DEFAULT_AGENTS = [
    "coding", "research", "browser", "writing", "vision",
    "planning", "memory", "review", "debug", "coordinator", "manager",
]
