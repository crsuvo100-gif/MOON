"""CYCLONE_TERMINAL_AI_V10 runtime configuration (local, no secrets)."""

from __future__ import annotations

import json
import os

# Repo layout: cyclone/ lives directly inside CYCLONE_TERMINAL_AI_V10/.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CYCLONE_ROOT = os.path.abspath(os.environ.get("CYCLONE_ROOT", REPO_ROOT))
CYCLONE_DIR = os.path.join(CYCLONE_ROOT, "CYCLONE_TERMINAL_AI_V10")
DATA_DIR = os.path.join(CYCLONE_DIR, ".data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
SNAPSHOTS_DIR = os.path.join(DATA_DIR, "snapshots")
PROVIDERS_FILE = os.path.join(DATA_DIR, "providers.json")
BINDINGS_FILE = os.path.join(DATA_DIR, "agent-bindings.json")
WORKFLOWS_FILE = os.path.join(DATA_DIR, "workflows.json")
DEFAULT_PROVIDERS = [
    {"name": "moons-model", "type": "ollama", "base_url": os.environ.get(
        "MOON_OLLAMA_URL", "http://127.0.0.1:11434/v1"),
     "model": os.environ.get("MOON_MODEL", "qwen2.5:1.5b"),
     "default": True},
]
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _save_json(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
