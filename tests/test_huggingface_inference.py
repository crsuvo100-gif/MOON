"""Tests for HuggingFace inference (chat + text_to_image) via mocked InferenceClient.

huggingface_hub is NOT installed in this sandbox and uses network + a token. So we
verify the service/tool logic by monkeypatching:
  * `app.services.hf_inference._inference_client_available` -> True
  * `app.services.hf_inference.HuggingFaceInference.chat/text_to_image` generally
    call `huggingface_hub.InferenceClient`; we patch that constructor to a fake.
No network, no token, no fabrication.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import app.services.hf_inference as hfi
from app.services.hf_inference import HuggingFaceInference
from app.tools.huggingface_tool import HuggingFaceTool


class _FakeCompletion:
    def __init__(self, content="How many Gs? Three."):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]

    def model_dump(self):
        return {"choices": [{"message": {"content": "How many Gs? Three."}}]}


class _FakeImage:
    def save(self, path):
        self.saved = path


class _FakeClient:
    def __init__(self, api_key=None, **kw):
        self.api_key = api_key
        self.calls = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: self._chat(**kwargs))
        )

    def _chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        return _FakeCompletion()

    def text_to_image(self, prompt, model):
        self.calls.append(("image", prompt, model))
        return _FakeImage()


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(hfi, "_inference_client_available", lambda: True)
    captured = {}

    def _fake_ctor(api_key=None, **kw):
        captured["client"] = _FakeClient(api_key=api_key, **kw)
        return captured["client"]

    import sys
    import types
    fake_mod = types.ModuleType("huggingface_hub")
    setattr(fake_mod, "InferenceClient", _fake_ctor)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_mod)

    # Also fake settings so HuggingFaceTool reads a non-empty api_key
    # (the real .env has HUGGINGFACE_API_KEY= empty). The tool creates a
    # HuggingFaceInference which reads get_settings from this module, so
    # patch it at the point of use. Keeps the test honest (client still
    # mocked, no network) while satisfying the api_key guard.
    from app.config.settings import Settings
    fake_settings = Settings()
    monkeypatch.setattr(fake_settings, "huggingface_api_key", "hf_test_dummy_key")
    monkeypatch.setattr(hfi, "get_settings", lambda: fake_settings)

    return captured


def test_chat_returns_content(patched):
    svc = HuggingFaceInference(api_key="hf_test")
    res = asyncio.run(svc.chat([{"role": "user", "content": "Hi"}]))
    assert res["choices"][0]["message"]["content"] == "How many Gs? Three."
    assert patched["client"].calls[0][0] == "chat"


def test_chat_passes_provider_when_given(patched):
    svc = HuggingFaceInference(api_key="hf_test")
    asyncio.run(svc.chat([{"role": "user", "content": "Hi"}], model="deepseek-ai/DeepSeek-R1", provider="novita"))
    _, kwargs = patched["client"].calls[0]
    assert kwargs["provider"] == "novita"
    assert kwargs["model"] == "deepseek-ai/DeepSeek-R1"


def test_chat_raises_without_token(monkeypatch):
    monkeypatch.setattr(hfi, "_inference_client_available", lambda: True)
    # Force settings to report no key so the token check actually fires.
    fake_settings = SimpleNamespace(huggingface_api_key="", huggingface_base_url="https://router.huggingface.co")
    monkeypatch.setattr(hfi, "get_settings", lambda: fake_settings)
    svc = HuggingFaceInference(api_key="")
    with pytest.raises(RuntimeError):
        asyncio.run(svc.chat([{"role": "user", "content": "Hi"}]))


def test_text_to_image_saves(patched, tmp_path):
    svc = HuggingFaceInference(api_key="hf_test")
    out = tmp_path / "img.png"
    res = asyncio.run(svc.text_to_image("a serene lake", model="black-forest-labs/FLUX.1-dev", output_path=str(out)))
    assert res["ok"] is True
    assert res["path"] == str(out)
    assert patched["client"].calls[0][0] == "image"


def test_tool_chat_action(patched):
    t = HuggingFaceTool()
    out = asyncio.run(t.execute("chat", messages=[{"role": "user", "content": "How many G in huggingface?"}]))
    assert "How many Gs? Three." in out


def test_tool_text_to_image_action(patched, tmp_path):
    t = HuggingFaceTool()
    out = asyncio.run(t.execute("text_to_image", prompt="a cat", output_path=str(tmp_path / "c.png")))
    assert '"ok": true' in out.lower() or '"ok": True' in out


def test_unavailable_package_reports_cleanly(monkeypatch):
    monkeypatch.setattr(hfi, "_inference_client_available", lambda: False)
    svc = HuggingFaceInference(api_key="hf_test")
    assert svc.available is False
    with pytest.raises(RuntimeError):
        asyncio.run(svc.chat([{"role": "user", "content": "x"}]))
