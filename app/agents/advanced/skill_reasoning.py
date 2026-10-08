"""skill_reasoning.py — skill discovery, selection, and composition.

Professional AI agents reason about their capabilities, select appropriate
skills for tasks, and compose skills to solve complex problems. This module
provides skill reasoning capabilities including skill discovery, skill
selection, skill composition, and capability assessment.

Skill reasoning capabilities:
- Skill discovery and inventory
- Skill selection based on task requirements
- Skill composition for complex tasks
- Capability assessment and gap analysis
- Skill learning and improvement tracking
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


class SkillCategory(str, Enum):
    ANALYSIS = "analysis"
    CREATION = "creation"
    COMMUNICATION = "communication"
    REASONING = "reasoning"
    EXECUTION = "execution"
    LEARNING = "learning"
    SOCIAL = "social"


class SkillLevel(str, Enum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class SkillStatus(str, Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    LEARNING = "learning"
    DEPRECATED = "deprecated"


@dataclass
class Skill:
    skill_id: str
    name: str
    description: str
    category: SkillCategory
    level: SkillLevel = SkillLevel.INTERMEDIATE
    status: SkillStatus = SkillStatus.AVAILABLE
    prerequisites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    success_rate: float = 0.0  # 0-1
    usage_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def record_usage(self, success: bool = True) -> None:
        self.usage_count += 1
        self.last_used = time.time()
        # Update success rate with exponential moving average
        alpha = 0.1
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (1.0 if success else 0.0)


@dataclass
class SkillRequirement:
    requirement_id: str
    description: str
    category: SkillCategory | None = None
    min_level: SkillLevel = SkillLevel.NOVICE
    mandatory: bool = True
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillSelection:
    selection_id: str
    task: str
    requirements: list[SkillRequirement] = field(default_factory=list)
    selected_skills: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SkillComposition:
    composition_id: str
    name: str
    skills: list[str] = field(default_factory=list)
    task: str = ""
    execution_order: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class CapabilityAssessment:
    assessment_id: str
    agent_id: str
    skills: list[str] = field(default_factory=list)
    overall_level: SkillLevel = SkillLevel.NOVICE
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class SkillReasoner:
    """Skill discovery, selection, and composition engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._skills: dict[str, Skill] = {}
        self._selections: dict[str, SkillSelection] = {}
        self._compositions: dict[str, SkillComposition] = {}
        self._assessments: dict[str, CapabilityAssessment] = {}

    def register_skill(
        self,
        name: str,
        description: str,
        category: SkillCategory,
        level: SkillLevel = SkillLevel.INTERMEDIATE,
        prerequisites: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        """Register a new skill."""
        skill = Skill(
            skill_id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            category=category,
            level=level,
            prerequisites=prerequisites or [],
            tags=tags or [],
        )
        self._skills[skill.skill_id] = skill
        return skill

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_skills(
        self,
        category: SkillCategory | None = None,
        status: SkillStatus | None = None,
    ) -> list[Skill]:
        """List skills with optional filtering."""
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        if status:
            skills = [s for s in skills if s.status == status]
        return skills

    async def select_skills(
        self,
        task: str,
        requirements: list[SkillRequirement] | None = None,
        context: str = "",
    ) -> SkillSelection:
        """Select appropriate skills for a task."""
        selection = SkillSelection(
            selection_id=str(uuid.uuid4())[:8],
            task=task,
            requirements=requirements or [],
        )

        # Generate requirements if not provided
        if not requirements and self._llm:
            try:
                prompt = (
                    f"Analyze this task and identify skill requirements:\n"
                    f"Task: {task}\n"
                    f"Context: {context}\n"
                    f"Respond with JSON array of requirements, each with: "
                    f"description, category, min_level, mandatory, weight"
                )
                response = await self._llm(prompt, "skill_requirements")
                selection.requirements = self._parse_requirements(response)
            except Exception as e:
                logger.warning("LLM skill requirements failed: %s", e)
                selection.requirements = self._default_requirements(task)
        elif not requirements:
            selection.requirements = self._default_requirements(task)

        # Score all skills against requirements
        available = [s for s in self._skills.values() if s.status == SkillStatus.AVAILABLE]
        for skill in available:
            score = self._score_skill_for_requirements(skill, selection.requirements)
            selection.scores[skill.skill_id] = score

        # Select top skills
        ranked = sorted(selection.scores.items(), key=lambda x: x[1], reverse=True)
        # Filter by mandatory requirements
        mandatory_cats = {r.category for r in selection.requirements if r.mandatory and r.category}
        selected = []
        for skill_id, score in ranked:
            skill = self._skills[skill_id]
            if score > 0.3:  # minimum threshold
                selected.append(skill_id)
            if mandatory_cats and skill.category in mandatory_cats:
                mandatory_cats.discard(skill.category)
            if not mandatory_cats and len(selected) >= 3:
                break

        selection.selected_skills = selected
        selection.confidence = self._compute_selection_confidence(selection)
        selection.reasoning = self._build_selection_reasoning(selection)

        self._selections[selection.selection_id] = selection
        return selection

    async def compose_skills(
        self,
        task: str,
        skill_ids: list[str],
        context: str = "",
    ) -> SkillComposition:
        """Compose multiple skills for complex task execution."""
        composition = SkillComposition(
            composition_id=str(uuid.uuid4())[:8],
            name=f"Composition for {task}",
            skills=skill_ids,
            task=task,
        )

        # Determine execution order based on dependencies
        composition.execution_order = self._determine_execution_order(skill_ids)
        composition.dependencies = self._build_dependency_graph(skill_ids)

        # LLM enhancement
        if self._llm:
            try:
                prompt = (
                    f"Compose skills for task: {task}\n"
                    f"Skills: {[(self._skills[sid].name, self._skills[sid].description) for sid in skill_ids if sid in self._skills]}\n"
                    f"Context: {context}\n"
                    f"Determine optimal execution order and dependencies:"
                )
                response = await self._llm(prompt, "skill_composition")
                # Parse response for execution order hints
                composition.metadata["llm_suggestion"] = response[:300]
            except Exception as e:
                logger.warning("LLM skill composition failed: %s", e)

        self._compositions[composition.composition_id] = composition
        return composition

    async def assess_capabilities(
        self,
        agent_id: str,
        target_task: str = "",
    ) -> CapabilityAssessment:
        """Assess agent capabilities and identify gaps."""
        assessment = CapabilityAssessment(
            assessment_id=str(uuid.uuid4())[:8],
            agent_id=agent_id,
        )

        # Inventory current skills
        assessment.skills = [s.skill_id for s in self._skills.values() if s.status == SkillStatus.AVAILABLE]

        # Determine overall level
        if self._skills:
            levels = [s.level for s in self._skills.values()]
            level_values = {SkillLevel.NOVICE: 1, SkillLevel.INTERMEDIATE: 2, SkillLevel.ADVANCED: 3, SkillLevel.EXPERT: 4}
            avg_level = sum(level_values[l] for l in levels) / len(levels)
            if avg_level >= 3.5:
                assessment.overall_level = SkillLevel.EXPERT
            elif avg_level >= 2.5:
                assessment.overall_level = SkillLevel.ADVANCED
            elif avg_level >= 1.5:
                assessment.overall_level = SkillLevel.INTERMEDIATE
            else:
                assessment.overall_level = SkillLevel.NOVICE

        # Identify strengths (high success rate, high usage)
        strengths = [s for s in self._skills.values() if s.success_rate > 0.7 and s.usage_count > 5]
        assessment.strengths = [s.skill_id for s in strengths]

        # Identify gaps
        if target_task and self._llm:
            try:
                prompt = (
                    f"Assess capability gaps for task: {target_task}\n"
                    f"Current skills: {[(s.name, s.category.value, s.level.value) for s in self._skills.values()]}\n"
                    f"Identify missing skills and gaps:"
                )
                response = await self._llm(prompt, "capability_assessment")
                assessment.gaps = self._parse_gaps(response)
            except Exception as e:
                logger.warning("LLM capability assessment failed: %s", e)
                assessment.gaps = ["Unable to assess gaps without LLM"]
        else:
            assessment.gaps = ["No target task specified for gap analysis"]

        # Generate recommendations
        assessment.recommendations = self._generate_recommendations(assessment)

        self._assessments[assessment.assessment_id] = assessment
        return assessment

    def _score_skill_for_requirements(self, skill: Skill, requirements: list[SkillRequirement]) -> float:
        """Score a skill against requirements."""
        if not requirements:
            return 0.5
        total_score = 0.0
        total_weight = 0.0
        for req in requirements:
            weight = req.weight
            total_weight += weight
            # Category match
            if req.category and skill.category == req.category:
                total_score += weight * 0.4
            # Level match
            level_values = {SkillLevel.NOVICE: 1, SkillLevel.INTERMEDIATE: 2, SkillLevel.ADVANCED: 3, SkillLevel.EXPERT: 4}
            if level_values[skill.level] >= level_values[req.min_level]:
                total_score += weight * 0.3
            # Success rate
            total_score += weight * skill.success_rate * 0.2
            # Usage experience
            total_score += weight * min(skill.usage_count / 10, 1.0) * 0.1
        return total_score / max(total_weight, 1.0)

    def _compute_selection_confidence(self, selection: SkillSelection) -> float:
        """Compute confidence in skill selection."""
        if not selection.selected_skills:
            return 0.2
        # Average score of selected skills
        selected_scores = [selection.scores[sid] for sid in selection.selected_skills if sid in selection.scores]
        avg_score = sum(selected_scores) / max(len(selected_scores), 1)
        # Coverage of mandatory requirements
        mandatory = [r for r in selection.requirements if r.mandatory]
        if mandatory:
            covered = sum(1 for r in mandatory if any(self._skills[sid].category == r.category for sid in selection.selected_skills if sid in self._skills))
            coverage = covered / len(mandatory)
        else:
            coverage = 1.0
        return min(avg_score * 0.6 + coverage * 0.4, 1.0)

    def _build_selection_reasoning(self, selection: SkillSelection) -> str:
        """Build human-readable selection reasoning."""
        parts = [f"Skill selection for: {selection.task}"]
        parts.append(f"Selected {len(selection.selected_skills)} skills:")
        for sid in selection.selected_skills:
            if sid in self._skills:
                skill = self._skills[sid]
                parts.append(f"  - {skill.name} ({skill.category.value}, {skill.level.value}): {selection.scores.get(sid, 0):.3f}")
        return "\n".join(parts)

    def _determine_execution_order(self, skill_ids: list[str]) -> list[str]:
        """Determine optimal execution order based on dependencies."""
        # Topological sort based on prerequisites
        order = []
        visited = set()
        temp = set()

        def visit(sid: str) -> None:
            if sid in temp:
                return  # cycle detected
            if sid in visited:
                return
            temp.add(sid)
            if sid in self._skills:
                for prereq in self._skills[sid].prerequisites:
                    if prereq in skill_ids:
                        visit(prereq)
            temp.remove(sid)
            visited.add(sid)
            order.append(sid)

        for sid in skill_ids:
            visit(sid)
        return order

    def _build_dependency_graph(self, skill_ids: list[str]) -> dict[str, list[str]]:
        """Build dependency graph for skills."""
        deps = {}
        for sid in skill_ids:
            if sid in self._skills:
                deps[sid] = [p for p in self._skills[sid].prerequisites if p in skill_ids]
        return deps

    def _default_requirements(self, task: str) -> list[SkillRequirement]:
        """Generate default requirements when LLM is unavailable."""
        return [
            SkillRequirement(
                requirement_id=str(uuid.uuid4())[:8],
                description=f"Primary skill for {task}",
                mandatory=True,
                weight=1.0,
            ),
        ]

    def _parse_requirements(self, response: str) -> list[SkillRequirement]:
        """Parse requirements from LLM response."""
        import json
        reqs = []
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("["):
                try:
                    data = json.loads(line)
                    for item in data:
                        reqs.append(SkillRequirement(
                            requirement_id=str(uuid.uuid4())[:8],
                            description=item.get("description", ""),
                            category=SkillCategory(item["category"]) if "category" in item else None,
                            min_level=SkillLevel(item.get("min_level", "novice")),
                            mandatory=item.get("mandatory", True),
                            weight=float(item.get("weight", 1.0)),
                        ))
                    break
                except (json.JSONDecodeError, KeyError):
                    continue
        return reqs

    def _parse_gaps(self, response: str) -> list[str]:
        """Parse capability gaps from LLM response."""
        gaps = []
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                gaps.append(line[1:].strip())
        return gaps if gaps else [response[:200]]

    def _generate_recommendations(self, assessment: CapabilityAssessment) -> list[str]:
        """Generate recommendations based on assessment."""
        recs = []
        if assessment.gaps:
            recs.append("Address identified skill gaps")
        if assessment.overall_level in (SkillLevel.NOVICE, SkillLevel.INTERMEDIATE):
            recs.append("Focus on skill development and practice")
        if not assessment.strengths:
            recs.append("Build expertise in core skill areas")
        recs.append("Regularly assess and update skill inventory")
        return recs

    def list_selections(self) -> list[str]:
        return list(self._selections.keys())

    def list_compositions(self) -> list[str]:
        return list(self._compositions.keys())

    def list_assessments(self) -> list[str]:
        return list(self._assessments.keys())
