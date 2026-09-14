"""
SelfReflection — self-reviews an answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.llm_service import ChatMessage, LLMService

logger = logging.getLogger("moontm.reflection")


@dataclass
class ReflectionResult:
    satisfactory: bool
    improvements: list[str] = None

    def __post_init__(self) -> None:
        if self.improvements is None:
            self.improvements = []


class SelfReflection:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self._llm = llm

    async def reflect(self, prompt: str, answer: str) -> ReflectionResult:
        if not self._llm:
            return ReflectionResult(satisfactory=True)

        messages = [
            ChatMessage(role="system", content=(
                "Reflect on whether the following answer is satisfactory. "
                "Reply with JSON: {\"satisfactory\": true/false, \"improvements\": [...]}"
            )),
            ChatMessage(role="user", content=f"QUESTION: {prompt}\n\nANSWER: {answer}"),
        ]
        result = await self._llm.complete(messages, max_tokens=300)
        try:
            import json
            data = json.loads(result.content)
            return ReflectionResult(
                satisfactory=data.get("satisfactory", True),
                improvements=data.get("improvements", []),
            )
        except Exception:
            return ReflectionResult(satisfactory=True)
