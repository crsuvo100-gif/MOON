"""Conversation history (rolling transcript for a session)."""

from __future__ import annotations

from collections import deque

from app.models.message import Message


class ConversationHistory:
    def __init__(self, session_id: str = "main", max_turns: int = 40) -> None:
        self.session_id = session_id
        self._buf: deque[Message] = deque(maxlen=max_turns * 2)

    def append(self, message: Message) -> None:
        self._buf.append(message)

    def clear(self) -> None:
        self._buf.clear()

    def messages(self) -> list[Message]:
        return list(self._buf)
