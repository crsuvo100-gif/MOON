"""Proactive memory surfacing -- automatically surface relevant memories.

Professional AI assistants don't wait to be asked about their memory; they
proactively surface relevant context when it's needed. This module monitors
the current task/conversation and automatically injects relevant memories
into the context before the LLM call.

Key features:
- Pre-task memory injection: before running a task, search all memory types
  and inject the top results into the context.
- Post-task memory extraction: after a task completes, extract and store
  important information (facts, lessons, decisions).
- Cross-session continuity: when a new session starts, surface relevant
  memories from previous sessions.
- Memory-triggered reminders: when a task matches a past failure or lesson,
  proactively warn the agent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger
from app.memory.advanced.unified_search import UnifiedSearcher, UnifiedResult

logger = get_logger(__name__)


@dataclass
class ProactiveContext:
    """A proactive memory injection into the context."""
    content: str
    source: str
    score: float
    reason: str  # why this was surfaced

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source,
            "score": round(self.score, 4),
            "reason": self.reason,
        }


class ProactiveMemory:
    """Proactively surfaces relevant memories for the current context.

    Usage:
        pm = ProactiveMemory(memory_manager)
        context_additions = pm.before_task("analyze this vulnerability")
        # ... inject context_additions into the LLM messages ...
        pm.after_task("analyze this vulnerability", result, success=True)
    """

    def __init__(
        self,
        memory_manager=None,
        searcher: UnifiedSearcher | None = None,
        max_injections: int = 5,
        min_score: float = 0.3,
    ) -> None:
        self._mm = memory_manager
        self._searcher = searcher
        self._max_injections = max_injections
        self._min_score = min_score
        self._session_start = time.time()
        self._task_count = 0
        self._injection_count = 0

    async def before_task(self, task_prompt: str) -> list[ProactiveContext]:
        """Search memory and return proactive context injections for this task.

        Args:
            task_prompt: The current task prompt.

        Returns:
            List of ProactiveContext to inject into the LLM context.
        """
        if not task_prompt or not task_prompt.strip():
            return []

        self._task_count += 1
        injections: list[ProactiveContext] = []

        # Use unified searcher if available
        if self._searcher is not None:
            try:
                results = await self._searcher.search(
                    task_prompt,
                    top_k=self._max_injections,
                    min_score=self._min_score,
                )
                for r in results:
                    reason = self._reason_for(r, task_prompt)
                    injections.append(ProactiveContext(
                        content=r.content,
                        source=r.source,
                        score=r.score,
                        reason=reason,
                    ))
            except Exception as exc:
                logger.debug("Proactive search failed: %s", exc)

        # Also check episodic for past failures/lessons
        if self._mm is not None and hasattr(self._mm, 'episodic'):
            try:
                episodes = self._mm.episodic.recall(task_prompt, k=3)
                for ep in episodes:
                    if ep.lesson and ep.lesson not in [i.content for i in injections]:
                        injections.append(ProactiveContext(
                            content=f"[past lesson] {ep.lesson}",
                            source="episodic",
                            score=0.7,
                            reason="past lesson from similar task",
                        ))
                    if not ep.success and ep.goal not in [i.content for i in injections]:
                        injections.append(ProactiveContext(
                            content=f"[past failure] Goal: {ep.goal} | Outcome: {ep.outcome}",
                            source="episodic",
                            score=0.6,
                            reason="past failure on similar task",
                        ))
            except Exception as exc:
                logger.debug("Episodic proactive check failed: %s", exc)

        self._injection_count += len(injections)
        if injections:
            logger.info(
                "Proactive memory: %d injections for task (score range: %.2f-%.2f)",
                len(injections),
                min(i.score for i in injections),
                max(i.score for i in injections),
            )
        return injections

    async def after_task(
        self,
        task_prompt: str,
        result: str,
        success: bool = True,
        lesson: str = "",
    ) -> None:
        """Extract and store important information after a task completes.

        Args:
            task_prompt: The task that was executed.
            result: The result/output of the task.
            success: Whether the task succeeded.
            lesson: Optional explicit lesson to store.
        """
        if not result or not result.strip():
            return

        # Store in episodic memory
        if self._mm is not None and hasattr(self._mm, 'episodic'):
            try:
                self._mm.episodic.record(
                    goal=task_prompt,
                    outcome=result[:1000],
                    lesson=lesson,
                    success=success,
                )
                if hasattr(self._mm, 'save_episodes'):
                    self._mm.save_episodes()
            except Exception as exc:
                logger.debug("Post-task episodic store failed: %s", exc)

        # Store in STM
        if self._mm is not None and hasattr(self._mm, '_stm'):
            try:
                self._mm._stm.add(
                    result[:500],
                    relevance=0.8 if success else 0.6,
                    metadata={"task": task_prompt[:100], "success": success},
                )
            except Exception as exc:
                logger.debug("Post-task STM store failed: %s", exc)

        # Run consolidator if available
        if self._mm is not None and hasattr(self._mm, '_consolidator') and self._mm._consolidator:
            try:
                await self._mm._consolidator.consolidate(
                    prompt=task_prompt,
                    response=result,
                    lesson=lesson,
                    success=success,
                )
            except Exception as exc:
                logger.debug("Post-task consolidation failed: %s", exc)

    async def session_start_context(self) -> list[ProactiveContext]:
        """Surface relevant memories from previous sessions at startup.

        Returns:
            List of ProactiveContext for session continuity.
        """
        injections: list[ProactiveContext] = []

        # Get recent episodic memories
        if self._mm is not None and hasattr(self._mm, 'episodic'):
            try:
                recent = self._mm.episodic.recall("", k=5)
                for ep in recent:
                    if ep.lesson:
                        injections.append(ProactiveContext(
                            content=f"[recent lesson] {ep.lesson}",
                            source="episodic",
                            score=0.5,
                            reason="recent lesson from previous session",
                        ))
            except Exception as exc:
                logger.debug("Session start episodic failed: %s", exc)

        # Get recent LTM entries
        if self._mm is not None and hasattr(self._mm, '_ltm'):
            try:
                entries = await self._mm._ltm.all()
                for entry in entries[-5:]:
                    injections.append(ProactiveContext(
                        content=entry.content,
                        source="ltm",
                        score=0.4,
                        reason="recent long-term memory",
                    ))
            except Exception as exc:
                logger.debug("Session start LTM failed: %s", exc)

        return injections

    @staticmethod
    def _reason_for(result: UnifiedResult, task_prompt: str) -> str:
        """Generate a human-readable reason why this memory was surfaced."""
        if result.source == "episodic":
            return "past experience with similar task"
        elif result.source == "ltm":
            return "relevant long-term knowledge"
        elif result.source == "graph":
            return "associated memory"
        elif result.source == "kb":
            return "indexed knowledge"
        elif result.source == "stm":
            return "recent context"
        return "relevant memory"

    def stats(self) -> dict[str, Any]:
        """Return proactive memory statistics."""
        return {
            "task_count": self._task_count,
            "injection_count": self._injection_count,
            "session_duration": time.time() - self._session_start,
        }
