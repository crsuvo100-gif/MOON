"""Global Connector -- MOON can connect to anything, with permission.

ADDITIVE: MOON can now reach OUT to the world -- external services, other AI
agents, MCP/tool servers, and webhooks -- under strict, least-privilege
permission control. This package NEVER replaces existing networking tools
(ApiRequestsTool, github_sync, telegram); it adds a permission-gated, persistent
CONNECTION REGISTRY on top of them so MOON can "connect everything globally."

Permission model (reuses app.capability.permission_manager.PermissionManager):
  - network.egress     -- any outbound internet call (CONFIRMATION by default;
                          SAFE only for hosts in the allowlist)
  - network.agent      -- talk to another AI agent (CONFIRMATION)
  - network.service    -- call an external HTTP/service (CONFIRMATION)
  - network.webhook    -- send outbound webhooks (CONFIRMATION)
  - secrets.read       -- read a stored credential for a connection (NEVER auto)
Outbound connections are always checked; active security ops still go through
app.security.authorization.require_auth. Nothing egresses without a passing gate.
"""

from __future__ import annotations

from app.connector.gateway import ConnectionGateway, ConnectionRecord
from app.connector.connectors import HTTPConnector, AgentConnector, WebSocketConnector, MCPConnector
from app.connector.tool import GlobalConnectorTool
from app.connector.permission import ConnectorPermissionManager

__all__ = [
    "ConnectionGateway",
    "ConnectionRecord",
    "HTTPConnector",
    "AgentConnector",
    "WebSocketConnector",
    "MCPConnector",
    "GlobalConnectorTool",
    "ConnectorPermissionManager",
]
