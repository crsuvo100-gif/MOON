"""evolution.py — agent self-evolution and strategy optimization.

Professional AI agents evolve over time by analyzing their performance,
identifying successful patterns, and adapting their strategies. This module
provides an evolution engine that tracks agent behavior, mutates strategies,
and selects the best-performing variants.

Evolution mechanisms:
- Mutation: modify strategy parameters
- Crossover: combine successful strategies
- Selection: keep best-performing variants
- Fitness scoring: evaluate strategy effectiveness
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from app.config.logging import get_logger

logger = get_logger(__name__)


class EvolutionStrategy(str, Enum):
    MUTATION = "mutation"
    CROSSOVER = "crossover"
    SELECTION = "selection"


class FitnessMetric(str, Enum):
    SUCCESS_RATE = "success_rate"
    LATENCY = "latency"
    TOKEN_EFFICIENCY = "token_efficiency"
    USER_SATISFACTION = "user_satisfaction"
    COMPOSITE = "composite"


@dataclass
class StrategyVariant:
    variant_id: str
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    generation: int = 0
    fitness: float = 0.0
    fitness_history: list[float] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def clone(self, new_id: str | None = None) -> StrategyVariant:
        return StrategyVariant(
            variant_id=new_id or str(uuid.uuid4())[:8],
            name=self.name,
            parameters=copy.deepcopy(self.parameters),
            generation=self.generation,
            fitness=0.0,
            fitness_history=[],
            parent_ids=[self.variant_id],
            metadata=copy.deepcopy(self.metadata),
        )


@dataclass
class EvolutionRecord:
    record_id: str
    generation: int
    strategy: EvolutionStrategy
    parent_variants: list[str]
    child_variant: str
    fitness_before: float
    fitness_after: float
    timestamp: float = field(default_factory=time.time)
    notes: str = ""


@dataclass
class EvolutionConfig:
    population_size: int = 10
    mutation_rate: float = 0.1
    crossover_rate: float = 0.3
    elitism_ratio: float = 0.2
    max_generations: int = 50
    fitness_threshold: float = 0.95
    tournament_size: int = 3


class EvolutionEngine:
    """Self-evolution engine for agent strategy optimization."""

    def __init__(
        self,
        config: EvolutionConfig | None = None,
        fitness_fn: Callable[[StrategyVariant], float] | None = None,
        storage_path: str | None = None,
    ) -> None:
        self._config = config or EvolutionConfig()
        self._fitness_fn = fitness_fn
        self._population: list[StrategyVariant] = []
        self._generation = 0
        self._history: list[EvolutionRecord] = []
        self._storage_path = Path(storage_path) if storage_path else None
        self._best_variant: StrategyVariant | None = None

    def initialize_population(
        self,
        base_parameters: dict[str, Any],
        name: str = "strategy",
    ) -> None:
        """Initialize population with random variations of base parameters."""
        self._population = []
        for i in range(self._config.population_size):
            params = copy.deepcopy(base_parameters)
            # Random mutation of numeric parameters
            for key, value in params.items():
                if isinstance(value, (int, float)):
                    noise = random.gauss(0, abs(value) * 0.1 if value != 0 else 0.1)
                    params[key] = type(value)(value + noise)
                elif isinstance(value, bool):
                    if random.random() < 0.1:
                        params[key] = not value
            variant = StrategyVariant(
                variant_id=str(uuid.uuid4())[:8],
                name=f"{name}_v{i}",
                parameters=params,
                generation=0,
            )
            self._population.append(variant)
        self._generation = 0
        logger.info("Initialized population of %d variants", len(self._population))

    async def evolve(self, generations: int | None = None) -> StrategyVariant | None:
        """Run evolution for specified generations."""
        target = generations or self._config.max_generations
        for _ in range(target):
            if self._best_variant and self._best_variant.fitness >= self._config.fitness_threshold:
                logger.info("Fitness threshold reached at generation %d", self._generation)
                break
            await self._evolve_generation()
        return self._best_variant or (self._population[0] if self._population else None)

    async def _evolve_generation(self) -> None:
        """Evolve one generation."""
        self._generation += 1

        # Evaluate fitness
        await self._evaluate_population()

        # Sort by fitness (descending)
        self._population.sort(key=lambda v: v.fitness, reverse=True)

        # Track best
        if not self._best_variant or self._population[0].fitness > self._best_variant.fitness:
            self._best_variant = self._population[0].clone()
            self._best_variant.fitness = self._population[0].fitness

        # Elitism: keep top performers
        elite_count = max(1, int(self._config.population_size * self._config.elitism_ratio))
        new_population = [v.clone() for v in self._population[:elite_count]]

        # Generate offspring
        while len(new_population) < self._config.population_size:
            strategy = self._select_evolution_strategy()
            if strategy == EvolutionStrategy.MUTATION:
                child = self._mutate()
            elif strategy == EvolutionStrategy.CROSSOVER:
                child = self._crossover()
            else:
                child = self._tournament_select().clone()

            child.generation = self._generation
            new_population.append(child)

        self._population = new_population
        logger.debug("Generation %d complete, best fitness: %.4f",
                     self._generation, self._population[0].fitness if self._population else 0)

    async def _evaluate_population(self) -> None:
        """Evaluate fitness for all variants."""
        for variant in self._population:
            if self._fitness_fn:
                try:
                    variant.fitness = self._fitness_fn(variant)
                except Exception as e:
                    logger.warning("Fitness evaluation failed for %s: %s", variant.variant_id, e)
                    variant.fitness = 0.0
            else:
                variant.fitness = self._default_fitness(variant)
            variant.fitness_history.append(variant.fitness)

    def _default_fitness(self, variant: StrategyVariant) -> float:
        """Default fitness function based on parameter diversity."""
        # Prefer variants with moderate parameter values
        score = 0.5
        for value in variant.parameters.values():
            if isinstance(value, (int, float)):
                # Prefer values close to 1.0 (normalized)
                score += 0.1 * (1.0 - min(abs(value - 1.0), 1.0))
            elif isinstance(value, bool):
                score += 0.05
        return min(score / max(len(variant.parameters), 1), 1.0)

    def _select_evolution_strategy(self) -> EvolutionStrategy:
        """Select evolution strategy based on configured rates."""
        r = random.random()
        if r < self._config.mutation_rate:
            return EvolutionStrategy.MUTATION
        elif r < self._config.mutation_rate + self._config.crossover_rate:
            return EvolutionStrategy.CROSSOVER
        else:
            return EvolutionStrategy.SELECTION

    def _mutate(self) -> StrategyVariant:
        """Create a mutated variant."""
        parent = self._tournament_select()
        child = parent.clone()
        # Mutate parameters
        for key, value in child.parameters.items():
            if isinstance(value, (int, float)):
                noise = random.gauss(0, abs(value) * 0.2 if value != 0 else 0.2)
                child.parameters[key] = type(value)(value + noise)
            elif isinstance(value, bool):
                if random.random() < 0.2:
                    child.parameters[key] = not value
        child.parent_ids = [parent.variant_id]
        child.metadata["evolution_strategy"] = "mutation"
        return child

    def _crossover(self) -> StrategyVariant:
        """Create a variant by crossing over two parents."""
        if len(self._population) < 2:
            return self._mutate()
        parent1 = self._tournament_select()
        parent2 = self._tournament_select()
        while parent2.variant_id == parent1.variant_id:
            parent2 = self._tournament_select()

        child = parent1.clone()
        # Crossover parameters
        for key in child.parameters:
            if key in parent2.parameters and random.random() < 0.5:
                child.parameters[key] = copy.deepcopy(parent2.parameters[key])
        child.parent_ids = [parent1.variant_id, parent2.variant_id]
        child.metadata["evolution_strategy"] = "crossover"
        return child

    def _tournament_select(self) -> StrategyVariant:
        """Select a variant using tournament selection."""
        tournament = random.sample(
            self._population,
            min(self._config.tournament_size, len(self._population)),
        )
        return max(tournament, key=lambda v: v.fitness)

    def get_best(self) -> StrategyVariant | None:
        """Get the best-performing variant."""
        return self._best_variant

    def get_population(self) -> list[StrategyVariant]:
        """Get current population."""
        return copy.deepcopy(self._population)

    def get_generation(self) -> int:
        """Get current generation number."""
        return self._generation

    def get_history(self) -> list[EvolutionRecord]:
        """Get evolution history."""
        return list(self._history)

    def save_state(self, path: str | None = None) -> None:
        """Save evolution state to disk."""
        target = Path(path) if path else self._storage_path
        if not target:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "generation": self._generation,
            "best_variant": asdict(self._best_variant) if self._best_variant else None,
            "population": [asdict(v) for v in self._population],
            "history": [asdict(r) for r in self._history],
            "config": asdict(self._config),
        }
        target.write_text(json.dumps(state, indent=2, default=str))
        logger.info("Evolution state saved to %s", target)

    def load_state(self, path: str | None = None) -> bool:
        """Load evolution state from disk."""
        target = Path(path) if path else self._storage_path
        if not target or not target.exists():
            return False
        try:
            state = json.loads(target.read_text())
            self._generation = state.get("generation", 0)
            if state.get("best_variant"):
                self._best_variant = StrategyVariant(**state["best_variant"])
            self._population = [StrategyVariant(**v) for v in state.get("population", [])]
            self._history = [EvolutionRecord(**r) for r in state.get("history", [])]
            logger.info("Evolution state loaded from %s (generation %d)", target, self._generation)
            return True
        except Exception as e:
            logger.warning("Failed to load evolution state: %s", e)
            return False
