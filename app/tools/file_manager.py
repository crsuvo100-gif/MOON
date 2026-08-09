"""File manager tool (read/write/list within an allowed root)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FileManagerTool(BaseTool):
    name = "file_manager"
    description = "Read, write, or list files within the allowed root."

    def __init__(self, allowed_root: str = ".") -> None:
        self._root = Path(allowed_root).resolve()

    def _safe(self, path: str) -> Path:
        p = (self._root / path).resolve()
        if self._root not in p.parents and p != self._root:
            raise ValueError("path escapes allowed root")
        return p

    async def execute(self, action: str = "read", path: str = "", content: str = "", **kwargs: Any) -> str:
        try:
            p = self._safe(path)
            if action == "read":
                return p.read_text(errors="replace")[:4000]
            if action == "write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content or "")
                return f"wrote {path}"
            if action == "list":
                return "\n".join(os.listdir(str(p)))
            return "[unknown action]"
        except Exception as exc:  # noqa: BLE001
            return f"[file_manager error: {exc}]"
