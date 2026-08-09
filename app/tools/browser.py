"""Browser automation tool (optional; requires playwright)."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    name = "browser"
    description = "Open a URL and extract readable text (requires playwright)."

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    async def execute(self, url: str = "", **kwargs: Any) -> str:
        if not self._enabled:
            return "[browser disabled]"
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(url or "about:blank")
                text = await page.inner_text("body")
                await browser.close()
                return (text or "")[:2000]
        except Exception as exc:  # noqa: BLE001
            return f"[browser error: {exc}]"
