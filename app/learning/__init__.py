"""Learning subsystem (spec sections 20, 23, 25, 26).

Implements the learning flow (spec 23): goal -> curriculum -> research ->
knowledge extraction -> practice -> test -> verification -> memory -> skill ->
mastery. Plus failure learning (spec 25) and reflection (spec 26).

This package reuses MOON's existing memory/reflection pieces where present and
adds the curriculum/mastery + failure-classification scaffolding. It does NOT
rewrite any existing module (non-destructive); it composes them.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Lesson:
    goal: str
    lesson: str
    success: bool
    at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return {"goal": self.goal, "lesson": self.lesson, "success": self.success, "at": self.at}


class Learner:
    """Curriculum + mastery tracking (spec 23). Maintains a per-topic mastery
    score that rises on verified success and falls on failure (spec 23, 25)."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        self._path = Path(store_path or Path("data") / "learning" / "mastery.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._mastery: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        try:
            return json.loads(self._path.read_text() or "{}")
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._mastery, indent=2))
        except Exception:  # noqa: BLE001
            pass

    def observe(self, topic: str, success: bool, *, weight: float = 0.1) -> float:
        cur = self._mastery.get(topic, 0.5)
        delta = weight if success else -weight
        cur = max(0.0, min(1.0, cur + delta))
        self._mastery[topic] = cur
        self._save()
        return cur

    def mastery(self, topic: str) -> float:
        return self._mastery.get(topic, 0.5)

    def weakest(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(self._mastery.items(), key=lambda kv: kv[1])[:n]


class FailureClassifier:
    """Classify failures and suggest a safe alternative (spec 25)."""

    _PATTERNS = [
        ("timeout", re.compile(r"timeout|timed out", re.I)),
        ("permission", re.compile(r"permission|denied|unauthorized|403|401", re.I)),
        ("not_found", re.compile(r"not found|no such|missing", re.I)),
        ("syntax", re.compile(r"syntax error|traceback|nameerror|typeerror", re.I)),
        ("network", re.compile(r"connection|network|dns|refused", re.I)),
        ("resource", re.compile(r"memory|oom|resource|disk full", re.I)),
    ]

    @classmethod
    def classify(cls, error: str) -> str:
        for label, rx in cls._PATTERNS:
            if rx.search(error or ""):
                return label
        return "unknown"

    @classmethod
    def safe_alternative(cls, kind: str) -> str:
        return {
            "timeout": "retry with a longer timeout / smaller input",
            "permission": "request required permission via approval gate",
            "not_found": "verify path/name; search registry before retry",
            "syntax": "validate input; re-run with corrected arguments",
            "network": "retry with backoff; fall back to cached result",
            "resource": "reduce scope; offload to a smaller model",
        }.get(kind, "recover with a smaller, verified step")


class Reflector:
    """Structured post-task reflection (spec 26): asks the canonical questions
    and stores only useful conclusions (spec 26 'not unlimited raw logs')."""

    QUESTIONS = [
        "What was the goal?",
        "What succeeded?",
        "What failed?",
        "Why?",
        "What knowledge was missing?",
        "What skill should be updated?",
        "Was the selected agent appropriate?",
        "Was the selected tool appropriate?",
        "Can the process be improved?",
    ]

    def reflect(self, *, goal: str, succeeded: bool, failure_kind: str = "",
                improvement: str = "") -> dict[str, Any]:
        return {
            "goal": goal,
            "succeeded": succeeded,
            "failure_kind": failure_kind,
            "improvement": improvement,
            "questions": self.QUESTIONS,
        }


__all__ = ["Lesson", "Learner", "FailureClassifier", "Reflector"]
