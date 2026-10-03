"""memory_graph.py -- Associative memory graph for linking related memories.

Professional AI assistants build associations between memories so that
recalling one memory can trigger recall of related ones. This module implements
a lightweight graph where nodes are memory entries and edges represent
associations (co-occurrence, semantic similarity, or explicit links).
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryNode:
    """A node in the memory graph."""
    id: str
    content: str
    memory_type: str  # "ltm", "stm", "episodic", "semantic"
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryNode:
        return cls(
            id=data["id"],
            content=data.get("content", ""),
            memory_type=data.get("memory_type", "ltm"),
            importance=float(data.get("importance", 0.5)),
            tags=list(data.get("tags", [])),
            created_at=float(data.get("created_at", time.time())),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MemoryEdge:
    """An edge connecting two memory nodes."""
    source: str
    target: str
    weight: float = 1.0
    edge_type: str = "association"  # "association", "semantic", "causal", "temporal"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
            "edge_type": self.edge_type,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEdge:
        return cls(
            source=data["source"],
            target=data["target"],
            weight=float(data.get("weight", 1.0)),
            edge_type=data.get("edge_type", "association"),
            created_at=float(data.get("created_at", time.time())),
        )


class MemoryGraph:
    """Associative memory graph with semantic similarity and co-occurrence edges.

    Features:
    - Add nodes from any memory type
    - Create edges between related memories
    - Find related memories via graph traversal
    - Semantic similarity edges (cosine of embeddings)
    - Co-occurrence edges (memories that appear together)
    - Path finding between memories
    - Community detection (simple clustering)
    """

    def __init__(
        self,
        persist_path: str = "app/logs/memory_graph.json",
        max_nodes: int = 5000,
        similarity_threshold: float = 0.5,
    ) -> None:
        self._persist_path = Path(persist_path)
        self._max_nodes = max_nodes
        self._similarity_threshold = similarity_threshold
        self._nodes: dict[str, MemoryNode] = {}
        self._edges: dict[str, list[MemoryEdge]] = {}  # adjacency list: node_id -> edges
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        if self._persist_path.exists():
            try:
                text = self._persist_path.read_text(encoding="utf-8")
                data = json.loads(text)
                for node_data in data.get("nodes", []):
                    node = MemoryNode.from_dict(node_data)
                    self._nodes[node.id] = node
                for edge_data in data.get("edges", []):
                    edge = MemoryEdge.from_dict(edge_data)
                    self._edges.setdefault(edge.source, []).append(edge)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Could not load memory graph: %s", exc)
        logger.info("Memory graph loaded %d nodes, %d edges", len(self._nodes), self._edge_count())

    async def add_memory(
        self,
        content: str,
        memory_type: str = "ltm",
        importance: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """Add a memory node (convenience wrapper around add_node)."""
        import hashlib
        node_id = hashlib.md5(content.encode()).hexdigest()[:16]
        return await self.add_node(
            node_id=node_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            metadata=metadata,
        )

    async def add_node(
        self,
        node_id: str,
        content: str,
        memory_type: str = "ltm",
        importance: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryNode:
        """Add a node to the graph."""
        node = MemoryNode(
            id=node_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or [],
            metadata=metadata or {},
        )
        async with self._lock:
            self._nodes[node_id] = node
            if node_id not in self._edges:
                self._edges[node_id] = []
            if len(self._nodes) > self._max_nodes:
                self._evict_oldest()
            await self._persist()
        return node

    async def add_edge(
        self,
        source: str,
        target: str,
        weight: float = 1.0,
        edge_type: str = "association",
    ) -> MemoryEdge | None:
        """Add an edge between two nodes."""
        if source not in self._nodes or target not in self._nodes:
            return None
        edge = MemoryEdge(
            source=source,
            target=target,
            weight=weight,
            edge_type=edge_type,
        )
        async with self._lock:
            self._edges.setdefault(source, []).append(edge)
            # Undirected: add reverse edge too
            reverse = MemoryEdge(
                source=target,
                target=source,
                weight=weight,
                edge_type=edge_type,
            )
            self._edges.setdefault(target, []).append(reverse)
            await self._persist()
        return edge

    async def link_co_occurring(
        self,
        node_ids: list[str],
        weight: float = 0.5,
    ) -> int:
        """Create edges between all pairs of co-occurring nodes."""
        created = 0
        for i, a in enumerate(node_ids):
            for b in node_ids[i + 1:]:
                if a in self._nodes and b in self._nodes:
                    await self.add_edge(a, b, weight=weight, edge_type="co-occurrence")
                    created += 1
        return created

    async def find_related(
        self,
        node_id: str,
        max_depth: int = 2,
        min_weight: float = 0.1,
        limit: int = 10,
    ) -> list[tuple[MemoryNode, float]]:
        """Find related memories via BFS traversal."""
        if node_id not in self._nodes:
            return []
        visited: set[str] = {node_id}
        frontier: list[tuple[str, float]] = [(node_id, 1.0)]
        results: list[tuple[MemoryNode, float]] = []

        for depth in range(max_depth):
            next_frontier: list[tuple[str, float]] = []
            for current_id, current_weight in frontier:
                for edge in self._edges.get(current_id, []):
                    if edge.target in visited:
                        continue
                    if edge.weight < min_weight:
                        continue
                    visited.add(edge.target)
                    new_weight = current_weight * edge.weight
                    if edge.target in self._nodes:
                        results.append((self._nodes[edge.target], new_weight))
                    next_frontier.append((edge.target, new_weight))
            frontier = next_frontier

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def find_path(
        self,
        source: str,
        target: str,
        max_depth: int = 5,
    ) -> list[MemoryNode] | None:
        """Find a path between two memories using BFS."""
        if source not in self._nodes or target not in self._nodes:
            return None
        if source == target:
            return [self._nodes[source]]

        visited: set[str] = {source}
        queue: list[tuple[str, list[str]]] = [(source, [source])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            for edge in self._edges.get(current, []):
                if edge.target in visited:
                    continue
                visited.add(edge.target)
                new_path = path + [edge.target]
                if edge.target == target:
                    return [self._nodes[nid] for nid in new_path]
                queue.append((edge.target, new_path))
        return None

    async def get_communities(self) -> list[list[MemoryNode]]:
        """Simple community detection via connected components."""
        visited: set[str] = set()
        communities: list[list[MemoryNode]] = []

        for node_id in self._nodes:
            if node_id in visited:
                continue
            # BFS to find connected component
            component: list[str] = []
            queue = [node_id]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                for edge in self._edges.get(current, []):
                    if edge.target not in visited:
                        queue.append(edge.target)
            communities.append([self._nodes[nid] for nid in component])

        return communities

    async def get_central_memories(self, top_k: int = 10) -> list[tuple[MemoryNode, float]]:
        """Get the most central memories by degree centrality."""
        centrality: dict[str, float] = {}
        for node_id in self._nodes:
            edges = self._edges.get(node_id, [])
            # Weighted degree centrality
            centrality[node_id] = sum(e.weight for e in edges)

        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        return [(self._nodes[nid], score) for nid, score in sorted_nodes[:top_k]]

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its edges."""
        async with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            # Remove all edges pointing to this node
            for edges in self._edges.values():
                edges[:] = [e for e in edges if e.target != node_id]
            # Remove this node's edge list
            self._edges.pop(node_id, None)
            await self._persist()
        return True

    async def search(self, keyword: str, limit: int = 5) -> list[str]:
        """Search graph nodes by keyword."""
        kw = keyword.lower()
        results = []
        for node in self._nodes.values():
            if kw in node.content.lower():
                results.append(node.content)
                if len(results) >= limit:
                    break
        return results

    def stats(self) -> dict[str, Any]:
        """Return graph statistics."""
        return {
            "nodes": len(self._nodes),
            "edges": self._edge_count(),
            "avg_degree": round(
                self._edge_count() / max(len(self._nodes), 1), 2
            ),
            "density": round(
                self._edge_count() / max(len(self._nodes) * (len(self._nodes) - 1) / 2, 1), 4
            ),
        }

    def _edge_count(self) -> int:
        return sum(len(edges) for edges in self._edges.values())

    def _evict_oldest(self) -> None:
        """Evict oldest, lowest-importance nodes."""
        sorted_nodes = sorted(
            self._nodes.values(),
            key=lambda n: (n.created_at, n.importance),
        )
        to_remove = len(self._nodes) - self._max_nodes
        for node in sorted_nodes[:to_remove]:
            del self._nodes[node.id]
            self._edges.pop(node.id, None)

    async def _persist(self) -> None:
        data = {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for edges in self._edges.values() for e in edges],
        }
        text = json.dumps(data, ensure_ascii=False, indent=2)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_text, text)

    def _write_text(self, text: str) -> None:
        self._persist_path.write_text(text, encoding="utf-8")
