"""ContextCompressor — compresses context when the window is full.

Every professional AI assistant needs to compress context when it runs
out of space. This module provides multiple compression strategies:
- Summarization (LLM-based)
- Truncation (keep head/tail)
- Selective eviction (remove low-value items)
- Hierarchical compression (compress old items first)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class CompressionStrategy(Enum):
    """Compression strategy."""
    SUMMARIZE = "summarize"       # LLM-based summarization
    TRUNCATE = "truncate"         # Keep head and tail
    SELECTIVE = "selective"       # Remove low-value items
    HIERARCHICAL = "hierarchical" # Compress old items first


@dataclass
class CompressionResult:
    """Result of context compression."""
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    strategy_used: str
    items_removed: int
    items_retained: int


class ContextCompressor:
    """Compresses context using multiple strategies.

    Can be used standalone or as part of the ContextOrchestrator.
    """

    def __init__(
        self,
        *,
        llm: Any = None,
        default_strategy: CompressionStrategy = CompressionStrategy.SELECTIVE,
        target_ratio: float = 0.5,  # Target 50% of original size
    ) -> None:
        self._llm = llm
        self._default_strategy = default_strategy
        self._target_ratio = target_ratio

    def compress(
        self,
        items: list[Any],
        *,
        strategy: CompressionStrategy | None = None,
        target_tokens: int | None = None,
    ) -> CompressionResult:
        """Compress a list of context items.

        Args:
            items: List of context items to compress.
            strategy: Compression strategy to use.
            target_tokens: Target token count for compressed output.

        Returns:
            CompressionResult with compressed text and metadata.
        """
        if not items:
            return CompressionResult(
                compressed_text="",
                original_tokens=0,
                compressed_tokens=0,
                strategy_used="none",
                items_removed=0,
                items_retained=0,
            )

        strat = strategy or self._default_strategy
        original_tokens = sum(self._estimate_tokens(self._get_content(item)) for item in items)

        if strat == CompressionStrategy.SUMMARIZE:
            return self._summarize(items, target_tokens, original_tokens)
        elif strat == CompressionStrategy.TRUNCATE:
            return self._truncate(items, target_tokens, original_tokens)
        elif strat == CompressionStrategy.SELECTIVE:
            return self._selective_compress(items, target_tokens, original_tokens)
        elif strat == CompressionStrategy.HIERARCHICAL:
            return self._hierarchical_compress(items, target_tokens, original_tokens)

        return self._selective_compress(items, target_tokens, original_tokens)

    def _summarize(
        self,
        items: list[Any],
        target_tokens: int | None,
        original_tokens: int,
    ) -> CompressionResult:
        """LLM-based summarization."""
        combined = "\n\n".join(self._get_content(item) for item in items)

        if self._llm is not None:
            try:
                target = target_tokens or int(original_tokens * self._target_ratio)
                prompt = f"Summarize the following context in {target} tokens or less:\n\n{combined}"
                summary = self._llm.complete(prompt, max_tokens=target)
                compressed_tokens = self._estimate_tokens(summary)
                return CompressionResult(
                    compressed_text=summary,
                    original_tokens=original_tokens,
                    compressed_tokens=compressed_tokens,
                    strategy_used="summarize",
                    items_removed=0,
                    items_retained=len(items),
                )
            except Exception as e:
                logger.debug(f"LLM summarization failed: {e}, falling back to selective")

        # Fallback to selective
        return self._selective_compress(items, target_tokens, original_tokens)

    def _truncate(
        self,
        items: list[Any],
        target_tokens: int | None,
        original_tokens: int,
    ) -> CompressionResult:
        """Keep head and tail of context."""
        target = target_tokens or int(original_tokens * self._target_ratio)
        target_chars = target * 4

        combined = "\n\n".join(self._get_content(item) for item in items)

        if len(combined) <= target_chars:
            return CompressionResult(
                compressed_text=combined,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                strategy_used="truncate",
                items_removed=0,
                items_retained=len(items),
            )

        head = combined[: target_chars // 2]
        tail = combined[-target_chars // 2 :]
        compressed = f"{head}\n...[truncated]...\n{tail}"
        compressed_tokens = self._estimate_tokens(compressed)

        return CompressionResult(
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            strategy_used="truncate",
            items_removed=0,
            items_retained=len(items),
        )

    def _selective_compress(
        self,
        items: list[Any],
        target_tokens: int | None,
        original_tokens: int,
    ) -> CompressionResult:
        """Remove low-value items to fit within target."""
        target = target_tokens or int(original_tokens * self._target_ratio)

        # Sort by importance * relevance (keep highest value)
        scored = []
        for item in items:
            relevance = self._get_relevance(item)
            importance = self._get_importance(item)
            score = relevance * importance
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Keep items until we hit the target
        kept: list[Any] = []
        current_tokens = 0
        for score, item in scored:
            item_tokens = self._estimate_tokens(self._get_content(item))
            if current_tokens + item_tokens > target and kept:
                break
            kept.append(item)
            current_tokens += item_tokens

        # Restore original order
        kept_ids = {id(item) for item in kept}
        kept_in_order = [item for item in items if id(item) in kept_ids]

        compressed = "\n\n".join(self._get_content(item) for item in kept_in_order)
        compressed_tokens = self._estimate_tokens(compressed)

        return CompressionResult(
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            strategy_used="selective",
            items_removed=len(items) - len(kept),
            items_retained=len(kept),
        )

    def _hierarchical_compress(
        self,
        items: list[Any],
        target_tokens: int | None,
        original_tokens: int,
    ) -> CompressionResult:
        """Compress old items first, keep recent items intact."""
        target = target_tokens or int(original_tokens * self._target_ratio)

        # Split into recent (keep) and old (compress)
        mid = len(items) // 2
        recent = items[mid:]
        old = items[:mid]

        # Compress old items
        old_compressed = self._selective_compress(old, target_tokens, original_tokens // 2)

        # Combine
        recent_text = "\n\n".join(self._get_content(item) for item in recent)
        compressed = f"{old_compressed.compressed_text}\n\n--- Recent Context ---\n\n{recent_text}"
        compressed_tokens = self._estimate_tokens(compressed)

        return CompressionResult(
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            strategy_used="hierarchical",
            items_removed=old_compressed.items_removed,
            items_retained=len(recent) + old_compressed.items_retained,
        )

    def _get_content(self, item: Any) -> str:
        if isinstance(item, dict):
            return item.get("content", item.get("chunk", ""))
        return getattr(item, "content", "")

    def _get_relevance(self, item: Any) -> float:
        if isinstance(item, dict):
            return item.get("relevance", 0.5)
        return getattr(item, "relevance", 0.5)

    def _get_importance(self, item: Any) -> float:
        if isinstance(item, dict):
            return item.get("importance", 0.5)
        return getattr(item, "importance", 0.5)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text length."""
        return len(text) // 4
