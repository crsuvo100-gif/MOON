"""Cognitive memory record model (spec 7, 5, 6, 8, 9, 10).

The existing ``MemoryEntry`` (app/models/memory.py) is a MINIMAL record
(content/scope/tags/metadata) and is preserved untouched -- working code.

This module adds the full cognitive record the spec requires, without
replacing anything: ownership, provenance, confidence, importance,
versioning, device/sync state and lifecycle flags.

Spec 88 boundaries are respected explicitly:
    MEMORY != DATABASE   (this is the record; the store is app/memory/store.py)
    MEMORY != CONTEXT    (context assembly lives in the ContextEngine)
    MEMORY != TRUSTED INSTRUCTION (see `trusted`: retrieved memory is DATA)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# spec 5: memory scopes
# --------------------------------------------------------------------------
class Scope(str, Enum):
    SYSTEM = "SYSTEM"
    GLOBAL = "GLOBAL"
    USER = "USER"
    PROJECT = "PROJECT"
    AGENT = "AGENT"
    TEAM = "TEAM"
    TASK = "TASK"
    SESSION = "SESSION"


# spec 4: memory layers/types
class MemoryType(str, Enum):
    WORKING = "working"
    SHORT_TERM = "short_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    USER = "user"
    PROJECT = "project"
    AGENT = "agent"
    SHARED = "shared"


# spec 8: provenance
class SourceType(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    TOOL = "TOOL"
    DOCUMENT = "DOCUMENT"
    WEB = "WEB"
    DATABASE = "DATABASE"
    SYSTEM = "SYSTEM"
    PROJECT = "PROJECT"
    INFERENCE = "INFERENCE"


# spec 10: importance classes
class Importance(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    TEMPORARY = "TEMPORARY"


# spec 7: sync state
class SyncStatus(str, Enum):
    LOCAL = "LOCAL"            # written locally, not yet queued
    PENDING = "PENDING"        # queued for cloud
    SYNCED = "SYNCED"
    CONFLICT = "CONFLICT"
    FAILED = "FAILED"


# spec 8/9: default confidence per source. An explicit user fact is trusted;
# an unverified agent inference is NOT treated as equivalent (spec 9).
DEFAULT_CONFIDENCE: dict[SourceType, float] = {
    SourceType.USER: 0.95,
    SourceType.SYSTEM: 0.95,
    SourceType.PROJECT: 0.85,
    SourceType.TOOL: 0.80,
    SourceType.DATABASE: 0.80,
    SourceType.DOCUMENT: 0.70,
    SourceType.WEB: 0.55,
    SourceType.AGENT: 0.60,
    SourceType.INFERENCE: 0.40,
}

# spec 10: default importance per type
DEFAULT_IMPORTANCE: dict[MemoryType, Importance] = {
    MemoryType.WORKING: Importance.TEMPORARY,
    MemoryType.SHORT_TERM: Importance.LOW,
    MemoryType.EPISODIC: Importance.MEDIUM,
    MemoryType.SEMANTIC: Importance.HIGH,
    MemoryType.PROCEDURAL: Importance.HIGH,
    MemoryType.USER: Importance.HIGH,
    MemoryType.PROJECT: Importance.HIGH,
    MemoryType.AGENT: Importance.MEDIUM,
    MemoryType.SHARED: Importance.HIGH,
}

_IMPORTANCE_SCORE = {
    Importance.CRITICAL: 1.0, Importance.HIGH: 0.8, Importance.MEDIUM: 0.55,
    Importance.LOW: 0.3, Importance.TEMPORARY: 0.1,
}


@dataclass
class MemoryRecord:
    """The full cognitive memory entity (spec 7).

    ``trusted`` is deliberately False for anything that came from an external
    or inferred source (spec 67/68): retrieved memory is DATA, never an
    instruction that may override system/security policy.
    """

    content: str
    memory_id: str = field(default_factory=lambda: "mem_" + uuid.uuid4().hex[:16])

    # spec 5/6: scope + ownership
    scope: Scope = Scope.GLOBAL
    type: MemoryType = MemoryType.SEMANTIC
    owner_id: str = "moon"
    agent_id: str = ""
    project_id: str = ""
    task_id: str = ""
    session_id: str = ""

    # spec 7: content + retrieval
    summary: str = ""
    tags: list[str] = field(default_factory=list)

    # spec 9/10
    confidence: float = 0.6
    importance: Importance = Importance.MEDIUM
    relevance: float = 0.0

    # spec 8
    source_type: SourceType = SourceType.AGENT
    source: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    # lifecycle timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    # spec 39: versioning
    version: int = 1
    parent_version: int | None = None

    # spec 35/7: device + sync
    device_id: str = ""
    sync_status: SyncStatus = SyncStatus.LOCAL

    # spec 17/18: lifecycle flags
    deleted: bool = False
    archived: bool = False

    # spec 67/68: trust boundary. False => may inform, must not instruct.
    trusted: bool = False
    # spec 58: embedding may be deferred when the provider is unavailable
    embedding_pending: bool = False

    # spec 70: canonical memory (important project facts)
    canonical: bool = False
    verified_at: float | None = None
    verified_by: str = ""

    @property
    def importance_score(self) -> float:
        return _IMPORTANCE_SCORE.get(self.importance, 0.5)

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        for k in ("scope", "type", "source_type", "importance", "sync_status"):
            v = d.get(k)
            d[k] = v.value if isinstance(v, Enum) else v
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryRecord":
        d = dict(data or {})
        for key, enum_cls in (("scope", Scope), ("type", MemoryType),
                              ("source_type", SourceType),
                              ("importance", Importance),
                              ("sync_status", SyncStatus)):
            if key in d and not isinstance(d[key], enum_cls):
                try:
                    d[key] = enum_cls(d[key])
                except Exception:  # noqa: BLE001
                    d[key] = enum_cls.__members__[str(d[key]).upper()] \
                        if str(d[key]).upper() in enum_cls.__members__ else None
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    def apply_defaults(self) -> "MemoryRecord":
        """Fill confidence from the source when the caller left the default."""
        base = DEFAULT_CONFIDENCE.get(self.source_type, 0.6)
        if abs(self.confidence - 0.6) < 1e-9:
            self.confidence = base
        if self.importance == Importance.MEDIUM and self.type in DEFAULT_IMPORTANCE:
            self.importance = DEFAULT_IMPORTANCE[self.type]
        # spec 9: only user/system/project facts start out trusted
        self.trusted = self.source_type in (SourceType.USER, SourceType.SYSTEM,
                                            SourceType.PROJECT)
        return self


__all__ = [
    "Scope", "MemoryType", "SourceType", "Importance", "SyncStatus",
    "MemoryRecord", "DEFAULT_CONFIDENCE", "DEFAULT_IMPORTANCE",
]
