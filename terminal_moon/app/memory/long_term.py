"""
Long-term memory — durable jsonl fact store, queryable by keyword/tags.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional


class LongTermMemory:
    """Persists entries to a jsonl file; supports keyword/tags queries."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def setup(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()

    def store(self, content: str, tags: Optional[list[str]] = None, **meta: Any) -> None:
        entry: dict[str, Any] = {"content": content}
        if tags:
            entry["tags"] = tags
        entry.update(meta)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def query(self, keyword: Optional[str] = None, limit: int = 5,
              tags: Optional[list[str]] = None) -> list[dict]:
        if not self._path.exists():
            return []

        results: list[dict] = []
        kw = keyword.lower() if keyword else None
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if kw and kw not in entry.get("content", "").lower():
                        continue
                    if tags:
                        entry_tags = set(entry.get("tags", []))
                        if not entry_tags.intersection(set(tags)):
                            continue

                    results.append(entry)
                    if len(results) >= limit:
                        break
        return results
