"""LLM service -- OpenAI-compatible chat client for a LOCAL model endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class CompletionResult:
    content: str | None
    has_tool_calls: bool
    tool_calls: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = []


class LLMService:
    """Thin async client over an OpenAI-compatible /v1/chat/completions API."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        api_key: str = "not-required",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        disable_thinking: bool | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model_name
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        # qwen3 / deepseek / glm-style "thinking" models spend their entire
        # token budget on hidden <reasoning> and emit NO usable content unless
        # thinking is disabled. On CPU-only local endpoints this also wastes
        # minutes. Default: disable thinking for known thinking-model families.
        if disable_thinking is None:
            disable_thinking = any(
                tok in model_name.lower()
                for tok in ("qwen3", "qwq", "deepseek-r1", "glm-z1", "thinking")
            )
        self._disable_thinking = disable_thinking
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def setup(self) -> None:
        # Nothing to pre-connect for httpx; placeholder for symmetry.
        return

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
        }
        # qwen3 / thinking models: disable hidden reasoning so the model emits
        # real assistant content instead of consuming the whole budget on
        # <reasoning>. Harmless for endpoints that ignore unknown keys.
        if self._disable_thinking:
            payload["think"] = False
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = await self._client.post(
                "/chat/completions", json=payload,
                timeout=min(45.0, self._timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]
            content = choice.get("content")
            raw_calls = choice.get("tool_calls") or []
            tool_calls = []
            for tc in raw_calls:
                fn = tc.get("function", {})
                tool_calls.append({"name": fn.get("name"), "arguments": fn.get("arguments", "{}")})
            return CompletionResult(
                content=content,
                has_tool_calls=bool(tool_calls),
                tool_calls=tool_calls,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM complete failed: %s", exc)
            return CompletionResult(content=None, has_tool_calls=False, tool_calls=[])

    async def teardown(self) -> None:
        await self._client.aclose()
