"""
SessionLock — MOON starts locked. Two unlock phrases + wake word.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("moontm.lock")

UNLOCK_PHRASES = [
    "MOON love you 3000",
    "love you 3000 moon",
]
WAKE_WORD = "moon"


class SessionLock:
    """Locked-at-start. Observing the unlock phrase sets locked=False."""

    def __init__(self, locked: bool = True, state_file: Optional[Path] = None) -> None:
        self._locked = locked
        self._state_file = state_file or Path("data/lock_state.json")
        self._lock = threading.Lock()
        if self._state_file.exists():
            self._load()

    def _load(self) -> None:
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._locked = data.get("locked", True)
        except Exception:
            self._locked = True

    def _persist(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps({"locked": self._locked}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist lock state: %s", exc)

    @property
    def locked(self) -> bool:
        with self._lock:
            return self._locked

    def observe(self, text: str) -> Optional[str]:
        """If text contains an unlock phrase → unlock. Return notice or None."""
        low = text.casefold()
        for phrase in UNLOCK_PHRASES:
            if phrase.casefold() in low:
                with self._lock:
                    if self._locked:
                        self._locked = False
                        self._persist()
                        return (
                            "🔓 MOON is now unlocked. Active operations are enabled. "
                            "Say 'moon' to wake the listening state."
                        )
                    return None
        if self._locked:
            return (
                "🔒 MOON is locked. Type the unlock phrase to enable active operations. "
                "Chat and knowledge queries still work while locked."
            )
        return None

    def hear(self, text: str) -> dict:
        """Classify audio input for the avatar: unlock | wake | none."""
        low = text.lower().strip()
        for phrase in UNLOCK_PHRASES:
            if phrase.lower() in low:
                with self._lock:
                    if self._locked:
                        self._locked = False
                        self._persist()
                        return {"kind": "unlock", "unlocked": True,
                                "notice": "Unlocked via voice."}
                return {"kind": "none", "unlocked": True, "notice": None}
        if WAKE_WORD in low.split():
            return {"kind": "wake", "unlocked": not self._locked,
                    "notice": "Listening..." if not self._locked else None}
        return {"kind": "none", "unlocked": not self._locked, "notice": None}
