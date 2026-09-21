"""SessionLock -- MOON Security Lock Mode (starts locked)."""

from __future__ import annotations

import json
from pathlib import Path


class SessionLock:
    # MOON is always unlocked — lock mode removed entirely.
    # Both phrases that USED to unlock MOON are now treated as normal greetings.
    UNLOCK_PHRASES = []   # no-op: nothing ever locks MOON
    WAKE_WORD = "moon"

    def __init__(self, locked: bool = False, state_file: str | Path | None = None) -> None:
        self.locked = False          # always unlocked
        self._state_file = None      # persistence disabled

    def observe(self, text: str) -> str | None:
        """ MOON is never locked — no notice, no unlock, no banner. """
        return None

    def hear(self, text: str) -> dict:
        """ MOON is never locked — every utterance is unauthenticated. """
        low = (text or "").lower().strip()
        if self.WAKE_WORD in low:
            return {"kind": "wake", "unlocked": True, "notice": "🌙 MOON is listening..."}
        return {"kind": "none", "unlocked": True, "notice": None}

    def _persist(self) -> None:
        pass   # no-op: lock state is never persisted
