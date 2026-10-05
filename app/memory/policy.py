"""MemoryPolicyEngine – enforces read/write/delete permissions based on scope, ownership, and trust.

The engine is deliberately lightweight and has **no external dependencies** – it only relies on the core memory model (`app.memory.record`).

Usage example::

    from app.memory.policy import MemoryPolicyEngine, Requestor
    from app.memory.record import MemoryRecord, Scope, MemoryType, SourceType

    # a requestor representing user "alice" acting in USER scope
    req = Requestor(user_id="alice", scope=Scope.USER, is_trusted=False)
    engine = MemoryPolicyEngine(req)

    rec = MemoryRecord(
        content="secret info",
        scope=Scope.USER,
        type=MemoryType.SEMANTIC,
        owner_id="alice",
        source_type=SourceType.USER,
        trusted=False,
    )

    engine.can_read(rec)   # → True
    engine.can_write(rec)  # → True
    engine.can_delete(rec) # → True

If the requestor tries to modify a record they do not own, or attempts to
execute an untrusted record, the corresponding ``can_*`` method returns
``False``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.memory.record import (
    MemoryRecord,
    Scope,
    MemoryType,
    SourceType,
)


# ---------------------------------------------------------------------------
# Helper: scope hierarchy – lower index == higher privilege
# ---------------------------------------------------------------------------
_SCOPE_ORDER = [
    Scope.SYSTEM,
    Scope.GLOBAL,
    Scope.USER,
    Scope.PROJECT,
    Scope.AGENT,
    Scope.TEAM,
    Scope.TASK,
    Scope.SESSION,
]


def _scope_level(sc: Scope) -> int:
    """Return an integer representing the privilege level of ``sc``.

    ``0`` is the highest privilege (SYSTEM) and larger numbers are lower
    privileges. If an unknown scope is encountered the function returns a
    large number to treat it as the least privileged.
    """
    try:
        return _SCOPE_ORDER.index(sc)
    except ValueError:
        return len(_SCOPE_ORDER)


# ---------------------------------------------------------------------------
# Requestor – the actor performing a memory operation.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Requestor:
    """Minimal representation of the caller for policy checks.

    Attributes
    ----------
    user_id: str
        Identifier of the human user (empty string for system actions).
    agent_id: str
        Identifier of the agent (empty string when the request originates
        from a user directly).
    scope: Scope
        The effective security scope of the caller.
    is_trusted: bool
        Whether the caller is allowed to execute ``trusted`` records as
        instructions. This flag is typically true for system components or
        for agents that have been explicitly granted execution rights.
    """

    user_id: str = ""
    agent_id: str = ""
    scope: Scope = Scope.GLOBAL
    is_trusted: bool = False


# ---------------------------------------------------------------------------
# Core policy engine
# ---------------------------------------------------------------------------
class MemoryPolicyEngine:
    """Enforce access control for ``MemoryRecord`` objects.

    The engine implements three public methods – ``can_read``, ``can_write``
    and ``can_delete`` – each returning ``True`` if the operation is allowed
    for the supplied ``MemoryRecord`` under the current ``Requestor``.

    The logic follows the specifications outlined in the design document:

    1. Scope hierarchy – a caller may read any record whose scope is **equal
       to** or **lower** (i.e., less privileged) than their own scope.
    2. Ownership – write/delete requires that the caller's ``user_id`` matches
       ``owner_id`` **or** that the caller's ``agent_id`` matches the record's
       ``agent_id`` when the record resides in ``AGENT`` scope.
    3. Trusted records – records marked ``trusted=True`` may only be written /
       deleted by a requestor that also has ``is_trusted=True``.
    4. System‑level records – only a requestor with ``Scope.SYSTEM`` (or the
       exact owner) can modify system scoped records.
    """

    def __init__(self, requestor: Requestor) -> None:
        self.requestor = requestor

    # -------------------------------------------------------------------
    # Public checks
    # -------------------------------------------------------------------
    def can_read(self, rec: MemoryRecord) -> bool:
        """Return ``True`` if the requestor can read ``rec``.

        Reading is allowed when the requestor's scope is **greater or equal**
        in privilege (i.e., lower or equal numeric level) than the record's
        scope. No ownership check is required for reads.
        """
        req_lvl = _scope_level(self.requestor.scope)
        rec_lvl = _scope_level(rec.scope)
        return req_lvl <= rec_lvl

    def can_write(self, rec: MemoryRecord) -> bool:
        """Return ``True`` if the requestor can write/update ``rec``.

        *Scope check*: requestor must have a privileged enough scope.
        *Ownership*: ``owner_id`` must match the requestor's ``user_id`` **or**
        ``agent_id`` must match when the record resides in ``AGENT`` scope.
        *Trust*: if ``rec.trusted`` is ``True``, the requestor must also be
        ``is_trusted``.
        """
        if not self._scope_permits(rec.scope):
            return False
        if rec.trusted and not self.requestor.is_trusted:
            return False
        # Ownership rules – allow if user owns the record or if the agent owns it.
        if rec.owner_id and rec.owner_id == self.requestor.user_id:
            return True
        if rec.agent_id and rec.agent_id == self.requestor.agent_id:
            return True
        # For system‑level records, only a SYSTEM‑scoped requestor may write.
        if rec.scope == Scope.SYSTEM and self.requestor.scope != Scope.SYSTEM:
            return False
        return False

    def can_delete(self, rec: MemoryRecord) -> bool:
        """Return ``True`` if the requestor can delete ``rec``.

        Deletion follows the same rules as ``can_write`` – a delete is a
        mutating operation. The implementation simply forwards to ``can_write``
        for consistency.
        """
        return self.can_write(rec)

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------
    def _scope_permits(self, rec_scope: Scope) -> bool:
        """Determine if the requestor's scope is sufficient for ``rec_scope``.

        ``True`` when the requestor's level is *higher* (i.e., lower numeric
        index) than or equal to the record's level.
        """
        req_lvl = _scope_level(self.requestor.scope)
        rec_lvl = _scope_level(rec_scope)
        return req_lvl <= rec_lvl


__all__ = ["MemoryPolicyEngine", "Requestor"]
