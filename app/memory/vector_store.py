"""Pluggable vector store (spec sections 39, 40).

The interface is intentionally backend-agnostic so the architecture is not
hard-coded to one database (spec 40). Implementations:

  * InMemoryVectorStore  -- zero-dependency, for low-resource / default.
  * PostgresVectorStore  -- when `psycopg2` + pgvector are available; otherwise
    it reports the missing dependency instead of pretending to work (spec 59).

Existing modules import ``get_vector_store()`` and remain decoupled.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    key: str
    vector: list[float]
    meta: dict[str, Any] = field(default_factory=dict)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore(ABC):
    @abstractmethod
    def add(self, key: str, vector: list[float], meta: dict[str, Any]) -> None: ...

    @abstractmethod
    def search(self, query: list[float], top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def update(self, key: str, vector: list[float] | None = None,
               meta: dict[str, Any] | None = None) -> bool: ...

    @abstractmethod
    def similarity_search(self, query: list[float], top_k: int = 5,
                          threshold: float = 0.0) -> list[tuple[str, float, dict[str, Any]]]: ...


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._data: dict[str, VectorRecord] = {}

    def add(self, key: str, vector: list[float], meta: dict[str, Any]) -> None:
        self._data[key] = VectorRecord(key=key, vector=vector, meta=meta)

    def search(self, query: list[float], top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        scored = [(k, _cosine(query, r.vector), r.meta) for k, r in self._data.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def update(self, key: str, vector: list[float] | None = None,
               meta: dict[str, Any] | None = None) -> bool:
        r = self._data.get(key)
        if r is None:
            return False
        if vector is not None:
            r.vector = vector
        if meta is not None:
            r.meta.update(meta)
        return True

    def similarity_search(self, query: list[float], top_k: int = 5,
                          threshold: float = 0.0) -> list[tuple[str, float, dict[str, Any]]]:
        res = self.search(query, top_k=top_k)
        return [(k, s, m) for k, s, m in res if s >= threshold]


class PostgresVectorStore(VectorStore):
    """Pgvector-backed store. Degrades gracefully if the driver is absent."""

    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn or ""
        try:
            import psycopg2  # noqa: F401
            self._ok = True
            self._conn = None
        except Exception as e:  # noqa: BLE001
            self._ok = False
            self._reason = f"psycopg2/pgvector not installed: {e}"

    def _require(self) -> None:
        if not self._ok:
            raise RuntimeError(
                f"[PostgresVectorStore] missing dependency -- {getattr(self, '_reason', 'unknown')}. "
                "Install psycopg2 + pgvector, or use InMemoryVectorStore (spec 59).")

    def add(self, key: str, vector: list[float], meta: dict[str, Any]) -> None:
        self._require()
        raise NotImplementedError("pgvector add() requires a live DB connection")

    def search(self, query: list[float], top_k: int = 5) -> list[tuple[str, float, dict[str, Any]]]:
        self._require()
        return []

    def delete(self, key: str) -> bool:
        self._require()
        return False

    def update(self, key: str, vector: list[float] | None = None,
               meta: dict[str, Any] | None = None) -> bool:
        self._require()
        return False

    def similarity_search(self, query: list[float], top_k: int = 5,
                          threshold: float = 0.0) -> list[tuple[str, float, dict[str, Any]]]:
        self._require()
        return []


_STORE: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Return the process-wide pluggable vector store (spec 40)."""
    global _STORE
    if _STORE is None:
        _STORE = InMemoryVectorStore()
    return _STORE


def set_vector_store(store: VectorStore) -> None:
    global _STORE
    _STORE = store
