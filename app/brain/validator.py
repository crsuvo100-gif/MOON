"""Validator -- checks a final answer for basic sanity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str]


class Validator:
    def __init__(self, llm=None, prompts=None) -> None:
        self._llm = llm
        self._prompts = prompts

    async def validate(self, prompt: str, answer: str) -> ValidationResult:
        issues: list[str] = []
        if not answer or not answer.strip():
            issues.append("empty answer")
        if len(answer or "") < 2:
            issues.append("answer too short")
        return ValidationResult(valid=len(issues) == 0, issues=issues)
