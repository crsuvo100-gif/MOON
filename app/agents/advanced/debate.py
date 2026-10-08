"""debate.py — multi-agent debate system for adversarial reasoning.

Professional AI agents use debate to stress-test ideas, surface hidden
assumptions, and arrive at more robust conclusions. This module provides
a structured debate framework where multiple agents argue for and against
positions, with a judge agent synthesizing the strongest points.

Debate formats:
- ADVERSARIAL: two agents argue opposite sides
- PANEL: multiple agents present independent perspectives
- Socratic: one agent questions another's reasoning
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class DebateFormat(str, Enum):
    ADVERSARIAL = "adversarial"
    PANEL = "panel"
    SOCRATIC = "socratic"


class DebatePhase(str, Enum):
    OPENING = "opening"
    ARGUMENTS = "arguments"
    REBUTTALS = "rebuttals"
    CLOSING = "closing"
    JUDGMENT = "judgment"


@dataclass
class DebateArgument:
    argument_id: str
    agent_id: str
    position: str  # "for", "against", "neutral"
    claim: str
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    strength: float = 0.5  # 0-1
    timestamp: float = field(default_factory=time.time)
    rebuttal_to: str | None = None  # argument_id this rebuts


@dataclass
class DebateRound:
    round_number: int
    phase: DebatePhase
    arguments: list[DebateArgument] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class DebateResult:
    debate_id: str
    topic: str
    format: DebateFormat
    rounds: list[DebateRound] = field(default_factory=list)
    winner: str | None = None  # agent_id or "consensus"
    synthesis: str = ""
    confidence: float = 0.0
    key_insights: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class AgentDebate:
    """Multi-agent debate system for adversarial reasoning."""

    def __init__(
        self,
        agents: dict[str, Callable[[str, str], Awaitable[str]]],
        judge_agent: Callable[[str, list[DebateArgument]], Awaitable[str]] | None = None,
    ) -> None:
        self._agents = agents
        self._judge = judge_agent
        self._debates: dict[str, DebateResult] = {}

    async def run_debate(
        self,
        topic: str,
        format: DebateFormat = DebateFormat.ADVERSARIAL,
        rounds: int = 3,
        context: str = "",
    ) -> DebateResult:
        """Run a structured debate on a topic."""
        debate_id = str(uuid.uuid4())[:8]
        result = DebateResult(
            debate_id=debate_id,
            topic=topic,
            format=format,
        )

        agent_ids = list(self._agents.keys())
        if len(agent_ids) < 2:
            result.synthesis = "Debate requires at least 2 agents."
            result.confidence = 0.0
            self._debates[debate_id] = result
            return result

        for round_num in range(1, rounds + 1):
            round_data = await self._run_round(
                topic=topic,
                round_num=round_num,
                total_rounds=rounds,
                agent_ids=agent_ids,
                format=format,
                context=context,
                previous_rounds=result.rounds,
            )
            result.rounds.append(round_data)

        # Judge / synthesize
        all_args = [a for r in result.rounds for a in r.arguments]
        if self._judge:
            try:
                synthesis = await self._judge(topic, all_args)
                result.synthesis = synthesis
            except Exception as e:
                logger.warning("Judge agent failed: %s", e)
                result.synthesis = self._default_synthesis(all_args)
        else:
            result.synthesis = self._default_synthesis(all_args)

        result.confidence = self._compute_confidence(all_args)
        result.key_insights = self._extract_insights(all_args)
        result.winner = self._determine_winner(all_args)

        self._debates[debate_id] = result
        return result

    async def _run_round(
        self,
        topic: str,
        round_num: int,
        total_rounds: int,
        agent_ids: list[str],
        format: DebateFormat,
        context: str,
        previous_rounds: list[DebateRound],
    ) -> DebateRound:
        """Run a single debate round."""
        phase = self._phase_for_round(round_num, total_rounds)
        round_data = DebateRound(round_number=round_num, phase=phase)

        if format == DebateFormat.ADVERSARIAL:
            # Two agents argue opposite sides
            for i, agent_id in enumerate(agent_ids[:2]):
                position = "for" if i == 0 else "against"
                prompt = self._build_debate_prompt(
                    topic=topic,
                    position=position,
                    round_num=round_num,
                    phase=phase,
                    context=context,
                    previous_rounds=previous_rounds,
                )
                try:
                    response = await self._agents[agent_id](prompt, topic)
                    arg = DebateArgument(
                        argument_id=str(uuid.uuid4())[:8],
                        agent_id=agent_id,
                        position=position,
                        claim=response[:500],
                        reasoning=response,
                        strength=self._estimate_strength(response),
                    )
                    round_data.arguments.append(arg)
                except Exception as e:
                    logger.warning("Debate agent %s failed: %s", agent_id, e)

        elif format == DebateFormat.PANEL:
            # All agents present independent perspectives
            for agent_id in agent_ids:
                prompt = self._build_panel_prompt(
                    topic=topic,
                    round_num=round_num,
                    phase=phase,
                    context=context,
                )
                try:
                    response = await self._agents[agent_id](prompt, topic)
                    arg = DebateArgument(
                        argument_id=str(uuid.uuid4())[:8],
                        agent_id=agent_id,
                        position="neutral",
                        claim=response[:500],
                        reasoning=response,
                        strength=self._estimate_strength(response),
                    )
                    round_data.arguments.append(arg)
                except Exception as e:
                    logger.warning("Panel agent %s failed: %s", agent_id, e)

        elif format == DebateFormat.SOCRATIC:
            # One agent questions another's reasoning
            if len(agent_ids) >= 2:
                questioner = agent_ids[0]
                respondent = agent_ids[1]
                # Get respondent's previous argument
                prev_args = [
                    a for r in previous_rounds for a in r.arguments
                    if a.agent_id == respondent
                ]
                if prev_args:
                    last_arg = prev_args[-1]
                    prompt = (
                        f"Question this argument: '{last_arg.claim}'\n"
                        f"Topic: {topic}\n"
                        f"Find weaknesses, hidden assumptions, or counterexamples."
                    )
                    try:
                        response = await self._agents[questioner](prompt, topic)
                        arg = DebateArgument(
                            argument_id=str(uuid.uuid4())[:8],
                            agent_id=questioner,
                            position="neutral",
                            claim=response[:500],
                            reasoning=response,
                            strength=self._estimate_strength(response),
                            rebuttal_to=last_arg.argument_id,
                        )
                        round_data.arguments.append(arg)
                    except Exception as e:
                        logger.warning("Socratic questioner failed: %s", e)

        return round_data

    def _phase_for_round(self, round_num: int, total_rounds: int) -> DebatePhase:
        if round_num == 1:
            return DebatePhase.OPENING
        elif round_num == total_rounds:
            return DebatePhase.CLOSING
        elif round_num == total_rounds - 1:
            return DebatePhase.REBUTTALS
        else:
            return DebatePhase.ARGUMENTS

    def _build_debate_prompt(
        self,
        topic: str,
        position: str,
        round_num: int,
        phase: DebatePhase,
        context: str,
        previous_rounds: list[DebateRound],
    ) -> str:
        parts = [
            f"Debate topic: {topic}",
            f"Your position: {position.upper()}",
            f"Round {round_num}, Phase: {phase.value}",
        ]
        if context:
            parts.append(f"Context: {context}")
        if previous_rounds:
            prev_args = [a for r in previous_rounds for a in r.arguments]
            if prev_args:
                parts.append("Previous arguments:")
                for a in prev_args[-4:]:
                    parts.append(f"  [{a.agent_id}] ({a.position}): {a.claim[:200]}")
        parts.append(f"Present your {phase.value} argument:")
        return "\n".join(parts)

    def _build_panel_prompt(
        self,
        topic: str,
        round_num: int,
        phase: DebatePhase,
        context: str,
    ) -> str:
        parts = [
            f"Panel discussion topic: {topic}",
            f"Round {round_num}, Phase: {phase.value}",
        ]
        if context:
            parts.append(f"Context: {context}")
        parts.append("Present your independent perspective:")
        return "\n".join(parts)

    def _estimate_strength(self, response: str) -> float:
        """Estimate argument strength from response characteristics."""
        score = 0.5
        # Longer responses with structure tend to be stronger
        if len(response) > 200:
            score += 0.1
        if len(response) > 500:
            score += 0.1
        # Evidence indicators
        evidence_words = ["because", "therefore", "evidence", "data", "study", "example", "research"]
        score += sum(0.05 for w in evidence_words if w.lower() in response.lower())
        # Reasoning indicators
        reasoning_words = ["however", "although", "consequently", "implies", "suggests"]
        score += sum(0.03 for w in reasoning_words if w.lower() in response.lower())
        return min(score, 1.0)

    def _default_synthesis(self, arguments: list[DebateArgument]) -> str:
        """Default synthesis when no judge agent is available."""
        if not arguments:
            return "No arguments were presented."

        by_position: dict[str, list[DebateArgument]] = {}
        for a in arguments:
            by_position.setdefault(a.position, []).append(a)

        parts = ["Debate Synthesis:"]
        for pos, args in by_position.items():
            avg_strength = sum(a.strength for a in args) / len(args) if args else 0
            parts.append(f"\n{pos.upper()} ({len(args)} arguments, avg strength: {avg_strength:.2f}):")
            for a in args[:3]:
                parts.append(f"  - {a.claim[:150]}")

        return "\n".join(parts)

    def _compute_confidence(self, arguments: list[DebateArgument]) -> float:
        """Compute overall debate confidence."""
        if not arguments:
            return 0.0
        # More arguments with higher strength = higher confidence
        avg_strength = sum(a.strength for a in arguments) / len(arguments)
        # Diversity of positions increases confidence
        positions = set(a.position for a in arguments)
        diversity_bonus = len(positions) * 0.1
        return min(avg_strength + diversity_bonus, 1.0)

    def _extract_insights(self, arguments: list[DebateArgument]) -> list[str]:
        """Extract key insights from debate arguments."""
        insights = []
        # Find strongest argument per position
        by_position: dict[str, list[DebateArgument]] = {}
        for a in arguments:
            by_position.setdefault(a.position, []).append(a)
        for pos, args in by_position.items():
            if args:
                strongest = max(args, key=lambda a: a.strength)
                insights.append(f"[{pos}] {strongest.claim[:200]}")
        return insights[:5]

    def _determine_winner(self, arguments: list[DebateArgument]) -> str | None:
        """Determine debate winner based on argument strength."""
        if not arguments:
            return None
        by_agent: dict[str, list[DebateArgument]] = {}
        for a in arguments:
            by_agent.setdefault(a.agent_id, []).append(a)
        if not by_agent:
            return None
        # Agent with highest average strength wins
        winner = max(
            by_agent.items(),
            key=lambda item: sum(a.strength for a in item[1]) / len(item[1]),
        )
        return winner[0]

    def get_debate(self, debate_id: str) -> DebateResult | None:
        return self._debates.get(debate_id)

    def list_debates(self) -> list[str]:
        return list(self._debates.keys())
