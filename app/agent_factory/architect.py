"""Agent Factory: Architect (design a new agent's spec before building).

Produces a deterministic AgentSpec (id, name, capabilities, required tools,
permissions, risk) from a CapabilityNeed. The spec is the contract the Builder
and Tester enforce (spec 15: generate implementation + metadata + tests).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agent_factory.capability_analyzer import CapabilityNeed


@dataclass
class AgentSpec:
    agent_id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    risk_level: str = "low"
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id, "name": self.name, "version": self.version,
            "description": self.description, "capabilities": self.capabilities,
            "required_tools": self.required_tools, "permissions": self.permissions,
            "risk_level": self.risk_level, "dependencies": self.dependencies,
        }


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s or "agent"


class AgentArchitect:
    """Designs the agent spec from a capability need (spec: AGENT ARCHITECT)."""

    def design(self, need: CapabilityNeed) -> AgentSpec:
        raw = need.raw or "generic capability"
        agent_id = _slug(raw)[:60] or "custom_agent"
        name = agent_id
        caps = [raw] + need.keywords
        # infer required tools from keywords (best-effort, real mapping)
        tool_map = {
            "python": "python_executor", "code": "python_executor",
            "file": "file_manager", "terminal": "terminal", "shell": "terminal",
            "web": "web_search", "browser": "browser", "github": "git_tool",
            "git": "git_tool", "image": "image_processing", "vision": "image_processing",
            "database": "database", "sql": "database", "api": "api_requests",
            "docker": "docker_tool", "audio": "audio", "pdf": "pdf_reader",
            "ocr": "ocr", "yaml": "file_manager",
        }
        req = []
        for kw in need.keywords:
            for k, t in tool_map.items():
                if k in kw and t not in req:
                    req.append(t)
        perms = ["READ"]
        if req:
            perms.append("EXECUTE")
        risk = "medium" if ("exec" in raw.lower() or "install" in raw.lower()) else "low"
        return AgentSpec(
            agent_id=agent_id, name=name, description=f"Agent for: {raw}",
            capabilities=caps, required_tools=req, permissions=perms, risk_level=risk,
        )


__all__ = ["AgentArchitect", "AgentSpec"]
