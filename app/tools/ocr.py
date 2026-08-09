"""OCR tool (optional; requires pytesseract + tesseract)."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class OcrTool(BaseTool):
    name = "ocr"
    description = "Extract text from an image via OCR."

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    async def execute(self, path: str = "", **kwargs: Any) -> str:
        if not self._enabled:
            return "[ocr disabled]"
        try:
            from PIL import Image
            import pytesseract

            return pytesseract.image_to_string(Image.open(path))[:2000]
        except Exception as exc:  # noqa: BLE001
            return f"[ocr error: {exc}]"
