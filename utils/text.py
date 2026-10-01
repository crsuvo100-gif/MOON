"""Text utilities."""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Split text into chunks no larger than ``max_chars`` (paragraph-aware)."""
    if not text:
        return []
    paragraphs = [p for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paragraphs:
        if len(cur) + len(p) + 1 <= max_chars:
            cur = (cur + "\n" + p).strip()
        else:
            if cur:
                chunks.append(cur)
            # Hard-split very long paragraphs.
            while len(p) > max_chars:
                chunks.append(p[:max_chars])
                p = p[max_chars:]
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


def count_tokens_approx(text: str) -> int:
    return max(1, len(text) // 4)


def extract_json_block(text: str) -> str:
    """Return the first fenced ```json ... ``` block, or the text itself."""
    import re

    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()
