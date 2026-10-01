"""ContextRetriever -- unifies history, semantic search, and galaxy retrieval."""

from __future__ import annotations

from typing import Any


class ContextRetriever:
    def __init__(self, history=None, semantic_search=None, galaxy=None) -> None:
        self._history = history
        self._semantic = semantic_search
        self._galaxy = galaxy

    async def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if self._semantic is not None:
            try:
                results.extend(await self._semantic.search(query, top_k=top_k))
            except Exception:  # noqa: BLE001
                pass
        return results
