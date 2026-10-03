"""ContextInjector — injects context into LLM prompts with formatting control.

Every professional AI assistant needs to inject retrieved context, history,
and system information into prompts in a structured way. This module
provides that capability with multiple injection strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class InjectionFormat(Enum):
    """Format for injecting context into prompts."""
    BULLET = "bullet"           # Bullet point list
    NUMBERED = "numbered"       # Numbered list
    PARAGRAPH = "paragraph"     # Free-form paragraphs
    XML = "xml"                 # XML-like tags
    JSON = "json"               # JSON structure
    MARKDOWN = "markdown"       # Markdown sections


@dataclass
class InjectionResult:
    """Result of context injection."""
    prompt: str
    injected_tokens: int
    injected_items: int
    format_used: str
    truncated: bool = False


class ContextInjector:
    """Injects context into prompts with configurable formatting.

    Supports multiple injection formats and can be configured to
    prioritize certain sources over others.
    """

    def __init__(
        self,
        *,
        format: InjectionFormat = InjectionFormat.BULLET,
        max_tokens: int = 4000,
        priority_sources: list[str] | None = None,
        include_metadata: bool = False,
    ) -> None:
        self._format = format
        self._max_tokens = max_tokens
        self._priority_sources = priority_sources or []
        self._include_metadata = include_metadata

    def inject(
        self,
        *,
        base_prompt: str,
        context_items: list[Any],
        system_prefix: str | None = None,
    ) -> InjectionResult:
        """Inject context items into a base prompt.

        Args:
            base_prompt: The original prompt to inject context into.
            context_items: List of context items (ContextItem or dict with content).
            system_prefix: Optional system prefix to prepend.

        Returns:
            InjectionResult with the formatted prompt and metadata.
        """
        if not context_items:
            return InjectionResult(
                prompt=base_prompt,
                injected_tokens=0,
                injected_items=0,
                format_used=self._format.value,
            )

        # Sort by priority sources first, then by relevance
        sorted_items = self._sort_by_priority(context_items)

        # Format the context
        context_text = self._format_context(sorted_items)

        # Check token budget
        estimated_tokens = len(context_text) // 4
        truncated = False
        if estimated_tokens > self._max_tokens:
            context_text = self._truncate_context(context_text, self._max_tokens)
            truncated = True
            estimated_tokens = len(context_text) // 4

        # Assemble the final prompt
        parts: list[str] = []
        if system_prefix:
            parts.append(system_prefix)
        if context_text:
            parts.append(context_text)
        parts.append(base_prompt)

        final_prompt = "\n\n".join(parts)

        return InjectionResult(
            prompt=final_prompt,
            injected_tokens=estimated_tokens,
            injected_items=len(sorted_items),
            format_used=self._format.value,
            truncated=truncated,
        )

    def inject_into_messages(
        self,
        *,
        messages: list[Any],
        context_items: list[Any],
        position: str = "before_last",
    ) -> list[Any]:
        """Inject context into a message list.

        Args:
            messages: List of message objects (must have .role and .content or be dicts).
            context_items: Context items to inject.
            position: Where to inject — "before_last", "after_system", "at_start".

        Returns:
            Modified message list with context injected.
        """
        if not context_items:
            return messages

        context_text = self._format_context(context_items)
        if not context_text:
            return messages

        # Create a system message with the context
        context_msg = {"role": "system", "content": f"Context:\n{context_text}"}

        if position == "before_last":
            # Insert before the last message
            messages.insert(len(messages) - 1, context_msg)
        elif position == "after_system":
            # Insert after the first system message
            insert_idx = 0
            for i, msg in enumerate(messages):
                role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
                if role == "system":
                    insert_idx = i + 1
                    break
            messages.insert(insert_idx, context_msg)
        else:  # at_start
            messages.insert(0, context_msg)

        return messages

    def _sort_by_priority(self, items: list[Any]) -> list[Any]:
        """Sort items by priority sources first, then by relevance."""
        def sort_key(item: Any) -> tuple:
            source = getattr(item, "source", "") if not isinstance(item, dict) else item.get("source", "")
            relevance = getattr(item, "relevance", 0.5) if not isinstance(item, dict) else item.get("relevance", 0.5)
            priority = 0 if source in self._priority_sources else 1
            return (priority, -relevance)

        return sorted(items, key=sort_key)

    def _format_context(self, items: list[Any]) -> str:
        """Format context items according to the configured format."""
        if self._format == InjectionFormat.BULLET:
            return self._format_bullet(items)
        elif self._format == InjectionFormat.NUMBERED:
            return self._format_numbered(items)
        elif self._format == InjectionFormat.PARAGRAPH:
            return self._format_paragraph(items)
        elif self._format == InjectionFormat.XML:
            return self._format_xml(items)
        elif self._format == InjectionFormat.JSON:
            return self._format_json(items)
        elif self._format == InjectionFormat.MARKDOWN:
            return self._format_markdown(items)
        return self._format_bullet(items)

    def _format_bullet(self, items: list[Any]) -> str:
        lines = []
        for item in items:
            content = self._get_content(item)
            if content:
                lines.append(f"- {content}")
        return "\n".join(lines)

    def _format_numbered(self, items: list[Any]) -> str:
        lines = []
        for i, item in enumerate(items, 1):
            content = self._get_content(item)
            if content:
                lines.append(f"{i}. {content}")
        return "\n".join(lines)

    def _format_paragraph(self, items: list[Any]) -> str:
        parts = []
        for item in items:
            content = self._get_content(item)
            if content:
                parts.append(content)
        return "\n\n".join(parts)

    def _format_xml(self, items: list[Any]) -> str:
        lines = ["<context>"]
        for item in items:
            content = self._get_content(item)
            source = self._get_source(item)
            if content:
                lines.append(f"  <item source=\"{source}\">{content}</item>")
        lines.append("</context>")
        return "\n".join(lines)

    def _format_json(self, items: list[Any]) -> str:
        import json
        data = []
        for item in items:
            content = self._get_content(item)
            source = self._get_source(item)
            if content:
                entry = {"content": content, "source": source}
                if self._include_metadata:
                    entry["relevance"] = self._get_relevance(item)
                    entry["importance"] = self._get_importance(item)
                data.append(entry)
        return json.dumps(data, indent=2)

    def _format_markdown(self, items: list[Any]) -> str:
        lines = ["## Context"]
        for item in items:
            content = self._get_content(item)
            source = self._get_source(item)
            if content:
                lines.append(f"\n**{source}:** {content}")
        return "\n".join(lines)

    def _get_content(self, item: Any) -> str:
        if isinstance(item, dict):
            return item.get("content", item.get("chunk", ""))
        return getattr(item, "content", "")

    def _get_source(self, item: Any) -> str:
        if isinstance(item, dict):
            return item.get("source", "unknown")
        return getattr(item, "source", "unknown")

    def _get_relevance(self, item: Any) -> float:
        if isinstance(item, dict):
            return item.get("relevance", 0.5)
        return getattr(item, "relevance", 0.5)

    def _get_importance(self, item: Any) -> float:
        if isinstance(item, dict):
            return item.get("importance", 0.5)
        return getattr(item, "importance", 0.5)

    def _truncate_context(self, text: str, max_tokens: int) -> str:
        """Truncate context text to fit within token budget."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        # Keep head and tail
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        return f"{head}\n...[truncated]...\n{tail}"
