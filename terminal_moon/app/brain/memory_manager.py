"""
MemoryManager — unified facade over STM/LTM/episodic/KB.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.memory.episodic_memory import EpisodicMemory
from app.memory.knowledge_base import KnowledgeBase
from app.memory.long_term import LongTermMemory
from app.memory.short_term import ShortTermMemory

logger = logging.getLogger("moontm.memory")


class MemoryManager:
    """Unified facade: remember, learn, recall, semantic_recall, index_document."""

    def __init__(
        self,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        knowledge_base: KnowledgeBase,
        episodic: EpisodicMemory,
    ) -> None:
        self._stm = short_term
        self._ltm = long_term
        self._kb = knowledge_base
        self._episodic = episodic

    async def setup(self) -> None:
        self._ltm.setup()
        await self._kb.setup()

    def remember(self, content: str, long_term: bool = False,
                 tags: Optional[list[str]] = None) -> None:
        self._stm.add(content)
        if long_term:
            self._ltm.store(content, tags=tags)

    def learn(self, content: str, tags: Optional[list[str]] = None) -> None:
        self._ltm.store(content, tags=tags)
        # KB index is async-friendly; best-effort
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._index_later(content))
            else:
                loop.run_until_complete(self._index_later(content))
        except Exception:
            pass

    async def _index_later(self, content: str) -> None:
        try:
            await self._kb.index_document("ltm", content, chunk_size=500)
        except Exception as exc:
            logger.warning("Deferred KB index failed: %s", exc)

    def recall(self, keyword: Optional[str] = None, limit: int = 5) -> list[str]:
        entries = self._ltm.query(keyword=keyword, limit=limit)
        return [e["content"] for e in entries]

    async def semantic_recall(self, query: str, top_k: int = 5) -> list[dict]:
        return await self._kb.search(query, top_k=top_k)

    async def index_document(self, doc_id: str, text: str) -> int:
        return await self._kb.index_document(doc_id, text)

    def load_episodes(self) -> None:
        self._episodic._load()

    def save_episodes(self) -> None:
        self._episodic.save()

    def __len__(self) -> int:
        return len(self._stm) + len(self._ltm._path.read_text(encoding="utf-8").splitlines()) \
               if self._ltm._path.exists() else len(self._stm)
