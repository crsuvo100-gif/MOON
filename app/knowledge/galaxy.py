"""knowledge/galaxy.py -- a lightweight knowledge graph ("galaxy").

Nodes are concepts/tools; edges are relationships. Built from the tool
registry so the brain can navigate related capabilities. Best-effort and
fully optional -- if building fails the orchestrator degrades gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GalaxyNode:
    id: str
    label: str
    kind: str = "concept"
    edges: list[str] = field(default_factory=list)


class GalaxyService:
    """Builds and queries a small knowledge galaxy from the tool registry."""

    def __init__(self) -> None:
        self._nodes: dict[str, GalaxyNode] = {}

    async def build(self, registry=None) -> "GalaxyService":
        if registry is not None:
            try:
                tools = registry.all()
                for t in tools:
                    name = getattr(t, "name", None) or getattr(t, "tool_name", None)
                    if name:
                        self._nodes[name] = GalaxyNode(id=name, label=name, kind="tool")
                # Link tools that share a category heuristically.
                names = list(self._nodes)
                for i, a in enumerate(names):
                    for b in names[i + 1 :]:
                        if a.split("_")[0] == b.split("_")[0]:
                            self._nodes[a].edges.append(b)
                            self._nodes[b].edges.append(a)
                logger.info("Galaxy built: %d nodes, %d edges", len(self._nodes),
                            sum(len(n.edges) for n in self._nodes.values()) // 2)
            except Exception as exc:  # noqa: BLE001
                logger.info("Galaxy build partial: %s", exc)
        return self

    def query(self, concept: str, top_k: int = 5) -> list[GalaxyNode]:
        hits = [n for n in self._nodes.values() if concept.lower() in n.label.lower()]
        return hits[:top_k]

    def nodes(self) -> list[GalaxyNode]:
        return list(self._nodes.values())
