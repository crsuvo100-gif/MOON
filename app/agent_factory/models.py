"""Agent Factory data models (spec sections 7, 8, 34, 39).

Pure, dependency-light dataclasses so every generated component is
independently testable and serialisable. No MOON core imports here.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    STAGING = "staging"
    ACTIVE = "active"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"


class AuditAction(str, Enum):
    CREATE = "agent.create"
    GENERATE = "agent.generate"
    TEST = "agent.test"
    SECURITY_REVIEW = "agent.security_review"
    REGISTER = "agent.register"
    ENABLE = "agent.enable"
    DISABLE = "agent.disable"
    ROLLBACK = "agent.rollback"
    QUARANTINE = "agent.quarantine"
    RUN = "agent.run"
    FAILURE = "agent.failure"


@dataclass
class AgentMetadata:
    """Structured agent metadata (spec section 8)."""

    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    risk_level: str = RiskLevel.LOW.value
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    status: str = AgentStatus.STAGING.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentMetadata":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class GeneratedAgent:
    """A generated agent: metadata + on-disk implementation + test paths."""

    metadata: AgentMetadata
    module_path: str = ""
    test_path: str = ""
    implementation: str = ""
    test_code: str = ""
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "module_path": self.module_path,
            "test_path": self.test_path,
            "execution_id": self.execution_id,
        }


@dataclass
class AgentFactoryRecord:
    """Persisted factory record (DB row-shaped)."""

    agent_id: str
    name: str
    version: str
    status: str
    stage: str  # staging | approved | quarantine (filesystem location)
    risk_level: str
    description: str
    permissions: str = ""          # pipe-separated
    required_tools: str = ""       # pipe-separated
    capabilities: str = ""         # pipe-separated
    module_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_version: str = ""
    previous_version: str = ""
    notes: str = ""


@dataclass
class AuditEvent:
    """Structured audit event (spec section 34). Never holds secrets."""

    action: str
    agent_id: str
    detail: str
    actor: str = "agent_factory"
    execution_id: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FactoryResult:
    """Machine-readable result returned by every factory operation (spec 7)."""

    success: bool
    status: str
    agent_id: str = ""
    agent_version: str = ""
    execution_id: str = ""
    result: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["errors"] = list(self.errors)
        d["warnings"] = list(self.warnings)
        return d
