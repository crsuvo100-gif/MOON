"""Generic HTTP API requests tool."""

from __future__ import annotations

import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ApiRequestsTool(BaseTool):
    name = "api_requests"
    description = "Make an HTTP request to an external API."

    async def execute(self, method: str = "GET", url: str = "", **kwargs: Any) -> str:
        if not url:
            return "[no url]"
        try:
            # Egress permission check via connector permission manager
            try:
                from app.connector.permission import ConnectorPermissionManager
                from urllib.parse import urlparse
                host = urlparse(url).hostname or ""
                perm = ConnectorPermissionManager()
                decision = perm.egress_decision(host, "network.egress")
                if not decision.allowed and decision.tier.name == "NEVER":
                    return f"[api error: egress to '{host}' blocked: {decision.reason}]"
            except Exception:
                pass  # permission check failed — fall through to direct request
            import requests

            resp = requests.request(method or "GET", url, timeout=15)
            return f"[{resp.status_code}] {resp.text[:1500]}"
        except Exception as exc:  # noqa: BLE001
            return f"[api error: {exc}]"
