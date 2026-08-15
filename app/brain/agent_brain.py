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
from app.services.llm_service import ChatMessage

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
    """An agent's own brain, wired to MOON's main brain for validation.

    Each agent can run on its OWN model (via AgentModelManager) so it generates
    a real, domain-suited first-pass answer before the result is sent up to the
    main MOON brain for the two-phase accuracy gate. If per-agent models are
    disabled or unavailable, the agent falls back to a template draft that the
    main brain still validates -- graceful degradation, never a crash.
    """

    def __init__(self, agent_name: str, main_brain=None,
                 agent_models: "AgentModelManager | None" = None) -> None:
        self.agent_name = agent_name
        self.main_brain = main_brain
        self.agent_models = agent_models
        self._llm: "LLMService | None" = None
        self.working = WorkingMemory()
        self.history = ConversationHistory(session_id=f"agent:{agent_name}")
        self._store = _AgentBrainStore(agent_name)
        self._refine = get_settings().enable_agent_validation

    async def setup(self) -> None:
        await self._store.load()
        # Lazily bind this agent's OWN model (pulled/installed on demand).
        if self.agent_models is not None:
            try:
                self._llm = await self.agent_models.get_llm(self.agent_name)
                logger.info("Agent '%s' brain bound to its own model", self.agent_name)
            except Exception as exc:  # noqa: BLE001
                logger.info("Agent '%s' own-model bind failed; template fallback: %s", self.agent_name, exc)
                self._llm = None
        logger.info("Agent brain '%s' ready (%d prior episodes)", self.agent_name, len(self._store.episodes()))

    async def remember(self, episode: dict[str, Any]) -> None:
        self.working.set(f"ep_{len(self._store.episodes())}", episode)
        await self._store.append(episode)

    async def draft(self, task: str, context: str = "") -> str:
        """Produce a first-pass answer from the agent's OWN brain/model.

        If the agent has its own LLMService (per-agent model), it actually
        generates an answer on that model. Otherwise it returns a prompt template
        so the main brain still has something to validate (graceful fallback).
        """
        prior = self._store.episodes()[-3:]
        prior_txt = "\n".join(f"- {e.get('outcome', '')[:200]}" for e in prior)
        if self._llm is not None:
            try:
                messages = [
                    ChatMessage(role="system", content=(
                        f"You are the {self.agent_name} agent of MOON, an expert sub-agent. "
                        f"Use your prior experience when relevant.\nPRIOR EXPERIENCE:\n{prior_txt}"
                    )),
                    ChatMessage(role="user", content=f"Task: {task}\nContext: {context}"),
                ]
                resp = await self._llm.complete(messages)
                if resp.content:
                    return resp.content
                logger.info("Agent '%s' own-model returned empty; using template fallback", self.agent_name)
            except Exception as exc:  # noqa: BLE001
                logger.info("Agent '%s' own-model draft failed; template fallback: %s", self.agent_name, exc)
        # Template fallback (no own model / call failed) -- main brain still validates.
        return (
            f"You are the {self.agent_name} agent of MOON. Use your prior experience:\n"
            f"{prior_txt}\n\nTask: {task}\nContext: {context}\nProduce a concise draft answer."
        )

    async def refine_with_main(self, draft_text: str, task: str) -> str:
        """Two-phase accuracy gate: main brain CRITIQUES then VERIFIES the draft.

        Phase 1 (critique): the main brain audits the agent's draft for factual,
        logical, instruction, safety, or hallucination errors and returns a
        strict JSON verdict. Phase 2 (verify): the main brain re-checks the
        (possibly corrected) result. Parsing is defensive -- if the model does
        not obey the JSON format, we extract a corrected answer heuristically.
        This catches mistakes instead of merely "improving" wording.
        """
        if not self._refine or self.main_brain is None:
            return draft_text
        try:
            critique_prompt = (
                f"You are MOON's MAIN BRAIN acting as a strict accuracy auditor for the "
                f"'{self.agent_name}' agent.\nTASK: {task}\n\nAGENT DRAFT:\n{draft_text}\n\n"
                f"Check the draft for factual errors, logical errors, missing key "
                f"requirements, unsafe/offensive content, and hallucination. "
                f"Reply with ONLY this JSON and nothing else:\n"
                f'{{"verdict": "ok" or "corrected", "answer": "<correct full answer if corrected, else the draft>"}}'
            )
            verdict = (await self.main_brain.refine(critique_prompt, temperature=0.1)).strip()
            corrected = self._extract_answer(verdict, draft_text)
            if corrected and corrected != draft_text:
                draft_text = corrected
            # Phase 2: verify once more
            verify_prompt = (
                f"Verify this final answer to the task is correct and complete. "
                f"TASK: {task}\nANSWER: {draft_text}\n"
                f'Reply ONLY JSON: {{"verdict": "verified" or "fix", "answer": "<better answer if fix>"}}.'
            )
            v = (await self.main_brain.refine(verify_prompt, temperature=0.1)).strip()
            fixed = self._extract_answer(v, draft_text)
            if fixed and fixed != draft_text:
                return fixed
            return draft_text
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent two-phase refine skipped: %s", exc)
            return draft_text

    @staticmethod
    def _extract_answer(raw: str, fallback: str) -> str:
        """Defensive parse of the auditor's JSON verdict; falls back to heuristics."""
        import json
        import re as _re
        raw = (raw or "").strip()
        if not raw:
            return fallback
        # Try strict JSON
        try:
            m = _re.search(r"\{.*\}", raw, _re.DOTALL)
            obj = json.loads(m.group(0)) if m else json.loads(raw)
            ans = (obj.get("answer") or "").strip()
            verdict = str(obj.get("verdict", "")).lower()
            if verdict == "corrected" and ans:
                return ans
            if verdict == "fix" and ans:
                return ans
            if ans and verdict in ("verified", "ok"):
                return ans
        except Exception:  # noqa: BLE001
            pass
        # Heuristic: model said "incorrect"/"wrong" OR gave a 'Corrected Answer:'
        low = raw.lower()
        if "corrected answer" in low:
            mm = _re.search(r"corrected answer[:\s]*\*?\*?([^\n*]+)", raw, _re.IGNORECASE)
            if mm:
                return mm.group(1).strip().strip("*").strip()
        if "incorrect" in low or "wrong" in low:
            # take the last non-empty line as the likely correction
            lines = [l.strip("* ").strip() for l in raw.splitlines() if l.strip()]
            for ln in reversed(lines):
                if ln and ln not in ("the original calculation is incorrect",):
                    return ln
        return fallback

    async def run(self, task: str, context: str = "") -> str:
        draft_text = await self.draft(task, context)
        return await self.refine_with_main(draft_text, task)

    async def teardown(self) -> None:
        return
