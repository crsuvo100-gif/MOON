"""context_sharing.py — inter-agent context sharing and memory.

Professional AI assistants share context between agents to avoid
redundant work and maintain consistency. This module provides a
context sharing system where agents can publish their findings,
subscribe to other agents' outputs, and maintain a shared
understanding of the task.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SharedContext:
    context_id: str
    task_id: str
    agent_id: str
    content: str
    context_type: str  # "finding", "hypothesis", "result", "question", "answer"
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    references: list[str] = field(default_factory=list)  # IDs of related contexts
    consumed_by: list[str] = field(default_factory=list)  # agent IDs that read this


class ContextSharing:
    """Inter-agent context sharing system.

    Agents publish findings to a shared context space and subscribe
    to relevant contexts from other agents. The system tracks which
    contexts have been consumed and provides relevance-based
    retrieval to avoid information overload.
    """

    def __init__(self, *, max_contexts: int = 1000) -> None:
        self._max_contexts = max_contexts
        self._contexts: dict[str, SharedContext] = {}
        self._task_contexts: dict[str, list[str]] = {}  # task_id -> context_ids
        self._agent_contexts: dict[str, list[str]] = {}  # agent_id -> context_ids
        self._subscriptions: dict[str, list[str]] = {}  # agent_id -> context_types
        self._lock = asyncio.Lock()

    async def publish(
        self,
        task_id: str,
        agent_id: str,
        content: str,
        *,
        context_type: str = "finding",
        confidence: float = 1.0,
        references: list[str] | None = None,
    ) -> str:
        import uuid
        context_id = uuid.uuid4().hex[:12]
        ctx = SharedContext(
            context_id=context_id,
            task_id=task_id,
            agent_id=agent_id,
            content=content[:2000],
            context_type=context_type,
            confidence=confidence,
            references=references or [],
        )
        async with self._lock:
            self._contexts[context_id] = ctx
            if len(self._contexts) > self._max_contexts:
                # Remove oldest
                oldest = min(self._contexts.values(), key=lambda c: c.timestamp)
                del self._contexts[oldest.context_id]

            if task_id not in self._task_contexts:
                self._task_contexts[task_id] = []
            self._task_contexts[task_id].append(context_id)

            if agent_id not in self._agent_contexts:
                self._agent_contexts[agent_id] = []
            self._agent_contexts[agent_id].append(context_id)

        logger.debug(
            "Agent %s published %s context for task %s",
            agent_id, context_type, task_id,
        )
        return context_id

    async def get_context(self, context_id: str) -> SharedContext | None:
        async with self._lock:
            return self._contexts.get(context_id)

    async def get_task_contexts(
        self,
        task_id: str,
        *,
        context_type: str | None = None,
        exclude_agent: str | None = None,
    ) -> list[SharedContext]:
        async with self._lock:
            context_ids = self._task_contexts.get(task_id, [])
            contexts = [self._contexts[cid] for cid in context_ids if cid in self._contexts]
            if context_type:
                contexts = [c for c in contexts if c.context_type == context_type]
            if exclude_agent:
                contexts = [c for c in contexts if c.agent_id != exclude_agent]
            return sorted(contexts, key=lambda c: c.timestamp)

    async def get_relevant_contexts(
        self,
        task_id: str,
        agent_id: str,
        *,
        query: str = "",
        limit: int = 10,
    ) -> list[SharedContext]:
        """Get contexts relevant to an agent's current work.

        Filters out contexts already consumed by this agent and
        ranks by relevance (simple keyword overlap for now).
        """
        async with self._lock:
            context_ids = self._task_contexts.get(task_id, [])
            contexts = [self._contexts[cid] for cid in context_ids if cid in self._contexts]

            # Filter out own contexts and already consumed
            contexts = [
                c for c in contexts
                if c.agent_id != agent_id and agent_id not in c.consumed_by
            ]

            if not contexts:
                return []

            # Simple relevance ranking
            query_words = set(query.lower().split()) if query else set()
            if query_words:
                def relevance(c: SharedContext) -> float:
                    content_words = set(c.content.lower().split())
                    overlap = query_words & content_words
                    return len(overlap) / max(1, len(query_words))
                contexts.sort(key=relevance, reverse=True)
            else:
                # No query: return most recent
                contexts.sort(key=lambda c: c.timestamp, reverse=True)

            return contexts[:limit]

    async def consume_context(self, context_id: str, agent_id: str) -> bool:
        """Mark a context as consumed by an agent."""
        async with self._lock:
            ctx = self._contexts.get(context_id)
            if not ctx:
                return False
            if agent_id not in ctx.consumed_by:
                ctx.consumed_by.append(agent_id)
            return True

    async def subscribe(self, agent_id: str, context_type: str) -> None:
        """Subscribe an agent to a context type."""
        async with self._lock:
            if agent_id not in self._subscriptions:
                self._subscriptions[agent_id] = []
            if context_type not in self._subscriptions[agent_id]:
                self._subscriptions[agent_id].append(context_type)

    async def get_subscriptions(self, agent_id: str) -> list[str]:
        async with self._lock:
            return list(self._subscriptions.get(agent_id, []))

    async def get_unconsumed(self, agent_id: str) -> list[SharedContext]:
        """Get all contexts not yet consumed by this agent."""
        async with self._lock:
            return [
                c for c in self._contexts.values()
                if c.agent_id != agent_id and agent_id not in c.consumed_by
            ]

    async def clear_task(self, task_id: str) -> None:
        """Clear all contexts for a task."""
        async with self._lock:
            context_ids = self._task_contexts.pop(task_id, [])
            for cid in context_ids:
                self._contexts.pop(cid, None)

    def stats(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for c in self._contexts.values():
            by_type[c.context_type] = by_type.get(c.context_type, 0) + 1
        return {
            "total_contexts": len(self._contexts),
            "total_tasks": len(self._task_contexts),
            "total_agents": len(self._agent_contexts),
            "by_type": by_type,
            "total_subscriptions": sum(len(s) for s in self._subscriptions.values()),
        }
