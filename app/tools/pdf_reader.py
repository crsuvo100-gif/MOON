"""PDF reader tool (optional; requires pypdf)."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class PdfReaderTool(BaseTool):
    name = "pdf_reader"
    description = "Extract text from a PDF file."

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    async def execute(self, path: str = "", **kwargs: Any) -> str:
        if not self._enabled:
            return "[pdf disabled]"
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:10])
            return text[:4000]
        except Exception as exc:  # noqa: BLE001
            return f"[pdf error: {exc}]"
