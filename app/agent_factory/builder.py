"""Agent Factory: Builder + Dependency Resolver (spec 15, 16).

Builder: turns an AgentSpec into a real agent module (implementation + tests),
reusing the existing deterministic generator. Dependency Resolver: resolves the
required tools against the live tool registry / CapabilityManager and reports
any missing dependency (spec: TOOL RESOLVER / DEPENDENCY MANAGER).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agent_factory.architect import AgentSpec
from app.agent_factory.models import AgentMetadata, GeneratedAgent, RiskLevel


@dataclass
class BuildArtifact:
    spec: AgentSpec
    module_path: str = ""
    test_path: str = ""
    ok: bool = False
    error: str = ""


def _to_meta(spec: AgentSpec) -> AgentMetadata:
    return AgentMetadata(
        id=spec.agent_id, name=spec.name, version=spec.version,
        description=spec.description, capabilities=spec.capabilities,
        required_tools=spec.required_tools, permissions=spec.permissions,
        risk_level=RiskLevel(spec.risk_level), dependencies=spec.dependencies,
    )


class AgentBuilder:
    """Generates the agent implementation + tests (reuses generator.generate)."""

    def build(self, spec: AgentSpec, staging_dir: str | Path) -> BuildArtifact:
        art = BuildArtifact(spec=spec)
        try:
            from app.agent_factory.generator import generate
            ga: GeneratedAgent = generate(_to_meta(spec), Path(staging_dir))
            art.module_path = ga.module_path
            art.test_path = ga.test_path
            art.ok = bool(art.module_path)
        except Exception as e:  # noqa: BLE001
            art.error = str(e)
        return art


class DependencyResolver:
    """Resolve required tools; report missing dependencies (spec: TOOL RESOLVER)."""

    def resolve(self, spec: AgentSpec) -> dict[str, Any]:
        missing: list[str] = []
        resolved: list[str] = []
        try:
            from app.tools.registry import ToolRegistry
            reg = ToolRegistry()
            known = set(reg.tool_names)
        except Exception:  # noqa: BLE001
            known = set()
        for t in spec.required_tools:
            if t in known:
                resolved.append(t)
            else:
                try:
                    from app.capability.manager import CapabilityManager
                    mgr = CapabilityManager()
                    if mgr.status(t) in ("available", "acquired"):
                        resolved.append(t)
                    else:
                        missing.append(t)
                except Exception:  # noqa: BLE001
                    missing.append(t)
        return {"resolved": resolved, "missing": missing, "all_present": len(missing) == 0}


__all__ = ["AgentBuilder", "BuildArtifact", "DependencyResolver"]
