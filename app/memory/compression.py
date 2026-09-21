"""Compression utilities for long transcripts (best-effort summary)."""

from __future__ import annotations


def compress_transcript(text: str, max_chars: int = 4000) -> str:
    """Naive head/tail compression for oversized transcripts."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n...[compressed]...\n{tail}"
