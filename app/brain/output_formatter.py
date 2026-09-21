"""OutputFormatter -- normalizes final answers."""

from __future__ import annotations


class OutputFormatter:
    def format(self, text: str) -> str:
        if not text:
            return text
        # Strip an accidental trailing persona preamble if echoed back.
        return text.strip()
