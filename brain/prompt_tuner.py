"""prompt_tuner.py -- MOON's self-improvement loop for agent personas.

Lessons extracted from interactions (corrections, preferences, failures) are
persisted to app/logs/lessons.jsonl. At startup the tuner loads them and
appends a compact "learned guidance" block to each agent persona, so MOON
steadily improves without anyone editing code by hand.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_LESSONS_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "logs" / "lessons.jsonl"


def record_lesson(text: str, *, kind: str = "general", agent: str | None = None) -> None:
    """Persist one improvement lesson (called by the consolidator / loops)."""
    text = (text or "").strip()
    if len(text) < 8:
        return
    try:
        _LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LESSONS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, "agent": agent, "text": text}) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_lesson failed: %s", exc)


def load_lessons(agent: str | None = None, limit: int = 8) -> list[str]:
    """Return the most recent lesson texts (optionally for one agent)."""
    if not _LESSONS_PATH.exists():
        return []
    out: list[str] = []
    try:
        lines = _LESSONS_PATH.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if agent and obj.get("agent") and obj["agent"] != agent:
                continue
            txt = obj.get("text")
            if txt:
                out.append(txt)
            if len(out) >= limit:
                break
    except Exception as exc:  # noqa: BLE001
        logger.debug("load_lessons failed: %s", exc)
    return out


def augment_persona(base_persona: str, agent: str | None = None) -> str:
    """Append learned lessons to a base persona (used by the context builder)."""
    lessons = load_lessons(agent)
    if not lessons:
        return base_persona
    block = "\n\nLearned guidance from past interactions:\n" + "\n".join(f"- {l}" for l in lessons)
    return base_persona + block
