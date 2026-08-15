"""Tests for the HuggingFace deploy tool (find / compare / deploy-with-gating).

The `hf` CLI and huggingface_hub are NOT installed in this sandbox, and deploying
an Inference Endpoint is BILLABLE. So we verify the tool's real logic with a
monkeypatched CLI runner: no network, no money, no fabrication.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.tools.huggingface_deploy import HuggingFaceDeployTool


def _tool_with_fake_cli(monkeypatch, cli_behavior):
    """Patch the internal _run so 'hf' appears installed and behaves as scripted."""
    monkeypatch.setattr("app.tools.huggingface_deploy._hf_cli", lambda: "/usr/bin/hf")
    monkeypatch.setattr(
        "app.tools.huggingface_deploy._run",
        lambda cmd, timeout=120: cli_behavior(cmd),
    )
    return HuggingFaceDeployTool()


def test_oauth_client_config_filled_from_website():
    t = HuggingFaceDeployTool()
    # Default settings have no website -> not configured
    cfg = t.oauth_client_config()
    assert cfg["configured"] is False
    # With a website set, payload mirrors the provided registration shape
    from app.config.settings import get_settings
    s = get_settings()
    saved = s.hf_oauth_website
    s.hf_oauth_website = "https://moon.example.com"
    try:
        cfg = t.oauth_client_config()
        assert cfg["configured"] is True
        assert cfg["client_id"] == "https://moon.example.com/.well-known/oauth-cimd"
        assert cfg["redirect_uris"] == ["https://moon.example.com/oauth/callback/huggingface"]
        assert cfg["token_endpoint_auth_method"] == "none"
        assert cfg["client_uri"] == "https://moon.example.com"
    finally:
        s.hf_oauth_website = saved


def test_compare_ranks_by_popularity():
    t = HuggingFaceDeployTool()
    cands = [
        {"id": "a/weak", "downloads": 10, "likes": 0},
        {"id": "b/pop", "downloads": 5000, "likes": 20},
        {"id": "c/mid", "downloads": 1000, "likes": 5},
    ]
    ranked = asyncio.run(t.compare(cands))
    assert [c["id"] for c in ranked] == ["b/pop", "c/mid", "a/weak"]


def test_deploy_requires_confirmation(monkeypatch):
    t = _tool_with_fake_cli(monkeypatch, lambda cmd: (0, "created", ""))
    res = asyncio.run(t.deploy("meta-llama/Llama-3.1-8B-Instruct", confirm=False))
    assert res["deployed"] is False
    assert res["reason"] == "confirmation required"
    assert "hf" in res["would_run"][0]


def test_deploy_runs_and_verifies_when_confirmed(monkeypatch):
    calls = []

    def _fake_run(cmd, timeout=120):
        calls.append(cmd)
        # create -> success; status -> running
        if "create" in cmd:
            return (0, "endpoint created", "")
        return (0, "status: running", "")

    t = _tool_with_fake_cli(monkeypatch, _fake_run)
    res = asyncio.run(t.deploy("meta-llama/Llama-3.1-8B-Instruct", hardware="cpu-small", confirm=True))
    assert res["deployed"] is True
    assert res["namespace"] == "crsuvo"
    assert res["endpoint"] == "crsuvo/llama-3-1-8b-instruct"
    # Both create and status were invoked
    assert any("create" in c for c in calls)
    assert any("status" in c for c in calls)


def test_deploy_failure_reported_not_faked(monkeypatch):
    def _fake_run(cmd, timeout=120):
        if "create" in cmd:
            return (1, "", "quota exceeded")
        return (1, "", "not found")

    t = _tool_with_fake_cli(monkeypatch, _fake_run)
    res = asyncio.run(t.deploy("x/y", confirm=True))
    assert res["deployed"] is False
    assert "quota exceeded" in res["error"]
