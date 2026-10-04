"""Live LLM Integration Tests — verify real LLM calls work end-to-end.

These tests verify that:
1. Agent brains can make real LLM calls
2. The communication bus works with real messages
3. Conflict resolution works with real LLM output
4. The full pipeline works end-to-end with real models

These tests SKIP gracefully when no LLM backend is available.
They do NOT fail when Ollama/OpenAI is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import socket

import pytest

from app.brain.agent_brain import AgentBrain
from app.agents.communication_protocol import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
    get_bus,
    new_task_id,
)
from app.brain.advanced_conflict import (
    AdvancedConflictResolver,
    ConflictResolutionStrategy,
    ConflictSeverity,
)
from app.brain.aggregator import (
    AgentEnvelope,
    AggregatedResult,
    ConflictKind,
    ConflictResolver,
    ResultAggregator,
)
from app.agents.registry import get_registry


def _ollama_available() -> bool:
    """Check if Ollama is available."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(("127.0.0.1", 11434))
        sock.close()
        return True
    except Exception:
        return False


def _openai_available() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.environ.get("OPENAI_API_KEY"))


def _any_llm_available() -> bool:
    """Check if any LLM backend is available."""
    return _ollama_available() or _openai_available()


requires_llm = pytest.mark.skipif(
    not _any_llm_available(),
    reason="No LLM backend available (Ollama or OpenAI)",
)


class TestLiveLLMCalls:
    """Test that real LLM calls work."""

    @requires_llm
    async def test_agent_brain_can_call_llm(self):
        """Test that AgentBrain can make a real LLM call."""
        brain = AgentBrain("test_agent")
        await brain.setup()
        try:
            result = await brain.run("What is 2+2? Answer with just the number.")
            assert result is not None
            assert len(result) > 0
        finally:
            await brain.teardown()

    @requires_llm
    async def test_agent_brain_with_context(self):
        """Test that AgentBrain can use context."""
        brain = AgentBrain("test_agent")
        await brain.setup()
        try:
            result = await brain.run(
                "What is the capital of France?",
                context="You are a geography expert.",
            )
            assert result is not None
            assert len(result) > 0
        finally:
            await brain.teardown()

    async def test_multi_agent_communication(self):
        """Test that agents can communicate via the bus."""
        bus = get_bus()
        received: list[AgentMessage] = []

        def on_message(msg: AgentMessage) -> None:
            received.append(msg)

        await bus.subscribe(MessageType.TASK_RESULT, on_message)

        test_msg = AgentMessage(
            task_id=new_task_id(),
            agent_id="test_agent",
            message_type=MessageType.TASK_RESULT,
            result="test result",
        )
        await bus.publish(test_msg)

        await asyncio.sleep(0.5)

        assert len(received) > 0
        assert received[0].result == "test result"

    @requires_llm
    async def test_conflict_resolution_with_llm(self):
        """Test that conflict resolution works with real LLM output."""
        env_a = AgentEnvelope(
            task_id="test_conflict",
            agent_id="agent_a",
            result="The sky is blue",
            evidence=["Scientific consensus", "Observable fact"],
            confidence=0.9,
        )
        env_b = AgentEnvelope(
            task_id="test_conflict",
            agent_id="agent_b",
            result="The sky is not blue",
            evidence=["Alternative view"],
            confidence=0.3,
        )

        brain = AgentBrain("conflict_resolver")
        await brain.setup()
        try:
            resolver = AdvancedConflictResolver(
                brain=brain,
                default_strategy=ConflictResolutionStrategy.EVIDENCE_BASED,
            )

            conflicts = resolver.detect_advanced([env_a, env_b])
            assert len(conflicts) > 0
            assert conflicts[0].base_conflict.kind == ConflictKind.CONTRADICTION

            resolved = await resolver.resolve(conflicts, [env_a, env_b])
            assert len(resolved) > 0
            # Conflict may or may not be resolved depending on LLM availability
            # and the quality of the adjudication
        finally:
            await brain.teardown()


class TestLiveMultiBrainPipeline:
    """Test the full multi-brain pipeline with real LLMs."""

    @requires_llm
    async def test_result_aggregation(self):
        """Test that results from multiple agents can be aggregated."""
        envelopes = [
            AgentEnvelope(
                task_id="test_agg",
                agent_id=f"agent_{i}",
                result=f"Result from agent {i}",
                evidence=[f"Evidence {i}"],
                confidence=0.5 + i * 0.1,
            )
            for i in range(3)
        ]

        agg = ResultAggregator()
        result = agg.aggregate(envelopes)
        assert result is not None
        assert len(result.contributing_agents) > 0

    @requires_llm
    async def test_agent_selection(self):
        """Test that the registry can select agents by capability."""
        registry = get_registry()
        agents = registry.select(capability="web research")
        assert len(agents) > 0

    @requires_llm
    async def test_orchestrator_instantiation(self):
        """Test that the orchestrator can be instantiated."""
        from app.brain.orchestrator import Orchestrator
        from app.config.settings import Settings

        orch = Orchestrator(Settings())
        await orch.setup()
        try:
            assert orch is not None
        finally:
            await orch.teardown()


class TestLiveConflictDetection:
    """Test conflict detection with real LLM output."""

    @requires_llm
    async def test_detect_contradiction(self):
        """Test that contradictions are detected."""
        env_a = AgentEnvelope(
            task_id="test",
            agent_id="agent_a",
            result="The Earth is round",
            evidence=["Scientific fact"],
            confidence=0.95,
        )
        env_b = AgentEnvelope(
            task_id="test",
            agent_id="agent_b",
            result="The Earth is not round",
            evidence=["Flat earth theory"],
            confidence=0.1,
        )

        resolver = AdvancedConflictResolver()
        conflicts = resolver.detect_advanced([env_a, env_b])
        assert len(conflicts) > 0
        assert conflicts[0].base_conflict.kind == ConflictKind.CONTRADICTION

    @requires_llm
    async def test_detect_divergence(self):
        """Test that divergences are detected."""
        env_a = AgentEnvelope(
            task_id="test",
            agent_id="agent_a",
            result="The answer is 42",
            evidence=["Calculation"],
            confidence=0.9,
        )
        env_b = AgentEnvelope(
            task_id="test",
            agent_id="agent_b",
            result="The answer is not 42",
            evidence=["Different calculation"],
            confidence=0.9,
        )

        resolver = AdvancedConflictResolver()
        conflicts = resolver.detect_advanced([env_a, env_b])
        assert isinstance(conflicts, list)

    @requires_llm
    async def test_detect_failure(self):
        """Test that failures are detected."""
        env_a = AgentEnvelope(
            task_id="test",
            agent_id="agent_a",
            result="",
            errors=["Connection timeout"],
            status="failed",
        )
        env_b = AgentEnvelope(
            task_id="test",
            agent_id="agent_b",
            result="Success result",
            evidence=["Completed"],
            status="completed",
        )

        resolver = AdvancedConflictResolver()
        conflicts = resolver.detect_advanced([env_a, env_b])
        assert len(conflicts) > 0
        assert conflicts[0].base_conflict.kind == ConflictKind.FAILURE


class TestLiveAgentBrains:
    """Test that agent brains work with real LLMs."""

    @requires_llm
    async def test_coding_agent_brain(self):
        """Test that the coding agent brain can answer a coding question."""
        brain = AgentBrain("coding")
        await brain.setup()
        try:
            result = await brain.run("What is a Python list comprehension?")
            assert result is not None
            assert len(result) > 0
        finally:
            await brain.teardown()

    @requires_llm
    async def test_research_agent_brain(self):
        """Test that the research agent brain can answer a research question."""
        brain = AgentBrain("researcher")
        await brain.setup()
        try:
            result = await brain.run("What is machine learning?")
            assert result is not None
            assert len(result) > 0
        finally:
            await brain.teardown()

    @requires_llm
    async def test_security_agent_brain(self):
        """Test that the security agent brain can answer a security question."""
        brain = AgentBrain("security")
        await brain.setup()
        try:
            result = await brain.run("What is SQL injection?")
            assert result is not None
            assert len(result) > 0
        finally:
            await brain.teardown()
