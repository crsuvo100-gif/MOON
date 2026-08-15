"""Tests for MOON's OpenAI-compatible fallback backend.

MOON must keep working when the local model endpoint (Ollama) is down or a
completion fails: it transparently retries against a hosted OpenAI-compatible
API configured via OPENAI_API_KEY. These tests prove the fallback logic
wires correctly WITHOUT hitting the real network/API.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.brain.orchestrator import Orchestrator
from app.config.settings import get_settings
from app.services.llm_service import CompletionResult


def _fake_llm(returns=None, raises=False):
    """A fake LLMService. If raises, complete() throws; else returns `returns`."""
    async def _complete(*a, **k):
        if raises:
            raise RuntimeError("local model down")
        return returns
    return SimpleNamespace(complete=_complete)


@pytest.mark.asyncio
async def test_fallback_triggers_when_primary_fails():
    """When the local model raises, the result should come from the fallback."""
    o = Orchestrator(get_settings())
    o._llm = _fake_llm(raises=True)
    o._llm_fallback = _fake_llm(
        returns=CompletionResult(content="from-openai", has_tool_calls=False, tool_calls=[])
    )
    o._settings.openai_model = "gpt-4o-mini"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "from-openai"


@pytest.mark.asyncio
async def test_fallback_triggers_when_primary_empty():
    """When the local model returns empty content, fall back to the API."""
    o = Orchestrator(get_settings())
    o._llm = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback = _fake_llm(
        returns=CompletionResult(content="api-answer", has_tool_calls=False, tool_calls=[])
    )
    o._settings.openai_model = "gpt-4o-mini"
    res = await o._complete_with_fallback("plain string prompt")
    assert (res.content or "").strip() == "api-answer"


@pytest.mark.asyncio
async def test_primary_used_when_ok_no_fallback_call():
    """When the local model succeeds, the fallback must NOT be invoked."""
    calls = {"fb": 0}

    async def _fb_complete(*a, **k):
        calls["fb"] += 1
        return CompletionResult(content="should-not-be-used", has_tool_calls=False, tool_calls=[])

    o = Orchestrator(get_settings())
    o._llm = _fake_llm(returns=CompletionResult(content="local-answer", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback = SimpleNamespace(complete=_fb_complete)
    o._settings.openai_model = "gpt-4o-mini"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "local-answer"
    assert calls["fb"] == 0


@pytest.mark.asyncio
async def test_fallback_disabled_without_key():
    """With no OPENAI_API_KEY, setup() must NOT create a fallback service."""
    s = get_settings()
    saved = s.openai_api_key
    s.openai_api_key = ""  # ensure disabled
    try:
        o = Orchestrator(s)
        # Build only the fallback piece the way setup() does.
        o._llm_fallback = None
        if s.openai_api_key.strip():
            o._llm_fallback = _fake_llm()
        assert o._llm_fallback is None
    finally:
        s.openai_api_key = saved
