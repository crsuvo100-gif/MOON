"""Tests for Agent Communication Protocol (spec 24, 25)."""
import asyncio
import pytest

from app.agents.communication_protocol import (
    AgentMessage,
    AgentCommunicationBus,
    MessageType,
    get_bus,
    new_task_id,
)


class TestMessageType:
    def test_all_spec25_types_exist(self):
        expected = {
            "TASK_REQUEST", "TASK_ACCEPTED", "TASK_REJECTED", "TASK_PROGRESS",
            "TASK_RESULT", "TASK_FAILED", "TOOL_REQUEST", "TOOL_RESULT",
            "PERMISSION_REQUEST", "VERIFICATION_REQUEST", "VERIFICATION_RESULT",
            "RECOVERY_REQUEST", "CANCEL_REQUEST", "CANCELLED", "COMPLETED",
        }
        actual = {t.name for t in MessageType}
        assert expected == actual

    def test_message_type_values(self):
        assert MessageType.TASK_REQUEST.value == "TASK_REQUEST"
        assert MessageType.COMPLETED.value == "COMPLETED"


class TestAgentMessage:
    def test_create_minimal(self):
        msg = AgentMessage(task_id="t1", agent_id="coding")
        assert msg.task_id == "t1"
        assert msg.agent_id == "coding"
        assert msg.message_type == MessageType.TASK_RESULT
        assert msg.status == "pending"
        assert msg.confidence == 0.5

    def test_to_dict_spec24_fields(self):
        msg = AgentMessage(
            task_id="t1",
            agent_id="coding",
            message_type=MessageType.TASK_RESULT,
            status="completed",
            objective="Fix bug",
            input="bug report",
            result="Fixed",
            evidence=["test passed"],
            errors=[],
            warnings=[],
            next_action="verify",
            confidence=0.9,
            artifacts=["file.py"],
        )
        d = msg.to_dict()
        # Spec 24 requires all these fields
        for field in [
            "task_id", "agent_id", "message_type", "timestamp", "status",
            "objective", "input", "result", "evidence", "errors",
            "warnings", "next_action", "confidence", "artifacts",
        ]:
            assert field in d, f"Missing spec-24 field: {field}"

    def test_from_dict_roundtrip(self):
        msg = AgentMessage(
            task_id="t1",
            agent_id="coding",
            message_type=MessageType.TASK_RESULT,
            status="completed",
            result="Fixed",
            confidence=0.9,
        )
        d = msg.to_dict()
        restored = AgentMessage.from_dict(d)
        assert restored.task_id == msg.task_id
        assert restored.agent_id == msg.agent_id
        assert restored.message_type == msg.message_type
        assert restored.status == msg.status
        assert restored.result == msg.result
        assert restored.confidence == msg.confidence

    def test_from_dict_ignores_unknown_fields(self):
        d = {
            "task_id": "t1",
            "agent_id": "coding",
            "message_type": "TASK_RESULT",
            "unknown_field": "should be ignored",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.task_id == "t1"
        assert not hasattr(msg, "unknown_field")


class TestAgentCommunicationBus:
    @pytest.fixture
    def bus(self):
        return AgentCommunicationBus()

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, bus):
        received = []
        await bus.subscribe(MessageType.TASK_RESULT, lambda m: received.append(m))
        msg = AgentMessage(task_id="t1", agent_id="coding", message_type=MessageType.TASK_RESULT)
        await bus.publish(msg)
        assert len(received) == 1
        assert received[0].task_id == "t1"

    @pytest.mark.asyncio
    async def test_subscribe_all(self, bus):
        received = []
        await bus.subscribe("*", lambda m: received.append(m))
        await bus.publish(AgentMessage(task_id="t1", message_type=MessageType.TASK_RESULT))
        await bus.publish(AgentMessage(task_id="t2", message_type=MessageType.TASK_FAILED))
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_request_response(self, bus):
        # Set up a responder
        async def responder():
            await asyncio.sleep(0.01)
            await bus.subscribe(
                MessageType.TASK_REQUEST,
                lambda m: asyncio.create_task(
                    bus.publish(AgentMessage(
                        task_id=m.task_id,
                        agent_id="responder",
                        message_type=MessageType.COMPLETED,
                        result="response",
                    ))
                ),
            )

        asyncio.create_task(responder())
        await asyncio.sleep(0.05)

        req = AgentMessage(
            task_id="req1",
            agent_id="requester",
            message_type=MessageType.TASK_REQUEST,
            objective="test",
        )
        resp = await bus.request(req, timeout=5.0)
        assert resp is not None
        assert resp.task_id == "req1"
        assert resp.message_type == MessageType.COMPLETED

    @pytest.mark.asyncio
    async def test_request_timeout(self, bus):
        req = AgentMessage(
            task_id="req1",
            agent_id="requester",
            message_type=MessageType.TASK_REQUEST,
        )
        resp = await bus.request(req, timeout=0.1)
        assert resp is None

    @pytest.mark.asyncio
    async def test_broadcast(self, bus):
        received = []
        await bus.subscribe(MessageType.TASK_REQUEST, lambda m: received.append(m))
        await bus.broadcast(["a1", "a2", "a3"], AgentMessage(
            task_id="t1",
            agent_id="main",
            message_type=MessageType.TASK_REQUEST,
        ))
        assert len(received) == 3

    def test_history(self, bus):
        # Manually add to history
        bus._history = [
            AgentMessage(task_id="t1", agent_id="a1", message_type=MessageType.TASK_RESULT),
            AgentMessage(task_id="t2", agent_id="a2", message_type=MessageType.TASK_FAILED),
            AgentMessage(task_id="t3", agent_id="a1", message_type=MessageType.COMPLETED),
        ]
        assert len(bus.history()) == 3
        assert len(bus.history(agent_id="a1")) == 2
        assert len(bus.history(message_type="TASK_FAILED")) == 1
        assert len(bus.history(limit=2)) == 2

    def test_stats(self, bus):
        bus._history = [
            AgentMessage(task_id="t1", agent_id="a1", message_type=MessageType.TASK_RESULT),
            AgentMessage(task_id="t2", agent_id="a2", message_type=MessageType.TASK_RESULT),
        ]
        stats = bus.stats()
        assert stats["total_messages"] == 2
        assert stats["by_type"]["TASK_RESULT"] == 2
        assert stats["by_agent"]["a1"] == 1


class TestHelpers:
    def test_new_task_id_unique(self):
        ids = {new_task_id() for _ in range(100)}
        assert len(ids) == 100

    def test_get_bus_singleton(self):
        b1 = get_bus()
        b2 = get_bus()
        assert b1 is b2
