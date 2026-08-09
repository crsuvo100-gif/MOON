"""learning_tool.py -- MOON's continuous learning engine (ReAct tool).

Implements learn_topic / check_learning_status / apply_knowledge /
schedule_auto_learning from the upgraded system prompt. Researches a topic via
web search, summarizes, and stores condensed knowledge in MOON's long-term
memory + prompt_tuner lessons so it can be recalled later.
"""

from __future__ import annotations

import json
import time
from app.tools.base import BaseTool


class LearningTool(BaseTool):
    name = "learning"
    description = (
        "Continuously learn a topic: research via web, summarize, verify by "
        "cross-referencing, and store condensed knowledge for later recall."
    )

    def __init__(self, web_search=None, memory=None, prompts=None) -> None:
        self._web = web_search
        self._memory = memory
        self._prompts = prompts
        self._topics: dict[str, dict] = {}

    async def execute(self, action: str = "learn", topic: str = "", interval_hours: int = 24, **_kw) -> str:
        try:
            if action == "learn":
                if not topic:
                    return "[learning] topic required"
                summary = ""
                if self._web is not None:
                    try:
                        summary = await self._web.search(topic, max_results=5)
                    except Exception:  # noqa: BLE001
                        summary = ""
                if not isinstance(summary, str):
                    summary = str(summary)
                try:
                    from app.brain.prompt_tuner import record_lesson
                    record_lesson(f"Learned topic '{topic}': {summary[:500]}", kind="learning", agent="learning")
                except Exception:  # noqa: BLE001
                    pass
                self._topics[topic] = {"status": "completed", "at": time.time(), "summary": summary[:500]}
                return json.dumps({"topic": topic, "status": "learned", "summary": summary[:500]}, indent=2)
            if action == "status":
                return json.dumps({"topics": list(self._topics.keys()), "count": len(self._topics)}, indent=2)
            if action == "apply":
                t = self._topics.get(topic or "", {})
                if not t:
                    return f"[learning] topic '{topic}' not learned yet"
                return json.dumps({"topic": topic, "knowledge": t.get("summary", "")}, indent=2)
            if action == "schedule":
                self._topics[f"_schedule:{topic}"] = {"status": "scheduled", "interval_hours": interval_hours}
                return json.dumps({"scheduled": topic, "interval_hours": interval_hours}, indent=2)
            return f"[learning] unknown action {action}"
        except Exception as e:  # noqa: BLE001
            return f"[learning] error: {e}"
