"""
ContextBuilder — builds the message list for the LLM.
"""
from __future__ import annotations

from typing import Optional

from app.services.llm_service import ChatMessage
from app.brain.prompt_manager import PromptManager


class ContextBuilder:
    """Assembles messages: system + history + retrieved + task + tool specs."""

    def __init__(self, prompts: PromptManager) -> None:
        self._prompts = prompts

    def build(
        self,
        task_prompt: str,
        history: list[ChatMessage],
        retrieved: Optional[list[str]] = None,
        agent_persona: Optional[str] = None,
        tool_specs: Optional[str] = None,
        system_override: Optional[str] = None,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []

        sys = system_override or self._prompts.system()
        if agent_persona:
            sys = f"{sys}\n\nYour agent persona: {agent_persona}"
        messages.append(ChatMessage(role="system", content=sys))

        if retrieved:
            ctx = self._prompts.context("\n---\n".join(retrieved))
            messages.append(ChatMessage(role="system", content=ctx))

        for h in history:
            messages.append(h)

        if tool_specs:
            messages.append(ChatMessage(role="system", content=self._prompts.tool_use(tool_specs)))

        messages.append(ChatMessage(role="user", content=task_prompt))
        return messages
