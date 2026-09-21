"""knowledge_consolidator.py -- MOON's autonomous self-learning loop.

After every interaction MOON consolidates whatever knowledge she gained into
her durable "main brain" (LongTermMemory, a disk-backed JSONL store that
survives restarts) and into the semantic KnowledgeBase (RAG) so future context
retrieval reuses it.

What gets learned ("all type of knowledge"):
  * factual statements from MOON's own answers (offline heuristic extraction of
    informative sentences: definitions, "X is/are Y", figures, dates, ...),
  * explicit user-provided facts,
  * tool execution results (what a tool returned), and
  * self-reflection lessons.

Extraction is OFFLINE-FIRST (fast, always works on a CPU-only box) with an
optional LLM pass (``use_llm``) for higher-quality structured extraction when
the host can afford an extra call. Everything is best-effort and never blocks
the reply. Deduplication keeps the brain from filling with repeats.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.brain.memory_manager import MemoryManager
    from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

_FACT_CUES = re.compile(
    r"\b(is|are|was|were|means|refers to|equals|defined as|stands for|"
    r"abbreviat|in short|because|requires|contains|consists of|located in|"
    r"founded|created|invented|published|released|version|protocol)\b",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"^\s*(ok|okay|sure|thanks|thank you|hello|hi|hey|yes|no|done|great|cool)\b", re.IGNORECASE)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[\n])\s*")


class KnowledgeConsolidator:
    """Automatically distills durable knowledge from an interaction."""

    def __init__(
        self,
        memory: MemoryManager,
        llm: LLMService | None = None,
        *,
        use_llm: bool = False,
        max_facts_per_turn: int = 6,
        recent_cache_size: int = 256,
    ) -> None:
        self._memory = memory
        self._llm = llm
        self._use_llm = use_llm
        self._max_facts = max_facts_per_turn
        self._seen: set[str] = set()
        self._cache_size = recent_cache_size

    async def consolidate(
        self,
        *,
        prompt: str,
        response: str,
        tool_results: list[str] | None = None,
        lesson: str = "",
        success: bool = True,
        agent: str | None = None,
    ) -> int:
        try:
            facts = await self._gather_facts(prompt, response, tool_results, lesson, success, agent)
            stored = 0
            for fact, tags in facts:
                if stored >= self._max_facts:
                    break
                if self._should_skip(fact):
                    continue
                try:
                    await self._memory.learn(fact, tags=tags)
                    self._mark_seen(fact)
                    stored += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("consolidate: learn failed for fact: %s", exc)
            if stored:
                logger.info("MOON learned %d new fact(s) into her brain", stored)
            return stored
        except Exception as exc:  # noqa: BLE001
            logger.warning("KnowledgeConsolidator.consolidate failed (skipped): %s", exc)
            return 0

    async def _gather_facts(
        self, prompt, response, tool_results, lesson, success, agent
    ) -> list[tuple[str, list[str]]]:
        facts: list[tuple[str, list[str]]] = []
        tags: list[str] = ["auto-learn"]
        if agent:
            tags.append(f"agent:{agent}")
        for s in self._sentences(prompt):
            if s.rstrip().endswith("?") or s.rstrip().endswith("?."):
                continue
            if _FACT_CUES.search(s) and len(s) > 24:
                facts.append((f"[user fact] {s.strip()}", tags + ["user"]))
        for s in self._sentences(response):
            if self._looks_factual(s):
                facts.append((s.strip(), tags + ["answer"]))
        for tr in tool_results or []:
            tr = (tr or "").strip()
            if 12 < len(tr) < 600:
                facts.append((f"[tool result] {tr}", tags + ["tool"]))
        if lesson:
            facts.append((f"[lesson] {lesson.strip()}", tags + ["lesson"]))
        if self._use_llm and self._llm is not None and response:
            try:
                llm_facts = await self._llm_extract(prompt, response)
                for f in llm_facts:
                    facts.append((f, tags + ["llm"]))
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM extraction skipped: %s", exc)
        return facts

    @staticmethod
    def _sentences(text: str) -> list[str]:
        text = (text or "").replace("\r", " ").strip()
        text = re.split(r"\n-{3,}\n", text)[-1]
        return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]

    def _looks_factual(self, sentence: str) -> bool:
        if len(sentence) < 24 or len(sentence) > 400:
            return False
        if _NOISE_RE.match(sentence):
            return False
        if not _FACT_CUES.search(sentence) and not re.search(r"\d", sentence):
            return False
        if sentence.lower().startswith(("let me", "i can", "i will", "sure,", "here is", "here's")):
            return False
        return True

    async def _llm_extract(self, prompt: str, response: str) -> list[str]:
        try:
            from app.services.llm_service import ChatMessage

            resp = await self._llm.complete(  # type: ignore[union-attr]
                [
                    ChatMessage(role="system", content=(
                        "Extract durable, reusable facts from the assistant's answer as a "
                        "JSON list of short strings (max 6). Ignore chit-chat. Return ONLY the JSON list."
                    )),
                    ChatMessage(role="user", content=f"Q: {prompt}\nA: {response}"),
                ],
                max_tokens=300,
                temperature=0.2,
            )
            import json

            txt = (resp.content or "").strip()
            txt = txt.strip("`").removeprefix("json")
            data = json.loads(txt)
            return [str(x).strip() for x in data if isinstance(x, str) and x.strip()][:6]
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_extract parse failed: %s", exc)
            return []

    def _hash(self, text: str) -> str:
        return hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:16]

    def _should_skip(self, fact: str) -> bool:
        return self._hash(fact) in self._seen

    def _mark_seen(self, fact: str) -> None:
        self._seen.add(self._hash(fact))
        if len(self._seen) > self._cache_size:
            self._seen = set(list(self._seen)[-self._cache_size // 2 :])
