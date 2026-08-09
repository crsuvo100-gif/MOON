"""SafetyValidator -- gates dangerous operations."""

from __future__ import annotations


class SafetyValidator:
    def __init__(self, allow_dangerous: bool = False) -> None:
        self._allow = allow_dangerous

    def is_safe(self, action: str) -> bool:
        risky = ("rm -rf", "sudo ", "format disk", "wipe")
        low = (action or "").lower()
        if any(r in low for r in risky):
            return self._allow
        return True
