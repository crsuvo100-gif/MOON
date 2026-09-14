"""
CapabilityManager — persistent capability registry + discovery + GitHub acquire.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.config.settings import get_settings

logger = logging.getLogger("moontm.capability")


class CapabilityManager:
    """Capability registry with discovery + acquisition (best-effort)."""

    def __init__(self, settings: Optional = None) -> None:
        self._settings = settings or get_settings()
        self._catalog: dict[str, dict] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        cat_path = Path("data") / "capability_catalog.json"
        if cat_path.exists():
            try:
                self._catalog = json.loads(cat_path.read_text(encoding="utf-8"))
            except Exception:
                self._catalog = {}
        # seed defaults
        defaults = {
            "web_search": {"name": "web_search", "provider": "duckduckgo", "status": "available"},
            "terminal": {"name": "terminal", "provider": "local_shell", "status": "available"},
            "file_manager": {"name": "file_manager", "provider": "local_fs", "status": "available"},
            "python_executor": {"name": "python_executor", "provider": "sandbox", "status": "available"},
            "voice": {"name": "voice", "provider": "kokoro/f5/xtts/openai/espeak", "status": "available"},
            "memory": {"name": "memory", "provider": "local", "status": "available"},
            "knowledge": {"name": "knowledge", "provider": "local_vector", "status": "available"},
        }
        for k, v in defaults.items():
            self._catalog.setdefault(k, v)

    def discover(self, prompt: str) -> list[dict]:
        """Discover capabilities needed for a prompt (keyword-based, stub)."""
        low = prompt.lower()
        needed: list[dict] = []
        if any(w in low for w in ("search", "web", "find", "look up", "research")):
            needed.append(self._catalog.get("web_search", {}))
        if any(w in low for w in ("run", "execute", "command", "shell", "terminal")):
            needed.append(self._catalog.get("terminal", {}))
        if any(w in low for w in ("read", "write", "file", "edit")):
            needed.append(self._catalog.get("file_manager", {}))
        if any(w in low for w in ("code", "python", "script", "program")):
            needed.append(self._catalog.get("python_executor", {}))
        if any(w in low for w in ("speak", "voice", "tts", "audio")):
            needed.append(self._catalog.get("voice", {}))
        if any(w in low for w in ("remember", "recall", "memory", "learn")):
            needed.append(self._catalog.get("memory", {}))
        if any(w in low for w in ("knowledge", "kb", "semantic", "index")):
            needed.append(self._catalog.get("knowledge", {}))
        return needed

    def acquire(self, need: dict) -> dict:
        """Best-effort acquisition — returns status."""
        name = need.get("name", "")
        if name in self._catalog:
            self._catalog[name]["status"] = "acquired"
            return {"name": name, "status": "acquired", "detail": "already in catalog"}
        return {"name": name, "status": "not_found", "detail": "not in catalog"}

    def acquire_by_catalog(self, keyword: str) -> Optional[dict]:
        """Match keyword to catalog entry."""
        for name, entry in self._catalog.items():
            if keyword in name or keyword in entry.get("name", ""):
                return self.acquire(entry)
        return None

    def search_github(self, query: str) -> list[dict]:
        """Stub: GitHub search for capability tools."""
        logger.info("CapabilityManager: GitHub search stub for '%s'", query)
        return []

    def feed_for_capability(self, capability: str, repo: Optional[str] = None) -> Optional[dict]:
        """Try to pull a tool from GitHub (stub)."""
        logger.info("CapabilityManager: feed stub for '%s' from %s", capability, repo or "default")
        return None

    def to_dict(self) -> dict:
        return {"capabilities": list(self._catalog.values())}

    def __len__(self) -> int:
        return len(self._catalog)
