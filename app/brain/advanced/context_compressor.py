"""Context window compression and summarization for agent cognition.

Compresses long conversation histories, tool outputs, and context into
compact summaries while preserving key information.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CompressedContext:
    """Result of context compression."""
    summary: str
    key_facts: list[str]
    compressed_tokens: int
    original_tokens: int
    compression_ratio: float
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextCompressor:
    """Compresses context to fit within token budgets.

    Uses extractive summarization: identifies key sentences, facts,
    and entities, then produces a compact representation.
    """

    def __init__(self, *, llm: Any = None, target_ratio: float = 0.3) -> None:
        self._llm = llm
        self._target_ratio = target_ratio

    async def compress(
        self,
        text: str,
        *,
        max_tokens: int = 2000,
        preserve_last_n: int = 3,
    ) -> CompressedContext:
        """Compress text to fit within a token budget.

        Args:
            text: The text to compress.
            max_tokens: Target maximum tokens.
            preserve_last_n: Number of recent items to preserve verbatim.

        Returns:
            CompressedContext with summary and metadata.
        """
        original_tokens = self._estimate_tokens(text)

        if original_tokens <= max_tokens:
            return CompressedContext(
                summary=text,
                key_facts=[],
                compressed_tokens=original_tokens,
                original_tokens=original_tokens,
                compression_ratio=1.0,
            )

        # Split into chunks (by lines or sentences)
        chunks = self._split_into_chunks(text)

        # Score chunks by importance
        scored = [(self._score_chunk(c), c) for c in chunks]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Select top chunks that fit in budget
        selected: list[str] = []
        current_tokens = 0
        for score, chunk in scored:
            chunk_tokens = self._estimate_tokens(chunk)
            if current_tokens + chunk_tokens > max_tokens:
                continue
            selected.append(chunk)
            current_tokens += chunk_tokens

        # Always preserve the last N chunks verbatim
        if len(chunks) > preserve_last_n:
            recent = chunks[-preserve_last_n:]
            for r in recent:
                if r not in selected:
                    selected.append(r)

        # Sort selected by original position
        selected.sort(key=lambda c: text.index(c) if c in text else 0)

        summary = "\n".join(selected)
        key_facts = self._extract_key_facts(text)
        compressed_tokens = self._estimate_tokens(summary)

        return CompressedContext(
            summary=summary,
            key_facts=key_facts,
            compressed_tokens=compressed_tokens,
            original_tokens=original_tokens,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
        )

    async def compress_messages(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4000,
    ) -> CompressedContext:
        """Compress a list of chat messages.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            max_tokens: Target maximum tokens.

        Returns:
            CompressedContext with summary.
        """
        # Format messages as text
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")
        text = "\n\n".join(parts)
        return await self.compress(text, max_tokens=max_tokens)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate (chars / 4)."""
        return len(text) // 4

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split text into chunks by paragraphs or lines."""
        chunks = text.split("\n\n")
        if len(chunks) < 3:
            chunks = text.split("\n")
        return [c.strip() for c in chunks if c.strip()]

    def _score_chunk(self, chunk: str) -> float:
        """Score a chunk by importance heuristics."""
        score = 0.0
        # Prefer chunks with key indicators
        lower = chunk.lower()
        if any(kw in lower for kw in ["error", "warning", "critical", "important"]):
            score += 2.0
        if any(kw in lower for kw in ["result", "output", "answer", "conclusion"]):
            score += 1.5
        if any(kw in lower for kw in ["step", "action", "tool", "command"]):
            score += 1.0
        # Prefer chunks with numbers/data
        if any(c.isdigit() for c in chunk):
            score += 0.5
        # Penalize very short chunks
        if len(chunk) < 20:
            score -= 1.0
        return score

    def _extract_key_facts(self, text: str) -> list[str]:
        """Extract key facts from text using simple heuristics."""
        facts = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            if any(kw in lower for kw in ["is", "are", "was", "were", "has", "have"]):
                if len(line) < 200:
                    facts.append(line)
            if len(facts) >= 10:
                break
        return facts
