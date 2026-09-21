"""
WebSearchTool — example tool: searches DuckDuckGo HTML and extracts snippets.
"""
from __future__ import annotations

import re
from typing import Any

import requests

from app.tools.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for a query and return top result snippets."

    async def execute(self, query: str = "", **kwargs: Any) -> str:
        if not query:
            return "[web_search] empty query"
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                timeout=10,
                headers={"User-Agent": "moontm"},
            )
            resp.raise_for_status()
            html = resp.text
            snippets = re.findall(r'result__snippet.*?>(.*?)<', html, re.S)
            cleaned = []
            for s in snippets[:5]:
                s = re.sub(r"<[^>]+>", "", s).strip()
                if s:
                    cleaned.append(s)
            if not cleaned:
                return f"[web_search] no results for: {query}"
            return "\n---\n".join(cleaned)
        except Exception as exc:
            return f"[web_search unavailable: {exc}]"
