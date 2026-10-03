"""Proactive Suggestions — anticipates user needs.

Analyzes conversation context, user behavior patterns, and task state
to proactively suggest next actions, relevant tools, or helpful information.
Reduces user cognitive load by surfacing needs before they are expressed.
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


class SuggestionType(Enum):
    NEXT_ACTION = "next_action"
    TOOL_RECOMMENDATION = "tool_recommendation"
    CONTEXT_REMINDER = "context_reminder"
    FOLLOW_UP = "follow_up"
    OPTIMIZATION = "optimization"
    SAFETY = "safety"


class SuggestionPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Suggestion:
    """A proactive suggestion."""
    suggestion_type: SuggestionType
    priority: SuggestionPriority
    text: str
    action: str | None = None
    confidence: float = 0.5
    source: str = "proactive"
    timestamp: float = field(default_factory=time.time)
    dismissed: bool = False
    accepted: bool = False

    @property
    def is_active(self) -> bool:
        return not self.dismissed and not self.accepted


@dataclass
class UserPattern:
    """A detected user behavior pattern."""
    pattern_type: str
    frequency: int
    last_seen: float
    confidence: float
    examples: list[str] = field(default_factory=list)


class ProactiveSuggestions:
    """Proactive suggestion engine.

    Monitors conversation context and user behavior to generate
    timely, relevant suggestions that anticipate user needs.
    """

    def __init__(self, *, max_suggestions: int = 5, cooldown: float = 60.0) -> None:
        self._suggestions: list[Suggestion] = []
        self._max_suggestions = max_suggestions
        self._cooldown = cooldown
        self._last_suggestion_time: dict[SuggestionType, float] = {}
        self._user_patterns: dict[str, UserPattern] = {}
        self._context_history: list[dict[str, Any]] = []
        self._metrics: dict[str, int] = defaultdict(int)

    async def analyze(
        self,
        *,
        conversation: list[dict[str, Any]],
        current_task: str = "",
        available_tools: list[str] | None = None,
        recent_actions: list[str] | None = None,
    ) -> list[Suggestion]:
        """Analyze context and generate proactive suggestions.

        Args:
            conversation: Recent conversation messages.
            current_task: The current task being worked on.
            available_tools: Tools available to the agent.
            recent_actions: Recently executed actions.

        Returns:
            List of active suggestions.
        """
        suggestions: list[Suggestion] = []

        # Pattern 1: Detect incomplete tasks
        incomplete = self._detect_incomplete_tasks(conversation, current_task)
        suggestions.extend(incomplete)

        # Pattern 2: Suggest relevant tools
        if available_tools:
            tool_suggestions = self._suggest_tools(current_task, available_tools, recent_actions or [])
            suggestions.extend(tool_suggestions)

        # Pattern 3: Follow-up suggestions
        follow_ups = self._suggest_follow_ups(conversation)
        suggestions.extend(follow_ups)

        # Pattern 4: Context reminders
        reminders = self._suggest_context_reminders(conversation)
        suggestions.extend(reminders)

        # Pattern 5: Optimization suggestions
        optimizations = self._suggest_optimizations(conversation, recent_actions or [])
        suggestions.extend(optimizations)

        # Filter by cooldown and deduplicate
        filtered = self._filter_suggestions(suggestions)

        # Store and return
        self._suggestions.extend(filtered)
        self._metrics["generated"] += len(filtered)

        # Trim old suggestions
        self._suggestions = [s for s in self._suggestions if s.is_active][-self._max_suggestions:]

        return filtered

    def _detect_incomplete_tasks(
        self,
        conversation: list[dict[str, Any]],
        current_task: str,
    ) -> list[Suggestion]:
        """Detect tasks that may be incomplete."""
        suggestions = []
        if not conversation:
            return suggestions

        # Check for error messages in recent conversation
        recent = conversation[-5:] if len(conversation) > 5 else conversation
        for msg in recent:
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            if any(kw in content.lower() for kw in ["error", "failed", "issue", "problem", "bug"]):
                suggestions.append(Suggestion(
                    suggestion_type=SuggestionType.NEXT_ACTION,
                    priority=SuggestionPriority.HIGH,
                    text="I noticed an error. Would you like me to investigate and fix it?",
                    action="investigate_error",
                    confidence=0.8,
                ))
                break

        # Check for questions that weren't answered
        for msg in reversed(recent[-3:]):
            content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
            if "?" in content and msg.get("role") == "user":
                suggestions.append(Suggestion(
                    suggestion_type=SuggestionType.FOLLOW_UP,
                    priority=SuggestionPriority.MEDIUM,
                    text="You asked a question that may not have been fully answered. Want me to elaborate?",
                    action="elaborate",
                    confidence=0.6,
                ))
                break

        return suggestions

    def _suggest_tools(
        self,
        task: str,
        available_tools: list[str],
        recent_actions: list[str],
    ) -> list[Suggestion]:
        """Suggest tools that might be useful for the task."""
        suggestions = []
        task_lower = task.lower()

        # Tool relevance mapping
        tool_keywords = {
            "web_search": ["search", "find", "look up", "research"],
            "file_read": ["read", "open", "view", "check"],
            "file_write": ["write", "create", "save", "edit"],
            "code_execution": ["run", "execute", "test", "debug"],
            "browser": ["browse", "visit", "scrape", "website"],
            "image_analysis": ["image", "picture", "screenshot", "visual"],
        }

        for tool in available_tools:
            if tool in recent_actions:
                continue  # Don't suggest recently used tools
            keywords = tool_keywords.get(tool, [])
            if any(kw in task_lower for kw in keywords):
                suggestions.append(Suggestion(
                    suggestion_type=SuggestionType.TOOL_RECOMMENDATION,
                    priority=SuggestionPriority.MEDIUM,
                    text=f"Consider using '{tool}' for this task",
                    action=f"use_tool:{tool}",
                    confidence=0.7,
                ))

        return suggestions[:2]  # Limit tool suggestions

    def _suggest_follow_ups(self, conversation: list[dict[str, Any]]) -> list[Suggestion]:
        """Suggest follow-up actions based on conversation."""
        suggestions = []
        if len(conversation) < 2:
            return suggestions

        # Check for completed tasks that might need verification
        last_assistant = None
        for msg in reversed(conversation):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                last_assistant = msg.get("content", "")
                break

        if last_assistant:
            if any(kw in last_assistant.lower() for kw in ["created", "written", "implemented", "done"]):
                suggestions.append(Suggestion(
                    suggestion_type=SuggestionType.FOLLOW_UP,
                    priority=SuggestionPriority.LOW,
                    text="Would you like me to verify the work by running tests?",
                    action="verify_work",
                    confidence=0.5,
                ))

        return suggestions

    def _suggest_context_reminders(self, conversation: list[dict[str, Any]]) -> list[Suggestion]:
        """Remind about important context that may have been forgotten."""
        suggestions = []

        # Check for user preferences mentioned earlier
        for msg in conversation[-10:]:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "")
            if "remember" in content.lower() or "always" in content.lower():
                suggestions.append(Suggestion(
                    suggestion_type=SuggestionType.CONTEXT_REMINDER,
                    priority=SuggestionPriority.LOW,
                    text="You mentioned a preference earlier. I'll keep that in mind.",
                    action=None,
                    confidence=0.4,
                ))
                break

        return suggestions

    def _suggest_optimizations(
        self,
        conversation: list[dict[str, Any]],
        recent_actions: list[str],
    ) -> list[Suggestion]:
        """Suggest process optimizations."""
        suggestions = []

        # Detect repeated actions
        if len(recent_actions) >= 3:
            action_counts = defaultdict(int)
            for a in recent_actions:
                action_counts[a] += 1
            for action, count in action_counts.items():
                if count >= 3:
                    suggestions.append(Suggestion(
                        suggestion_type=SuggestionType.OPTIMIZATION,
                        priority=SuggestionPriority.LOW,
                        text=f"You've used '{action}' {count} times. Consider batching or automating this.",
                        action=f"optimize:{action}",
                        confidence=0.6,
                    ))
                    break

        return suggestions

    def _filter_suggestions(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        """Filter by cooldown and deduplicate."""
        now = time.time()
        filtered = []
        seen_types = set()

        for s in suggestions:
            # Cooldown check
            last_time = self._last_suggestion_time.get(s.suggestion_type, 0)
            if now - last_time < self._cooldown:
                continue

            # Deduplicate by type
            if s.suggestion_type in seen_types:
                continue

            seen_types.add(s.suggestion_type)
            self._last_suggestion_time[s.suggestion_type] = now
            filtered.append(s)

        return filtered[:self._max_suggestions]

    def dismiss(self, suggestion: Suggestion) -> None:
        """Dismiss a suggestion."""
        suggestion.dismissed = True
        self._metrics["dismissed"] += 1

    def accept(self, suggestion: Suggestion) -> None:
        """Accept a suggestion."""
        suggestion.accepted = True
        self._metrics["accepted"] += 1

    def get_active(self) -> list[Suggestion]:
        """Get all active suggestions."""
        return [s for s in self._suggestions if s.is_active]

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "active_suggestions": len(self.get_active()),
            "total_generated": self._metrics["generated"],
        }
