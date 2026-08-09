"""ContextBuilder -- assembles the message list for a task."""

from __future__ import annotations

from typing import Any

from app.config.logging import get_logger
from app.models.message import Message

logger = get_logger(__name__)


class ContextBuilder:
    def __init__(self, prompts) -> None:
        self._prompts = prompts
        self._retriever = None

    def set_retriever(self, retriever) -> None:
        self._retriever = retriever

    async def build(
        self,
        *,
        task,
        history,
        retrieved: list[dict[str, Any]] | None = None,
        system_override: str | None = None,
        agent=None,
    ) -> list[Message]:
        if system_override:
            sys_text = system_override
        elif agent is not None:
            from app.brain.agent_registry import persona_for
            from app.brain.prompt_tuner import augment_persona

            base = persona_for(getattr(agent, "name", str(agent)))
            sys_text = augment_persona(base, getattr(agent, "name", None))
        else:
            sys_text = self._prompts.system_prompt() if self._prompts else "You are MOON."
        messages = [Message.system(sys_text)]
        if retrieved:
            ctx = "\n".join(f"- {r.get('content', r.get('chunk', ''))}" for r in retrieved[:5])
            if ctx.strip():
                messages.append(Message.system(f"Relevant context:\n{ctx}"))
        messages.extend(history.messages())
        messages.append(Message.user(task.prompt))
        return messages
