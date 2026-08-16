"""Pytest configuration for MOON.

Provides a `live` marker + session guard: tests that require a running model
backend (Ollama / live Orchestrator) are automatically SKIPPED when the backend
is unreachable, so CI on GitHub (no Ollama, no GPU) stays green and honest --
the skip reason clearly states WHY, and the offline-safe suite still runs.

Local dev with Ollama up: every test (including live ones) runs normally.
Force a dry run of the offline path with:  OLLAMA_HOST=127.0.0.1:9 pytest
"""
from __future__ import annotations

import os
import urllib.request

import pytest


def _ollama_reachable() -> bool:
    host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
    # Allow forcing offline for CI / dry-runs.
    if os.environ.get("MOON_OFFLINE") in ("1", "true", "yes"):
        return False
    url = f"http://{host}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


# Register the marker so pytest doesn't warn about it.
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: test requires a live model backend (Ollama); auto-skipped when unreachable.",
    )


# Session-wide reachability (computed once).
_OLLAMA_UP = _ollama_reachable()


def pytest_collection_modifyitems(config, items):
    if _OLLAMA_UP:
        return
    skip = pytest.mark.skip(
        reason="live model backend (Ollama) not reachable -> skipping live test "
               "(set OLLAMA_HOST / start Ollama to run; CI runs offline-safe suite)."
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
