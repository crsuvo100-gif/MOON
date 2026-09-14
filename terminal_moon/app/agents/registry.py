"""
Structured agent registry — capability-based selection.
"""
from __future__ import annotations

from app.brain.agent_registry import AgentCard, build_agents


class AgentRegistry:
    """Structured registry: built-in + factory + spec40 agents."""

    def __init__(self, tool_names: list[str]) -> None:
        self._cards: dict[str, AgentCard] = build_agents(tool_names)

    def get(self, name: str) -> AgentCard | None:
        return self._cards.get(name)

    def all(self) -> list[AgentCard]:
        return list(self._cards.values())

    def select(self, capability: Optional[str] = None) -> AgentCard | None:
        if capability:
            for card in self._cards.values():
                if capability in card.capabilities or capability in card.name:
                    return card
        # default: coordinator
        return self._cards.get("coordinator")

    def to_dict(self) -> list[dict]:
        return [c.to_dict() for c in self._cards.values()]

    def __len__(self) -> int:
        return len(self._cards)
