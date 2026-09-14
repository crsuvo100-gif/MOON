"""
ConversationHistory — chat message history per session.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Optional

from app.services.llm_service import ChatMessage


class ConversationHistory:
    """Stores recent ChatMessages for context building."""

    def __init__(self, session_id: str = "main", capacity: int = 200) -> None:
        self._session = session_id
        self._buf: deque[ChatMessage] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, msg: ChatMessage) -> None:
        with self._lock:
            self._buf.append(msg)

    def get_messages(self, limit: Optional[int] = None) -> list[ChatMessage]:
        with self._lock:
            if limit:
                return list(self._buf)[-limit:]
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)
