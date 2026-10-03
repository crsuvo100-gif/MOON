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

pytestmark = pytest.mark.live  # requires a live model backend (Ollama)

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
    o._llm_fallback2 = None
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
    o._llm_fallback2 = None
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
    o._llm_fallback2 = None
    o._settings.openai_model = "gpt-4o-mini"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "local-answer"
    assert calls["fb"] == 0


@pytest.mark.asyncio
async def test_fallback_chain_local_openai_openrouter():
    """When local AND OpenAI fail, the secondary OpenRouter backend is used."""
    o = Orchestrator(get_settings())
    o._llm = _fake_llm(raises=True)
    o._llm_fallback = _fake_llm(raises=True)  # OpenAI also down
    o._llm_fallback2 = _fake_llm(
        returns=CompletionResult(content="from-openrouter", has_tool_calls=False, tool_calls=[])
    )
    o._settings.openai_model = "gpt-4o-mini"
    o._settings.openrouter_model = "openai/gpt-4o-mini"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "from-openrouter"


@pytest.mark.asyncio
async def test_openrouter_used_when_local_empty_and_openai_empty():
    """OpenRouter is the last resort when local+OpenAI return empty content."""
    o = Orchestrator(get_settings())
    o._llm = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback2 = _fake_llm(
        returns=CompletionResult(content="routed-to-openrouter", has_tool_calls=False, tool_calls=[])
    )
    o._settings.openrouter_model = "openai/gpt-4o-mini"
    res = await o._complete_with_fallback("plain prompt")
    assert (res.content or "").strip() == "routed-to-openrouter"


@pytest.mark.asyncio
async def test_openai_preferred_over_openrouter():
    """When OpenAI succeeds, OpenRouter must NOT be called."""
    calls = {"or": 0}

    async def _or_complete(*a, **k):
        calls["or"] += 1
        return CompletionResult(content="should-not-be-used", has_tool_calls=False, tool_calls=[])

    o = Orchestrator(get_settings())
    o._llm = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback = _fake_llm(
        returns=CompletionResult(content="openai-answer", has_tool_calls=False, tool_calls=[])
    )
    o._llm_fallback2 = SimpleNamespace(complete=_or_complete)
    o._settings.openai_model = "gpt-4o-mini"
    o._settings.openrouter_model = "openai/gpt-4o-mini"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "openai-answer"
    assert calls["or"] == 0


@pytest.mark.asyncio
async def test_huggingface_used_when_all_prior_fail():
    """HuggingFace (tertiary) is used when local+OpenAI+OpenRouter all fail."""
    o = Orchestrator(get_settings())
    o._llm = _fake_llm(raises=True)
    o._llm_fallback = _fake_llm(raises=True)
    o._llm_fallback2 = _fake_llm(raises=True)
    o._llm_fallback3 = _fake_llm(
        returns=CompletionResult(content="from-huggingface", has_tool_calls=False, tool_calls=[])
    )
    o._settings.huggingface_model = "meta-llama/Llama-3.1-8B-Instruct"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "from-huggingface"


@pytest.mark.asyncio
async def test_openrouter_preferred_over_huggingface():
    """When OpenRouter succeeds, HuggingFace must NOT be called."""
    calls = {"hf": 0}

    async def _hf_complete(*a, **k):
        calls["hf"] += 1
        return CompletionResult(content="should-not-be-used", has_tool_calls=False, tool_calls=[])

    o = Orchestrator(get_settings())
    o._llm = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback = _fake_llm(returns=CompletionResult(content="", has_tool_calls=False, tool_calls=[]))
    o._llm_fallback2 = _fake_llm(
        returns=CompletionResult(content="openrouter-answer", has_tool_calls=False, tool_calls=[])
    )
    o._llm_fallback3 = SimpleNamespace(complete=_hf_complete)
    o._settings.openrouter_model = "openai/gpt-4o-mini"
    o._settings.huggingface_model = "meta-llama/Llama-3.1-8B-Instruct"
    res = await o._complete_with_fallback([{"role": "user", "content": "hi"}])
    assert (res.content or "").strip() == "openrouter-answer"
    assert calls["hf"] == 0

