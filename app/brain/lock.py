"""SessionLock -- MOON Security Lock Mode (starts locked)."""

from __future__ import annotations

import json
from pathlib import Path


class SessionLock:
    # Both phrases unlock MOON (existing operator phrase + the one from the
    # upgraded system prompt). Supporting both avoids ever locking the operator out.
    UNLOCK_PHRASES = ["MOON love you 3000", "love you 3000 moon"]

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
        low = (text or "").lower()
        if any(ph.lower() in low for ph in self.UNLOCK_PHRASES):
            self.locked = False
            self._persist()
            return "🔓 MOON unlocked. How can I help, my love?"
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
