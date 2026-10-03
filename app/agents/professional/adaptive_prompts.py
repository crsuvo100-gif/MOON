"""Adaptive Prompts — dynamic prompt engineering.

Automatically adjusts system prompts, temperature, and token budgets
based on task complexity, user expertise, and conversation context.
Ensures optimal LLM performance across diverse scenarios.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


class UserExpertise(Enum):
    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


@dataclass
class PromptConfig:
    """Configuration for adaptive prompting."""
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: list[str] = field(default_factory=list)
    few_shot_examples: list[dict[str, str]] = field(default_factory=list)
    chain_of_thought: bool = False
    self_consistency: bool = False


@dataclass
class PromptTemplate:
    """A reusable prompt template."""
    name: str
    template: str
    variables: list[str] = field(default_factory=list)
    description: str = ""
    category: str = "general"


class AdaptivePrompts:
    """Adaptive prompt engineering system.

    Dynamically adjusts prompts based on task complexity,
    user expertise, and conversation context.
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}
        self._performance_history: dict[str, list[float]] = {}
        self._user_expertise: UserExpertise = UserExpertise.INTERMEDIATE
        self._complexity_weights = {
            TaskComplexity.SIMPLE: {"temperature": 0.3, "max_tokens": 1024, "top_p": 0.8},
            TaskComplexity.MODERATE: {"temperature": 0.5, "max_tokens": 2048, "top_p": 0.9},
            TaskComplexity.COMPLEX: {"temperature": 0.7, "max_tokens": 4096, "top_p": 0.95},
            TaskComplexity.EXPERT: {"temperature": 0.8, "max_tokens": 8192, "top_p": 0.98},
        }
        self._expertise_adjustments = {
            UserExpertise.NOVICE: {"temperature_offset": -0.1, "explanation_level": "detailed"},
            UserExpertise.INTERMEDIATE: {"temperature_offset": 0.0, "explanation_level": "standard"},
            UserExpertise.ADVANCED: {"temperature_offset": 0.1, "explanation_level": "concise"},
            UserExpertise.EXPERT: {"temperature_offset": 0.2, "explanation_level": "minimal"},
        }
        self._metrics: dict[str, int] = defaultdict(int)

    def register_template(self, template: PromptTemplate) -> None:
        """Register a prompt template."""
        self._templates[template.name] = template
        logger.debug("Registered prompt template: %s", template.name)

    def set_user_expertise(self, expertise: UserExpertise) -> None:
        """Set the user's expertise level."""
        self._user_expertise = expertise
        logger.info("User expertise set to: %s", expertise.value)

    def assess_complexity(self, task: str, context: str = "") -> TaskComplexity:
        """Assess the complexity of a task."""
        # Heuristic complexity assessment
        score = 0

        # Length-based
        word_count = len(task.split())
        if word_count > 100:
            score += 2
        elif word_count > 50:
            score += 1

        # Keyword-based
        complex_keywords = ["implement", "design", "architect", "optimize", "refactor", "debug", "analyze"]
        simple_keywords = ["what", "when", "where", "who", "list", "show"]

        task_lower = task.lower()
        for kw in complex_keywords:
            if kw in task_lower:
                score += 1
        for kw in simple_keywords:
            if kw in task_lower:
                score -= 1

        # Context-based
        if context:
            context_words = len(context.split())
            if context_words > 500:
                score += 1

        # Multi-step detection
        if any(kw in task_lower for kw in ["then", "after", "before", "step", "first", "next"]):
            score += 1

        if score >= 4:
            return TaskComplexity.EXPERT
        elif score >= 2:
            return TaskComplexity.COMPLEX
        elif score >= 0:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE

    def generate_config(
        self,
        *,
        task: str,
        context: str = "",
        base_system: str = "",
        task_type: str = "general",
    ) -> PromptConfig:
        """Generate an adaptive prompt configuration.

        Args:
            task: The task description.
            context: Additional context.
            base_system: Base system prompt.
            task_type: Type of task.

        Returns:
            PromptConfig optimized for the task.
        """
        self._metrics["configs_generated"] += 1

        # Assess complexity
        complexity = self.assess_complexity(task, context)
        weights = self._complexity_weights[complexity]

        # Apply expertise adjustments
        adj = self._expertise_adjustments[self._user_expertise]
        temperature = max(0.0, min(1.0, weights["temperature"] + adj["temperature_offset"]))

        # Determine if chain-of-thought is needed
        cot = complexity in (TaskComplexity.COMPLEX, TaskComplexity.EXPERT)

        # Build system prompt
        system = base_system
        if adj["explanation_level"] == "detailed":
            system += "\n\nProvide detailed explanations with examples."
        elif adj["explanation_level"] == "concise":
            system += "\n\nBe concise and technical."
        elif adj["explanation_level"] == "minimal":
            system += "\n\nAssume expert knowledge. Be brief."

        if cot:
            system += "\n\nThink step by step before answering."

        # Select few-shot examples based on task type
        few_shots = self._select_few_shots(task_type, complexity)

        config = PromptConfig(
            system_prompt=system,
            temperature=temperature,
            max_tokens=weights["max_tokens"],
            top_p=weights["top_p"],
            chain_of_thought=cot,
            few_shot_examples=few_shots,
        )

        logger.debug(
            "Generated prompt config: complexity=%s, temp=%.2f, max_tokens=%d, cot=%s",
            complexity.value, temperature, weights["max_tokens"], cot,
        )

        return config

    def _select_few_shots(
        self,
        task_type: str,
        complexity: TaskComplexity,
    ) -> list[dict[str, str]]:
        """Select appropriate few-shot examples."""
        # This would typically load from a curated examples database
        # For now, return empty — can be extended with a few-shot library
        return []

    def render_template(self, name: str, **variables: Any) -> str:
        """Render a prompt template with variables."""
        template = self._templates.get(name)
        if not template:
            logger.warning("Template not found: %s", name)
            return ""

        result = template.template
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value))

        self._metrics["templates_rendered"] += 1
        return result

    def record_performance(self, config_name: str, score: float) -> None:
        """Record performance score for a prompt configuration."""
        if config_name not in self._performance_history:
            self._performance_history[config_name] = []
        self._performance_history[config_name].append(score)
        self._metrics["performance_recorded"] += 1

    def get_best_config(self, task_type: str) -> str | None:
        """Get the best-performing config name for a task type."""
        best_name = None
        best_score = -1.0

        for name, scores in self._performance_history.items():
            if name.startswith(task_type):
                avg = sum(scores) / len(scores) if scores else 0
                if avg > best_score:
                    best_score = avg
                    best_name = name

        return best_name

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "templates_registered": len(self._templates),
            "user_expertise": self._user_expertise.value,
            "configs_tracked": len(self._performance_history),
        }
