"""Base agent: wraps an AgentBrain with a run loop."""
from __future__ import annotations

import logging
from typing import Any

from app.brain.agent_brain import AgentBrain

logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, name: str, main_brain=None, agent_models=None) -> None:
        self.name = name
        self.brain = AgentBrain(name, main_brain=main_brain, agent_models=agent_models)

    async def setup(self) -> None:
        await self.brain.setup()

    async def run(self, task: str, context: str = "") -> str:
        return await self.brain.run(task, context)

    async def teardown(self) -> None:
        await self.brain.teardown()

    # --- Agent memory interface (spec 61) ---
    # Agents request memory operations through these controlled interfaces.
    # Agents NEVER access database tables directly.

    async def memory_search(self, query: str, *, top_k: int = 5, scope: str | None = None) -> list[dict[str, Any]]:
        """Search memory for relevant information.

        Args:
            query: Natural-language search query.
            top_k: Maximum results to return.
            scope: Optional scope filter (USER, PROJECT, AGENT, etc.).

        Returns:
            List of memory records with content, score, source, importance.
        """
        cog = getattr(self.brain, "_cognitive_memory", None) or getattr(self.brain, "main_brain", None)
        if cog is None:
            return []
        try:
            results = await cog.search(query, top_k=top_k, scope=scope)
            return [
                {
                    "content": r.content if hasattr(r, "content") else str(r),
                    "score": r.score if hasattr(r, "score") else 0.0,
                    "source": r.source if hasattr(r, "source") else "unknown",
                    "importance": r.importance if hasattr(r, "importance") else 0.5,
                }
                for r in results
            ]
        except Exception:
            logger.warning("Agent %s memory search failed", self.name, exc_info=True)
            return []

    async def memory_store(self, content: str, *, memory_type: str = "semantic",
                           importance: float = 0.5, scope: str = "AGENT",
                           metadata: dict[str, Any] | None = None) -> str | None:
        """Store a memory.

        Args:
            content: Memory content to store.
            memory_type: Type of memory (episodic, semantic, procedural, etc.).
            importance: Importance score 0.0-1.0.
            scope: Memory scope (USER, PROJECT, AGENT, etc.).
            metadata: Optional metadata dict.

        Returns:
            Memory ID if stored, None if rejected.
        """
        cog = getattr(self.brain, "_cognitive_memory", None) or getattr(self.brain, "main_brain", None)
        if cog is None:
            return None
        try:
            record = await cog.store(
                content=content,
                memory_type=memory_type,
                importance=importance,
                scope=scope,
                agent_id=self.name,
                metadata=metadata or {},
            )
            return record.memory_id if hasattr(record, "memory_id") else str(record)
        except Exception:
            logger.warning("Agent %s memory store failed", self.name, exc_info=True)
            return None

    async def memory_forget(self, query: str) -> int:
        """Forget memories matching query (spec 18).

        Args:
            query: Natural-language query to match memories to forget.

        Returns:
            Number of memories deleted.
        """
        cog = getattr(self.brain, "_cognitive_memory", None) or getattr(self.brain, "main_brain", None)
        if cog is None:
            return 0
        try:
            return await cog.forget(query)
        except Exception:
            logger.warning("Agent %s memory forget failed", self.name, exc_info=True)
            return 0

    async def memory_update(self, memory_id: str, content: str) -> bool:
        """Update an existing memory (spec 39).

        Args:
            memory_id: ID of memory to update.
            content: New content.

        Returns:
            True if updated, False otherwise.
        """
        cog = getattr(self.brain, "_cognitive_memory", None) or getattr(self.brain, "main_brain", None)
        if cog is None:
            return False
        try:
            return await cog.update(memory_id, content)
        except Exception:
            logger.warning("Agent %s memory update failed", self.name, exc_info=True)
            return False
