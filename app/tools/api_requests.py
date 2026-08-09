"""Generic HTTP API requests tool."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ApiRequestsTool(BaseTool):
    name = "api_requests"
    description = "Make an HTTP request to an external API."

    async def execute(self, method: str = "GET", url: str = "", **kwargs: Any) -> str:
        if not url:
            return "[no url]"
        try:
            import requests

            resp = requests.request(method or "GET", url, timeout=15)
            return f"[{resp.status_code}] {resp.text[:1500]}"
        except Exception as exc:  # noqa: BLE001
            return f"[api error: {exc}]"
