"""negotiation.py — multi-agent negotiation and consensus building.

Professional AI agents negotiate to resolve conflicts, allocate resources,
and reach consensus among stakeholders with different objectives. This
module provides negotiation protocols including bargaining, auction-based
allocation, and consensus-building mechanisms.

Negotiation protocols:
- BARGAINING: iterative offer/counteroffer with concession strategy
- AUCTION: competitive bidding for resource allocation
- CONSENSUS: collaborative agreement seeking
- VOTING: preference aggregation with various voting rules
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


class NegotiationProtocol(str, Enum):
    BARGAINING = "bargaining"
    AUCTION = "auction"
    CONSENSUS = "consensus"
    VOTING = "voting"


class NegotiationPhase(str, Enum):
    PREPARATION = "preparation"
    OFFERING = "offering"
    BARGAINING = "bargaining"
    AGREEMENT = "agreement"
    IMPLEMENTATION = "implementation"


class VotingRule(str, Enum):
    MAJORITY = "majority"
    UNANIMOUS = "unanimous"
    BORDA = "borda"
    APPROVAL = "approval"


@dataclass
class NegotiationOffer:
    offer_id: str
    agent_id: str
    round_number: int
    proposal: dict[str, Any]
    utility: float  # utility to the offering agent
    target_agent: str | None = None  # None = broadcast
    timestamp: float = field(default_factory=time.time)
    response_to: str | None = None  # offer_id this responds to


@dataclass
class NegotiationRound:
    round_number: int
    phase: NegotiationPhase
    offers: list[NegotiationOffer] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class NegotiationResult:
    negotiation_id: str
    topic: str
    protocol: NegotiationProtocol
    rounds: list[NegotiationRound] = field(default_factory=list)
    agreement: dict[str, Any] | None = None
    winner: str | None = None
    utility_scores: dict[str, float] = field(default_factory=dict)
    consensus_level: float = 0.0  # 0-1
    timestamp: float = field(default_factory=time.time)


class AgentNegotiation:
    """Multi-agent negotiation system for conflict resolution and consensus."""

    def __init__(
        self,
        agents: dict[str, Callable[..., Awaitable[Any]]],
        utility_fns: dict[str, Callable[[dict[str, Any]], float]] | None = None,
    ) -> None:
        self._agents = agents
        self._utility_fns = utility_fns or {}
        self._negotiations: dict[str, NegotiationResult] = {}

    async def negotiate(
        self,
        topic: str,
        protocol: NegotiationProtocol = NegotiationProtocol.BARGAINING,
        rounds: int = 5,
        context: str = "",
        initial_proposals: dict[str, dict[str, Any]] | None = None,
    ) -> NegotiationResult:
        """Run a negotiation session."""
        neg_id = str(uuid.uuid4())[:8]
        result = NegotiationResult(
            negotiation_id=neg_id,
            topic=topic,
            protocol=protocol,
        )

        agent_ids = list(self._agents.keys())

        if protocol == NegotiationProtocol.BARGAINING:
            result.rounds = await self._run_bargaining(
                topic, rounds, agent_ids, context, initial_proposals
            )
        elif protocol == NegotiationProtocol.AUCTION:
            result.rounds = await self._run_auction(
                topic, rounds, agent_ids, context, initial_proposals
            )
        elif protocol == NegotiationProtocol.CONSENSUS:
            result.rounds = await self._run_consensus(
                topic, rounds, agent_ids, context, initial_proposals
            )
        elif protocol == NegotiationProtocol.VOTING:
            result.rounds = await self._run_voting(
                topic, rounds, agent_ids, context, initial_proposals
            )

        # Determine outcome
        all_offers = [o for r in result.rounds for o in r.offers]
        if all_offers:
            result.agreement = self._extract_agreement(all_offers)
            result.utility_scores = self._compute_utility_scores(all_offers)
            result.consensus_level = self._compute_consensus_level(all_offers)
            result.winner = self._determine_winner(all_offers)

        self._negotiations[neg_id] = result
        return result

    async def _run_bargaining(
        self,
        topic: str,
        rounds: int,
        agent_ids: list[str],
        context: str,
        initial_proposals: dict[str, dict[str, Any]] | None,
    ) -> list[NegotiationRound]:
        """Run bargaining protocol."""
        negotiation_rounds: list[NegotiationRound] = []
        current_proposals: dict[str, dict[str, Any]] = initial_proposals or {}
        last_offers: dict[str, NegotiationOffer] = {}

        for round_num in range(1, rounds + 1):
            phase = (
                NegotiationPhase.OFFERING if round_num == 1
                else NegotiationPhase.BARGAINING if round_num < rounds
                else NegotiationPhase.AGREEMENT
            )
            nr = NegotiationRound(round_number=round_num, phase=phase)

            for agent_id in agent_ids:
                # Build prompt with context of previous offers
                prompt = self._build_bargaining_prompt(
                    topic=topic,
                    agent_id=agent_id,
                    round_num=round_num,
                    total_rounds=rounds,
                    context=context,
                    current_proposals=current_proposals,
                    last_offers=last_offers,
                )
                try:
                    response = await self._agents[agent_id](prompt, topic)
                    proposal = self._parse_proposal(response)
                    utility = self._compute_utility(agent_id, proposal)
                    offer = NegotiationOffer(
                        offer_id=str(uuid.uuid4())[:8],
                        agent_id=agent_id,
                        round_number=round_num,
                        proposal=proposal,
                        utility=utility,
                    )
                    nr.offers.append(offer)
                    current_proposals[agent_id] = proposal
                    last_offers[agent_id] = offer
                except Exception as e:
                    logger.warning("Bargaining agent %s failed: %s", agent_id, e)

            negotiation_rounds.append(nr)

        return negotiation_rounds

    async def _run_auction(
        self,
        topic: str,
        rounds: int,
        agent_ids: list[str],
        context: str,
        initial_proposals: dict[str, dict[str, Any]] | None,
    ) -> list[NegotiationRound]:
        """Run auction protocol."""
        negotiation_rounds: list[NegotiationRound] = []
        best_bid: dict[str, Any] | None = None
        best_agent: str | None = None

        for round_num in range(1, rounds + 1):
            nr = NegotiationRound(round_number=round_num, phase=NegotiationPhase.BARGAINING)

            for agent_id in agent_ids:
                prompt = (
                    f"Auction round {round_num} for: {topic}\n"
                    f"Context: {context}\n"
                    f"Current best bid: {best_bid}\n"
                    f"Submit your bid (JSON with 'value' and 'bid_amount' fields):"
                )
                try:
                    response = await self._agents[agent_id](prompt, topic)
                    bid = self._parse_bid(response)
                    if bid and (best_bid is None or bid.get("bid_amount", 0) > best_bid.get("bid_amount", 0)):
                        best_bid = bid
                        best_agent = agent_id
                    offer = NegotiationOffer(
                        offer_id=str(uuid.uuid4())[:8],
                        agent_id=agent_id,
                        round_number=round_num,
                        proposal=bid or {},
                        utility=bid.get("value", 0) if bid else 0,
                    )
                    nr.offers.append(offer)
                except Exception as e:
                    logger.warning("Auction agent %s failed: %s", agent_id, e)

            negotiation_rounds.append(nr)

        return negotiation_rounds

    async def _run_consensus(
        self,
        topic: str,
        rounds: int,
        agent_ids: list[str],
        context: str,
        initial_proposals: dict[str, dict[str, Any]] | None,
    ) -> list[NegotiationRound]:
        """Run consensus-building protocol."""
        negotiation_rounds: list[NegotiationRound] = []
        proposals: dict[str, dict[str, Any]] = initial_proposals or {}

        for round_num in range(1, rounds + 1):
            nr = NegotiationRound(round_number=round_num, phase=NegotiationPhase.BARGAINING)

            for agent_id in agent_ids:
                prompt = (
                    f"Consensus-building round {round_num} for: {topic}\n"
                    f"Context: {context}\n"
                    f"Other proposals: {proposals}\n"
                    f"Propose a compromise that works for everyone:"
                )
                try:
                    response = await self._agents[agent_id](prompt, topic)
                    proposal = self._parse_proposal(response)
                    utility = self._compute_utility(agent_id, proposal)
                    offer = NegotiationOffer(
                        offer_id=str(uuid.uuid4())[:8],
                        agent_id=agent_id,
                        round_number=round_num,
                        proposal=proposal,
                        utility=utility,
                    )
                    nr.offers.append(offer)
                    proposals[agent_id] = proposal
                except Exception as e:
                    logger.warning("Consensus agent %s failed: %s", agent_id, e)

            negotiation_rounds.append(nr)

        return negotiation_rounds

    async def _run_voting(
        self,
        topic: str,
        rounds: int,
        agent_ids: list[str],
        context: str,
        initial_proposals: dict[str, dict[str, Any]] | None,
    ) -> list[NegotiationRound]:
        """Run voting protocol."""
        negotiation_rounds: list[NegotiationRound] = []
        # Collect proposals first
        proposals: dict[str, dict[str, Any]] = initial_proposals or {}

        # Round 1: collect proposals
        nr1 = NegotiationRound(round_number=1, phase=NegotiationPhase.OFFERING)
        for agent_id in agent_ids:
            prompt = f"Submit your proposal for: {topic}\nContext: {context}"
            try:
                response = await self._agents[agent_id](prompt, topic)
                proposal = self._parse_proposal(response)
                proposals[agent_id] = proposal
                offer = NegotiationOffer(
                    offer_id=str(uuid.uuid4())[:8],
                    agent_id=agent_id,
                    round_number=1,
                    proposal=proposal,
                    utility=1.0,
                )
                nr1.offers.append(offer)
            except Exception as e:
                logger.warning("Voting proposal agent %s failed: %s", agent_id, e)
        negotiation_rounds.append(nr1)

        # Round 2: vote on proposals
        nr2 = NegotiationRound(round_number=2, phase=NegotiationPhase.BARGAINING)
        votes: dict[str, list[str]] = {}  # proposal_agent -> voter_agents
        for voter_id in agent_ids:
            prompt = (
                f"Vote for the best proposal for: {topic}\n"
                f"Proposals: {list(proposals.keys())}\n"
                f"Context: {context}\n"
                f"Respond with the agent_id of your preferred proposal:"
            )
            try:
                response = await self._agents[voter_id](prompt, topic)
                choice = response.strip().split("\n")[0].strip()
                if choice in proposals:
                    votes.setdefault(choice, []).append(voter_id)
            except Exception as e:
                logger.warning("Voting agent %s failed: %s", voter_id, e)
        negotiation_rounds.append(nr2)

        return negotiation_rounds

    def _build_bargaining_prompt(
        self,
        topic: str,
        agent_id: str,
        round_num: int,
        total_rounds: int,
        context: str,
        current_proposals: dict[str, dict[str, Any]],
        last_offers: dict[str, NegotiationOffer],
    ) -> str:
        parts = [
            f"Negotiation topic: {topic}",
            f"You are agent: {agent_id}",
            f"Round {round_num}/{total_rounds}",
        ]
        if context:
            parts.append(f"Context: {context}")
        if current_proposals:
            parts.append(f"Current proposals: {current_proposals}")
        if last_offers:
            parts.append(f"Last offers: {[(o.agent_id, o.proposal) for o in last_offers.values()]}")
        parts.append("Submit your offer (JSON format):")
        return "\n".join(parts)

    def _parse_proposal(self, response: str) -> dict[str, Any]:
        """Parse a proposal from agent response."""
        import json
        # Try to find JSON in response
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        # Fallback: treat entire response as text proposal
        return {"text": response[:500]}

    def _parse_bid(self, response: str) -> dict[str, Any] | None:
        """Parse a bid from agent response."""
        import json
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def _compute_utility(self, agent_id: str, proposal: dict[str, Any]) -> float:
        """Compute utility of a proposal for an agent."""
        if agent_id in self._utility_fns:
            try:
                return self._utility_fns[agent_id](proposal)
            except Exception:
                pass
        # Default: use 'value' or 'utility' field if present
        return float(proposal.get("value", proposal.get("utility", 0.5)))

    def _extract_agreement(self, offers: list[NegotiationOffer]) -> dict[str, Any]:
        """Extract agreement from offers."""
        if not offers:
            return {}
        # Use the last offer as the agreement basis
        last = offers[-1]
        return last.proposal

    def _compute_utility_scores(self, offers: list[NegotiationOffer]) -> dict[str, float]:
        """Compute utility scores per agent."""
        scores: dict[str, float] = {}
        for o in offers:
            if o.agent_id not in scores or o.utility > scores[o.agent_id]:
                scores[o.agent_id] = o.utility
        return scores

    def _compute_consensus_level(self, offers: list[NegotiationOffer]) -> float:
        """Compute consensus level (0-1) from offers."""
        if not offers:
            return 0.0
        # Higher when utilities are similar across agents
        utilities = [o.utility for o in offers]
        if len(utilities) < 2:
            return 1.0
        avg = sum(utilities) / len(utilities)
        variance = sum((u - avg) ** 2 for u in utilities) / len(utilities)
        # Lower variance = higher consensus
        return max(0.0, 1.0 - variance)

    def _determine_winner(self, offers: list[NegotiationOffer]) -> str | None:
        """Determine negotiation winner."""
        if not offers:
            return None
        # Agent with highest utility in their last offer
        by_agent: dict[str, NegotiationOffer] = {}
        for o in offers:
            by_agent[o.agent_id] = o
        if not by_agent:
            return None
        winner = max(by_agent.items(), key=lambda item: item[1].utility)
        return winner[0]

    def get_negotiation(self, neg_id: str) -> NegotiationResult | None:
        return self._negotiations.get(neg_id)

    def list_negotiations(self) -> list[str]:
        return list(self._negotiations.keys())
