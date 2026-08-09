"""Semantic search facade over the knowledge base + history."""

from __future__ import annotations

from typing import Any


class SemanticSearch:
    def __init__(self, knowledge_base=None, history=None) -> None:
        self._kb = knowledge_base
        self._history = history

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if self._kb is None:
            return []
        try:
            return await self._kb.search(query, top_k=top_k)
        except Exception:  # noqa: BLE001
            return []
