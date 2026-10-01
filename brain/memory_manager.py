"""memory_manager.py -- coordinates short/long-term memory and knowledge base."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config.logging import get_logger
from app.memory.episodic_memory import EpisodicMemory

logger = get_logger(__name__)

EPISODE_PATH = Path(__file__).resolve().parent.parent / "memory" / "episodes.json"

if TYPE_CHECKING:
    from app.memory.knowledge_base import KnowledgeBase
    from app.memory.long_term import LongTermMemory
    from app.memory.short_term import ShortTermMemory


class MemoryManager:
    """Unified interface over the memory subsystems."""

    def __init__(
        self,
        short_term: ShortTermMemory | None = None,
        long_term: LongTermMemory | None = None,
        knowledge_base: KnowledgeBase | None = None,
        episodic: EpisodicMemory | None = None,
    ) -> None:
        self._stm = short_term
        self._ltm = long_term
        self._kb = knowledge_base
        self.episodic = episodic or EpisodicMemory()
        self._load_episodes()

    def _load_episodes(self) -> None:
        try:
            if EPISODE_PATH.exists():
                data = json.loads(EPISODE_PATH.read_text())
                for d in data:
                    self.episodic.record(
                        goal=d.get("goal", ""),
                        outcome=d.get("outcome", ""),
                        lesson=d.get("lesson", ""),
                        success=bool(d.get("success", True)),
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load episodes (%s); starting fresh", exc)

    def save_episodes(self) -> None:
        try:
            eps = [
                {"goal": e.goal, "outcome": e.outcome, "lesson": e.lesson, "success": e.success}
                for e in self.episodic._eps
            ]
            EPISODE_PATH.parent.mkdir(parents=True, exist_ok=True)
            EPISODE_PATH.write_text(json.dumps(eps, indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save episodes (%s)", exc)

    async def setup(self) -> None:
        if self._ltm is not None:
            await self._ltm.setup()
        if self._kb is not None:
            await self._kb.setup()

    async def remember(self, content: str, *, long_term: bool = False, tags: list[str] | None = None) -> None:
        if self._stm is not None:
            self._stm.add(content)
        if self._ltm is not None and long_term:
            await self._ltm.store({"content": content, "tags": tags or []})

    async def learn(self, content: str, *, tags: list[str] | None = None) -> None:
        """Consolidate ``content`` into MOON's durable brain."""
        if self._ltm is not None:
            await self._ltm.store({"content": content, "tags": tags or []})
        else:
            if self._stm is not None:
                self._stm.add(content)
        if self._kb is not None:
            try:
                doc_id = f"learn_{int(time.time() * 1000)}_{abs(hash(content)) & 0xFFFF}"
                await self._kb.index_document(doc_id, content)
            except Exception as exc:  # noqa: BLE001
                logger.debug("learn: KB index skipped (%s)", exc)

    async def recall(self, keyword: str, limit: int = 5) -> list[str]:
        if self._ltm is not None:
            entries = await self._ltm.query(keyword, limit=limit)
            if entries:
                return [e.content for e in entries]
        if self._stm is not None:
            return [i for i in self._stm.recent(limit) if keyword.lower() in i.lower()]
        return []

    async def index_document(self, doc_id: str, text: str) -> int:
        if self._kb is not None:
            return await self._kb.index_document(doc_id, text)
        logger.warning("No knowledge base configured; skipping index")
        return 0

    async def semantic_recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if self._kb is not None:
            return await self._kb.search(query, top_k=top_k)
        return []
