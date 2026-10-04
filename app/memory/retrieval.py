"""Hybrid memory retrieval (spec 19, 20, 21, 22, 54).

Spec 20 is explicit: do NOT rely on vector similarity alone. The final score
combines semantic + keyword + task relevance + importance + recency +
confidence + scope relevance, normalised before combining.

Spec 54 adds a retrieval cache that must never let stale results override
verified persistent memory.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from app.memory.record import Importance, MemoryRecord, Scope

_IMPORTANCE_W = {
    Importance.CRITICAL: 1.0, Importance.HIGH: 0.8, Importance.MEDIUM: 0.55,
    Importance.LOW: 0.3, Importance.TEMPORARY: 0.12,
}

# spec 20: default weights (sum-normalised at use time)
DEFAULT_WEIGHTS = {
    "semantic": 0.34,
    "keyword": 0.18,
    "task": 0.14,
    "importance": 0.14,
    "recency": 0.08,
    "confidence": 0.08,
    "scope": 0.04,
}


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", (s or "").lower()))


def keyword_score(query: str, text: str) -> float:
    """Jaccard-ish overlap, bounded 0..1."""
    q, t = _words(query), _words(text)
    if not q or not t:
        return 0.0
    inter = len(q & t)
    return inter / math.sqrt(len(q) * len(t))


def recency_score(updated_at: float, *, half_life_days: float = 30.0) -> float:
    if not updated_at:
        return 0.0
    age_days = max(0.0, (time.time() - updated_at) / 86400.0)
    return 0.5 ** (age_days / max(0.5, half_life_days))


# spec 22: scope relevance for the CURRENT agent/task
def scope_score(rec: MemoryRecord, *, agent_id: str = "", project_id: str = "",
                task_id: str = "", session_id: str = "") -> float:
    """Higher when the memory belongs to the asking context.

    AGENT-private memory of a DIFFERENT agent scores 0 and is filtered out by
    the caller (spec 40/88 isolation).
    """
    if rec.scope is Scope.AGENT:
        return 1.0 if (agent_id and rec.agent_id == agent_id) else 0.0
    if rec.scope is Scope.SESSION and session_id:
        return 1.0 if rec.session_id == session_id else 0.0
    if rec.scope is Scope.TASK and task_id:
        return 1.0 if rec.task_id == task_id else 0.0
    if rec.scope is Scope.PROJECT and project_id:
        return 1.0 if rec.project_id == project_id else 0.3
    if rec.scope in (Scope.USER, Scope.GLOBAL, Scope.SYSTEM):
        return 0.7
    return 0.4


@dataclass
class Scored:
    record: MemoryRecord
    score: float
    parts: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"memory_id": self.record.memory_id, "content": self.record.content,
                "score": round(self.score, 4),
                "parts": {k: round(v, 4) for k, v in self.parts.items()},
                "scope": self.record.scope.value, "type": self.record.type.value,
                "confidence": self.record.confidence,
                "importance": self.record.importance.value}


class HybridRetriever:
    """Combines every signal (spec 20) over a candidate set."""

    def __init__(self, *, weights: dict[str, float] | None = None,
                 embed_fn: Callable[[str], list[float]] | None = None,
                 vector_store: Any = None) -> None:
        self._w = dict(weights or DEFAULT_WEIGHTS)
        self._embed = embed_fn
        self._vectors = vector_store

    # -- semantic (spec 19) ---------------------------------------------
    def _semantic_scores(self, query: str,
                         records: list[MemoryRecord]) -> dict[str, float]:
        """Vector similarity when an embedding fn + store are available.

        spec 58: when embeddings are unavailable we return {} and the keyword
        signal carries retrieval -- the system degrades, it does not fail.
        """
        if not self._embed or self._vectors is None or not records:
            return {}
        try:
            qv = self._embed(query)
            if not qv:
                return {}
            hits = self._vectors.search(qv, top_k=len(records))
            raw = {k: s for k, s, _ in hits}
            # normalise to 0..1
            if not raw:
                return {}
            lo, hi = min(raw.values()), max(raw.values())
            span = (hi - lo) or 1.0
            return {k: (v - lo) / span for k, v in raw.items()}
        except Exception:  # noqa: BLE001
            return {}

    # -- main -----------------------------------------------------------
    def rank(self, query: str, records: Iterable[MemoryRecord], *,
             agent_id: str = "", project_id: str = "", task_id: str = "",
             session_id: str = "", task_text: str = "",
             now: float | None = None) -> list[Scored]:
        recs = [r for r in records if not r.deleted]
        if not recs:
            return []
        # spec 40/88: never leak another agent's private memory. Fail CLOSED: an
        # AGENT-scoped record with no owner is dropped rather than exposed.
        def _visible(r: MemoryRecord) -> bool:
            if r.scope is not Scope.AGENT:
                return True
            if not r.agent_id:
                return False
            return bool(agent_id) and r.agent_id == agent_id

        recs = [r for r in recs if _visible(r)]

        sem = self._semantic_scores(query, recs)
        task_query = task_text or query
        out: list[Scored] = []
        for r in recs:
            parts = {
                "semantic": sem.get(r.memory_id, 0.0),
                "keyword": keyword_score(query, r.content + " " + r.summary),
                "task": keyword_score(task_query, r.content + " " + " ".join(r.tags)),
                "importance": _IMPORTANCE_W.get(r.importance, 0.5),
                "recency": recency_score(r.updated_at),
                "confidence": max(0.0, min(1.0, r.confidence)),
                "scope": scope_score(r, agent_id=agent_id, project_id=project_id,
                                     task_id=task_id, session_id=session_id),
            }
            total = sum(parts[k] * self._w.get(k, 0.0) for k in parts)
            # canonical/verified facts get a small floor so they are never lost
            if r.canonical:
                total = max(total, 0.5)
            out.append(Scored(record=r, score=total, parts=parts))
        out.sort(key=lambda s: s.score, reverse=True)
        return out

    def search(self, query: str, records: Iterable[MemoryRecord], *,
               top_k: int = 5, min_score: float = 0.0, **kw: Any) -> list[Scored]:
        ranked = self.rank(query, records, **kw)
        return [s for s in ranked if s.score >= min_score][:top_k]


# --------------------------------------------------------------------------
# spec 21: query rewriting
# --------------------------------------------------------------------------
_STOP = {"the", "a", "an", "of", "to", "and", "or", "is", "are", "was", "we",
         "i", "you", "it", "that", "this", "for", "on", "in", "with", "my"}


def rewrite_query(text: str, *, max_queries: int = 10) -> list[str]:
    """spec 21: expand one request into several retrieval signals.

    "Continue the Python project we worked on." ->
        ["python project", "python", "project", "continue"]
    """
    t = (text or "").strip()
    if not t:
        return []
    queries: list[str] = [t]
    content = [w for w in re.findall(r"[A-Za-z0-9_]+", t.lower())
               if w not in _STOP and len(w) > 2]
    if content:
        queries.append(" ".join(content))
        # Include EVERY content term as its own signal (bounded). Taking only
        # the longest two dropped short-but-distinctive terms like "qwen",
        # "git" or "api", so a query mentioning them found nothing.
        for w in dict.fromkeys(content):
            queries.append(w)
    # dedupe, preserve order, bound the count
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:max_queries]


# --------------------------------------------------------------------------
# spec 54: retrieval cache
# --------------------------------------------------------------------------
class RetrievalCache:
    """Short-TTL cache keyed on (query, context). Invalidated on write.

    spec 54: must never let a stale entry override verified persistent memory --
    so any write bumps ``_generation`` and every entry from an older generation
    is treated as a miss.
    """

    def __init__(self, *, ttl: float = 20.0, max_size: int = 128) -> None:
        self._ttl = ttl
        self._max = max_size
        self._data: dict[tuple, tuple[float, int, Any]] = {}
        self._generation = 0

    def invalidate(self) -> None:
        self._generation += 1
        self._data.clear()

    def key(self, query: str, **ctx: Any) -> tuple:
        return (query, tuple(sorted((k, str(v)) for k, v in ctx.items())))

    def get(self, key: tuple) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        ts, gen, val = item
        if gen != self._generation or (time.time() - ts) > self._ttl:
            self._data.pop(key, None)
            return None
        return val

    def put(self, key: tuple, val: Any) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._data.items(), key=lambda kv: kv[1][0])[0]
            self._data.pop(oldest, None)
        self._data[key] = (time.time(), self._generation, val)

    def stats(self) -> dict[str, Any]:
        return {"entries": len(self._data), "generation": self._generation,
                "ttl": self._ttl}


__all__ = [
    "HybridRetriever", "Scored", "RetrievalCache", "rewrite_query",
    "keyword_score", "recency_score", "scope_score", "DEFAULT_WEIGHTS",
]
