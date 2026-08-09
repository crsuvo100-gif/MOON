"""SelfReflection -- reviews an answer and suggests improvements."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReflectionResult:
    satisfactory: bool
    improvements: list[str]


class SelfReflection:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def reflect(self, prompt: str, answer: str) -> ReflectionResult:
        # Heuristic reflection: flagged only on obvious problems.
        improvements: list[str] = []
        if not answer or len(answer) < 5:
            improvements.append("answer is too short")
        return ReflectionResult(satisfactory=len(improvements) == 0, improvements=improvements)
