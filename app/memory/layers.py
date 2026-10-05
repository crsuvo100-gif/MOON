"""Memory layer definitions and retention policies.

This module formalises the cognitive memory layers described in the specification
(section 4‑8). Each :class:`MemoryType` is mapped to a :class:`Layer` that
captures:

* ``name`` – human‑readable layer name.
* ``memory_type`` – the corresponding :class:`~app.memory.record.MemoryType`.
* ``retention_seconds`` – how long records of this layer are kept in the
  local store before being eligible for decay or archival. ``None`` means
  indefinite retention.
* ``description`` – brief purpose of the layer.

The ``LAYER_REGISTRY`` provides a quick lookup by ``MemoryType`` and is used by
the :class:`~app.memory.store.LocalMemoryStore` and the future ContextEngine to
apply layer‑specific policies (e.g., automatic decay, promotion, or archival).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict

from .record import MemoryType


@dataclass(frozen=True, slots=True)
class Layer:
    """Definition of a memory layer.

    Attributes
    ----------
    name: str
        Human‑readable identifier.
    memory_type: MemoryType
        The :class:`MemoryType` that belongs to this layer.
    retention_seconds: Optional[int]
        Number of seconds a record may remain in the local store before it is
        considered for decay/archive. ``None`` means the layer is persistent.
    description: str
        Short description of the layer's purpose.
    """

    name: str
    memory_type: MemoryType
    retention_seconds: Optional[int]
    description: str


# ---------------------------------------------------------------------------
# Layer definitions (spec 4‑8). Values are chosen to satisfy the design goals
# while remaining safe for low‑resource environments. They can be overridden
# at runtime via the ``MOON_LAYER_TTLS`` environment variable if needed.
# ---------------------------------------------------------------------------

LAYER_REGISTRY: Dict[MemoryType, Layer] = {
    MemoryType.WORKING: Layer(
        name="Working Memory",
        memory_type=MemoryType.WORKING,
        retention_seconds=300,  # 5 min – transient task state
        description="Temporary information for the current task execution.",
    ),
    MemoryType.SHORT_TERM: Layer(
        name="Short‑Term Memory",
        memory_type=MemoryType.SHORT_TERM,
        retention_seconds=3_600,  # 1 h – recent interactions
        description="Recent conversation or task context that may be promoted.",
    ),
    MemoryType.EPISODIC: Layer(
        name="Episodic Memory",
        memory_type=MemoryType.EPISODIC,
        retention_seconds=86_400,  # 24 h – events that could be promoted
        description="Recorded events with timestamps for later analysis.",
    ),
    MemoryType.SEMANTIC: Layer(
        name="Semantic Memory",
        memory_type=MemoryType.SEMANTIC,
        retention_seconds=None,  # indefinite – core knowledge
        description="Stable facts and knowledge extracted from the environment.",
    ),
    MemoryType.PROCEDURAL: Layer(
        name="Procedural Memory",
        memory_type=MemoryType.PROCEDURAL,
        retention_seconds=None,  # indefinite – documented procedures
        description="How‑to knowledge and repeatable processes.",
    ),
    MemoryType.USER: Layer(
        name="User Memory",
        memory_type=MemoryType.USER,
        retention_seconds=None,
        description="User‑approved persistent information.",
    ),
    MemoryType.PROJECT: Layer(
        name="Project Memory",
        memory_type=MemoryType.PROJECT,
        retention_seconds=None,
        description="Project‑specific facts, configuration, and constraints.",
    ),
    MemoryType.AGENT: Layer(
        name="Agent Private Memory",
        memory_type=MemoryType.AGENT,
        retention_seconds=None,
        description="Isolated memory scoped to an individual agent.",
    ),
    MemoryType.SHARED: Layer(
        name="Shared Memory",
        memory_type=MemoryType.SHARED,
        retention_seconds=None,
        description="Information explicitly shared between agents.",
    ),
}

__all__ = ["Layer", "LAYER_REGISTRY"]
