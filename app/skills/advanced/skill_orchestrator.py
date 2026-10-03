"""Unified skill orchestrator.

Ties together all advanced skill modules into a cohesive system:
discovery, matching, validation, lifecycle, context injection,
chaining, and performance tracking.
"""

from __future__ import annotations

import time
from typing import Any

from app.skills.advanced.skill_matcher import SkillMatcher, SkillMatch
from app.skills.advanced.skill_chainer import SkillChainer, SkillChain, ChainResult
from app.skills.advanced.skill_performance import SkillPerformance, SkillUsageRecord
from app.skills.advanced.skill_context import SkillContextInjector
from app.skills.advanced.skill_discovery import SkillDiscovery
from app.skills.advanced.skill_validator import SkillValidator, ValidationResult
from app.skills.advanced.skill_lifecycle import SkillLifecycle, SkillState
from app.skills.advanced.skill_registry import AdvancedSkillRegistry, SkillMetadata


class SkillOrchestrator:
    """Unified skill orchestrator.

    Provides a single interface to the complete skill system:
    - Discover skills from filesystem and knowledge base
    - Match skills to tasks with multi-signal scoring
    - Validate skill quality
    - Inject skill context into prompts
    - Chain skills for complex workflows
    - Track skill performance
    - Manage skill lifecycle
    """

    def __init__(self):
        self._discovery = SkillDiscovery()
        self._matcher = SkillMatcher()
        self._chainer = SkillChainer()
        self._performance = SkillPerformance()
        self._context_injector = SkillContextInjector()
        self._validator = SkillValidator()
        self._lifecycle = SkillLifecycle()
        self._registry = AdvancedSkillRegistry()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the skill orchestrator.

        Discovers all available skills, validates them, and
        registers them in the registry and matcher.
        """
        if self._initialized:
            return

        # Discover skills from filesystem
        discovered = self._discovery.discover()

        # Register each skill
        for name, meta in discovered.items():
            # Validate
            validation = self._validator.validate(name, meta)

            # Create SkillMetadata
            skill_meta = SkillMetadata(
                name=name,
                description=meta.get("description", ""),
                keywords=meta.get("keywords", []),
                tags=meta.get("tags", []),
                instructions=meta.get("instructions", ""),
                examples=meta.get("examples", []),
                constraints=meta.get("constraints", []),
                parameters=meta.get("parameters", {}),
                output_format=meta.get("output_format", ""),
                source=meta.get("source", ""),
                format=meta.get("format", "markdown"),
                state=SkillState.ACTIVE if validation.valid else SkillState.DISCOVERED,
                metadata={"validation_score": validation.score},
            )

            # Register in all subsystems
            self._registry.register(skill_meta)
            self._matcher.register_skill(name, meta)
            self._lifecycle.register(name, meta)

            # Transition to ACTIVE if valid
            if validation.valid:
                self._lifecycle.transition(name, SkillState.VALIDATED, "auto-validated")
                self._lifecycle.transition(name, SkillState.ACTIVE, "auto-activated")

        self._initialized = True

    def match_skills(self, task: str, top_k: int = 5) -> list[SkillMatch]:
        """Find the most relevant skills for a task."""
        return self._matcher.match(task, top_k=top_k)

    def get_best_skill(self, task: str) -> SkillMatch | None:
        """Get the single best matching skill for a task."""
        return self._matcher.get_best_match(task)

    def inject_skill_context(self, skill_name: str, task: str) -> str:
        """Get skill context injection for a prompt."""
        meta = self._registry.get(skill_name)
        if not meta:
            return ""
        return self._context_injector.inject(skill_name, meta.__dict__, task)

    def inject_multiple_skills(self, skill_names: list[str], task: str) -> str:
        """Get combined context injection for multiple skills."""
        skills_data: list[tuple[str, dict[str, Any]]] = []
        for name in skill_names:
            meta = self._registry.get(name)
            if meta:
                skills_data.append((name, meta.__dict__))
        return self._context_injector.inject_multiple(skills_data, task)

    def suggest_chain(self, task: str) -> SkillChain | None:
        """Suggest a skill chain for a task."""
        available = [n for n in self._registry.list_names() if self._lifecycle.is_active(n)]
        return self._chainer.suggest_chain(task, available)

    async def execute_chain(
        self,
        chain_name: str,
        initial_input: str,
        skill_executor,
    ) -> ChainResult:
        """Execute a skill chain."""
        return await self._chainer.execute_chain(chain_name, initial_input, skill_executor)

    def record_skill_usage(
        self,
        skill_name: str,
        task: str,
        success: bool,
        execution_time: float,
    ) -> None:
        """Record skill usage for performance tracking."""
        record = SkillUsageRecord(
            skill_name=skill_name,
            task=task,
            success=success,
            execution_time=execution_time,
            timestamp=time.time(),
        )
        self._performance.record(record)
        self._matcher.record_usage(skill_name, success)
        self._registry.record_usage(skill_name, success, execution_time)

    def get_performance_summary(self) -> dict[str, Any]:
        """Get skill performance summary."""
        return self._performance.get_summary()

    def get_registry_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        return self._registry.get_stats()

    def get_active_skills(self) -> list[str]:
        """Get all active skill names."""
        return self._lifecycle.get_active_skills()

    def get_skill_metadata(self, name: str) -> SkillMetadata | None:
        """Get metadata for a specific skill."""
        return self._registry.get(name)

    def search_skills(self, query: str) -> list[SkillMetadata]:
        """Search skills by query."""
        return self._registry.search(query)

    def validate_skill(self, name: str, data: dict[str, Any]) -> ValidationResult:
        """Validate a skill definition."""
        return self._validator.validate(name, data)

    def get_lifecycle_state(self, name: str) -> SkillState | None:
        """Get the lifecycle state of a skill."""
        return self._lifecycle.get_state(name)

    def transition_skill(self, name: str, new_state: SkillState, reason: str = "") -> bool:
        """Transition a skill to a new lifecycle state."""
        return self._lifecycle.transition(name, new_state, reason)

    def get_injected_skills(self) -> dict[str, dict[str, Any]]:
        """Get all injected skill records."""
        return self._context_injector.get_injected_skills()

    def get_all_skills(self) -> dict[str, SkillMetadata]:
        """Get all registered skills."""
        return self._registry.get_all()

    def get_summary(self) -> dict[str, Any]:
        """Get a complete summary of the skill system."""
        return {
            "initialized": self._initialized,
            "total_skills": len(self._registry.get_all()),
            "active_skills": len(self._lifecycle.get_active_skills()),
            "registry_stats": self._registry.get_stats(),
            "performance_summary": self._performance.get_summary(),
            "validation_avg_score": self._validator.get_average_score(),
            "injected_skills": len(self._context_injector.get_injected_skills()),
        }
