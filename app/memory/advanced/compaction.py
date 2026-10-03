"""Memory compaction -- compress older memories to free context space.

Professional AI assistants manage limited context windows by compacting
older memories into condensed summaries. This module provides:

1. STM compaction: when short-term memory exceeds a threshold, compress
   older items into a summary and archive them.
2. LTM compaction: periodically summarize clusters of related LTM entries
   into consolidated "super-memories".
3. Episodic compaction: merge similar episodes to reduce redundancy.
4. Context window management: ensure the total memory footprint stays
   within configurable bounds.

The compaction preserves the most important and most recent information
while discarding or archiving the rest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    source: str                    # "stm", "ltm", "episodic"
    items_before: int
    items_after: int
    items_removed: int
    summary: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def reduction_pct(self) -> float:
        if self.items_before == 0:
            return 0.0
        return (self.items_removed / self.items_before) * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "items_before": self.items_before,
            "items_after": self.items_after,
            "items_removed": self.items_removed,
            "reduction_pct": round(self.reduction_pct, 1),
            "summary": self.summary[:200],
            "timestamp": self.timestamp,
        }


class MemoryCompactor:
    """Compacts memories to manage context window space.

    Usage:
        compactor = MemoryCompactor(memory_manager)
        # Periodically:
        results = await compactor.compact_all()
        # Or compact a specific subsystem:
        result = await compactor.compact_stm()
    """

    def __init__(
        self,
        memory_manager=None,
        stm_threshold: int = 50,
        ltm_threshold: int = 200,
        episodic_threshold: int = 100,
        llm_service=None,
    ) -> None:
        self._mm = memory_manager
        self._stm_threshold = stm_threshold
        self._ltm_threshold = ltm_threshold
        self._episodic_threshold = episodic_threshold
        self._llm = llm_service
        self._compaction_history: list[CompactionResult] = []

    async def compact_all(self) -> list[CompactionResult]:
        """Run compaction on all subsystems that exceed their thresholds."""
        results: list[CompactionResult] = []

        # Compact STM
        stm_result = await self.compact_stm()
        if stm_result:
            results.append(stm_result)

        # Compact LTM
        ltm_result = await self.compact_ltm()
        if ltm_result:
            results.append(ltm_result)

        # Compact Episodic
        epi_result = await self.compact_episodic()
        if epi_result:
            results.append(epi_result)

        if results:
            logger.info(
                "Memory compaction: %d subsystems compacted, total reduction: %.1f%%",
                len(results),
                sum(r.reduction_pct for r in results),
            )
        return results

    async def compact_stm(self) -> CompactionResult | None:
        """Compact short-term memory when it exceeds threshold.

        Strategy: Keep the most recent N items, summarize the rest into
        a single "context summary" item.
        """
        if self._mm is None or not hasattr(self._mm, '_stm'):
            return None

        stm = self._mm._stm
        items = list(stm._items) if hasattr(stm, '_items') else []
        if len(items) <= self._stm_threshold:
            return None

        # Keep the most recent 70%, summarize the older 30%
        keep_count = int(self._stm_threshold * 0.7)
        keep_items = items[-keep_count:]
        old_items = items[:-keep_count]

        # Generate summary of old items
        summary = await self._summarize_items(
            [item.content for item in old_items],
            "conversation context",
        )

        # Replace STM with kept items + summary
        # Handle both simple string-based STM and enhanced item-based STM
        if hasattr(stm, '_items'):
            stm._items = keep_items
            if summary:
                # Try enhanced STM first (has ShortTermItem)
                try:
                    from app.memory.enhanced_short_term import ShortTermItem
                    stm._items.insert(0, ShortTermItem(
                        content=f"[compacted context] {summary}",
                        relevance=0.5,
                        metadata={"compacted": True, "original_count": len(old_items)},
                    ))
                except (ImportError, AttributeError):
                    # Simple string-based STM
                    stm._items.insert(0, f"[compacted context] {summary}")
        elif hasattr(stm, '_buf'):
            # Simple deque-based STM
            from collections import deque
            new_buf = deque(maxlen=stm._buf.maxlen)
            for item in keep_items:
                new_buf.append(item)
            if summary:
                new_buf.appendleft(f"[compacted context] {summary}")
            stm._buf = new_buf

        result = CompactionResult(
            source="stm",
            items_before=len(items),
            items_after=len(stm._items),
            items_removed=len(old_items),
            summary=summary,
        )
        self._compaction_history.append(result)
        logger.info("STM compaction: %d -> %d (%.1f%% reduction)", result.items_before, result.items_after, result.reduction_pct)
        return result

    async def compact_ltm(self) -> CompactionResult | None:
        """Compact long-term memory when it exceeds threshold.

        Strategy: Group by tags, summarize each group into a consolidated
        entry, remove the originals.
        """
        if self._mm is None or not hasattr(self._mm, '_ltm'):
            return None

        ltm = self._mm._ltm
        entries = await ltm.all()
        if len(entries) <= self._ltm_threshold:
            return None

        # Group entries by primary tag
        tag_groups: dict[str, list] = {}
        for entry in entries:
            primary_tag = entry.tags[0] if entry.tags else "general"
            tag_groups.setdefault(primary_tag, []).append(entry)

        # For groups with > 5 entries, consolidate
        removed = 0
        for tag, group in tag_groups.items():
            if len(group) > 5:
                # Keep the 3 most important, summarize the rest
                group.sort(key=lambda e: getattr(e, 'importance', 0.5), reverse=True)
                keep = group[:3]
                old = group[3:]

                summary = await self._summarize_items(
                    [e.content for e in old],
                    f"long-term memories tagged '{tag}'",
                )

                if summary:
                    await ltm.store({
                        "content": f"[consolidated {tag}] {summary}",
                        "tags": [tag, "consolidated"],
                        "metadata": {"consolidated_from": len(old)},
                    })

                # Remove old entries (EnhancedLongTermMemory has no delete();
                # use purge() to remove lowest-importance entries)
                # Mark them for removal by setting importance to 0, then purge
                for entry in old:
                    await ltm.update_importance(entry.id, -1.0)  # set to 0
                # Purge the zeroed entries
                purged = await ltm.purge(len(old))
                removed += len(purged)

        result = CompactionResult(
            source="ltm",
            items_before=len(entries),
            items_after=len(entries) - removed,
            items_removed=removed,
        )
        self._compaction_history.append(result)
        logger.info("LTM compaction: %d -> %d (%.1f%% reduction)", result.items_before, result.items_after, result.reduction_pct)
        return result

    async def compact_episodic(self) -> CompactionResult | None:
        """Compact episodic memory when it exceeds threshold.

        Strategy: Merge episodes with similar goals, keep the most
        recent and most important.
        """
        if self._mm is None or not hasattr(self._mm, 'episodic'):
            return None

        epi = self._mm.episodic
        episodes = list(epi._eps) if hasattr(epi, '_eps') else []
        if len(episodes) <= self._episodic_threshold:
            return None

        # Sort by timestamp, keep the most recent 80%
        episodes.sort(key=lambda e: e.ts, reverse=True)
        keep_count = int(self._episodic_threshold * 0.8)
        keep = episodes[:keep_count]
        old = episodes[keep_count:]

        # Summarize old episodes
        summary = await self._summarize_items(
            [f"{e.goal}: {e.outcome}" for e in old],
            "past task episodes",
        )

        # Replace episodes
        epi._eps = keep
        if summary:
            from app.memory.episodic_memory import Episode
            epi._eps.insert(0, Episode(
                goal="[consolidated episodes]",
                outcome=summary,
                lesson="",
                success=True,
                ts=time.time(),
            ))

        result = CompactionResult(
            source="episodic",
            items_before=len(episodes),
            items_after=len(epi._eps),
            items_removed=len(old),
            summary=summary,
        )
        self._compaction_history.append(result)
        logger.info("Episodic compaction: %d -> %d (%.1f%% reduction)", result.items_before, result.items_after, result.reduction_pct)
        return result

    async def _summarize_items(self, items: list[str], context: str) -> str:
        """Summarize a list of memory items using the LLM.

        Falls back to a simple truncation if LLM is unavailable.
        """
        if not items:
            return ""

        # If LLM is available, use it for summarization
        if self._llm is not None:
            try:
                combined = "\n".join(items[:20])  # Limit to avoid token overflow
                prompt = (
                    f"Summarize the following {context} into a concise paragraph. "
                    f"Preserve key facts, decisions, and lessons. Max 200 words.\n\n"
                    f"{combined}"
                )
                result = await self._llm.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                )
                if result and result.content:
                    return result.content.strip()
            except Exception as exc:
                logger.debug("LLM summarization failed: %s", exc)

        # Fallback: simple truncation
        combined = " | ".join(items[:10])
        if len(combined) > 500:
            combined = combined[:500] + "..."
        return f"[auto-summary] {combined}"

    def stats(self) -> dict[str, Any]:
        """Return compaction statistics."""
        return {
            "total_compactions": len(self._compaction_history),
            "last_compaction": self._compaction_history[-1].to_dict() if self._compaction_history else None,
            "total_items_removed": sum(r.items_removed for r in self._compaction_history),
        }
