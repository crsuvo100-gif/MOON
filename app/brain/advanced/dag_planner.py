"""DAG-based task planning with dependency resolution.

Builds a directed acyclic graph of subtasks, resolves dependencies,
and produces an execution plan with parallelizable stages.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class NodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DAGNode:
    """A node in the task DAG."""
    id: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.PENDING
    result: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DAGPlan:
    """A complete DAG execution plan."""
    nodes: dict[str, DAGNode]
    stages: list[list[str]]  # Each stage is a list of node IDs that can run in parallel
    total_nodes: int
    completed_nodes: int = 0
    failed_nodes: int = 0

    @property
    def is_complete(self) -> bool:
        return self.completed_nodes + self.failed_nodes >= self.total_nodes

    @property
    def progress(self) -> float:
        if self.total_nodes == 0:
            return 1.0
        return (self.completed_nodes + self.failed_nodes) / self.total_nodes


class DAGPlanner:
    """Plans task execution as a DAG with dependency resolution.

    Given a list of subtasks with dependencies, produces a staged
    execution plan where each stage contains nodes that can run in parallel.
    """

    def __init__(self, *, max_stages: int = 20) -> None:
        self._max_stages = max_stages

    def plan(self, subtasks: list[dict[str, Any]]) -> DAGPlan:
        """Build a DAG plan from subtasks.

        Args:
            subtasks: List of dicts with keys: id, description, dependencies (optional).

        Returns:
            DAGPlan with nodes and execution stages.
        """
        nodes: dict[str, DAGNode] = {}
        for st in subtasks:
            node_id = st.get("id", "")
            if not node_id:
                continue
            nodes[node_id] = DAGNode(
                id=node_id,
                description=st.get("description", ""),
                dependencies=st.get("dependencies", []),
                metadata=st.get("metadata", {}),
            )

        # Validate dependencies exist
        for node in nodes.values():
            node.dependencies = [d for d in node.dependencies if d in nodes]

        # Topological sort into stages
        stages: list[list[str]] = []
        completed: set[str] = set()
        remaining = set(nodes.keys())

        while remaining and len(stages) < self._max_stages:
            # Find nodes whose dependencies are all satisfied
            ready = [
                nid for nid in remaining
                if all(d in completed for d in nodes[nid].dependencies)
            ]
            if not ready:
                # Circular dependency or missing dependency — break remaining into a stage
                logger.warning("DAG has %d unresolvable nodes", len(remaining))
                stages.append(list(remaining))
                break
            stages.append(ready)
            completed.update(ready)
            remaining -= set(ready)

        return DAGPlan(
            nodes=nodes,
            stages=stages,
            total_nodes=len(nodes),
        )

    async def execute(
        self,
        plan: DAGPlan,
        *,
        executor: Any,  # Callable[[DAGNode], Awaitable[str]]
        on_stage_complete: Any | None = None,  # Callable[[int, list[DAGNode]], Awaitable[None]]
        max_concurrency: int = 5,
    ) -> DAGPlan:
        """Execute a DAG plan stage by stage.

        Args:
            plan: The DAG plan to execute.
            executor: Async callable that takes a DAGNode and returns a result string.
            on_stage_complete: Optional callback after each stage.
            max_concurrency: Max parallel executions per stage.

        Returns:
            The updated DAGPlan with results.
        """
        for stage_idx, stage in enumerate(plan.stages):
            # Execute nodes in this stage with bounded concurrency
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _run_node(node_id: str) -> None:
                async with semaphore:
                    node = plan.nodes[node_id]
                    node.status = NodeStatus.RUNNING
                    try:
                        result = await executor(node)
                        node.result = result
                        node.status = NodeStatus.COMPLETED
                        plan.completed_nodes += 1
                    except Exception as exc:
                        node.result = f"Error: {exc}"
                        node.status = NodeStatus.FAILED
                        plan.failed_nodes += 1
                        logger.warning("DAG node %s failed: %s", node_id, exc)

            await asyncio.gather(*[_run_node(nid) for nid in stage])

            if on_stage_complete:
                try:
                    await on_stage_complete(stage_idx, [plan.nodes[nid] for nid in stage])
                except Exception as exc:
                    logger.warning("Stage callback failed: %s", exc)

        return plan

    def get_ready_nodes(self, plan: DAGPlan) -> list[DAGNode]:
        """Get nodes that are ready to execute (all dependencies satisfied)."""
        ready = []
        for node in plan.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps_satisfied = all(
                plan.nodes[d].status == NodeStatus.COMPLETED
                for d in node.dependencies
                if d in plan.nodes
            )
            if deps_satisfied:
                ready.append(node)
        return ready

    def get_execution_order(self, plan: DAGPlan) -> list[str]:
        """Get a flat execution order (topological sort)."""
        order: list[str] = []
        for stage in plan.stages:
            order.extend(stage)
        return order
