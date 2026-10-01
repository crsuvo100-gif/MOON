"""CapabilityManagerTool -- exposes the Capability Manager to MOON's tool layer.

This is the agent-facing tool. It EXTENDS (not replaces) MOON's existing
tool-calling surface. Logical operations (per spec section 16):
  discover_capabilities, inspect_capability, search_github, inspect_repository,
  analyze_dependencies, install_capability, verify_capability,
  execute_capability, repair_capability, list_capabilities, health_check_capability.

All calls are routed through the CapabilityManager, which enforces the
acquisition priority and the safety/permission policy.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class CapabilityManagerTool(BaseTool):
    name = "capability_manager"
    description = (
        "MOON's autonomous capability system. Discover, acquire, verify, and "
        "manage tools/libraries/runtimes needed for a task (reusing existing "
        "capabilities first, then safe install). Actions: "
        "discover, list, health, search_github, install, verify, inspect."
    )

    def __init__(self, manager: Any | None = None) -> None:
        # Lazy singleton manager so it can be shared across calls.
        self._manager = manager

    @property
    def manager(self):
        if self._manager is None:
            from app.capability.manager import CapabilityManager
            self._manager = CapabilityManager()
        return self._manager

    async def execute(self, action: str = "list", task: str = "", name: str = "",
                      query: str = "", **kwargs: Any) -> str:
        try:
            mgr = self.manager
            a = (action or "list").lower()
            if a == "discover":
                caps = mgr.discover(task or name)
                return ("REQUIRED CAPABILITIES:\n" +
                        "\n".join(f"- {c}: {mgr.status(c)}" for c in caps) +
                        ("\n(none inferred)" if not caps else ""))
            if a in ("list", "list_capabilities"):
                caps = mgr.list_capabilities()
                if not caps:
                    return "[capabilities] registry empty -- no acquired capabilities yet."
                return "REGISTERED CAPABILITIES:\n" + "\n".join(
                    f"- {c['name']} [{c['status']}/{c['health']}] src={c['source']}"
                    for c in caps)
            if a in ("health", "health_check"):
                rep = mgr.health_report()
                return "CAPABILITY HEALTH:\n" + "\n".join(
                    f"- {h['name']}: {h['status']} ({h['health']})" for h in rep) or \
                    "[capabilities] none registered"
            if a == "search_github":
                q = query or task or name
                cands = mgr.search_github(q)
                if not cands:
                    return f"[github] no candidates for '{q}' (or search unavailable)"
                return "GITHUB CANDIDATES:\n" + "\n".join(
                    f"- {c['full_name']} stars={c.get('stars',0)} "
                    f"trust={c.get('trust_score',0)} flags={list(c.get('flags',[]))}"
                    for c in cands)
            if a in ("install", "install_capability"):
                if not name:
                    return "[capability_manager] install needs 'name='"
                res = await mgr.acquire(name)
                return self._report(res)
            if a in ("verify", "verify_capability"):
                st = mgr.status(name)
                return f"[capability_manager] {name}: {st}"
            if a == "inspect":
                st = mgr.status(name)
                rec = mgr.registry.get(name)
                return (f"[capability_manager] {name}: {st}\n"
                        f"{json.dumps(rec.to_dict(), indent=2) if rec else '(not in registry)'}")
            return ("[capability_manager] unknown action. Use one of: "
                    "discover, list, health, search_github, install, verify, inspect")
        except Exception as exc:  # noqa: BLE001
            return f"[capability_manager] error: {exc}"

    @staticmethod
    def _report(res) -> str:
        return (
            f"=== Capability Acquisition ===\n"
            f"Name   : {res.name}\n"
            f"Status : {res.status}\n"
            f"Source : {res.source}\n"
            f"Detail : {res.detail}\n"
        )
