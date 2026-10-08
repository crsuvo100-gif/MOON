"""Association engine -- build semantic associations between memories.

Professional AI assistants don't just store isolated facts; they build
a web of associations between related memories. This module:

1. Discovers associations between memories using keyword overlap,
   tag similarity, temporal proximity, and shared context.
2. Scores association strength (0.0-1.0).
3. Traverses the association graph to find related memories.
4. Suggests new associations based on transitive relationships.
5. Prunes weak associations to keep the graph manageable.

The association engine complements the existing memory graph by
providing richer, weighted, typed associations.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Association:
    """A typed, weighted association between two memories."""
    source_id: str
    target_id: str
    strength: float              # 0.0-1.0
    association_type: str        # "keyword", "tag", "temporal", "context", "transitive"
    shared_keywords: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "strength": round(self.strength, 4),
            "association_type": self.association_type,
            "shared_keywords": self.shared_keywords,
            "created_at": self.created_at,
        }


@dataclass
class AssociationPath:
    """A path through the association graph."""
    path: list[str]              # memory IDs in order
    total_strength: float        # product of edge strengths
    hops: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "total_strength": round(self.total_strength, 4),
            "hops": self.hops,
        }


class AssociationEngine:
    """Builds and queries semantic associations between memories.

    Usage:
        engine = AssociationEngine(memory_manager)
        await engine.build_associations()
        related = await engine.get_related("mem_1", max_hops=2)
        paths = await engine.find_paths("mem_1", "mem_2")
    """

    def __init__(
        self,
        memory_manager=None,
        min_strength: float = 0.1,
        max_associations_per_memory: int = 20,
    ) -> None:
        self._mm = memory_manager
        self._min_strength = min_strength
        self._max_per_memory = max_associations_per_memory
        self._associations: dict[str, list[Association]] = {}  # source_id -> [Association]
        self._built = False

    async def build_associations(self) -> int:
        """Build associations between all memories.

        Returns:
            Number of associations created.
        """
        if self._mm is None:
            return 0

        count = 0
        try:
            # Gather all memories with their content and tags
            memories = await self._gather_memories()
            if not memories:
                return 0

            # Build associations between all pairs
            for i, (id_a, content_a, tags_a, ts_a) in enumerate(memories):
                for id_b, content_b, tags_b, ts_b in memories[i+1:]:
                    strength, assoc_type, shared = self._compute_association(
                        content_a, tags_a, ts_a,
                        content_b, tags_b, ts_b,
                    )
                    if strength >= self._min_strength:
                        assoc = Association(
                            source_id=id_a,
                            target_id=id_b,
                            strength=strength,
                            association_type=assoc_type,
                            shared_keywords=shared,
                        )
                        self._associations.setdefault(id_a, []).append(assoc)
                        # Bidirectional
                        reverse = Association(
                            source_id=id_b,
                            target_id=id_a,
                            strength=strength,
                            association_type=assoc_type,
                            shared_keywords=shared,
                        )
                        self._associations.setdefault(id_b, []).append(reverse)
                        count += 1

            # Prune weak associations
            self._prune_associations()
            self._built = True
            logger.info("Association engine: built %d associations", count)
        except Exception as exc:
            logger.warning("Association building failed: %s", exc)
        return count

    async def _gather_memories(self) -> list[tuple[str, str, list[str], float]]:
        """Gather all memories as (id, content, tags, timestamp) tuples."""
        memories: list[tuple[str, str, list[str], float]] = []
        try:
            if hasattr(self._mm, '_ltm'):
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    entries = loop.run_until_complete(self._mm._ltm.all())
                except RuntimeError:
                    entries = []
                for entry in entries:
                    tags = getattr(entry, 'tags', [])
                    inner = getattr(entry, 'entry', entry)
                    tags = getattr(inner, 'tags', tags)
                    ts = getattr(inner, 'created_at', time.time())
                    memories.append((entry.id, entry.content, tags, ts))
        except Exception as exc:
            logger.debug("Gather memories failed: %s", exc)
        return memories

    def _compute_association(
        self,
        content_a: str, tags_a: list[str], ts_a: float,
        content_b: str, tags_b: list[str], ts_b: float,
    ) -> tuple[float, str, list[str]]:
        """Compute association strength between two memories.

        Returns (strength, type, shared_keywords).
        """
        words_a = set(content_a.lower().split())
        words_b = set(content_b.lower().split())
        shared_words = words_a & words_b

        # Keyword overlap score
        kw_score = len(shared_words) / max(len(words_a | words_b), 1)

        # Tag overlap score
        tag_a = set(t.lower() for t in tags_a)
        tag_b = set(t.lower() for t in tags_b)
        shared_tags = tag_a & tag_b
        tag_score = len(shared_tags) / max(len(tag_a | tag_b), 1)

        # Temporal proximity score (exponential decay with time diff)
        time_diff = abs(ts_a - ts_b)
        temporal_score = math.exp(-time_diff / (86400.0 * 7))  # 7-day half-life

        # Determine primary association type and combined strength
        scores = {
            "keyword": kw_score,
            "tag": tag_score,
            "temporal": temporal_score,
        }
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # Combined score: weighted combination
        combined = 0.4 * kw_score + 0.3 * tag_score + 0.3 * temporal_score

        return combined, best_type, list(shared_words)[:10]

    def _prune_associations(self) -> None:
        """Keep only the top N strongest associations per memory."""
        for source_id in self._associations:
            assocs = self._associations[source_id]
            if len(assocs) > self._max_per_memory:
                assocs.sort(key=lambda a: a.strength, reverse=True)
                self._associations[source_id] = assocs[:self._max_per_memory]

    async def get_related(
        self,
        memory_id: str,
        max_hops: int = 1,
        min_strength: float | None = None,
    ) -> list[Association]:
        """Get all associations for a memory, optionally traversing multiple hops.

        Args:
            memory_id: The memory to find associations for.
            max_hops: How many hops to traverse (1 = direct only).
            min_strength: Minimum association strength to include.

        Returns:
            List of Association objects.
        """
        thresh = min_strength or self._min_strength
        visited: set[str] = {memory_id}
        results: list[Association] = []
        current_level = [memory_id]

        for _ in range(max_hops):
            next_level: list[str] = []
            for mid in current_level:
                for assoc in self._associations.get(mid, []):
                    if assoc.strength >= thresh and assoc.target_id not in visited:
                        results.append(assoc)
                        visited.add(assoc.target_id)
                        next_level.append(assoc.target_id)
            current_level = next_level
            if not current_level:
                break

        return results

    async def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 3,
    ) -> list[AssociationPath]:
        """Find all paths between two memories through the association graph.

        Uses BFS with depth limit.
        """
        paths: list[AssociationPath] = []
        # BFS: (current_id, path_so_far, strength_so_far)
        queue: list[tuple[str, list[str], float]] = [(source_id, [source_id], 1.0)]

        while queue:
            current, path, strength = queue.pop(0)
            if len(path) > max_hops + 1:
                continue
            for assoc in self._associations.get(current, []):
                if assoc.target_id in path:
                    continue  # avoid cycles
                new_path = path + [assoc.target_id]
                new_strength = strength * assoc.strength
                if assoc.target_id == target_id:
                    paths.append(AssociationPath(
                        path=new_path,
                        total_strength=new_strength,
                        hops=len(new_path) - 1,
                    ))
                else:
                    queue.append((assoc.target_id, new_path, new_strength))

        paths.sort(key=lambda p: p.total_strength, reverse=True)
        return paths

    async def suggest_new_associations(self) -> list[Association]:
        """Suggest new associations based on transitive relationships.

        If A->B and B->C exist, suggest A->C if not already present.
        """
        suggestions: list[Association] = []
        existing_pairs: set[tuple[str, str]] = set()

        for source_id, assocs in self._associations.items():
            for assoc in assocs:
                existing_pairs.add((source_id, assoc.target_id))

        for source_id, assocs in self._associations.items():
            for assoc in assocs:
                # source_id -> assoc.target_id -> ?
                for second_hop in self._associations.get(assoc.target_id, []):
                    pair = (source_id, second_hop.target_id)
                    if pair not in existing_pairs and source_id != second_hop.target_id:
                        # Transitive suggestion
                        strength = assoc.strength * second_hop.strength * 0.5  # decay
                        if strength >= self._min_strength:
                            suggestions.append(Association(
                                source_id=source_id,
                                target_id=second_hop.target_id,
                                strength=strength,
                                association_type="transitive",
                            ))
                            existing_pairs.add(pair)

        return suggestions

    def get_stats(self) -> dict[str, Any]:
        """Return association engine statistics."""
        total = sum(len(a) for a in self._associations.values())
        by_type: dict[str, int] = {}
        for assocs in self._associations.values():
            for a in assocs:
                by_type[a.association_type] = by_type.get(a.association_type, 0) + 1
        return {
            "total_associations": total,
            "memories_with_associations": len(self._associations),
            "by_type": by_type,
            "built": self._built,
            "min_strength": self._min_strength,
        }

    def stats(self) -> dict[str, Any]:
        """Alias for get_stats."""
        return self.get_stats()
