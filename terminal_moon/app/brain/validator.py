"""
Validator — validates final_text against task prompt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.llm_service import ChatMessage, LLMService

logger = logging.getLogger("moontm.validator")


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = None

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []


class Validator:
    def __init__(self, llm: Optional[LLMService] = None) -> None:
        self._llm = llm

    async def validate(self, prompt: str, answer: str) -> ValidationResult:
        if not self._llm:
            return ValidationResult(valid=True)

        messages = [
            ChatMessage(role="system", content=(
                "Check whether the following answer addresses the user's question. "
                "Reply with JSON: {\"valid\": true/false, \"issues\": [...]}"
            )),
            ChatMessage(role="user", content=f"QUESTION: {prompt}\n\nANSWER: {answer}"),
        ]
        result = await self._llm.complete(messages, max_tokens=300)
        try:
            import json
            data = json.loads(result.content)
            return ValidationResult(
                valid=data.get("valid", True),
                issues=data.get("issues", []),
            )
        except Exception:
            return ValidationResult(valid=True)
