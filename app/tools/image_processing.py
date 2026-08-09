"""Image processing tool (optional; requires Pillow)."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ImageProcessingTool(BaseTool):
    name = "image_processing"
    description = "Basic image transforms (resize/convert) via Pillow."

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    async def execute(self, path: str = "", action: str = "info", **kwargs: Any) -> str:
        if not self._enabled:
            return "[image processing disabled]"
        try:
            from PIL import Image

            img = Image.open(path)
            if action == "info":
                return f"size={img.size} mode={img.mode}"
            if action == "resize":
                w = int(kwargs.get("width", 256))
                img = img.resize((w, int(w * img.height / img.width)))
                out = path + ".resized.png"
                img.save(out)
                return out
            return "[unknown action]"
        except Exception as exc:  # noqa: BLE001
            return f"[image error: {exc}]"
