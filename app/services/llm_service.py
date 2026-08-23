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
    reasoning: str | None = None  # thinking-model trace (real brain state)

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
        # Thinking models (qwen3 / deepseek-r1 / glm-z1 / ...): KEEP thinking
        # ENABLED for better reasoning + answer quality (per operator preference:
        # "make it thinking capability for better perform"). We surface the
        # reasoning trace separately so the UI can stream the real brain state,
        # and we keep enough token budget for the final answer to appear in
        # `content` (otherwise the model spends the whole budget on <reasoning>
        # and emits an empty answer).
        if disable_thinking is None:
            disable_thinking = False
        self._disable_thinking = disable_thinking
        # Generous floor for local-first models: qwen3:0.6b on CPU routinely
        # takes 35-120s per call, and a COLD first call after backend start can
        # exceed even 120s (Ollama model load). A tight timeout here silently
        # raised httpx.ReadTimeout -> empty content -> fake-success/fallback.
        # Use the configured timeout but never below 300s for reliability.
        _client_timeout = max(float(timeout), 300.0)
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_client_timeout,
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
        eff_max = max_tokens if max_tokens is not None else self._max_tokens
        # Thinking models (qwen3 / deepseek-r1 / glm-z1) spend part of the token
        # budget "thinking" before emitting the final answer in `content`. A small
        # cap (e.g. 50-200) gets exhausted by reasoning and leaves `content` empty
        # (finish_reason: length). To keep thinking ON for quality yet still get a
        # real answer, ensure thinking models have enough headroom.
        if not self._disable_thinking and eff_max < 1024:
            eff_max = 1024
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else self._temperature,
            "max_tokens": eff_max,
        }
        # qwen3 / deepseek-r1 / glm-z1 style "thinking" models: keep thinking
        # ON for better performance (operator preference). The correct key is
        # `enable_thinking`; Ollama/qwen3 ignores unknown `think` keys.
        if self._disable_thinking:
            payload["enable_thinking"] = False
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            # Per-request timeout must match the client floor: local-first models
            # (qwen3:0.6b on CPU) routinely need 35-120s, and a COLD first call
            # after backend start can exceed 120s. A tight timeout here raises
            # httpx.ReadTimeout -> empty content -> fake-success. Never below 300s.
            _req_timeout = max(float(self._timeout), 300.0)
            resp = await self._client.post(
                "/chat/completions", json=payload,
                timeout=_req_timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]
            content = choice.get("content")
            reasoning = choice.get("reasoning") or choice.get("reasoning_content")
            # Thinking models may leave `content` empty and place the answer in the
            # reasoning trace. Extract the REAL final answer from reasoning rather
            # than just the last line (which is mid-thought). Heuristic: the answer
            # usually follows a closing thought or is the most substantive trailing
            # sentence. Never return None (nil content would break later chat calls).
            if not content and reasoning:
                content = _extract_answer_from_reasoning(reasoning)
            if content is None:
                content = ""
            raw_calls = choice.get("tool_calls") or []
            tool_calls = []
            for tc in raw_calls:
                fn = tc.get("function", {})
                tool_calls.append({"name": fn.get("name"), "arguments": fn.get("arguments", "{}")})
            return CompletionResult(
                content=content,
                has_tool_calls=bool(tool_calls),
                tool_calls=tool_calls,
                reasoning=reasoning,
            )
        except Exception as exc:  # noqa: BLE001
            # Classify the failure so a rate-limited / unauthorized cloud key
            # fails CLEANLY and is never retried in a tight loop (Phase 23/25):
            # 401/403 = auth/quota hard-fail -> circuit-break this service.
            # 429 = rate-limited -> same treatment (retrying only wastes quota).
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403, 429):
                self._disabled = True
                logger.info(
                    "LLM %s@%s unavailable (HTTP %s) — disabling this backend; "
                    "local-first path continues.",
                    self._model, self._base, status,
                )
            else:
                logger.warning("LLM complete failed [%s]: %s", type(exc).__name__, exc)
            return CompletionResult(content=None, has_tool_calls=False, tool_calls=[])


def _extract_answer_from_reasoning(reasoning: str) -> str:
    """Pull the final, substantive answer out of a thinking-model trace.

    qwen3/deepseek-r1 emit reasoning in `reasoning` and the answer at the end.
    We skip the preamble and return the most answer-like trailing text.
    """
    import re as _re
    txt = reasoning.strip()
    if not txt:
        return ""
    # Strip common XML-ish thinking wrappers if present.
    txt = _re.sub(r"</?think>", "", txt, flags=_re.IGNORECASE).strip()
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    if not lines:
        return txt
    # The answer is typically the longest / last confident statement. Prefer the
    # final non-boilerplate line; if it looks like a question echo, back up.
    for l in reversed(lines):
        low = l.lower()
        if low.startswith(("okay,", "so i", "let me", "hmm", "wait,", "i need to", "first,")):
            continue
        return l
    return lines[-1]

    async def teardown(self) -> None:
        await self._client.aclose()
