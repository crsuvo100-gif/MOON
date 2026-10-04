"""In-memory vector store (cosine similarity).

Memory notes (this is the single biggest consumer of MOON's RSS):

* Vectors are stored as packed ``array('f')`` (4 bytes/value) instead of a
  Python ``list[float]`` (24 bytes/value object + pointer). At ~88k chunks x 384
  dims that is the difference between ~815 MB and ~136 MB -- on a 3.7 GB host the
  list-of-floats form made MOON the kernel's OOM victim mid-task.
* ``_cosine`` previously computed ``sum(x * x)`` for BOTH the dot product and the
  norms (it used ``a`` twice), so ranking was wrong: it scored every vector by
  its own magnitude instead of its alignment with the query. Fixed to a real dot
  product plus cached per-vector norms.
"""

from __future__ import annotations

import math
from array import array
from typing import Any


def _pack(vec: Any) -> array:
    """Store a vector as packed float32, regardless of input container."""
    if isinstance(vec, array):
        return vec
    return array("f", (float(x) for x in vec))


class InMemoryVectorStore:
    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        # (key, packed vector, meta, cached L2 norm)
        self._items: list[tuple[str, array, dict[str, Any], float]] = []

    def add(self, key: str, vec: Any, meta: dict[str, Any]) -> None:
        packed = _pack(vec)
        norm = math.sqrt(sum(float(x) * float(x) for x in packed))
        self._items.append((key, packed, meta, norm))

    def search(self, query: Any, top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        q = _pack(query)
        qn = math.sqrt(sum(float(x) * float(x) for x in q))
        if qn == 0.0:
            return []
        scored: list[tuple[str, float, dict[str, Any]]] = []
        for key, vec, meta, vn in self._items:
            if vn == 0.0:
                continue
            # real dot product (the previous version used `a` twice -> wrong)
            dot = 0.0
            for x, y in zip(q, vec):
                dot += float(x) * float(y)
            scored.append((key, dot / (qn * vn), meta))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @property
    def size(self) -> int:
        return len(self._items)

    def approx_bytes(self) -> int:
        """Rough resident size of the packed vectors (for observability)."""
        return sum(len(v) * 4 for _, v, _, _ in self._items)

    @staticmethod
    def _cosine(a: Any, b: Any) -> float:
        """Cosine similarity of two raw vectors (kept for external callers)."""
        va, vb = _pack(a), _pack(b)
        if not va or not vb:
            return 0.0
        dot = sum(float(x) * float(y) for x, y in zip(va, vb))
        na = math.sqrt(sum(float(x) * float(x) for x in va))
        nb = math.sqrt(sum(float(y) * float(y) for y in vb))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
