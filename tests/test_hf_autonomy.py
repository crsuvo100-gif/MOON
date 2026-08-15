"""Tests that MOON can autonomously CHOOSE (discover + acquire) her built-in
Hugging Face capabilities -- the "free / choose yourself" autonomy loop.

No network, no pip install: 'builtin' capabilities resolve as already present and
are verified against the live tool registry.
"""

from __future__ import annotations

import asyncio

from app.capability.manager import CapabilityManager, _BUILTIN_SPECS
from app.capability.installer import InstallationManager
from app.capability.verification import VerificationEngine


def test_hf_specs_registered_as_builtin():
    for key in ("huggingface", "image generation", "text to image", "text-to-image", "hosted model"):
        assert key in _BUILTIN_SPECS, f"missing HF capability spec: {key}"
        assert _BUILTIN_SPECS[key]["method"] == "none"


def test_discover_routes_image_and_hf_tasks():
    mgr = CapabilityManager()
    d1 = mgr.discover("generate an image with hugging face flux")
    assert "hugging face" in d1 or "huggingface" in d1
    assert "image generation" in mgr.discover("create a text-to-image picture of a cat") or \
           "text-to-image" in mgr.discover("create a text-to-image picture of a cat") or \
           "text to image" in mgr.discover("create a text-to-image picture of a cat")
    d3 = mgr.discover("use a hosted model gpt-oss for this task")
    assert "huggingface" in d3 or "hosted model" in d3


def test_installer_none_method_is_noop_success():
    r = InstallationManager().install({"method": "none", "package": ""})
    assert r.ok is True and r.method == "builtin"


def test_verifier_builtin_confirms_hf_tool_present():
    r = VerificationEngine().verify("builtin", "huggingface")
    assert r.ok is True
    r2 = VerificationEngine().verify("builtin", "huggingface_deploy")
    assert r2.ok is True


def test_acquire_builtin_hf_returns_acquired_no_network():
    mgr = CapabilityManager()
    res = asyncio.run(mgr.acquire("huggingface", github_ok=False))
    assert res.status in ("acquired", "cached")
    assert res.source in ("builtin", "registry")
