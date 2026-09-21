"""Structured Agent Registry (spec sections 7, 8, 12, 39 + MOON 40-agent spec).

This is ADDITIVE: it does NOT replace the existing 39 persona agents in
``app.brain.agent_registry.AGENT_DEFS``. Instead it reads those definitions and
enriches every agent with the structured metadata the spec requires (id,
version, capabilities, required_tools, permissions, risk_level, dependencies,
success_criteria, status) so the runtime can answer:

  "Which agent capability does this task need?"  ->  select from registry.

Generated agents from the Agent Factory are merged in automatically. Built-in
personas get sensible default metadata derived from their existing scope; the
Factory-supplied metadata is used verbatim for generated agents.

The registry is the single source of truth for agent *selection* (spec 12:
capability match, not name-only). The orchestrator's working persona dispatch
is preserved untouched; this registry layers structured metadata on top.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# Default risk/permission profiles per built-in scope so personas get real
# structured metadata without manually authoring all 39.
_SCOPE_PROFILE: dict[str, dict[str, Any]] = {
    "all":      {"risk": "medium", "perms": ["READ", "WRITE", "EXECUTE", "NETWORK"]},
    "research": {"risk": "low",    "perms": ["READ", "NETWORK"]},
    "knowledge": {"risk": "low",   "perms": ["READ"]},
    "writing":  {"risk": "low",    "perms": ["READ", "WRITE"]},
    "none":     {"risk": "low",    "perms": ["READ"]},
    "browser":  {"risk": "low",    "perms": ["READ", "NETWORK"]},
    "vision":   {"risk": "low",    "perms": ["READ"]},
}


@dataclass
class AgentMetadata:
    """Structured per-agent metadata (spec section 8)."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    risk_level: str = "low"  # low|medium|high|critical
    input_schema: str = "text"
    output_schema: str = "text"
    dependencies: list[str] = field(default_factory=list)
    status: str = "active"  # active|disabled|quarantined
    source: str = "builtin"  # builtin|generated|factory|spec40
    role_group: str = ""  # core|advanced (MOON 40-agent spec)
    success_criteria: str = ""
    created_at: str = ""
    updated_at: str = ""
    module_path: str = ""  # for generated agents

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentMetadata":
        known = {f.name for f in cls.__dataclass_fields__.values()} if False else None
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


class AgentRegistry:
    """In-memory + JSON-persisted registry of agent metadata (spec 8/39)."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self._root = Path(data_root or Path("data") / "agents" / "agent_registry")
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._agents: dict[str, AgentMetadata] = {}
        self._load_builtins()
        self._load_persisted()
        self._load_factory_agents()

    # ---- built-ins (reuse existing AGENT_DEFS, non-destructive) ----
    def _load_builtins(self) -> None:
        try:
            from app.brain.agent_registry import AGENT_DEFS
        except Exception:  # noqa: BLE001
            AGENT_DEFS = {}
        for name, (desc, _persona, scope) in AGENT_DEFS.items():
            prof = _SCOPE_PROFILE.get(scope, _SCOPE_PROFILE["all"])
            caps = self._infer_capabilities(name, desc)
            self._agents[name] = AgentMetadata(
                id=name, name=name, description=desc,
                capabilities=caps, required_tools=self._infer_tools(name, scope),
                permissions=list(prof["perms"]), risk_level=prof["risk"],
                input_schema="text", output_schema="text",
                status="active", source="builtin",
                success_criteria=f"produces a correct {name} result with evidence",
            )

    @staticmethod
    def _infer_capabilities(name: str, desc: str) -> list[str]:
        caps = [name.replace("_", " ")]
        extra = {
            "coding": ["write code", "refactor", "debug code"],
            "research": ["web search", "doc reading", "github search"],
            "browser": ["web navigation", "read web page"],
            "debug": ["diagnose failure", "fix bug"],
            "security": ["security audit", "hardening"],
            "cyber": ["authorized recon", "vuln assessment"],
            "github_sync": ["git sync", "safe commit", "push"],
            "vision": ["image analysis"],
            "audio": ["speech to text", "audio analysis"],
            "data_science": ["data analysis", "statistics"],
            "planner": ["task decomposition"],
            "memory": ["knowledge recall", "knowledge index"],
            "qa": ["test design", "quality check"],
            "infra": ["devops", "deployment"],
        }.get(name, [])
        return caps + extra

    @staticmethod
    def _infer_tools(name: str, scope: str) -> list[str]:
        mapping = {
            "research": ["web_search", "browser"],
            "browser": ["browser"],
            "coding": ["python_executor", "file_manager", "terminal"],
            "debug": ["python_executor", "terminal", "file_manager"],
            "security": ["system_command", "file_manager", "log_analyzer"],
            "cyber": ["recon_tool", "vuln_scanner", "exploit_intel_tool"],
            "github_sync": ["git_tool", "github_sync_tool"],
            "vision": ["image_processing", "ocr"],
            "audio": ["audio", "transcribe"],
            "data_science": ["python_executor", "database"],
            "infra": ["terminal", "docker_tool", "system_command"],
            "memory": ["memory_search"],
            "planner": [],
            "qa": ["python_executor"],
        }
        return mapping.get(name, [])

    # ---- persisted generated/registered agents ----
    def _load_persisted(self) -> None:
        for f in self._root.glob("*.json"):
            try:
                d = json.loads(f.read_text())
                meta = AgentMetadata.from_dict(d)
                self._agents[meta.id] = meta
            except Exception:  # noqa: BLE001
                pass

    def _load_factory_agents(self) -> None:
        """Merge Agent Factory-generated agents (additive; non-destructive)."""
        try:
            from app.agent_factory.store import AgentStore
            for rec in AgentStore().all():
                if rec.agent_id in self._agents:
                    continue  # builtin wins for id collision
                self._agents[rec.agent_id] = AgentMetadata(
                    id=rec.agent_id, name=rec.name, version=rec.version,
                    description=rec.description,
                    capabilities=rec.capabilities.split("|") if rec.capabilities else [rec.name],
                    required_tools=rec.required_tools.split("|") if rec.required_tools else [],
                    permissions=rec.permissions.split("|") if rec.permissions else ["READ"],
                    risk_level=rec.risk_level or "low",
                    status=rec.status, source="factory",
                    module_path=rec.module_path,
                    success_criteria="generated agent passes sandbox tests + security review",
                )
        except Exception:  # noqa: BLE001
            pass

    # ---- API ----
    def all(self) -> list[AgentMetadata]:
        return list(self._agents.values())

    def get(self, agent_id: str) -> AgentMetadata | None:
        return self._agents.get(agent_id)

    def register(self, meta: AgentMetadata) -> None:
        with self._lock:
            self._agents[meta.id] = meta
            self._persist(meta)

    def _persist(self, meta: AgentMetadata) -> None:
        try:
            (self._root / f"{meta.id}.json").write_text(json.dumps(meta.to_dict(), indent=2))
        except Exception:  # noqa: BLE001
            pass

    def select(self, *, capability: str | None = None, risk_max: str = "critical",
               required_perm: str | None = None) -> list[AgentMetadata]:
        """Capability-based selection (spec 12): match by capability/name, not
        solely by name. Returns candidates sorted by risk then capability match."""
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        cap = (capability or "").lower().strip()
        # Tokenise multi-word queries so "web research" matches "web_research".
        toks = [t for t in cap.replace("_", " ").split() if t]
        out: list[AgentMetadata] = []
        for m in self._agents.values():
            if m.status != "active":
                continue
            if order.get(m.risk_level, 9) > order.get(risk_max, 9):
                continue
            if required_perm and required_perm not in m.permissions:
                continue
            if cap:
                hay = (m.id + " " + " ".join(m.capabilities)).lower()
                matched = cap in hay or all(tok in hay for tok in toks)
                if not matched:
                    continue
            out.append(m)
        out.sort(key=lambda m: (order.get(m.risk_level, 9), m.source != "builtin"))
        return out

    def to_report(self) -> dict[str, Any]:
        by_source = {}
        for m in self._agents.values():
            by_source[m.source] = by_source.get(m.source, 0) + 1
        return {"total": len(self._agents), "by_source": by_source,
                "agents": [m.to_dict() for m in self._agents.values()]}


# Module-level singleton (lazy import-safe).
_REGISTRY: "AgentRegistry | None" = None


def get_registry() -> AgentRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = AgentRegistry()
    # Idempotently register the 40 MOON spec agents (additive; skips if present).
    try:
        from app.agents.spec_agents import register_spec_agents
        register_spec_agents()
    except Exception:  # noqa: BLE001
        pass
    return _REGISTRY


__all__ = ["AgentMetadata", "AgentRegistry", "get_registry"]
