"""SessionLock -- MOON Security Lock Mode (starts locked)."""

from __future__ import annotations

import json
from pathlib import Path


class SessionLock:
    # Both phrases unlock MOON (existing operator phrase + the one from the
    # upgraded system prompt). Supporting both avoids ever locking the operator out.
    UNLOCK_PHRASES = ["MOON love you 3000", "love you 3000 moon"]

    # Wake word: saying "Moon" makes her open her eyes / listen. It is NOT an
    # unlock -- only the phrases above unlock her.
    WAKE_WORD = "moon"

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

    def hear(self, text: str) -> dict:
        """Classify a user utterance for the terminal avatar.

        Returns one of:
          {"kind": "unlock", "unlocked": True,  "notice": "..."}
          {"kind": "wake",   "unlocked": <bool>, "notice": "🌙 MOON is listening..."}
          {"kind": "none",   "unlocked": <bool>, "notice": None}
        Wake ('Moon') does not unlock; only the unlock phrases do.
        """
        low = (text or "").lower().strip()
        if any(ph.lower() in low for ph in self.UNLOCK_PHRASES):
            notice = self.observe(text)
            return {"kind": "unlock", "unlocked": not self.locked, "notice": notice}
        if self.WAKE_WORD in low:
            return {"kind": "wake", "unlocked": not self.locked,
                    "notice": "🌙 MOON is listening..."}
        return {"kind": "none", "unlocked": not self.locked, "notice": None}

    def _persist(self) -> None:
        if self._state_file:
            try:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
                self._state_file.write_text(json.dumps({"locked": self.locked}))
            except Exception:
                pass
