"""
Episodic memory — goal/outcome/lesson/success records, persisted to JSON.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Episode(BaseModel):
    goal: str
    outcome: str
    lesson: str = ""
    success: bool = True
    agent: str = "coordinator"
    timestamp: float = 0.0


class EpisodicMemory:
    """In-memory episodic store loaded from / saved to episodes.json."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._episodes: list[Episode] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.touch()
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._episodes = [Episode(**e) for e in data]
        except Exception:
            self._episodes = []

    def record(self, goal: str, outcome: str, lesson: str = "",
               success: bool = True, agent: str = "coordinator") -> Episode:
        ep = Episode(
            goal=goal,
            outcome=outcome,
            lesson=lesson,
            success=success,
            agent=agent,
            timestamp=0.0,  # caller can set if needed
        )
        with self._lock:
            self._episodes.append(ep)
        self.save()
        return ep

    def recall(self, query: Optional[str] = None, k: int = 3) -> list[Episode]:
        with self._lock:
            if not query:
                return self._episodes[-k:]
            q = query.lower()
            scored = [
                (ep, ep.outcome.lower().count(q) + ep.lesson.lower().count(q) + ep.goal.lower().count(q))
                for ep in self._episodes
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [ep for ep, _ in scored[:k]]

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps([ep.model_dump() for ep in self._episodes], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
