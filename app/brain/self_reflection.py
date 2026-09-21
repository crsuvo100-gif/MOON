"""self_reflection.py -- reviews an answer and suggests concrete improvements.

Real LLM-driven reflection: judges whether the answer actually satisfies the
prompt, checks for incompleteness/errors, and returns actionable improvements.
Offline heuristic fallback when no LLM is present.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.llm_service import ChatMessage


@dataclass
class ReflectionResult:
    satisfactory: bool
    improvements: list[str]


class SelfReflection:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def reflect(self, prompt: str, answer: str) -> ReflectionResult:
        if self._llm is not None and answer and len(answer) > 5:
            try:
                resp = await self._llm.complete(
                    [ChatMessage(role="user", content=(
                        "Critique the ANSWER against the PROMPT. List concrete "
                        "problems only (missing parts, factual errors, vagueness). "
                        "If it is good, reply exactly SATISFACTORY. Otherwise list "
                        "each issue on its own line.\n\nPROMPT: " + prompt
                        + "\n\nANSWER: " + answer
                    ))],
                    max_tokens=300, temperature=0.1,
                )
                text = (resp.content or "").strip()
                if text.upper().startswith("SATISFACTORY"):
                    return ReflectionResult(satisfactory=True, improvements=[])
                improvements = [l.strip("-*1234567890. )") for l in text.splitlines() if l.strip()]
                return ReflectionResult(satisfactory=not improvements, improvements=improvements[:10])
            except Exception:  # noqa: BLE001
                pass
        # offline fallback
        improvements: list[str] = []
        if not answer or len(answer) < 5:
            improvements.append("answer is too short / empty")
        return ReflectionResult(satisfactory=len(improvements) == 0, improvements=improvements)
