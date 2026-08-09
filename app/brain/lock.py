"""SessionLock -- MOON Security Lock Mode (starts locked)."""

from __future__ import annotations

import json
from pathlib import Path


class SessionLock:
    UNLOCK_PHRASE = "MOON love you 3000"

    def __init__(self, locked: bool = True, state_file: str | Path | None = None) -> None:
        self.locked = locked
        self._state_file = Path(state_file) if state_file else None
        if self._state_file and self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self.locked = bool(data.get("locked", locked))
            except Exception:
                pass

    def observe(self, text: str) -> str | None:
        """Return a notice if locked; unlock + return banner if phrase seen."""
        if self.UNLOCK_PHRASE.lower() in (text or "").lower():
            self.locked = False
            self._persist()
            return "🔓 MOON unlocked. How can I help?"
        if self.locked:
            return (
                "🔒 MOON is currently locked.\n\n"
                "To unlock, say the exact phrase:\nMOON love you 3000"
            )
        return None

    def _persist(self) -> None:
        if self._state_file:
            try:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                self._state_file.write_text(json.dumps({"locked": self.locked}))
            except Exception:
                pass
