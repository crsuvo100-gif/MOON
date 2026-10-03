"""Agent Communication Bus — event-driven inter-agent communication.

Provides a publish/subscribe system for agents to communicate, coordinate,
and share state without tight coupling. Supports typed events, priorities,
and delivery guarantees.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


class EventPriority(Enum):
    """Event priority levels."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class AgentEvent:
    """An event published to the communication bus."""
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    ttl: float = 300.0  # seconds before event expires
    delivered: bool = False

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


@dataclass
class Subscription:
    """A subscription to events of a specific type."""
    event_type: str
    callback: Callable[[AgentEvent], Any]
    subscriber_id: str
    priority_filter: EventPriority | None = None
    active: bool = True


class CommunicationBus:
    """Event-driven communication bus for inter-agent messaging.

    Agents publish events to the bus and subscribe to event types they
    care about. The bus handles delivery, filtering, and dead-letter
    routing for undeliverable events.
    """

    def __init__(self, *, max_queue_size: int = 1000, delivery_timeout: float = 30.0) -> None:
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        self._event_queue: deque[AgentEvent] = deque(maxlen=max_queue_size)
        self._dead_letter: deque[AgentEvent] = deque(maxlen=100)
        self._delivery_timeout = delivery_timeout
        self._running = False
        self._delivery_task: asyncio.Task | None = None
        self._metrics: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the delivery loop."""
        if self._running:
            return
        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_loop())
        logger.info("Communication bus started")

    async def stop(self) -> None:
        """Stop the delivery loop."""
        self._running = False
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass
        logger.info("Communication bus stopped")

    def subscribe(
        self,
        event_type: str,
        callback: Callable[[AgentEvent], Any],
        *,
        subscriber_id: str = "",
        priority_filter: EventPriority | None = None,
    ) -> str:
        """Subscribe to events of a specific type.

        Args:
            event_type: The event type to subscribe to.
            callback: Async or sync callback function.
            subscriber_id: Unique subscriber identifier.
            priority_filter: Only deliver events at or above this priority.

        Returns:
            Subscription ID for later unsubscribe.
        """
        sub_id = subscriber_id or f"sub_{uuid.uuid4().hex[:8]}"
        sub = Subscription(
            event_type=event_type,
            callback=callback,
            subscriber_id=sub_id,
            priority_filter=priority_filter,
        )
        self._subscriptions[event_type].append(sub)
        self._metrics["subscriptions_total"] += 1
        logger.debug("New subscription: %s -> %s", sub_id, event_type)
        return sub_id

    def unsubscribe(self, event_type: str, subscriber_id: str) -> bool:
        """Remove a subscription."""
        subs = self._subscriptions.get(event_type, [])
        for i, sub in enumerate(subs):
            if sub.subscriber_id == subscriber_id:
                subs.pop(i)
                self._metrics["subscriptions_cancelled"] += 1
                return True
        return False

    async def publish(self, event: AgentEvent) -> int:
        """Publish an event to the bus.

        Returns:
            Number of subscribers that received the event.
        """
        self._event_queue.append(event)
        self._metrics["events_published"] += 1
        # Immediate delivery attempt for critical events
        if event.priority == EventPriority.CRITICAL:
            return await self._deliver_event(event)
        return len(self._subscriptions.get(event.event_type, []))

    async def publish_nowait(self, event: AgentEvent) -> None:
        """Publish without waiting for delivery (fire-and-forget)."""
        self._event_queue.append(event)
        self._metrics["events_published"] += 1

    async def _delivery_loop(self) -> None:
        """Background task that delivers queued events."""
        while self._running:
            try:
                if self._event_queue:
                    event = self._event_queue.popleft()
                    if event.is_expired():
                        self._metrics["events_expired"] += 1
                        continue
                    await self._deliver_event(event)
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Delivery loop error: %s", exc)
                await asyncio.sleep(0.1)

    async def _deliver_event(self, event: AgentEvent) -> int:
        """Deliver an event to all matching subscribers."""
        subs = self._subscriptions.get(event.event_type, [])
        if not subs:
            self._metrics["events_no_subscribers"] += 1
            return 0

        delivered = 0
        for sub in subs:
            if not sub.active:
                continue
            if sub.priority_filter and event.priority.value > sub.priority_filter.value:
                continue
            try:
                result = sub.callback(event)
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=self._delivery_timeout)
                delivered += 1
                self._metrics["events_delivered"] += 1
            except asyncio.TimeoutError:
                self._metrics["delivery_timeouts"] += 1
                logger.warning("Delivery timeout for %s -> %s", event.event_type, sub.subscriber_id)
            except Exception as exc:  # noqa: BLE001
                self._metrics["delivery_errors"] += 1
                logger.debug("Delivery error for %s -> %s: %s", event.event_type, sub.subscriber_id, exc)

        event.delivered = delivered > 0
        if not event.delivered:
            self._dead_letter.append(event)
            self._metrics["events_dead_letter"] += 1
        return delivered

    def get_metrics(self) -> dict[str, Any]:
        """Get bus metrics."""
        return {
            **self._metrics,
            "queue_size": len(self._event_queue),
            "dead_letter_size": len(self._dead_letter),
            "active_subscriptions": sum(
                1 for subs in self._subscriptions.values() for s in subs if s.active
            ),
            "event_types": list(self._subscriptions.keys()),
        }

    def get_dead_letter(self, *, clear: bool = False) -> list[AgentEvent]:
        """Get dead-letter events (undeliverable)."""
        events = list(self._dead_letter)
        if clear:
            self._dead_letter.clear()
        return events
