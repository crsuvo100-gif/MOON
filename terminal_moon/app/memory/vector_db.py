"""
In-memory vector store — cosine similarity search over embedded chunks.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


class InMemoryVectorStore:
    """Stores {id, vector, chunk} and supports cosine-similarity top-k search."""

    def __init__(self) -> None:
        self._items: list[dict] = []  # {id, vector, chunk}

    def add(self, id: str, vector: list[float], chunk: str) -> None:
        self._items.append({"id": id, "vector": vector, "chunk": chunk})

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        if not self._items:
            return []
        qv = np.array(query_vector, dtype=np.float32)
        qt = np.linalg.norm(qv)
        if qt == 0:
            return []
        scored: list[tuple[int, float]] = []
        for i, item in enumerate(self._items):
            iv = np.array(item["vector"], dtype=np.float32)
            it = np.linalg.norm(iv)
            if it == 0:
                continue
            sim = float(np.dot(qv, iv) / (qt * it))
            scored.append((i, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {"chunk": self._items[i]["chunk"], "score": round(s, 4)}
            for i, s in scored[:top_k]
        ]

    def __len__(self) -> int:
        return len(self._items)
