"""Professional cognitive loop — integrates ReAct reasoning, working memory,
context compression, and tool composition into a single reasoning pipeline.

This is the core reasoning engine that the Orchestrator's _run_cognition_loop
should use for professional-grade agent cognition.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger
from app.brain.advanced.working_memory import WorkingMemory
from app.brain.advanced.context_compressor import ContextCompressor
from app.brain.advanced.tool_composer import ToolComposer
from app.brain.advanced.uncertainty import UncertaintyEstimator
from app.brain.advanced.metacognition import Metacognition, Strategy

logger = get_logger(__name__)


@dataclass
class CognitiveLoopResult:
    """Result of a cognitive loop execution."""
    answer: str
    success: bool
    iterations: int
    tool_calls: int
    reasoning_trace: list[dict[str, Any]] = field(default_factory=list)
    working_memory_context: str = ""
    confidence: float = 0.5
    uncertainty: float = 0.5
    strategy_used: str = ""
    execution_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class CognitiveLoop:
    """Professional cognitive loop with ReAct reasoning, working memory,
    context compression, and tool composition.

    This loop enhances the basic ReAct pattern with:
    - Working memory for attention tracking and context retention
    - Context compression for managing long contexts
    - Tool composition for chaining multiple tools
    - Metacognitive strategy selection
    - Uncertainty estimation for confidence calibration
    """

    def __init__(
        self,
        *,
        llm: Any = None,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None,
        max_iterations: int = 10,
        max_tool_calls: int = 5,
        working_memory_capacity: int = 20,
        enable_compression: bool = True,
        enable_tool_composition: bool = True,
        enable_metacognition: bool = True,
        enable_uncertainty: bool = True,
    ) -> None:
        self._llm = llm
        self._tool_executor = tool_executor
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls
        self._enable_compression = enable_compression
        self._enable_tool_composition = enable_tool_composition
        self._enable_metacognition = enable_metacognition
        self._enable_uncertainty = enable_uncertainty

        # Subsystems
        self._working_memory = WorkingMemory(capacity=working_memory_capacity)
        self._compressor = ContextCompressor(llm=llm) if llm else None
        self._composer = ToolComposer(tool_executor=tool_executor) if tool_executor else None
        self._uncertainty = UncertaintyEstimator()
        self._meta = Metacognition()

    async def run(
        self,
        *,
        task: str,
        context: str | None = None,
        available_tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        history: list[Any] | None = None,
    ) -> CognitiveLoopResult:
        """Execute the professional cognitive loop.

        Args:
            task: The user task.
            context: Additional context.
            available_tools: Available tool specs.
            system_prompt: System prompt.
            history: Conversation history.

        Returns:
            CognitiveLoopResult with the answer and full execution metadata.
        """
        start_time = time.time()
        reasoning_trace: list[dict[str, Any]] = []
        tool_call_count = 0

        # Step 1: Metacognitive strategy selection
        strategy = Strategy.REACT
        if self._enable_metacognition:
            strategy = await self._meta.recommend_strategy()
            await self._meta.update(confidence=0.5, uncertainty=0.5)

        # Step 2: Add task to working memory
        await self._working_memory.add(task, importance=0.9, metadata={"type": "task"})

        # Step 3: Build initial prompt with working memory context
        wm_context = self._working_memory.to_context_string(max_items=5)
        prompt = self._build_prompt(task, system_prompt, context, available_tools, wm_context)

        # Step 4: Compress context if too long
        if self._enable_compression and self._compressor and len(prompt) > 8000:
            try:
                compressed = await self._compressor.compress(prompt, max_tokens=4000)
                if compressed:
                    prompt = compressed
                    reasoning_trace.append({
                        "step": "compression",
                        "detail": f"Compressed prompt from {len(prompt)} to {len(compressed)} chars",
                    })
            except Exception as exc:
                logger.warning("Context compression failed: %s", exc)

        # Step 5: ReAct reasoning loop
        answer = ""
        for iteration in range(self._max_iterations):
            # Reasoning step
            thought = await self._reason(prompt, reasoning_trace, iteration)
            reasoning_trace.append({
                "step": "thought",
                "iteration": iteration,
                "content": thought[:500],
            })

            # Check for terminal answer
            if self._is_terminal(thought):
                answer = self._extract_answer(thought)
                reasoning_trace.append({
                    "step": "answer",
                    "content": answer[:500],
                })
                break

            # Action step: extract and execute tool call
            tool_name, tool_args = self._parse_action(thought)
            if tool_name and tool_call_count < self._max_tool_calls:
                # Try tool composition first
                if self._enable_tool_composition and self._composer:
                    try:
                        chain_result = await self._try_tool_chain(tool_name, tool_args, available_tools)
                        if chain_result:
                            tool_call_count += 1
                            reasoning_trace.append({
                                "step": "tool_chain",
                                "tool": tool_name,
                                "result": chain_result[:500],
                            })
                            prompt += f"\n\nObservation: {chain_result}"
                            continue
                    except Exception as exc:
                        logger.debug("Tool chain failed: %s", exc)

                # Single tool execution
                if self._tool_executor:
                    try:
                        result = await self._tool_executor(tool_name, tool_args)
                    except Exception as exc:
                        result = f"Error executing {tool_name}: {exc}"
                else:
                    result = f"[no executor for {tool_name}]"

                tool_call_count += 1
                reasoning_trace.append({
                    "step": "tool_call",
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result[:500],
                })

                # Add observation to prompt
                prompt += f"\n\nObservation: {result}"

                # Add to working memory
                await self._working_memory.add(
                    f"Tool {tool_name}: {result[:200]}",
                    importance=0.6,
                    metadata={"type": "observation", "tool": tool_name},
                )

            elif tool_call_count >= self._max_tool_calls:
                answer = self._force_answer(reasoning_trace)
                reasoning_trace.append({
                    "step": "answer",
                    "content": answer[:500],
                })
                break
        else:
            answer = self._force_answer(reasoning_trace)
            reasoning_trace.append({
                "step": "answer",
                "content": answer[:500],
            })

        # Step 6: Add result to working memory
        if answer:
            await self._working_memory.add(
                answer[:500],
                importance=0.7,
                metadata={"type": "result"},
            )

        # Step 7: Uncertainty estimation
        confidence = 0.5
        uncertainty = 0.5
        if self._enable_uncertainty:
            uncertainty_result = await self._uncertainty.estimate(
                model_confidence=0.7 if answer else 0.3,
                task_complexity=0.5,
                task_type="general",
            )
            confidence = uncertainty_result.confidence
            uncertainty = uncertainty_result.uncertainty

        # Step 8: Metacognitive update
        execution_time = time.time() - start_time
        if self._enable_metacognition:
            await self._meta.update(
                confidence=confidence,
                uncertainty=uncertainty,
                latency=execution_time,
                error=not answer,
                success=bool(answer),
            )
            await self._meta.record_strategy_result(strategy, bool(answer), execution_time)

        # Step 9: Get working memory context
        wm_context = self._working_memory.to_context_string(max_items=10)

        return CognitiveLoopResult(
            answer=answer,
            success=bool(answer.strip()),
            iterations=iteration + 1,
            tool_calls=tool_call_count,
            reasoning_trace=reasoning_trace,
            working_memory_context=wm_context,
            confidence=confidence,
            uncertainty=uncertainty,
            strategy_used=strategy.value,
            execution_time=execution_time,
            metadata={
                "metacognition": self._meta.get_summary() if self._enable_metacognition else {},
                "working_memory_items": self._working_memory.size,
            },
        )

    def _build_prompt(
        self,
        task: str,
        system_prompt: str | None,
        context: str | None,
        available_tools: list[dict[str, Any]] | None,
        wm_context: str,
    ) -> str:
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if context:
            parts.append(f"Context:\n{context}")
        if wm_context:
            parts.append(wm_context)
        if available_tools:
            tool_desc = "\n".join(
                f"- {t.get('name', '?')}: {t.get('description', '')}"
                for t in available_tools
            )
            parts.append(f"Available tools:\n{tool_desc}")
        parts.append(f"Task: {task}")
        parts.append(
            "Think step by step. For each step, either:\n"
            "1. Reason about the problem (prefix with 'Thought:')\n"
            "2. Call a tool (prefix with 'Action: tool_name(args)')\n"
            "3. When you have the final answer, prefix with 'Answer:'"
        )
        return "\n\n".join(parts)

    async def _reason(self, prompt: str, trace: list[dict[str, Any]], iteration: int) -> str:
        """Ask the LLM for the next reasoning step."""
        if self._llm is None:
            return f"Thought: iteration {iteration}, no LLM configured"
        try:
            from app.services.llm_service import ChatMessage
            resp = await self._llm.complete(
                [ChatMessage(role="user", content=prompt)],
                max_tokens=1024,
                temperature=0.2,
            )
            return (resp.content or "").strip()
        except Exception as exc:
            logger.warning("Cognitive loop reasoning failed: %s", exc)
            return f"Thought: error in reasoning: {exc}"

    def _is_terminal(self, thought: str) -> bool:
        return thought.strip().lower().startswith("answer:")

    def _extract_answer(self, thought: str) -> str:
        lines = thought.split("\n")
        for line in lines:
            if line.strip().lower().startswith("answer:"):
                return line.split(":", 1)[1].strip()
        return thought

    def _parse_action(self, thought: str) -> tuple[str | None, dict[str, Any]]:
        for line in thought.split("\n"):
            line = line.strip()
            if line.lower().startswith("action:"):
                action_str = line.split(":", 1)[1].strip()
                if "(" in action_str and action_str.endswith(")"):
                    tool_name = action_str[:action_str.index("(")].strip()
                    args_str = action_str[action_str.index("(") + 1:-1]
                    try:
                        import json
                        args = json.loads(args_str) if args_str.strip() else {}
                    except (json.JSONDecodeError, ValueError):
                        args = {"raw": args_str}
                    return tool_name, args
                return action_str, {}
        return None, {}

    def _force_answer(self, trace: list[dict[str, Any]]) -> str:
        thoughts = [s.get("content", "") for s in trace if s.get("step") == "thought"]
        observations = [s.get("result", "") for s in trace if s.get("step") in ("tool_call", "tool_chain")]
        if observations:
            return f"Based on analysis: {observations[-1][:500]}"
        if thoughts:
            return f"Analysis incomplete. Last thought: {thoughts[-1][:500]}"
        return "Unable to complete the task within the iteration budget."

    async def _try_tool_chain(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        available_tools: list[dict[str, Any]] | None,
    ) -> str | None:
        """Try to compose a tool chain for complex operations."""
        if not self._composer or not available_tools:
            return None
        # Simple chain: if the tool produces output that could be fed to another tool
        # This is a placeholder for more sophisticated chain logic
        return None

    async def get_working_memory_context(self) -> str:
        """Get working memory as a context string."""
        return self._working_memory.to_context_string()

    async def clear(self) -> None:
        """Clear all state."""
        await self._working_memory.clear()
        await self._meta.reset()
