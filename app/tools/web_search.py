"""Web search tool (best-effort; uses duckduckgo html if requests available)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for a query and return snippets."

    async def execute(self, query: str = "", **kwargs: Any) -> str:
        try:
            import requests

            resp = requests.get(
                "https://html.duckduckgo.com/html/", params={"q": query}, timeout=10, headers={"User-Agent": "moon"}
            )
            snippets = re.findall(r"result__snippet[^>]*>(.*?)</a>", resp.text, re.DOTALL)
            text = " | ".join(s[:200] for s in snippets[:5])
            return text or f"No direct results for: {query}"
        except Exception as exc:  # noqa: BLE001
            return f"[web_search unavailable: {exc}]"
