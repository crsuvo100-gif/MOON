"""
PromptManager — prompt templates for system, tool-use, planning, etc.
"""
from __future__ import annotations

from pydantic import BaseModel


class PromptManager:
    """Provides prompt templates."""

    def __init__(self) -> None:
        self._system_prompt = (
            "You are MOON, a capable general-purpose AI assistant. "
            "Be concise, accurate, and helpful. When tools are available, "
            "use them thoughtfully to answer the user's question."
        )
        self._tool_prompt = (
            "You have access to the following tools. If the user's request "
            "would benefit from using a tool, call it. Otherwise, answer directly.\n\n"
            "{tool_specs}"
        )
        self._planning_prompt = (
            "Break this task into concrete, sequential subtasks:\n\n{task}\n\n"
            "Return a numbered plan."
        )
        self._context_prompt = (
            "Use the following context to answer the user's question. "
            "If the context does not help, answer from your own knowledge.\n\n"
            "{context}"
        )

    def system(self) -> str:
        return self._system_prompt

    def tool_use(self, tool_specs: str) -> str:
        return self._tool_prompt.format(tool_specs=tool_specs)

    def planning(self, task: str) -> str:
        return self._planning_prompt.format(task=task)

    def context(self, context: str) -> str:
        return self._context_prompt.format(context=context)
