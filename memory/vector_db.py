"""In-memory vector store (cosine similarity)."""

from __future__ import annotations

from typing import Any


class InMemoryVectorStore:
    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        self._items: list[tuple[str, list[float], dict[str, Any]]] = []

    def add(self, key: str, vec: list[float], meta: dict[str, Any]) -> None:
        self._items.append((key, vec, meta))

    def search(self, query: list[float], top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        scored = [(k, self._cosine(query, v), m) for k, v, m in self._items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
