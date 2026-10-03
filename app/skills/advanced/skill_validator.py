"""Skill validation and quality checking.

Validates skill definitions for completeness, correctness,
and quality before they are used in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Result of validating a skill."""
    skill_name: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0  # 0.0 - 1.0 quality score


class SkillValidator:
    """Validates skill definitions for quality and completeness.

    Checks:
    - Required fields present (name, description, instructions)
    - Content quality (length, specificity)
    - Format correctness
    - Constraint validity
    """

    def __init__(self):
        self._validation_history: list[ValidationResult] = []

    def validate(self, skill_name: str, skill_data: dict[str, Any]) -> ValidationResult:
        """Validate a skill definition.

        Args:
            skill_name: Name of the skill
            skill_data: Skill metadata to validate

        Returns:
            ValidationResult with errors, warnings, and quality score
        """
        errors: list[str] = []
        warnings: list[str] = []
        score = 1.0

        # Required fields
        if not skill_data.get("description"):
            errors.append("Missing required field: description")
            score -= 0.3

        if not skill_data.get("instructions"):
            errors.append("Missing required field: instructions")
            score -= 0.3

        # Name validation
        if not skill_name or skill_name == "unknown":
            errors.append("Invalid skill name")
            score -= 0.2

        # Description quality
        desc = skill_data.get("description", "")
        if desc and len(desc) < 10:
            warnings.append("Description is very short (< 10 chars)")
            score -= 0.05
        if desc and len(desc) > 500:
            warnings.append("Description is very long (> 500 chars)")
            score -= 0.05

        # Instructions quality
        instructions = skill_data.get("instructions", "")
        if instructions:
            if len(instructions) < 20:
                warnings.append("Instructions are very short (< 20 chars)")
                score -= 0.1
            if len(instructions) > 5000:
                warnings.append("Instructions are very long (> 5000 chars)")
                score -= 0.05

        # Keywords
        keywords = skill_data.get("keywords", [])
        if not keywords:
            warnings.append("No keywords defined (reduces discoverability)")
            score -= 0.1
        elif len(keywords) > 20:
            warnings.append("Too many keywords (> 20, reduces precision)")
            score -= 0.05

        # Tags
        tags = skill_data.get("tags", [])
        if not tags:
            warnings.append("No tags defined (reduces categorization)")
            score -= 0.05

        # Examples
        examples = skill_data.get("examples", [])
        if not examples:
            warnings.append("No examples provided (reduces effectiveness)")
            score -= 0.1
        elif len(examples) > 10:
            warnings.append("Too many examples (> 10, may bloat context)")
            score -= 0.05

        # Constraints
        constraints = skill_data.get("constraints", [])
        if not constraints:
            warnings.append("No constraints defined (may produce inconsistent output)")
            score -= 0.05

        # Format check
        source = skill_data.get("source", "")
        if source and not source.endswith((".md", ".py", ".yaml", ".yml")):
            warnings.append(f"Unusual skill source format: {source}")
            score -= 0.05

        score = max(0.0, min(1.0, score))
        valid = len(errors) == 0

        result = ValidationResult(
            skill_name=skill_name,
            valid=valid,
            errors=errors,
            warnings=warnings,
            score=round(score, 3),
        )
        self._validation_history.append(result)
        return result

    def validate_batch(self, skills: dict[str, dict[str, Any]]) -> list[ValidationResult]:
        """Validate multiple skills at once."""
        return [self.validate(name, data) for name, data in skills.items()]

    def get_validation_history(self) -> list[ValidationResult]:
        """Get all validation results."""
        return list(self._validation_history)

    def get_average_score(self) -> float:
        """Get the average quality score across all validations."""
        if not self._validation_history:
            return 0.0
        return sum(r.score for r in self._validation_history) / len(self._validation_history)
