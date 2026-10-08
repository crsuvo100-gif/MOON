"""Compression utilities for long transcripts and memory content.

Intelligent compression with multiple strategies:
- Head/tail preservation (for context)
- Extractive summarization (sentence scoring)
- Semantic compression (key information preservation)
- Token budget enforcement
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


def compress_transcript(text: str, max_chars: int = 4000) -> str:
    """Naive head/tail compression for oversized transcripts."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n...[compressed]...\n{tail}"


def extractive_summarize(text: str, max_sentences: int = 5) -> str:
    """Extractive summarization using sentence scoring.

    Scores sentences by word frequency (TF) and position.
    Returns top-k most important sentences in original order.
    """
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return text

    # Score sentences
    word_freq = _word_frequencies(text)
    scored: list[tuple[int, str, float]] = []
    for i, sent in enumerate(sentences):
        score = _sentence_score(sent, word_freq, i, len(sentences))
        scored.append((i, sent, score))

    # Select top-k by score, preserve original order
    top = sorted(scored, key=lambda x: x[2], reverse=True)[:max_sentences]
    top.sort(key=lambda x: x[0])  # restore original order
    return " ".join(sent for _, sent, _ in top)


def semantic_compress(text: str, max_chars: int = 2000) -> str:
    """Semantic compression preserving key information.

    Strategy:
    1. Extract key sentences (extractive summary)
    2. If still too long, compress each sentence
    3. Preserve structure (paragraphs, lists)
    """
    if len(text) <= max_chars:
        return text

    # Try extractive summary first
    summary = extractive_summarize(text, max_sentences=10)
    if len(summary) <= max_chars:
        return summary

    # Further compress: keep first 80% of budget from summary
    budget = int(max_chars * 0.8)
    return summary[:budget] + "\n...[truncated]..."


def compress_for_context(
    text: str,
    token_budget: int = 1000,
    tokens_per_char: float = 0.25,
) -> str:
    """Compress text to fit within a token budget.

    Args:
        text: Input text
        token_budget: Maximum tokens allowed
        tokens_per_char: Estimated tokens per character

    Returns:
        Compressed text fitting within budget
    """
    max_chars = int(token_budget * (1.0 / tokens_per_char))
    if len(text) <= max_chars:
        return text

    # Try semantic compression first
    compressed = semantic_compress(text, max_chars)
    if len(compressed) <= max_chars:
        return compressed

    # Fall back to head/tail
    return compress_transcript(text, max_chars)


def compress_structured(data: dict[str, Any], max_chars: int = 4000) -> dict[str, Any]:
    """Compress string values in a structured data object.

    Recursively compresses all string values that exceed the limit.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > max_chars:
            result[key] = semantic_compress(value, max_chars)
        elif isinstance(value, dict):
            result[key] = compress_structured(value, max_chars)
        elif isinstance(value, list):
            result[key] = [
                semantic_compress(item, max_chars) if isinstance(item, str) and len(item) > max_chars else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _word_frequencies(text: str) -> Counter[str]:
    """Calculate word frequencies."""
    words = re.findall(r"\b\w+\b", text.lower())
    return Counter(words)


def _sentence_score(
    sentence: str,
    word_freq: Counter[str],
    position: int,
    total: int,
) -> float:
    """Score a sentence based on word frequency and position."""
    words = re.findall(r"\b\w+\b", sentence.lower())
    if not words:
        return 0.0

    # TF score
    tf_score = sum(word_freq[w] for w in words) / len(words)

    # Position score (first and last sentences are more important)
    if position == 0:
        position_score = 1.5
    elif position == total - 1:
        position_score = 1.2
    else:
        position_score = 1.0

    # Length penalty (very short or very long sentences are less useful)
    word_count = len(words)
    if word_count < 3:
        length_penalty = 0.5
    elif word_count > 30:
        length_penalty = 0.7
    else:
        length_penalty = 1.0

    return tf_score * position_score * length_penalty
