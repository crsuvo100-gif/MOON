"""Skill context injection into prompts.

Injects relevant skill instructions, examples, and constraints into
the LLM prompt context so the model can follow skill-specific
guidelines during task execution.
"""

from __future__ import annotations

from typing import Any


class SkillContextInjector:
    """Injects skill context into LLM prompts.

    When a skill is matched to a task, its instructions, examples,
    and constraints are injected into the system prompt to guide
    the LLM's behavior.
    """

    def __init__(self):
        self._injected_skills: dict[str, dict[str, Any]] = {}

    def inject(self, skill_name: str, skill_data: dict[str, Any], task: str) -> str:
        """Build a context injection string for a skill.

        Args:
            skill_name: Name of the skill
            skill_data: Skill metadata (instructions, examples, constraints)
            task: The user's task

        Returns:
            Formatted context string to inject into the system prompt
        """
        parts: list[str] = []

        # Skill header
        parts.append(f"[Active Skill: {skill_name}]")

        # Instructions
        instructions = skill_data.get("instructions", "")
        if instructions:
            parts.append(f"Instructions:\n{instructions}")

        # Examples
        examples = skill_data.get("examples", [])
        if examples:
            parts.append("Examples:")
            for i, ex in enumerate(examples[:3], 1):
                if isinstance(ex, dict):
                    parts.append(f"  {i}. Input: {ex.get('input', '')}")
                    parts.append(f"     Output: {ex.get('output', '')}")
                else:
                    parts.append(f"  {i}. {ex}")

        # Constraints
        constraints = skill_data.get("constraints", [])
        if constraints:
            parts.append("Constraints:")
            for c in constraints[:5]:
                parts.append(f"  - {c}")

        # Parameters
        parameters = skill_data.get("parameters", {})
        if parameters:
            parts.append("Parameters:")
            for k, v in parameters.items():
                parts.append(f"  - {k}: {v}")

        # Store for tracking
        self._injected_skills[skill_name] = {
            "task": task[:200],
            "instructions_length": len(instructions),
            "examples_count": len(examples),
            "constraints_count": len(constraints),
        }

        return "\n".join(parts)

    def inject_multiple(self, skills: list[tuple[str, dict[str, Any]]], task: str) -> str:
        """Inject context for multiple skills.

        Args:
            skills: List of (skill_name, skill_data) tuples
            task: The user's task

        Returns:
            Combined context string for all skills
        """
        parts: list[str] = []
        for name, data in skills:
            ctx = self.inject(name, data, task)
            parts.append(ctx)
        return "\n\n".join(parts)

    def get_injected_skills(self) -> dict[str, dict[str, Any]]:
        """Get all injected skill records."""
        return dict(self._injected_skills)

    def clear(self) -> None:
        """Clear all injected skill records."""
        self._injected_skills.clear()

    def build_skill_prompt_suffix(self, skill_name: str, skill_data: dict[str, Any]) -> str:
        """Build a prompt suffix that reminds the LLM to follow the skill.

        This is appended to the user message to reinforce skill adherence.
        """
        suffix_parts: list[str] = []

        # Reminder
        suffix_parts.append(f"\n\n[Remember: Follow the '{skill_name}' skill guidelines]")

        # Key constraints as reminders
        constraints = skill_data.get("constraints", [])
        if constraints:
            suffix_parts.append("Key constraints to follow:")
            for c in constraints[:3]:
                suffix_parts.append(f"  - {c}")

        # Output format
        output_format = skill_data.get("output_format", "")
        if output_format:
            suffix_parts.append(f"Output format: {output_format}")

        return "\n".join(suffix_parts)
