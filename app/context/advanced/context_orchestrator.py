"""ContextOrchestrator — unified context self-function orchestrator.

This is the central orchestrator that ties together all context self-function
modules into a cohesive system. Every agent, brain, and tool in MOON can use
this orchestrator to manage its own context like a professional AI assistant.

The orchestrator provides:
- Context window management (token budget tracking)
- Context awareness (health monitoring, recommendations)
- Context injection (prompt formatting)
- Context lifecycle (phase tracking, staleness, expiration)
- Context compression (summarization when full)
- Context retrieval (semantic search integration)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.context.advanced.context_window import ContextWindow, ContextItem, EvictionPolicy
from app.context.advanced.context_awareness import ContextAwareness, ContextHealth, ContextAwarenessState
from app.context.advanced.context_injector import ContextInjector, InjectionFormat, InjectionResult
from app.context.advanced.context_lifecycle import ContextLifecycle, ContextPhase

logger = get_logger(__name__)


@dataclass
class ContextSnapshot:
    """Complete snapshot of context state."""
    window_summary: dict[str, Any]
    awareness_state: ContextAwarenessState
    lifecycle_stats: dict[str, Any]
    trend: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class ContextOrchestrator:
    """Unified context self-function orchestrator.

    This is the main entry point for context self-function. It coordinates
    all context subsystems and provides a simple interface for agents,
    brains, and tools to manage their context.

    Usage:
        ctx = ContextOrchestrator(max_tokens=8000)
        ctx.add("some information", source="retrieval", relevance=0.8)
        ctx.add("user message", source="history", importance=0.9)

        # Before LLM call
        state = ctx.assess()
        if state.health in (ContextHealth.WARNING, ContextHealth.CRITICAL):
            ctx.compress()

        # Inject into prompt
        result = ctx.inject(base_prompt="What is the answer?")
        messages = [{"role": "user", "content": result.prompt}]

        # After LLM call
        ctx.add("LLM response", source="response", importance=0.7)
    """

    def __init__(
        self,
        *,
        max_tokens: int = 8000,
        reserved_tokens: int = 2000,
        eviction_policy: EvictionPolicy = EvictionPolicy.HYBRID,
        injection_format: InjectionFormat = InjectionFormat.BULLET,
        stale_after_seconds: float = 300.0,
        expire_after_seconds: float = 3600.0,
        warning_threshold: float = 0.7,
        critical_threshold: float = 0.9,
        enable_awareness: bool = True,
        enable_lifecycle: bool = True,
    ) -> None:
        self._window = ContextWindow(
            max_tokens=max_tokens,
            reserved_tokens=reserved_tokens,
            eviction_policy=eviction_policy,
            auto_evict=True,
        )
        self._awareness = ContextAwareness(
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
        ) if enable_awareness else None
        self._injector = ContextInjector(
            format=injection_format,
            max_tokens=max_tokens - reserved_tokens,
        )
        self._lifecycle = ContextLifecycle(
            stale_after_seconds=stale_after_seconds,
            expire_after_seconds=expire_after_seconds,
        ) if enable_lifecycle else None

    @property
    def window(self) -> ContextWindow:
        return self._window

    @property
    def awareness(self) -> ContextAwareness | None:
        return self._awareness

    @property
    def injector(self) -> ContextInjector:
        return self._injector

    @property
    def lifecycle(self) -> ContextLifecycle | None:
        return self._lifecycle

    def add(
        self,
        content: str,
        *,
        source: str = "unknown",
        relevance: float = 0.5,
        importance: float = 0.5,
        tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextItem:
        """Add content to the context window."""
        item = self._window.add(
            content,
            source=source,
            relevance=relevance,
            importance=importance,
            tokens=tokens,
            metadata=metadata,
        )
        if self._lifecycle:
            self._lifecycle.register(f"{source}_{id(item)}")
            self._lifecycle.activate(f"{source}_{id(item)}")
        return item

    def assess(self) -> ContextAwarenessState | None:
        """Assess context health and get recommendations."""
        if self._awareness is None:
            return None
        return self._awareness.assess(self._window)

    def inject(self, *, base_prompt: str, system_prefix: str | None = None) -> InjectionResult:
        """Inject context into a prompt."""
        items = self._window.items
        return self._injector.inject(
            base_prompt=base_prompt,
            context_items=items,
            system_prefix=system_prefix,
        )

    def compress(self, *, target_tokens: int | None = None) -> str:
        """Compress context into a single string."""
        return self._window.compress(target_tokens=target_tokens)

    def get_recommendations(self) -> list[str]:
        """Get context management recommendations."""
        state = self.assess()
        if state is None:
            return []
        return state.recommendations

    def should_compress(self) -> bool:
        """Check if compression is recommended."""
        if self._awareness is None:
            return self._window.utilization > 0.8
        return self._awareness.should_compress()

    def should_retrieve(self) -> bool:
        """Check if more retrieval is recommended."""
        if self._awareness is None:
            return self._window.utilization < 0.5
        return self._awareness.should_retrieve()

    def get_snapshot(self) -> ContextSnapshot:
        """Get a complete snapshot of context state."""
        awareness_state = self.assess()
        lifecycle_stats = self._lifecycle.get_stats() if self._lifecycle else {}
        trend = self._awareness.get_trend() if self._awareness else {}

        return ContextSnapshot(
            window_summary=self._window.summary(),
            awareness_state=awareness_state,
            lifecycle_stats=lifecycle_stats,
            trend=trend,
        )

    def clear(self, *, source: str | None = None) -> int:
        """Clear context, optionally only from a specific source."""
        count = self._window.clear(source=source)
        if self._lifecycle and source is None:
            self._lifecycle._phase_map.clear()
        return count

    def get_items(
        self,
        *,
        source: str | None = None,
        min_relevance: float = 0.0,
    ) -> list[ContextItem]:
        """Get context items, optionally filtered."""
        return self._window.get(source=source, min_relevance=min_relevance)

    def update_lifecycle(self, *, item_ages: dict[str, float] | None = None) -> list[Any]:
        """Update lifecycle phases."""
        if self._lifecycle is None:
            return []
        return self._lifecycle.update(item_ages=item_ages)

    def get_expired(self) -> list[str]:
        """Get expired item IDs."""
        if self._lifecycle is None:
            return []
        return self._lifecycle.get_expired()

    def remove_expired(self) -> int:
        """Remove expired items from the context window."""
        if self._lifecycle is None:
            return 0
        expired = self._lifecycle.get_expired()
        count = 0
        for item_id in expired:
            # Find and remove the item
            for item in self._window.items:
                if f"{item.source}_{id(item)}" == item_id:
                    self._window.remove(item)
                    self._lifecycle.remove(item_id)
                    count += 1
                    break
        return count
