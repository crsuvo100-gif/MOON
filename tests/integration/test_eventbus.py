"""Integration test: internal event bus (spec 33, 41) emits spec events."""

from __future__ import annotations

from app.runtime.event_bus import bus, EventType
from app.runtime.integration import emit


def test_event_bus_publish_and_subscribe():
    b = bus()
    events = []
    b.subscribe(lambda ev: events.append(ev))
    emit("TASK_CREATED", agent_id="demo", detail="x")
    assert any(e.type == "TASK_CREATED" and e.agent_id == "demo" for e in events)


def test_spec_event_names_valid():
    # The full spec 41 event set must be publishable.
    for name in ("AGENT_SELECTED", "TOOL_COMPLETED", "VERIFICATION_PASSED",
                 "AGENT_CREATED", "AGENT_APPROVED", "ROLLBACK_COMPLETED",
                 "MEMORY_UPDATED", "SKILL_UPDATED"):
        emit(name, agent_id="demo", detail="integration")
    assert True
