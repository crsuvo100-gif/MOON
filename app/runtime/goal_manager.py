"""GoalManager (spec section 9).

Manages the lifecycle of a goal: create an execution id, capture the structured
GoalSpec, check memory + knowledge for relevant prior context, and record the
final outcome. Reuses MOON's existing memory/knowledge layers when available;
degrades gracefully (reports missing context) instead of failing (spec 59).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.runtime.task_analyzer import GoalSpec, TaskAnalyzer


@dataclass
class Goal:
    execution_id: str
    spec: GoalSpec
    created_at: str
    memory_hits: list[str] = field(default_factory=list)
    knowledge_hits: list[str] = field(default_factory=list)
    status: str = "created"
    result: str = ""


class GoalManager:
    def __init__(self, analyzer: TaskAnalyzer | None = None,
                 knowledge_base: Any | None = None) -> None:
        self.analyzer = analyzer or TaskAnalyzer()
        self._goals: dict[str, Goal] = {}
        # Optional shared knowledge base (e.g. the orchestrator's live KB).
        # When None we lazily build a real InMemory-backed KnowledgeBase so
        # knowledge search is actually operational instead of silently dead.
        self._kb = knowledge_base
        self._kb_built = False

    def _get_kb(self):
        """Return a working KnowledgeBase, building one on first use.

        Reuses the orchestrator's injected KB when provided; otherwise
        constructs a real KnowledgeBase (InMemoryVectorStore + EmbeddingService)
        exactly like app.brain.orchestrator does. Returns None only if the
        embedding service is unavailable, in which case callers degrade
        gracefully.
        """
        if self._kb is not None:
            return self._kb
        if self._kb_built:
            return getattr(self, "_kb_lazy", None)
        self._kb_built = True
        try:
            from app.memory.knowledge_base import KnowledgeBase
            from app.memory.vector_store import InMemoryVectorStore
            from app.services.embedding_service import EmbeddingService
            from app.config.model_config import build_embedding_config
            from app.config.settings import get_settings
            ecfg = build_embedding_config(get_settings())
            store = InMemoryVectorStore()
            embeddings = EmbeddingService(
                dim=ecfg.dim, enabled=ecfg.enabled,
                base_url=ecfg.base_url, model_name=ecfg.model_name,
            )
            self._kb_lazy = KnowledgeBase(store, embeddings)
            return self._kb_lazy
        except Exception:  # noqa: BLE001
            self._kb_lazy = None
            return None

    def create(self, request: str) -> Goal:
        spec = self.analyzer.analyze(request)
        gid = uuid.uuid4().hex[:12]
        goal = Goal(execution_id=gid, spec=spec,
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._goals[gid] = goal
        try:
            self._search_context(goal)
        except Exception:  # noqa: BLE001
            pass
        return goal

    def _search_context(self, goal: Goal) -> None:
        """Enrich the goal with memory + knowledge hits.

        Runs the (async) memory/knowledge searches on a short-lived isolated
        event loop so this works whether called from a sync context or from
        inside the orchestrator's running event loop (asyncio.run() would
        refuse to nest). Degrades gracefully on any failure.
        """
        async def _run() -> tuple[list[Any], list[Any]]:
            mem_hits: list[Any] = []
            kb_hits: list[Any] = []
            try:
                from app.brain.memory_manager import MemoryManager
                mm = MemoryManager()
                mem_hits = await mm.semantic_recall(goal.spec.goal, top_k=3) or []
            except Exception:  # noqa: BLE001
                mem_hits = []
            try:
                kb = self._get_kb()
                if kb is not None:
                    kb_hits = await kb.search(goal.spec.goal, top_k=3) or []
            except Exception:  # noqa: BLE001
                kb_hits = []
            return mem_hits, kb_hits

        # Run the async search on a dedicated worker thread with its own event
        # loop. This is safe whether called from a sync context or from inside
        # the orchestrator's running event loop (a nested run_until_complete
        # would otherwise raise "event loop is already running").
        mem_hits: list[Any] = []
        kb_hits: list[Any] = []
        try:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                mem_hits, kb_hits = ex.submit(asyncio.run, _run()).result(timeout=30)
        except Exception:  # noqa: BLE001
            mem_hits, kb_hits = [], []
        goal.memory_hits = [str(h)[:120] for h in (mem_hits or [])]
        goal.knowledge_hits = [str(h)[:120] for h in (kb_hits or [])]

    def complete(self, execution_id: str, result: str) -> Goal | None:
        g = self._goals.get(execution_id)
        if g:
            g.status = "completed"
            g.result = result
        return g

    def get(self, execution_id: str) -> Goal | None:
        return self._goals.get(execution_id)

    def all(self) -> list[Goal]:
        return list(self._goals.values())

    def to_report(self, goal: Goal) -> dict[str, Any]:
        return {
            "execution_id": goal.execution_id,
            "goal": goal.spec.goal,
            "risk": goal.spec.risk,
            "required_capabilities": goal.spec.required_capabilities,
            "memory_hits": len(goal.memory_hits),
            "knowledge_hits": len(goal.knowledge_hits),
            "status": goal.status,
        }
