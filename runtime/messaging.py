"""Internal agent messaging (spec section 33).

Agent A -> task message -> Agent B -> result -> Orchestrator.

Every message carries: message_id, execution_id, sender, receiver, timestamp,
type, payload, priority. This is a REAL in-process message bus: agents can post
and consume messages by receiver id, and the orchestrator can subscribe to the
result stream. Non-destructive; standalone module.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    EVENT = "event"
    CONTROL = "control"


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    payload: Any
    execution_id: str = ""
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    type: MessageType = MessageType.TASK
    priority: int = 5  # 1 (low) .. 10 (high)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id, "execution_id": self.execution_id,
            "sender": self.sender, "receiver": self.receiver,
            "timestamp": self.timestamp, "type": self.type.value,
            "payload": self.payload, "priority": self.priority,
        }


class MessageBus:
    """In-process pub/sub message bus (spec 33). Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, list[AgentMessage]] = {}     # receiver -> messages
        self._subscribers: dict[str, list[Any]] = {}          # receiver -> callbacks
        self._history: list[AgentMessage] = []

    def send(self, msg: AgentMessage) -> None:
        with self._lock:
            self._history.append(msg)
            self._queues.setdefault(msg.receiver, []).append(msg)
            for cb in self._subscribers.get(msg.receiver, []):
                try:
                    cb(msg)
                except Exception:  # noqa: BLE001
                    pass

    def post(self, *, sender: str, receiver: str, payload: Any,
             execution_id: str = "", type: MessageType = MessageType.TASK,
             priority: int = 5) -> AgentMessage:
        msg = AgentMessage(sender=sender, receiver=receiver, payload=payload,
                           execution_id=execution_id, type=type, priority=priority)
        self.send(msg)
        return msg

    def receive(self, receiver: str, *, block: bool = False, timeout: float = 0.0) -> AgentMessage | None:
        with self._lock:
            q = self._queues.get(receiver, [])
            if q:
                return q.pop(0)
        if not block:
            return None
        # best-effort blocking wait
        import time as _t
        deadline = _t.time() + max(0.0, timeout)
        while _t.time() < deadline:
            with self._lock:
                q = self._queues.get(receiver, [])
                if q:
                    return q.pop(0)
            _t.sleep(0.05)
        return None

    def subscribe(self, receiver: str, callback) -> None:
        with self._lock:
            self._subscribers.setdefault(receiver, []).append(callback)

    def history(self, receiver: str | None = None) -> list[AgentMessage]:
        with self._lock:
            if receiver is None:
                return list(self._history)
            return [m for m in self._history if m.receiver == receiver]


# Module-level default bus.
_BUS = MessageBus()


def get_bus() -> MessageBus:
    return _BUS


__all__ = ["AgentMessage", "MessageBus", "MessageType", "get_bus"]
