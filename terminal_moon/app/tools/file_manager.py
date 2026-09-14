"""
FileManagerTool — read/write files within an allowed root.
"""
from __future__ import annotations

import os
from typing import Any

from app.tools.base import BaseTool


class FileManagerTool(BaseTool):
    name = "file_manager"
    description = "Read or write files inside an allowed root directory."

    def __init__(self, allowed_root: str = "") -> None:
        super().__init__()
        self._root = os.path.abspath(allowed_root) if allowed_root else os.getcwd()

    async def execute(self, action: str = "", path: str = "", content: str = "", **kwargs: Any) -> str:
        if not action:
            return "[file_manager] no action (read/write)"

        if not path:
            return "[file_manager] no path"

        # forbid traversal
        if ".." in path or path.startswith("/") or path.startswith("~"):
            return "[file_manager] path traversal not allowed"

        full = os.path.normpath(os.path.join(self._root, path))
        if not full.startswith(self._root):
            return "[file_manager] path outside allowed root"

        if action == "read":
            if not os.path.isfile(full):
                return f"[file_manager] file not found: {path}"
            try:
                with open(full, "r", errors="replace") as f:
                    return f.read(40000)
            except Exception as e:
                return f"[file_manager] read error: {e}"

        elif action == "write":
            try:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content or "")
                return f"[file_manager] wrote {len(content or '')} bytes to {path}"
            except Exception as e:
                return f"[file_manager] write error: {e}"

        return f"[file_manager] unknown action: {action}"
