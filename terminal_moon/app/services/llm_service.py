"""
LLM service — OpenAI-compatible async client with multi-tier fallback chain.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("moontm.llm")


CYBER_CRITICAL_KEYWORDS = (
    "exploit", "vuln", "cve", "scan", "red team", "offensive", "pentest",
    "malware", "forensic", "reverse", "recon", "payload", "attack",
    "privilege escalation", "lateral movement", "crack", "hack", "bindshell",
    "reverse shell", "rootkit", "exfiltration", "ransomware", "botnet",
    "vulnerability", "exploitation", "pivoting", "zero-day",
)


@dataclass
class ChatMessage:
    role: str       # "user" | "assistant" | "tool" | "system"
    content: str


@dataclass
class CompletionResult:
    content: Optional[str]
    has_tool_calls: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    reasoning: Optional[str] = None


class LLMService:
    """Thin async client over an OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str = "not-required",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        disable_thinking: Optional[bool] = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model_name
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._disable_thinking = disable_thinking
        self._client: Optional[httpx.AsyncClient] = None
        self._disabled: bool = False

    async def setup(self) -> None:
        headers: dict[str, str] = {"Authorization": f"Bearer {self._api_key}"}
        if self._api_key == "not-required":
            headers = {}
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=headers,
            timeout=max(self._timeout, 150.0),
        )

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: Optional[list[dict]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> CompletionResult:
        if self._disabled:
            return CompletionResult(content="")

        if not self._client:
            await self.setup()

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }

        if self._disable_thinking is False:
            payload["enable_thinking"] = True
            payload["thinking_budget"] = 600

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            resp = await self._client.post(
                "/chat/completions",
                json=payload,
                timeout=max(self._timeout, 150.0),
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]

            content = choice.get("content")
            reasoning = choice.get("reasoning") or choice.get("reasoning_content")
            tool_calls = choice.get("tool_calls", [])

            if content is None and reasoning:
                content = self._extract_answer_from_reasoning(reasoning)

            if content is None:
                content = ""

            return CompletionResult(
                content=content or "",
                has_tool_calls=bool(tool_calls),
                tool_calls=tool_calls,
                reasoning=reasoning,
            )

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403, 429):
                logger.warning("LLM backend %s disabled after %s", self._base, code)
                self._disabled = True
                return CompletionResult(content="")
            logger.warning("LLM HTTP error %s: %s", code, exc)
            return CompletionResult(content="")

        except httpx.TimeoutException:
            logger.warning("LLM timeout on %s", self._base)
            return CompletionResult(content="")

        except Exception as exc:
            logger.warning("LLM error on %s: %s", self._base, exc)
            return CompletionResult(content="")

    @staticmethod
    def _extract_answer_from_reasoning(reasoning: str) -> str:
        """Strip <think> wrappers and pick the last substantive line."""
        text = reasoning
        for tag in ("<think>", "</think>", "<thinking>", "</thinking>"):
            text = text.replace(tag, "")
        text = text.strip()

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for line in reversed(lines):
            low = line.lower()
            if low.startswith("here") or low.startswith("so"):
                continue
            if len(line) > 10:
                return line
        return lines[-1] if lines else ""

    async def teardown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class FallbackChain:
    """Tries providers in order until one returns non-empty content."""

    def __init__(self, providers: list[LLMService], default_model: str) -> None:
        self._providers = providers
        self._default_model = default_model
        self._lock = asyncio.Lock()

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: Optional[list[dict]] = None,
    ) -> CompletionResult:
        if not self._providers:
            return CompletionResult(content="")
        for p in self._providers:
            if p._disabled:
                continue
            result = await p.complete(messages, tools=tools)
            if result.content:
                return result
        return CompletionResult(content="")
