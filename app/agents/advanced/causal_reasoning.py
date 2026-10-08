"""causal_reasoning.py — causal inference and root cause analysis.

Professional AI agents reason about cause and effect, not just correlation.
This module provides causal reasoning capabilities including causal graph
construction, counterfactual analysis, root cause identification, and
intervention planning.

Causal reasoning capabilities:
- Causal graph construction from observations
- Counterfactual analysis (what-if scenarios)
- Root cause identification via causal chains
- Intervention planning and effect prediction
- Causal discovery from temporal data
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class CausalRelationType(str, Enum):
    CAUSES = "causes"
    PREVENTS = "prevents"
    ENABLES = "enables"
    INHIBITS = "inhibits"
    CORRELATES = "correlates"  # non-causal association


class InterventionType(str, Enum):
    DO = "do"  # Pearl's do-operator
    CONDITION = "condition"  # observe/condition on
    COUNTERFACTUAL = "counterfactual"  # what if


@dataclass
class CausalNode:
    node_id: str
    label: str
    description: str = ""
    node_type: str = "event"  # event, action, outcome, latent
    probability: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CausalEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation_type: CausalRelationType
    strength: float = 0.5  # 0-1
    confidence: float = 0.5  # 0-1
    evidence: list[str] = field(default_factory=list)
    is_temporal: bool = True  # source happens before target
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CausalGraph:
    graph_id: str
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    edges: list[CausalEdge] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: CausalNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: CausalEdge) -> None:
        self.edges.append(edge)

    def get_parents(self, node_id: str) -> list[CausalNode]:
        """Get direct parents (causes) of a node."""
        parent_ids = [e.source_id for e in self.edges if e.target_id == node_id]
        return [self.nodes[pid] for pid in parent_ids if pid in self.nodes]

    def get_children(self, node_id: str) -> list[CausalNode]:
        """Get direct children (effects) of a node."""
        child_ids = [e.target_id for e in self.edges if e.source_id == node_id]
        return [self.nodes[cid] for cid in child_ids if cid in self.nodes]

    def get_ancestors(self, node_id: str) -> list[str]:
        """Get all ancestors (transitive causes)."""
        visited: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for parent in self.get_parents(current):
                if parent.node_id not in visited:
                    visited.add(parent.node_id)
                    stack.append(parent.node_id)
        return list(visited)

    def get_descendants(self, node_id: str) -> list[str]:
        """Get all descendants (transitive effects)."""
        visited: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for child in self.get_children(current):
                if child.node_id not in visited:
                    visited.add(child.node_id)
                    stack.append(child.node_id)
        return list(visited)

    def get_root_causes(self) -> list[CausalNode]:
        """Get nodes with no parents (root causes)."""
        has_parents = {e.target_id for e in self.edges}
        return [n for nid, n in self.nodes.items() if nid not in has_parents]

    def get_leaf_effects(self) -> list[CausalNode]:
        """Get nodes with no children (final effects)."""
        has_children = {e.source_id for e in self.edges}
        return [n for nid, n in self.nodes.items() if nid not in has_children]


@dataclass
class CounterfactualScenario:
    scenario_id: str
    base_scenario: str
    intervention: dict[str, Any]  # variable -> value
    predicted_outcome: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class RootCauseAnalysis:
    analysis_id: str
    symptom: str
    root_causes: list[CausalNode] = field(default_factory=list)
    causal_chains: list[list[str]] = field(default_factory=list)  # node_id paths
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class InterventionPlan:
    plan_id: str
    target: str
    intervention: dict[str, Any]
    predicted_effects: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class CausalReasoner:
    """Causal inference and root cause analysis engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._graphs: dict[str, CausalGraph] = {}

    def create_graph(self, name: str, description: str = "") -> CausalGraph:
        """Create a new causal graph."""
        graph = CausalGraph(
            graph_id=str(uuid.uuid4())[:8],
            metadata={"name": name, "description": description},
        )
        self._graphs[graph.graph_id] = graph
        return graph

    def get_graph(self, graph_id: str) -> CausalGraph | None:
        return self._graphs.get(graph_id)

    async def analyze_root_cause(
        self,
        graph: CausalGraph,
        symptom_node_id: str,
        max_depth: int = 5,
    ) -> RootCauseAnalysis:
        """Analyze root causes of a symptom in a causal graph."""
        analysis = RootCauseAnalysis(
            analysis_id=str(uuid.uuid4())[:8],
            symptom=symptom_node_id,
        )

        if symptom_node_id not in graph.nodes:
            logger.warning("Symptom node %s not in graph", symptom_node_id)
            return analysis

        # Find all ancestors (potential root causes)
        ancestor_ids = graph.get_ancestors(symptom_node_id)
        ancestors = [graph.nodes[aid] for aid in ancestor_ids if aid in graph.nodes]

        # Filter to root causes (no parents in the graph)
        root_causes = [a for a in ancestors if not graph.get_parents(a.node_id)]
        analysis.root_causes = root_causes

        # Build causal chains (paths from roots to symptom)
        analysis.causal_chains = self._find_causal_chains(graph, symptom_node_id, max_depth)

        # Compute confidence based on evidence and graph completeness
        analysis.confidence = self._compute_analysis_confidence(graph, root_causes, analysis.causal_chains)

        # Generate recommendations
        analysis.recommendations = self._generate_recommendations(graph, root_causes, symptom_node_id)

        # If LLM agent available, enhance analysis
        if self._llm:
            try:
                prompt = self._build_rca_prompt(graph, symptom_node_id, root_causes, analysis.causal_chains)
                response = await self._llm(prompt, "root_cause_analysis")
                analysis.evidence.append(response[:500])
            except Exception as e:
                logger.warning("LLM RCA enhancement failed: %s", e)

        return analysis

    async def counterfactual_analysis(
        self,
        graph: CausalGraph,
        base_scenario: str,
        intervention: dict[str, Any],
    ) -> CounterfactualScenario:
        """Perform counterfactual analysis (what-if)."""
        scenario = CounterfactualScenario(
            scenario_id=str(uuid.uuid4())[:8],
            base_scenario=base_scenario,
            intervention=intervention,
        )

        # Predict effects by propagating intervention through graph
        predicted_effects = self._predict_intervention_effects(graph, intervention)
        scenario.predicted_outcome = ", ".join(predicted_effects) if predicted_effects else "No significant predicted effects"

        # Compute confidence
        scenario.confidence = self._compute_counterfactual_confidence(graph, intervention)

        # Build reasoning
        scenario.reasoning = self._build_counterfactual_reasoning(graph, intervention, predicted_effects)

        # If LLM available, enhance
        if self._llm:
            try:
                prompt = (
                    f"Counterfactual analysis for graph '{graph.metadata.get('name', 'unknown')}':\n"
                    f"Base scenario: {base_scenario}\n"
                    f"Intervention: {intervention}\n"
                    f"Predicted effects: {predicted_effects}\n"
                    f"Analyze this counterfactual scenario:"
                )
                response = await self._llm(prompt, "counterfactual_analysis")
                scenario.reasoning = response[:500]
            except Exception as e:
                logger.warning("LLM counterfactual enhancement failed: %s", e)

        return scenario

    async def plan_intervention(
        self,
        graph: CausalGraph,
        target_node_id: str,
        desired_outcome: str,
    ) -> InterventionPlan:
        """Plan an intervention to achieve a desired outcome."""
        plan = InterventionPlan(
            plan_id=str(uuid.uuid4())[:8],
            target=target_node_id,
            intervention={},
        )

        if target_node_id not in graph.nodes:
            logger.warning("Target node %s not in graph", target_node_id)
            return plan

        # Find causes of target that can be manipulated
        parents = graph.get_parents(target_node_id)
        manipulable = [p for p in parents if p.node_type in ("action", "event")]

        if manipulable:
            # Choose the parent with highest strength edge
            best_parent = None
            best_strength = 0.0
            for p in manipulable:
                for e in graph.edges:
                    if e.source_id == p.node_id and e.target_id == target_node_id:
                        if e.strength > best_strength:
                            best_strength = e.strength
                            best_parent = p

            if best_parent:
                plan.intervention = {
                    best_parent.node_id: f"modify {best_parent.label} to achieve {desired_outcome}"
                }
                plan.predicted_effects = [desired_outcome]
                plan.confidence = best_strength * 0.8  # discount for uncertainty

        # Find side effects (descendants of intervention targets)
        for target in plan.intervention:
            descendants = graph.get_descendants(target)
            plan.side_effects = [f"{graph.nodes[d].node_id}: {graph.nodes[d].label}" for d in descendants[:5] if d in graph.nodes]

        # If LLM available, enhance
        if self._llm:
            try:
                prompt = (
                    f"Plan intervention to achieve '{desired_outcome}' on node '{target_node_id}':\n"
                    f"Graph: {graph.metadata.get('name', 'unknown')}\n"
                    f"Causes: {[(p.node_id, p.label) for p in parents]}\n"
                    f"Suggest the best intervention strategy:"
                )
                response = await self._llm(prompt, "intervention_planning")
                if not plan.intervention:
                    plan.intervention = {"llm_suggestion": response[:200]}
            except Exception as e:
                logger.warning("LLM intervention planning failed: %s", e)

        return plan

    def _find_causal_chains(
        self,
        graph: CausalGraph,
        symptom_node_id: str,
        max_depth: int,
    ) -> list[list[str]]:
        """Find all causal chains from roots to symptom."""
        chains: list[list[str]] = []

        def dfs(current: str, path: list[str], depth: int) -> None:
            if depth > max_depth:
                return
            parents = graph.get_parents(current)
            if not parents:
                # Reached a root
                chains.append(list(reversed(path + [current])))
                return
            for parent in parents:
                if parent.node_id not in path:  # avoid cycles
                    dfs(parent.node_id, path + [current], depth + 1)

        dfs(symptom_node_id, [], 0)
        return chains

    def _compute_analysis_confidence(
        self,
        graph: CausalGraph,
        root_causes: list[CausalNode],
        chains: list[list[str]],
    ) -> float:
        """Compute confidence in root cause analysis."""
        if not root_causes:
            return 0.0
        # More root causes with more chains = higher confidence
        base = min(len(root_causes) * 0.1, 0.3)
        chain_bonus = min(len(chains) * 0.05, 0.3)
        # Edge confidence avg
        if graph.edges:
            edge_conf = sum(e.confidence for e in graph.edges) / len(graph.edges)
        else:
            edge_conf = 0.3
        return min(base + chain_bonus + edge_conf * 0.4, 1.0)

    def _generate_recommendations(
        self,
        graph: CausalGraph,
        root_causes: list[CausalNode],
        symptom_node_id: str,
    ) -> list[str]:
        """Generate recommendations based on root cause analysis."""
        recs = []
        for rc in root_causes:
            recs.append(f"Address root cause: {rc.label} ({rc.description})")
        if not root_causes:
            recs.append("No root causes identified in causal graph — consider collecting more data")
        return recs

    def _predict_intervention_effects(
        self,
        graph: CausalGraph,
        intervention: dict[str, Any],
    ) -> list[str]:
        """Predict effects of an intervention by propagating through graph."""
        effects = []
        for node_id in intervention:
            if node_id in graph.nodes:
                descendants = graph.get_descendants(node_id)
                for d in descendants:
                    if d in graph.nodes:
                        effects.append(f"{graph.nodes[d].node_id}: {graph.nodes[d].label}")
        return effects

    def _compute_counterfactual_confidence(
        self,
        graph: CausalGraph,
        intervention: dict[str, Any],
    ) -> float:
        """Compute confidence in counterfactual prediction."""
        if not intervention:
            return 0.0
        # Check if intervention targets exist in graph
        valid_targets = sum(1 for k in intervention if k in graph.nodes)
        coverage = valid_targets / len(intervention) if intervention else 0
        # Edge confidence
        if graph.edges:
            edge_conf = sum(e.confidence for e in graph.edges) / len(graph.edges)
        else:
            edge_conf = 0.3
        return min(coverage * 0.5 + edge_conf * 0.5, 1.0)

    def _build_counterfactual_reasoning(
        self,
        graph: CausalGraph,
        intervention: dict[str, Any],
        predicted_effects: list[str],
    ) -> str:
        """Build human-readable counterfactual reasoning."""
        parts = ["Counterfactual Analysis:"]
        for var, val in intervention.items():
            if var in graph.nodes:
                parts.append(f"  Intervention: Set '{graph.nodes[var].label}' to '{val}'")
        if predicted_effects:
            parts.append("  Predicted effects:")
            for e in predicted_effects:
                parts.append(f"    - {e}")
        else:
            parts.append("  No significant predicted effects")
        return "\n".join(parts)

    def _build_rca_prompt(
        self,
        graph: CausalGraph,
        symptom_node_id: str,
        root_causes: list[CausalNode],
        chains: list[list[str]],
    ) -> str:
        """Build prompt for LLM-enhanced root cause analysis."""
        parts = [
            f"Root cause analysis for symptom: {graph.nodes[symptom_node_id].label}",
            f"Root causes found: {[(rc.node_id, rc.label) for rc in root_causes]}",
            f"Causal chains: {chains}",
            f"Graph: {graph.metadata.get('name', 'unknown')}",
            "Provide deeper analysis of the root causes and their interactions:",
        ]
        return "\n".join(parts)

    def list_graphs(self) -> list[str]:
        return list(self._graphs.keys())
