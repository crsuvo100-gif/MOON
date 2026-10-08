"""Memory clustering -- group related memories into clusters.

Professional AI assistants organize memories into meaningful groups.
This module provides clustering capabilities:

1. Topic clustering: Group memories by topic similarity
2. Temporal clustering: Group memories by time proximity
3. Agent clustering: Group memories by agent ownership
4. Tag clustering: Group memories by shared tags
5. Semantic clustering: Group memories by semantic similarity

Clusters help with:
- Faster retrieval (search within relevant clusters)
- Better organization (hierarchical memory structure)
- Pattern discovery (find common themes)
- Memory consolidation (merge similar memories)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryCluster:
    """A cluster of related memories."""
    cluster_id: str
    label: str
    memory_ids: list[str] = field(default_factory=list)
    centroid: str = ""  # Representative content
    coherence: float = 0.0  # 0.0 - 1.0
    created_at: float = field(default_factory=time.time)

    @property
    def size(self) -> int:
        return len(self.memory_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "memory_ids": self.memory_ids,
            "centroid": self.centroid[:200] if self.centroid else "",
            "coherence": round(self.coherence, 4),
            "size": self.size,
            "created_at": self.created_at,
        }


class MemoryClustering:
    """Clusters memories by various criteria.

    Usage:
        clustering = MemoryClustering(memory_manager)
        clusters = clustering.cluster_by_topic(top_k=100)
        clusters = clustering.cluster_by_time(max_gap_hours=24)
        clusters = clustering.cluster_by_tags()
    """

    def __init__(self, memory_manager=None) -> None:
        self._mm = memory_manager
        self._cluster_count = 0

    def cluster_by_topic(
        self,
        top_k: int = 100,
        min_cluster_size: int = 2,
    ) -> list[MemoryCluster]:
        """Cluster memories by topic similarity.

        Uses keyword overlap to determine similarity.
        """
        self._cluster_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Topic clustering retrieval failed: %s", exc)
            return []

        if len(results) < min_cluster_size:
            return []

        # Extract keywords from each memory
        mem_keywords: dict[str, set[str]] = {}
        for r in results:
            mem_id = self._get_id(r)
            content = self._get_content(r).lower()
            keywords = set(re.findall(r"[a-z_]{3,}", content))
            mem_keywords[mem_id] = keywords

        # Simple agglomerative clustering
        clusters: list[dict[str, Any]] = []
        assigned: set[str] = set()

        for mem_id, keywords in mem_keywords.items():
            if mem_id in assigned:
                continue

            # Find best matching cluster
            best_cluster = None
            best_score = 0.0

            for cluster in clusters:
                cluster_keywords = cluster["keywords"]
                if not cluster_keywords:
                    continue
                overlap = len(keywords & cluster_keywords) / max(len(keywords), len(cluster_keywords))
                if overlap > best_score:
                    best_score = overlap
                    best_cluster = cluster

            if best_score >= 0.3 and best_cluster is not None:
                best_cluster["memory_ids"].append(mem_id)
                best_cluster["keywords"] |= keywords
                assigned.add(mem_id)
            else:
                clusters.append({
                    "memory_ids": [mem_id],
                    "keywords": set(keywords),
                })
                assigned.add(mem_id)

        # Convert to MemoryCluster objects
        result: list[MemoryCluster] = []
        for i, cluster in enumerate(clusters):
            if len(cluster["memory_ids"]) < min_cluster_size:
                continue

            # Find centroid (most central memory)
            centroid = self._find_centroid(cluster["memory_ids"])

            # Calculate coherence
            coherence = self._calculate_coherence(cluster["memory_ids"])

            # Generate label
            label = self._generate_label(cluster["keywords"])

            result.append(MemoryCluster(
                cluster_id=f"topic_{i}",
                label=label,
                memory_ids=cluster["memory_ids"],
                centroid=centroid,
                coherence=coherence,
            ))

        result.sort(key=lambda c: c.size, reverse=True)
        return result

    def cluster_by_time(
        self,
        top_k: int = 100,
        max_gap_hours: float = 24.0,
    ) -> list[MemoryCluster]:
        """Cluster memories by time proximity.

        Memories created close together are grouped.
        """
        self._cluster_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Time clustering retrieval failed: %s", exc)
            return []

        # Sort by timestamp
        timed_memories: list[tuple[float, str]] = []
        for r in results:
            ts = self._get_timestamp(r)
            mem_id = self._get_id(r)
            timed_memories.append((ts, mem_id))

        timed_memories.sort(key=lambda x: x[0])

        if not timed_memories:
            return []

        # Group by time gap
        clusters: list[dict[str, Any]] = []
        current_cluster: dict[str, Any] = {
            "memory_ids": [timed_memories[0][1]],
            "start": timed_memories[0][0],
            "end": timed_memories[0][0],
        }

        max_gap_seconds = max_gap_hours * 3600

        for ts, mem_id in timed_memories[1:]:
            if ts - current_cluster["end"] <= max_gap_seconds:
                current_cluster["memory_ids"].append(mem_id)
                current_cluster["end"] = ts
            else:
                clusters.append(current_cluster)
                current_cluster = {
                    "memory_ids": [mem_id],
                    "start": ts,
                    "end": ts,
                }

        clusters.append(current_cluster)

        # Convert to MemoryCluster objects
        result: list[MemoryCluster] = []
        for i, cluster in enumerate(clusters):
            if len(cluster["memory_ids"]) < 2:
                continue

            centroid = self._find_centroid(cluster["memory_ids"])
            coherence = 1.0  # Time clusters are coherent by definition

            start_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(cluster["start"]))
            end_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(cluster["end"]))
            label = f"Time cluster: {start_str} - {end_str}"

            result.append(MemoryCluster(
                cluster_id=f"time_{i}",
                label=label,
                memory_ids=cluster["memory_ids"],
                centroid=centroid,
                coherence=coherence,
            ))

        result.sort(key=lambda c: c.size, reverse=True)
        return result

    def cluster_by_tags(
        self,
        top_k: int = 100,
        min_cluster_size: int = 2,
    ) -> list[MemoryCluster]:
        """Cluster memories by shared tags."""
        self._cluster_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Tag clustering retrieval failed: %s", exc)
            return []

        # Group by tags
        tag_groups: dict[str, list[str]] = {}
        for r in results:
            mem_id = self._get_id(r)
            tags = self._get_tags(r)
            for tag in tags:
                if tag not in tag_groups:
                    tag_groups[tag] = []
                tag_groups[tag].append(mem_id)

        # Convert to MemoryCluster objects
        result: list[MemoryCluster] = []
        for i, (tag, mem_ids) in enumerate(tag_groups.items()):
            if len(mem_ids) < min_cluster_size:
                continue

            centroid = self._find_centroid(mem_ids)
            coherence = min(1.0, 0.5 + 0.1 * len(mem_ids))

            result.append(MemoryCluster(
                cluster_id=f"tag_{tag}",
                label=f"Tag: {tag}",
                memory_ids=mem_ids,
                centroid=centroid,
                coherence=coherence,
            ))

        result.sort(key=lambda c: c.size, reverse=True)
        return result

    def cluster_by_agent(
        self,
        top_k: int = 100,
    ) -> list[MemoryCluster]:
        """Cluster memories by agent ownership."""
        self._cluster_count += 1

        if self._mm is None:
            return []

        try:
            results = self._mm.search("", top_k=top_k)
        except Exception as exc:
            logger.debug("Agent clustering retrieval failed: %s", exc)
            return []

        # Group by agent
        agent_groups: dict[str, list[str]] = {}
        for r in results:
            mem_id = self._get_id(r)
            agent = self._get_agent(r)
            if agent not in agent_groups:
                agent_groups[agent] = []
            agent_groups[agent].append(mem_id)

        # Convert to MemoryCluster objects
        result: list[MemoryCluster] = []
        for i, (agent, mem_ids) in enumerate(agent_groups.items()):
            if len(mem_ids) < 2:
                continue

            centroid = self._find_centroid(mem_ids)
            coherence = min(1.0, 0.5 + 0.1 * len(mem_ids))

            result.append(MemoryCluster(
                cluster_id=f"agent_{agent}",
                label=f"Agent: {agent}",
                memory_ids=mem_ids,
                centroid=centroid,
                coherence=coherence,
            ))

        result.sort(key=lambda c: c.size, reverse=True)
        return result

    def _find_centroid(self, memory_ids: list[str]) -> str:
        """Find the most central memory in a cluster."""
        if not memory_ids:
            return ""

        # For now, return the first memory's content
        # A more sophisticated approach would find the memory with highest
        # average similarity to all others
        if self._mm is None:
            return ""

        try:
            rec = self._mm._store.get(memory_ids[0])
            if rec:
                return self._get_content(rec)[:200]
        except Exception:
            pass

        return ""

    def _calculate_coherence(self, memory_ids: list[str]) -> float:
        """Calculate the coherence of a cluster."""
        if len(memory_ids) < 2:
            return 1.0

        # Simple coherence: average pairwise keyword overlap
        if self._mm is None:
            return 0.5

        keywords_list: list[set[str]] = []
        for mem_id in memory_ids:
            try:
                rec = self._mm._store.get(mem_id)
                if rec:
                    content = self._get_content(rec).lower()
                    keywords = set(re.findall(r"[a-z_]{3,}", content))
                    keywords_list.append(keywords)
            except Exception:
                continue

        if len(keywords_list) < 2:
            return 0.5

        # Calculate average pairwise overlap
        total_overlap = 0.0
        count = 0
        for i in range(len(keywords_list)):
            for j in range(i + 1, len(keywords_list)):
                if keywords_list[i] and keywords_list[j]:
                    overlap = len(keywords_list[i] & keywords_list[j]) / max(
                        len(keywords_list[i]), len(keywords_list[j])
                    )
                    total_overlap += overlap
                    count += 1

        return total_overlap / count if count > 0 else 0.5

    def _generate_label(self, keywords: set[str]) -> str:
        """Generate a label from cluster keywords."""
        if not keywords:
            return "Unknown"
        # Take top 3 most common keywords
        return f"Topic: {', '.join(list(keywords)[:3])}"

    @staticmethod
    def _get_id(mem: Any) -> str:
        if hasattr(mem, "memory_id"):
            return str(mem.memory_id)
        if hasattr(mem, "record"):
            return str(mem.record.memory_id)
        return str(id(mem))

    @staticmethod
    def _get_content(mem: Any) -> str:
        if hasattr(mem, "content"):
            return str(mem.content)
        if hasattr(mem, "record"):
            return str(mem.record.content)
        return str(mem)

    @staticmethod
    def _get_timestamp(mem: Any) -> float:
        if hasattr(mem, "created_at"):
            return float(mem.created_at)
        if hasattr(mem, "record"):
            return float(mem.record.created_at)
        return 0.0

    @staticmethod
    def _get_tags(mem: Any) -> list[str]:
        if hasattr(mem, "tags"):
            return list(mem.tags)
        if hasattr(mem, "record"):
            return list(mem.record.tags)
        return []

    @staticmethod
    def _get_agent(mem: Any) -> str:
        if hasattr(mem, "agent_id"):
            return str(mem.agent_id)
        if hasattr(mem, "record"):
            return str(mem.record.agent_id)
        return "unknown"

    def stats(self) -> dict[str, Any]:
        """Return clustering statistics."""
        return {
            "cluster_count": self._cluster_count,
        }
