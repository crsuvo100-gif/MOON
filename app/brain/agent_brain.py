"""agent_brain.py -- each agent's OWN brain, connected to MOON's main brain.

Every agent gets an isolated WorkingMemory + ConversationHistory plus a
durable per-agent episodic store (JSONL under app/logs/agent_brains/<agent>.jsonl)
so an agent's accumulated experience persists across restarts. The two-phase
"connect to main brain" path validates/refines an agent's draft answer through
the orchestrator's main model when ENABLE_AGENT_VALIDATION is on; otherwise the
agent runs standalone on its own brain.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.config.settings import get_settings
from app.memory.conversation_history import ConversationHistory
from app.memory.working_memory import WorkingMemory

logger = logging.getLogger(__name__)

_AGENT_BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "logs" / "agent_brains"


class _AgentBrainStore:
    """Durable JSONL episode store for one agent's brain."""

    def __init__(self, agent: str) -> None:
        self._path = _AGENT_BRAIN_DIR / f"{agent}.jsonl"
        self._lock = asyncio.Lock()
        self._eps: list[dict[str, Any]] = []

    def _ensure(self) -> None:
        _AGENT_BRAIN_DIR.mkdir(parents=True, exist_ok=True)

    async def load(self) -> None:
        self._ensure()
        if self._path.exists():
            try:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, self._path.read_text, "utf-8"
                )
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            self._eps.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent_brain load failed (%s): %s", self._path, exc)

    async def append(self, episode: dict[str, Any]) -> None:
        self._ensure()
        self._eps.append(episode)
        line = json.dumps(episode, ensure_ascii=False) + "\n"
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, self._append_line, line)

    def _append_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def episodes(self) -> list[dict[str, Any]]:
        return list(self._eps)


class AgentBrain:
    """An agent's own brain, wired to MOON's main brain for validation."""

    def __init__(self, agent_name: str, main_brain=None) -> None:
        self.agent_name = agent_name
        self.main_brain = main_brain
        self.working = WorkingMemory()
        self.history = ConversationHistory(session_id=f"agent:{agent_name}")
        self._store = _AgentBrainStore(agent_name)
        self._refine = get_settings().enable_agent_validation

    async def setup(self) -> None:
        await self._store.load()
        logger.info("Agent brain '%s' ready (%d prior episodes)", self.agent_name, len(self._store.episodes()))

    async def remember(self, episode: dict[str, Any]) -> None:
        self.working.set(f"ep_{len(self._store.episodes())}", episode)
        await self._store.append(episode)

    async def draft(self, task: str, context: str = "") -> str:
        """Produce a first-pass answer from the agent's own brain."""
        prior = self._store.episodes()[-3:]
        prior_txt = "\n".join(f"- {e.get('outcome', '')[:200]}" for e in prior)
        prompt = (
            f"You are the {self.agent_name} agent of MOON. Use your prior experience:\n"
            f"{prior_txt}\n\nTask: {task}\nContext: {context}\nProduce a concise draft answer."
        )
        return prompt

    async def refine_with_main(self, draft_text: str, task: str) -> str:
        """Two-phase: let the main brain validate/improve the draft."""
        if not self._refine or self.main_brain is None:
            return draft_text
        try:
            refine_prompt = (
                f"MOON main brain: review this {self.agent_name} agent draft for correctness "
                f"and improve it.\nTASK: {task}\nDRAFT: {draft_text}\nReturn the improved answer only."
            )
            result = await self.main_brain.refine(refine_prompt)
            return result or draft_text
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent refine skipped: %s", exc)
            return draft_text

    async def run(self, task: str, context: str = "") -> str:
        draft_text = await self.draft(task, context)
        return await self.refine_with_main(draft_text, task)

    async def teardown(self) -> None:
        return
