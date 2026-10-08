"""creative_thinking.py — creative ideation and divergent thinking.

Professional AI agents generate novel ideas, explore unconventional solutions,
and think outside established patterns. This module provides creative
thinking frameworks including brainstorming, lateral thinking, analogical
reasoning, and SCAMPER-based innovation.

Creative thinking methods:
- BRAINSTORMING: free-form idea generation with quantity focus
- LATERAL: random stimulus and forced connections
- ANALOGICAL: cross-domain pattern transfer
- SCAMPER: systematic innovation (Substitute, Combine, Adapt, Modify, Put to other use, Eliminate, Reverse)
- MORPHOLOGICAL: structured combination of dimensions
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

from app.config.logging import get_logger

logger = get_logger(__name__)


class CreativeMethod(str, Enum):
    BRAINSTORMING = "brainstorming"
    LATERAL = "lateral"
    ANALOGICAL = "analogical"
    SCAMPER = "scamper"
    MORPHOLOGICAL = "morphological"


class IdeaCategory(str, Enum):
    NOVEL = "novel"  # completely new
    ADAPTIVE = "adaptive"  # adapted from existing
    COMBINATIVE = "combinative"  # combination of existing
    TRANSFORMATIVE = "transformative"  # significant modification
    INCREMENTAL = "incremental"  # small improvement


@dataclass
class CreativeIdea:
    idea_id: str
    title: str
    description: str
    method: CreativeMethod
    category: IdeaCategory
    novelty_score: float = 0.0  # 0-1
    feasibility_score: float = 0.0  # 0-1
    impact_score: float = 0.0  # 0-1
    tags: list[str] = field(default_factory=list)
    parent_ideas: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def overall_score(self) -> float:
        return (self.novelty_score + self.feasibility_score + self.impact_score) / 3


@dataclass
class CreativeSession:
    session_id: str
    topic: str
    method: CreativeMethod
    ideas: list[CreativeIdea] = field(default_factory=list)
    context: str = ""
    constraints: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SCAMPERResult:
    result_id: str
    original: str
    substitute: str = ""
    combine: str = ""
    adapt: str = ""
    modify: str = ""
    put_to_other_use: str = ""
    eliminate: str = ""
    reverse: str = ""
    timestamp: float = field(default_factory=time.time)


class CreativeThinker:
    """Creative ideation and divergent thinking engine."""

    def __init__(
        self,
        llm_agent: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        self._llm = llm_agent
        self._sessions: dict[str, CreativeSession] = {}
        self._ideas: dict[str, CreativeIdea] = {}

    async def brainstorm(
        self,
        topic: str,
        context: str = "",
        constraints: list[str] | None = None,
        num_ideas: int = 10,
    ) -> CreativeSession:
        """Run a brainstorming session."""
        session = CreativeSession(
            session_id=str(uuid.uuid4())[:8],
            topic=topic,
            method=CreativeMethod.BRAINSTORMING,
            context=context,
            constraints=constraints or [],
        )

        if self._llm:
            prompt = self._build_brainstorming_prompt(topic, context, constraints, num_ideas)
            try:
                response = await self._llm(prompt, "brainstorming")
                ideas = self._parse_ideas(response, CreativeMethod.BRAINSTORMING)
                session.ideas = ideas[:num_ideas]
            except Exception as e:
                logger.warning("LLM brainstorming failed: %s", e)
                session.ideas = self._generate_fallback_ideas(topic, num_ideas)
        else:
            session.ideas = self._generate_fallback_ideas(topic, num_ideas)

        self._sessions[session.session_id] = session
        for idea in session.ideas:
            self._ideas[idea.idea_id] = idea
        return session

    async def lateral_thinking(
        self,
        topic: str,
        random_stimulus: str | None = None,
        context: str = "",
    ) -> CreativeSession:
        """Run lateral thinking with random stimulus."""
        session = CreativeSession(
            session_id=str(uuid.uuid4())[:8],
            topic=topic,
            method=CreativeMethod.LATERAL,
            context=context,
        )

        stimulus = random_stimulus or self._generate_random_stimulus()

        if self._llm:
            prompt = (
                f"Lateral thinking exercise for: {topic}\n"
                f"Random stimulus: {stimulus}\n"
                f"Context: {context}\n"
                f"Force connections between the stimulus and the topic. Generate creative ideas:"
            )
            try:
                response = await self._llm(prompt, "lateral_thinking")
                ideas = self._parse_ideas(response, CreativeMethod.LATERAL)
                session.ideas = ideas
            except Exception as e:
                logger.warning("LLM lateral thinking failed: %s", e)
                session.ideas = self._generate_fallback_ideas(topic, 5)
        else:
            session.ideas = self._generate_fallback_ideas(topic, 5)

        self._sessions[session.session_id] = session
        for idea in session.ideas:
            self._ideas[idea.idea_id] = idea
        return session

    async def analogical_reasoning(
        self,
        topic: str,
        source_domain: str,
        context: str = "",
    ) -> CreativeSession:
        """Apply analogical reasoning from a source domain."""
        session = CreativeSession(
            session_id=str(uuid.uuid4())[:8],
            topic=topic,
            method=CreativeMethod.ANALOGICAL,
            context=context,
        )

        if self._llm:
            prompt = (
                f"Analogical reasoning:\n"
                f"Target problem: {topic}\n"
                f"Source domain: {source_domain}\n"
                f"Context: {context}\n"
                f"Find structural similarities between {source_domain} and {topic}. "
                f"Transfer solutions from {source_domain} to {topic}:"
            )
            try:
                response = await self._llm(prompt, "analogical_reasoning")
                ideas = self._parse_ideas(response, CreativeMethod.ANALOGICAL)
                session.ideas = ideas
            except Exception as e:
                logger.warning("LLM analogical reasoning failed: %s", e)
                session.ideas = self._generate_fallback_ideas(topic, 5)
        else:
            session.ideas = self._generate_fallback_ideas(topic, 5)

        self._sessions[session.session_id] = session
        for idea in session.ideas:
            self._ideas[idea.idea_id] = idea
        return session

    async def scamper(
        self,
        topic: str,
        context: str = "",
    ) -> SCAMPERResult:
        """Apply SCAMPER innovation framework."""
        result = SCAMPERResult(
            result_id=str(uuid.uuid4())[:8],
            original=topic,
        )

        if self._llm:
            prompt = (
                f"Apply SCAMPER to: {topic}\n"
                f"Context: {context}\n"
                f"For each SCAMPER dimension, provide one creative idea:\n"
                f"S - Substitute: What can be replaced?\n"
                f"C - Combine: What can be merged?\n"
                f"A - Adapt: What can be adjusted?\n"
                f"M - Modify: What can be magnified or minimized?\n"
                f"P - Put to other use: What else can this be used for?\n"
                f"E - Eliminate: What can be removed?\n"
                f"R - Reverse: What can be flipped or reordered?\n"
                f"Respond in JSON format with keys: substitute, combine, adapt, modify, put_to_other_use, eliminate, reverse"
            )
            try:
                response = await self._llm(prompt, "scamper")
                import json
                # Try to parse JSON from response
                for line in response.split("\n"):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            result.substitute = data.get("substitute", "")
                            result.combine = data.get("combine", "")
                            result.adapt = data.get("adapt", "")
                            result.modify = data.get("modify", "")
                            result.put_to_other_use = data.get("put_to_other_use", "")
                            result.eliminate = data.get("eliminate", "")
                            result.reverse = data.get("reverse", "")
                            break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning("LLM SCAMPER failed: %s", e)

        return result

    async def morphological_analysis(
        self,
        topic: str,
        dimensions: dict[str, list[str]],
        context: str = "",
        max_combinations: int = 20,
    ) -> CreativeSession:
        """Run morphological analysis (structured combination)."""
        session = CreativeSession(
            session_id=str(uuid.uuid4())[:8],
            topic=topic,
            method=CreativeMethod.MORPHOLOGICAL,
            context=context,
        )

        # Generate combinations
        import itertools
        dim_names = list(dimensions.keys())
        dim_values = [dimensions[d] for d in dim_names]

        combinations = list(itertools.product(*dim_values))
        random.shuffle(combinations)
        selected = combinations[:max_combinations]

        ideas = []
        for i, combo in enumerate(selected):
            combo_dict = dict(zip(dim_names, combo))
            idea = CreativeIdea(
                idea_id=str(uuid.uuid4())[:8],
                title=f"Morphological combination {i+1}",
                description=f"Combination: {combo_dict}",
                method=CreativeMethod.MORPHOLOGICAL,
                category=IdeaCategory.COMBINATIVE,
                novelty_score=random.uniform(0.3, 0.8),
                feasibility_score=random.uniform(0.4, 0.9),
                impact_score=random.uniform(0.3, 0.8),
                tags=dim_names,
                metadata={"combination": combo_dict},
            )
            ideas.append(idea)

        session.ideas = ideas
        self._sessions[session.session_id] = session
        for idea in session.ideas:
            self._ideas[idea.idea_id] = idea
        return session

    def evaluate_idea(self, idea: CreativeIdea) -> dict[str, float]:
        """Evaluate an idea across multiple dimensions."""
        return {
            "novelty": idea.novelty_score,
            "feasibility": idea.feasibility_score,
            "impact": idea.impact_score,
            "overall": idea.overall_score,
        }

    def rank_ideas(self, session_id: str) -> list[CreativeIdea]:
        """Rank ideas in a session by overall score."""
        session = self._sessions.get(session_id)
        if not session:
            return []
        return sorted(session.ideas, key=lambda i: i.overall_score, reverse=True)

    def get_session(self, session_id: str) -> CreativeSession | None:
        return self._sessions.get(session_id)

    def get_idea(self, idea_id: str) -> CreativeIdea | None:
        return self._ideas.get(idea_id)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    def _build_brainstorming_prompt(
        self,
        topic: str,
        context: str,
        constraints: list[str] | None,
        num_ideas: int,
    ) -> str:
        parts = [
            f"Brainstorming session for: {topic}",
            f"Generate {num_ideas} creative ideas.",
        ]
        if context:
            parts.append(f"Context: {context}")
        if constraints:
            parts.append(f"Constraints: {constraints}")
        parts.append("For each idea, provide: title, description, novelty (0-1), feasibility (0-1), impact (0-1)")
        return "\n".join(parts)

    def _parse_ideas(self, response: str, method: CreativeMethod) -> list[CreativeIdea]:
        """Parse ideas from LLM response."""
        ideas = []
        import json
        # Try to find JSON array in response
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("["):
                try:
                    data = json.loads(line)
                    for item in data:
                        idea = CreativeIdea(
                            idea_id=str(uuid.uuid4())[:8],
                            title=item.get("title", "Untitled"),
                            description=item.get("description", ""),
                            method=method,
                            category=IdeaCategory.NOVEL,
                            novelty_score=float(item.get("novelty", 0.5)),
                            feasibility_score=float(item.get("feasibility", 0.5)),
                            impact_score=float(item.get("impact", 0.5)),
                        )
                        ideas.append(idea)
                    break
                except json.JSONDecodeError:
                    continue
        # Fallback: create one idea from response
        if not ideas:
            ideas.append(CreativeIdea(
                idea_id=str(uuid.uuid4())[:8],
                title="Generated Idea",
                description=response[:500],
                method=method,
                category=IdeaCategory.NOVEL,
            ))
        return ideas

    def _generate_random_stimulus(self) -> str:
        """Generate a random stimulus for lateral thinking."""
        stimuli = [
            "a tree", "a river", "a clock", "a mirror", "a bridge",
            "a seed", "a storm", "a puzzle", "a recipe", "a map",
            "a musical instrument", "a camera", "a book", "a game", "a dream",
        ]
        return random.choice(stimuli)

    def _generate_fallback_ideas(self, topic: str, count: int) -> list[CreativeIdea]:
        """Generate fallback ideas when LLM is unavailable."""
        ideas = []
        templates = [
            f"Reimagine {topic} from first principles",
            f"Apply {topic} in a completely different context",
            f"Combine {topic} with an unrelated field",
            f"Invert the assumptions of {topic}",
            f"Scale {topic} to an extreme (very large or very small)",
            f"Remove the core constraint of {topic}",
            f"Find the opposite of {topic} and explore it",
            f"Use {topic} as a metaphor for something else",
        ]
        for i in range(min(count, len(templates))):
            ideas.append(CreativeIdea(
                idea_id=str(uuid.uuid4())[:8],
                title=templates[i],
                description=f"Creative exploration: {templates[i]}",
                method=CreativeMethod.BRAINSTORMING,
                category=IdeaCategory.NOVEL,
                novelty_score=random.uniform(0.4, 0.8),
                feasibility_score=random.uniform(0.3, 0.7),
                impact_score=random.uniform(0.3, 0.7),
            ))
        return ideas
