"""Skill chaining and composition.

Enables chaining multiple skills together where the output of one
skill becomes the input context for the next.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SkillChain:
    """A chain of skills to execute in sequence."""
    name: str
    skills: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainResult:
    """Result of executing a skill chain."""
    chain_name: str
    success: bool
    stages: list[dict[str, Any]] = field(default_factory=list)
    final_output: str = ""
    execution_time: float = 0.0
    errors: list[str] = field(default_factory=list)


class SkillChainer:
    """Chains multiple skills into a pipeline.

    Each skill in the chain receives the output of the previous skill
    as additional context. This enables complex multi-step workflows
    like: research -> analyze -> write -> review.
    """

    def __init__(self):
        self._chains: dict[str, SkillChain] = {}
        self._skill_outputs: dict[str, str] = {}

    def register_chain(self, chain: SkillChain) -> None:
        """Register a skill chain."""
        self._chains[chain.name] = chain

    def create_chain(self, name: str, skills: list[str], description: str = "") -> SkillChain:
        """Create and register a new skill chain."""
        chain = SkillChain(name=name, skills=skills, description=description)
        self.register_chain(chain)
        return chain

    def get_chain(self, name: str) -> SkillChain | None:
        """Get a registered chain by name."""
        return self._chains.get(name)

    def list_chains(self) -> list[SkillChain]:
        """List all registered chains."""
        return list(self._chains.values())

    async def execute_chain(
        self,
        chain_name: str,
        initial_input: str,
        skill_executor: Callable[[str, str], str],
    ) -> ChainResult:
        """Execute a skill chain.

        Args:
            chain_name: Name of the chain to execute
            initial_input: Initial input for the first skill
            skill_executor: Async callable(skill_name, input) -> output

        Returns:
            ChainResult with all stage outputs and final result
        """
        chain = self._chains.get(chain_name)
        if not chain:
            return ChainResult(
                chain_name=chain_name,
                success=False,
                errors=[f"Chain '{chain_name}' not found"],
            )

        start = time.monotonic()
        current_input = initial_input
        stages: list[dict[str, Any]] = []
        errors: list[str] = []

        for skill_name in chain.skills:
            try:
                t0 = time.monotonic()
                output = await skill_executor(skill_name, current_input)
                elapsed = time.monotonic() - t0

                stages.append({
                    "skill": skill_name,
                    "input_length": len(current_input),
                    "output_length": len(output),
                    "execution_time": round(elapsed, 3),
                    "success": True,
                })

                # Output becomes input for next skill
                current_input = output
                self._skill_outputs[skill_name] = output

            except Exception as exc:
                errors.append(f"{skill_name}: {exc}")
                stages.append({
                    "skill": skill_name,
                    "success": False,
                    "error": str(exc),
                })
                # Continue with next skill using original input
                continue

        return ChainResult(
            chain_name=chain_name,
            success=len(errors) == 0,
            stages=stages,
            final_output=current_input,
            execution_time=round(time.monotonic() - start, 3),
            errors=errors,
        )

    def suggest_chain(self, task: str, available_skills: list[str]) -> SkillChain | None:
        """Suggest a skill chain based on the task and available skills.

        Uses heuristics to determine if a multi-skill chain would be
        beneficial for the task.
        """
        task_lower = task.lower()

        # Research chain: research -> analyze -> write
        if any(k in task_lower for k in ("research", "analyze", "write report", "deep dive")):
            chain_skills = []
            for s in available_skills:
                s_lower = s.lower()
                if "research" in s_lower or "search" in s_lower:
                    chain_skills.append(s)
                elif "analy" in s_lower:
                    chain_skills.append(s)
                elif "writ" in s_lower or "report" in s_lower:
                    chain_skills.append(s)
            if len(chain_skills) >= 2:
                return SkillChain(
                    name="research_pipeline",
                    skills=chain_skills[:3],
                    description="Research -> Analyze -> Write pipeline",
                )

        # Code chain: plan -> code -> test -> review
        if any(k in task_lower for k in ("build", "create", "implement", "develop")):
            chain_skills = []
            for s in available_skills:
                s_lower = s.lower()
                if "plan" in s_lower or "design" in s_lower:
                    chain_skills.append(s)
                elif "code" in s_lower or "implement" in s_lower:
                    chain_skills.append(s)
                elif "test" in s_lower or "verify" in s_lower:
                    chain_skills.append(s)
                elif "review" in s_lower:
                    chain_skills.append(s)
            if len(chain_skills) >= 2:
                return SkillChain(
                    name="code_pipeline",
                    skills=chain_skills[:4],
                    description="Plan -> Code -> Test -> Review pipeline",
                )

        # Security chain: recon -> scan -> analyze -> report
        if any(k in task_lower for k in ("security", "pentest", "vuln", "audit", "scan")):
            chain_skills = []
            for s in available_skills:
                s_lower = s.lower()
                if "recon" in s_lower or "scan" in s_lower:
                    chain_skills.append(s)
                elif "analy" in s_lower or "vuln" in s_lower:
                    chain_skills.append(s)
                elif "report" in s_lower or "write" in s_lower:
                    chain_skills.append(s)
            if len(chain_skills) >= 2:
                return SkillChain(
                    name="security_pipeline",
                    skills=chain_skills[:3],
                    description="Recon -> Analyze -> Report pipeline",
                )

        return None
