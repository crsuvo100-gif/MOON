"""Agent Communication Protocol (spec 24, 25).

Formal message types for agent-to-agent and agent-to-Main-Brain communication.
Every message carries the full spec-24 field set: task_id, agent_id,
message_type, timestamp, status, objective, input, result, evidence, errors,
warnings, next_action, confidence, artifacts.

Message types (spec 25):
    TASK_REQUEST, TASK_ACCEPTED, TASK_REJECTED, TASK_PROGRESS, TASK_RESULT,
    TASK_FAILED, TOOL_REQUEST, TOOL_RESULT, PERMISSION_REQUEST,
    VERIFICATION_REQUEST, VERIFICATION_RESULT, RECOVERY_REQUEST,
    CANCEL_REQUEST, CANCELLED, COMPLETED
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


class MessageType(str, Enum):
    """Spec 25 message types."""
    TASK_REQUEST = "TASK_REQUEST"
    TASK_ACCEPTED = "TASK_ACCEPTED"
    TASK_REJECTED = "TASK_REJECTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_RESULT = "TASK_RESULT"
    TASK_FAILED = "TASK_FAILED"
    TOOL_REQUEST = "TOOL_REQUEST"
    TOOL_RESULT = "TOOL_RESULT"
    PERMISSION_REQUEST = "PERMISSION_REQUEST"
    VERIFICATION_REQUEST = "VERIFICATION_REQUEST"
    VERIFICATION_RESULT = "VERIFICATION_RESULT"
    RECOVERY_REQUEST = "RECOVERY_REQUEST"
    CANCEL_REQUEST = "CANCEL_REQUEST"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


@dataclass
class AgentMessage:
    """Formal agent communication message (spec 24).

    Every message must contain where applicable: task_id, agent_id,
    message_type, timestamp, status, objective, input, result, evidence,
    errors, warnings, next_action, confidence, artifacts.
    """
    task_id: str = ""
    agent_id: str = ""
    message_type: MessageType = MessageType.TASK_RESULT
    timestamp: float = field(default_factory=time.time)
    status: str = "pending"
    objective: str = ""
    input: str = ""
    result: str = ""
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: str = ""
    confidence: float = 0.5
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp,
            "status": self.status,
            "objective": self.objective,
            "input": self.input,
            "result": self.result,
            "evidence": self.evidence,
            "errors": self.errors,
            "warnings": self.warnings,
            "next_action": self.next_action,
            "confidence": self.confidence,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentMessage":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        valid = {k: v for k, v in d.items() if k in known}
        if "message_type" in valid and isinstance(valid["message_type"], str):
            valid["message_type"] = MessageType(valid["message_type"])
        return cls(**valid)


class AgentCommunicationBus:
    """Agent-to-agent and agent-to-Main-Brain messaging bus.

    Supports publish/subscribe, request/response, and broadcast patterns.
    All messages are logged for observability.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[AgentMessage], None]]] = {}
        self._history: list[AgentMessage] = []
        self._lock = asyncio.Lock()
        self._max_history = 1000

    async def publish(self, message: AgentMessage) -> None:
        """Publish a message to all subscribers of the message type."""
        async with self._lock:
            self._history.append(message)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        # Notify subscribers
        msg_type = message.message_type.value
        subscribers = self._subscribers.get(msg_type, []) + self._subscribers.get("*", [])
        for fn in subscribers:
            try:
                fn(message)
            except Exception as exc:  # noqa: BLE001
                logger.warning("message subscriber failed: %s", exc)

    async def subscribe(
        self, message_type: str | MessageType, callback: Callable[[AgentMessage], None]
    ) -> None:
        """Subscribe to a message type (or "*" for all)."""
        key = message_type.value if isinstance(message_type, MessageType) else message_type
        async with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            self._subscribers[key].append(callback)

    async def unsubscribe(
        self, message_type: str | MessageType, callback: Callable[[AgentMessage], None]
    ) -> None:
        """Unsubscribe from a message type."""
        key = message_type.value if isinstance(message_type, MessageType) else message_type
        async with self._lock:
            if key in self._subscribers:
                try:
                    self._subscribers[key].remove(callback)
                except ValueError:
                    pass

    async def request(
        self, message: AgentMessage, *, timeout: float = 30.0
    ) -> AgentMessage | None:
        """Send a request and wait for a response (request/response pattern).

        The response is expected to have the same task_id and a COMPLETED
        or TASK_RESULT message type.
        """
        response_future: asyncio.Future[AgentMessage] = asyncio.get_event_loop().create_future()

        def _on_response(msg: AgentMessage) -> None:
            if (
                msg.task_id == message.task_id
                and msg.message_type in (MessageType.COMPLETED, MessageType.TASK_RESULT)
                and msg.agent_id != message.agent_id
                and not response_future.done()
            ):
                response_future.set_result(msg)

        # Subscribe to response types, not the request type
        response_types = [MessageType.COMPLETED, MessageType.TASK_RESULT]
        for rt in response_types:
            await self.subscribe(rt, _on_response)
        try:
            await self.publish(message)
            return await asyncio.wait_for(response_future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("request timeout for task %s", message.task_id)
            return None
        finally:
            for rt in response_types:
                await self.unsubscribe(rt, _on_response)

    async def broadcast(
        self, agent_ids: list[str], message: AgentMessage
    ) -> None:
        """Broadcast a message to multiple agents."""
        for agent_id in agent_ids:
            msg = AgentMessage(
                task_id=message.task_id,
                agent_id=agent_id,
                message_type=message.message_type,
                status=message.status,
                objective=message.objective,
                input=message.input,
                result=message.result,
                evidence=message.evidence,
                errors=message.errors,
                warnings=message.warnings,
                next_action=message.next_action,
                confidence=message.confidence,
                artifacts=message.artifacts,
                metadata=message.metadata,
            )
            await self.publish(msg)

    def history(
        self, *, limit: int = 100, agent_id: str | None = None,
        message_type: str | None = None,
    ) -> list[AgentMessage]:
        """Get message history with optional filters."""
        msgs = self._history
        if agent_id:
            msgs = [m for m in msgs if m.agent_id == agent_id]
        if message_type:
            msgs = [m for m in msgs if m.message_type.value == message_type]
        return msgs[-limit:]

    def stats(self) -> dict[str, Any]:
        """Get bus statistics."""
        by_type: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for m in self._history:
            by_type[m.message_type.value] = by_type.get(m.message_type.value, 0) + 1
            by_agent[m.agent_id] = by_agent.get(m.agent_id, 0) + 1
        return {
            "total_messages": len(self._history),
            "by_type": by_type,
            "by_agent": by_agent,
            "subscribers": {k: len(v) for k, v in self._subscribers.items()},
        }


# Module-level singleton
_BUS: AgentCommunicationBus | None = None


def get_bus() -> AgentCommunicationBus:
    global _BUS
    if _BUS is None:
        _BUS = AgentCommunicationBus()
    return _BUS


def new_task_id() -> str:
    return uuid.uuid4().hex[:12]


__all__ = [
    "MessageType", "AgentMessage", "AgentCommunicationBus",
    "get_bus", "new_task_id",
]
