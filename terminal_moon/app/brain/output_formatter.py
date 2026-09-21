"""
OutputFormatter — cleans/Formats final text.
"""
from __future__ import annotations


class OutputFormatter:
    def format(self, text: str) -> str:
        if not text:
            return ""
        # trim excessive whitespace — collapse internal whitespace per line too
        lines = [" ".join(ln.split()) for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]
        return " ".join(lines).strip()
