"""Tiny JSON-backed state helper used by the Cyclone REST router."""

from __future__ import annotations

import json
import os

from .config import _load_json, _save_json


class StateStore:
    """Load/save the Cyclone persisted brain state (JSON)."""

    def __init__(self, path):
        self.path = path

    @classmethod
    def load(cls, path):
        payload = _load_json(path, {})
        if not isinstance(payload, dict):
            payload = {}
        return cls(path)._coerce(payload)

    def _coerce(self, payload):
        payload.setdefault("version", 1)
        payload.setdefault("created", "")
        payload.setdefault("memories", [])
        payload.setdefault("history", {})
        return payload

    def save(self):
        _save_json(self.path, self._coerce(self._load()))
        return self._load()

    def _load(self):
        payload = _load_json(self.path, {})
        return self._coerce(payload) if isinstance(payload, dict) else {}
