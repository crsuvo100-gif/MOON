"""ReAct (Reasoning + Acting) loop for professional agent cognition.

Implements the classic ReAct pattern: Thought → Action → Observation → Thought → ...
with bounded iterations, structured reasoning traces, and graceful termination.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class StepType(str, Enum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    ANSWER = "answer"


@dataclass
class ReActStep:
    """One step in the ReAct loop."""
    step_type: StepType
    content: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: str | None = None
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())


@dataclass
class ReActResult:
    """Result of a ReAct loop execution."""
    answer: str
    steps: list[ReActStep]
    iterations: int
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class ReActLoop:
    """Bounded ReAct loop with structured reasoning traces.

    The loop alternates between reasoning (thought) and acting (tool calls),
    observing results, and deciding whether to continue or terminate.
    """

    def __init__(
        self,
        *,
        max_iterations: int = 10,
        max_tool_calls: int = 5,
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None,
        llm: Any = None,
    ) -> None:
        self._max_iterations = max_iterations
        self._max_tool_calls = max_tool_calls
        self._tool_executor = tool_executor
        self._llm = llm

    async def run(
        self,
        *,
        task: str,
        system_prompt: str | None = None,
        context: str | None = None,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> ReActResult:
        """Execute the ReAct loop for a given task.

        Args:
            task: The user task/prompt.
            system_prompt: Optional system prompt override.
            context: Optional additional context.
            available_tools: List of tool specs (name, description, parameters).

        Returns:
            ReActResult with the final answer and full reasoning trace.
        """
        steps: list[ReActStep] = []
        tool_call_count = 0
        answer = ""

        # Build the initial prompt
        prompt = self._build_prompt(task, system_prompt, context, available_tools, steps)

        for iteration in range(self._max_iterations):
            # Reasoning step: ask the LLM what to do next
            thought = await self._reason(prompt, steps, iteration)
            steps.append(ReActStep(step_type=StepType.THOUGHT, content=thought))

            # Check if the model wants to terminate with an answer
            if self._is_terminal(thought):
                answer = self._extract_answer(thought)
                steps.append(ReActStep(step_type=StepType.ANSWER, content=answer))
                break

            # Action step: extract and execute tool call
            tool_name, tool_args = self._parse_action(thought)
            if tool_name and tool_call_count < self._max_tool_calls:
                if self._tool_executor:
                    try:
                        result = await self._tool_executor(tool_name, tool_args)
                    except Exception as exc:
                        result = f"Error executing {tool_name}: {exc}"
                else:
                    result = f"[no executor for {tool_name}]"
                tool_call_count += 1
                steps.append(ReActStep(
                    step_type=StepType.ACTION,
                    content=f"Calling {tool_name}({tool_args})",
                    tool_name=tool_name,
                    tool_args=tool_args,
                ))
                steps.append(ReActStep(
                    step_type=StepType.OBSERVATION,
                    content=result,
                    tool_name=tool_name,
                    tool_result=result,
                ))
                # Append observation to prompt for next iteration
                prompt += f"\n\nObservation: {result}"
            elif tool_call_count >= self._max_tool_calls:
                # Force termination when tool budget exhausted
                answer = self._force_answer(steps)
                steps.append(ReActStep(step_type=StepType.ANSWER, content=answer))
                break
        else:
            # Loop exhausted without termination
            answer = self._force_answer(steps)
            steps.append(ReActStep(step_type=StepType.ANSWER, content=answer))

        return ReActResult(
            answer=answer,
            steps=steps,
            iterations=iteration + 1,
            success=bool(answer.strip()),
            metadata={"tool_calls": tool_call_count},
        )

    def _build_prompt(
        self,
        task: str,
        system_prompt: str | None,
        context: str | None,
        available_tools: list[dict[str, Any]] | None,
        steps: list[ReActStep],
    ) -> str:
        parts = []
        if system_prompt:
            parts.append(system_prompt)
        if context:
            parts.append(f"Context:\n{context}")
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

    async def _reason(self, prompt: str, steps: list[ReActStep], iteration: int) -> str:
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
            logger.warning("ReAct reasoning failed: %s", exc)
            return f"Thought: error in reasoning: {exc}"

    def _is_terminal(self, thought: str) -> bool:
        """Check if the thought indicates a final answer."""
        return thought.strip().lower().startswith("answer:")

    def _extract_answer(self, thought: str) -> str:
        """Extract the answer from a terminal thought."""
        lines = thought.split("\n")
        for line in lines:
            if line.strip().lower().startswith("answer:"):
                return line.split(":", 1)[1].strip()
        return thought

    def _parse_action(self, thought: str) -> tuple[str | None, dict[str, Any]]:
        """Parse a tool call from a thought."""
        for line in thought.split("\n"):
            line = line.strip()
            if line.lower().startswith("action:"):
                action_str = line.split(":", 1)[1].strip()
                # Parse tool_name(args) format
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

    def _force_answer(self, steps: list[ReActStep]) -> str:
        """Generate a fallback answer from the reasoning trace."""
        thoughts = [s.content for s in steps if s.step_type == StepType.THOUGHT]
        observations = [s.content for s in steps if s.step_type == StepType.OBSERVATION]
        if observations:
            return f"Based on analysis: {observations[-1][:500]}"
        if thoughts:
            return f"Analysis incomplete. Last thought: {thoughts[-1][:500]}"
        return "Unable to complete the task within the iteration budget."
