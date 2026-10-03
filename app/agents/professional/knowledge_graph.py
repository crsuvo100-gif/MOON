"""Knowledge Graph — integrated knowledge representation.

Maintains a lightweight knowledge graph of entities, relationships,
and facts learned during agent operation. Supports semantic search,
inference, and context enrichment.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class EntityType(Enum):
    PERSON = "person"
    PROJECT = "project"
    CONCEPT = "concept"
    TOOL = "tool"
    FILE = "file"
    TASK = "task"
    DECISION = "decision"
    PREFERENCE = "preference"
    FACT = "fact"


class RelationType(Enum):
    USES = "uses"
    DEPENDS_ON = "depends_on"
    CREATED = "created"
    OWNS = "owns"
    PREFERS = "prefers"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    LEARNED = "learned"
    DECIDED = "decided"


@dataclass
class Entity:
    """A knowledge graph entity."""
    id: str
    name: str
    entity_type: EntityType
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    confidence: float = 1.0


@dataclass
class Relationship:
    """A relationship between two entities."""
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)


@dataclass
class Fact:
    """A learned fact."""
    id: str
    statement: str
    source: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    verified: bool = False
    tags: list[str] = field(default_factory=list)


class KnowledgeGraph:
    """Lightweight knowledge graph for agent memory.

    Stores entities, relationships, and facts learned during
    operation. Supports semantic search and inference.
    """

    def __init__(self, *, storage_path: str = ".moon/knowledge_graph.json") -> None:
        self._entities: dict[str, Entity] = {}
        self._relationships: dict[str, Relationship] = {}
        self._facts: dict[str, Fact] = {}
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._storage_path = Path(storage_path)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._metrics: dict[str, int] = defaultdict(int)

    def add_entity(
        self,
        name: str,
        entity_type: EntityType,
        *,
        properties: dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> Entity:
        """Add an entity to the graph."""
        # Check for existing entity
        for entity in self._entities.values():
            if entity.name == name and entity.entity_type == entity_type:
                entity.updated_at = time.time()
                if properties:
                    entity.properties.update(properties)
                return entity

        entity = Entity(
            id=str(uuid.uuid4())[:8],
            name=name,
            entity_type=entity_type,
            properties=properties or {},
            confidence=confidence,
        )
        self._entities[entity.id] = entity
        self._metrics["entities_added"] += 1
        return entity

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        *,
        properties: dict[str, Any] | None = None,
        confidence: float = 1.0,
    ) -> Relationship | None:
        """Add a relationship between two entities."""
        if source_id not in self._entities or target_id not in self._entities:
            return None

        rel = Relationship(
            id=str(uuid.uuid4())[:8],
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            confidence=confidence,
        )
        self._relationships[rel.id] = rel
        self._adjacency[source_id].append(target_id)
        self._metrics["relationships_added"] += 1
        return rel

    def add_fact(
        self,
        statement: str,
        *,
        source: str = "agent",
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> Fact:
        """Add a learned fact."""
        fact = Fact(
            id=str(uuid.uuid4())[:8],
            statement=statement,
            source=source,
            confidence=confidence,
            tags=tags or [],
        )
        self._facts[fact.id] = fact
        self._metrics["facts_added"] += 1
        return fact

    def search(
        self,
        query: str,
        *,
        entity_type: EntityType | None = None,
        limit: int = 10,
    ) -> list[Entity]:
        """Search entities by name and properties."""
        query_lower = query.lower()
        results = []

        for entity in self._entities.values():
            if entity_type and entity.entity_type != entity_type:
                continue

            # Name match
            if query_lower in entity.name.lower():
                results.append(entity)
                continue

            # Property match
            for value in entity.properties.values():
                if isinstance(value, str) and query_lower in value.lower():
                    results.append(entity)
                    break

        # Sort by confidence
        results.sort(key=lambda e: e.confidence, reverse=True)
        self._metrics["searches"] += 1
        return results[:limit]

    def get_related(
        self,
        entity_id: str,
        *,
        relation_type: RelationType | None = None,
    ) -> list[tuple[Entity, Relationship]]:
        """Get related entities."""
        results = []
        for rel_id, rel in self._relationships.items():
            if rel.source_id == entity_id or rel.target_id == entity_id:
                if relation_type and rel.relation_type != relation_type:
                    continue
                other_id = rel.target_id if rel.source_id == entity_id else rel.source_id
                other = self._entities.get(other_id)
                if other:
                    results.append((other, rel))
        return results

    def infer(self, entity_id: str, depth: int = 2) -> list[Fact]:
        """Infer facts from the knowledge graph."""
        inferred = []
        visited = set()
        queue = [(entity_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_id in visited or current_depth > depth:
                continue
            visited.add(current_id)

            entity = self._entities.get(current_id)
            if not entity:
                continue

            # Generate inferred facts
            for rel_id, rel in self._relationships.items():
                if rel.source_id == current_id:
                    target = self._entities.get(rel.target_id)
                    if target:
                        statement = f"{entity.name} {rel.relation_type.value} {target.name}"
                        inferred.append(Fact(
                            id=str(uuid.uuid4())[:8],
                            statement=statement,
                            source="inference",
                            confidence=rel.confidence * 0.8,
                            tags=["inferred"],
                        ))
                        queue.append((rel.target_id, current_depth + 1))

        self._metrics["inferences"] += 1
        return inferred

    def get_context_enrichment(self, query: str) -> str:
        """Get context enrichment for a query."""
        entities = self.search(query, limit=5)
        if not entities:
            return ""

        parts = []
        for entity in entities:
            related = self.get_related(entity.id)
            if related:
                rel_strs = [f"{r.relation_type.value} {e.name}" for e, r in related[:3]]
                parts.append(f"{entity.name} ({entity.entity_type.value}): {', '.join(rel_strs)}")
            else:
                parts.append(f"{entity.name} ({entity.entity_type.value})")

        return "\n".join(parts)

    def export_graph(self) -> dict[str, Any]:
        """Export the full graph."""
        return {
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "type": e.entity_type.value,
                    "properties": e.properties,
                    "confidence": e.confidence,
                }
                for e in self._entities.values()
            ],
            "relationships": [
                {
                    "id": r.id,
                    "source": r.source_id,
                    "target": r.target_id,
                    "type": r.relation_type.value,
                    "confidence": r.confidence,
                }
                for r in self._relationships.values()
            ],
            "facts": [
                {
                    "id": f.id,
                    "statement": f.statement,
                    "source": f.source,
                    "confidence": f.confidence,
                    "verified": f.verified,
                }
                for f in self._facts.values()
            ],
        }

    async def save(self) -> None:
        """Persist the graph to disk."""
        try:
            data = self.export_graph()
            self._storage_path.write_text(json.dumps(data, indent=2, default=str))
            logger.info("Knowledge graph saved (%d entities, %d relationships)", len(self._entities), len(self._relationships))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save knowledge graph: %s", exc)

    async def load(self) -> bool:
        """Load the graph from disk."""
        if not self._storage_path.exists():
            return False

        try:
            data = json.loads(self._storage_path.read_text())
            for e_data in data.get("entities", []):
                entity = Entity(
                    id=e_data["id"],
                    name=e_data["name"],
                    entity_type=EntityType(e_data["type"]),
                    properties=e_data.get("properties", {}),
                    confidence=e_data.get("confidence", 1.0),
                )
                self._entities[entity.id] = entity

            for r_data in data.get("relationships", []):
                rel = Relationship(
                    id=r_data["id"],
                    source_id=r_data["source"],
                    target_id=r_data["target"],
                    relation_type=RelationType(r_data["type"]),
                    confidence=r_data.get("confidence", 1.0),
                )
                self._relationships[rel.id] = rel
                self._adjacency[rel.source_id].append(rel.target_id)

            for f_data in data.get("facts", []):
                fact = Fact(
                    id=f_data["id"],
                    statement=f_data["statement"],
                    source=f_data["source"],
                    confidence=f_data["confidence"],
                    verified=f_data.get("verified", False),
                )
                self._facts[fact.id] = fact

            logger.info("Knowledge graph loaded (%d entities, %d relationships)", len(self._entities), len(self._relationships))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load knowledge graph: %s", exc)
            return False

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "total_entities": len(self._entities),
            "total_relationships": len(self._relationships),
            "total_facts": len(self._facts),
        }
