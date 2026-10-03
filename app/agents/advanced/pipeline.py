"""pipeline.py — multi-stage agent pipeline with stage chaining.

Professional AI assistants process tasks through a pipeline of specialized
stages (classify → plan → execute → verify → refine). This module provides
a composable pipeline where each stage is an agent or function, with
conditional branching, parallel execution, and result aggregation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

StageFunc = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class PipelineStage:
    name: str
    func: StageFunc
    condition: Callable[[dict[str, Any]], bool] | None = None
    parallel: bool = False
    timeout: float = 60.0
    retries: int = 1


@dataclass
class PipelineResult:
    success: bool
    stages_executed: list[str] = field(default_factory=list)
    stages_skipped: list[str] = field(default_factory=list)
    stage_results: dict[str, Any] = field(default_factory=dict)
    final_output: str = ""
    total_time: float = 0.0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentPipeline:
    """Composable multi-stage agent pipeline.

    Stages are executed in order. Each stage receives the accumulated
    context dict and returns an updated dict. Stages can be conditional
    (skipped based on context), parallel (run concurrently), and have
    per-stage timeout and retry configuration.
    """

    def __init__(self, name: str = "pipeline") -> None:
        self.name = name
        self._stages: list[PipelineStage] = []
        self._stage_map: dict[str, PipelineStage] = {}

    def add_stage(
        self,
        name: str,
        func: StageFunc,
        *,
        condition: Callable[[dict[str, Any]], bool] | None = None,
        parallel: bool = False,
        timeout: float = 60.0,
        retries: int = 1,
    ) -> AgentPipeline:
        stage = PipelineStage(name, func, condition, parallel, timeout, retries)
        self._stages.append(stage)
        self._stage_map[name] = stage
        return self

    def remove_stage(self, name: str) -> bool:
        if name in self._stage_map:
            self._stages = [s for s in self._stages if s.name != name]
            del self._stage_map[name]
            return True
        return False

    async def execute(self, initial_context: dict[str, Any] | None = None) -> PipelineResult:
        ctx = dict(initial_context or {})
        executed: list[str] = []
        skipped: list[str] = []
        results: dict[str, Any] = {}
        errors: list[str] = []
        start = time.monotonic()

        # Group consecutive parallel stages
        i = 0
        while i < len(self._stages):
            stage = self._stages[i]

            # Check condition
            if stage.condition and not stage.condition(ctx):
                skipped.append(stage.name)
                i += 1
                continue

            # Collect parallel group
            if stage.parallel:
                parallel_group = [stage]
                j = i + 1
                while j < len(self._stages) and self._stages[j].parallel:
                    next_stage = self._stages[j]
                    if next_stage.condition and not next_stage.condition(ctx):
                        skipped.append(next_stage.name)
                        j += 1
                        continue
                    parallel_group.append(next_stage)
                    j += 1

                # Execute parallel group
                async def _run_stage(s: PipelineStage) -> tuple[str, Any, str | None]:
                    for attempt in range(s.retries + 1):
                        try:
                            result = await asyncio.wait_for(
                                s.func(ctx), timeout=s.timeout
                            )
                            return s.name, result, None
                        except asyncio.TimeoutError:
                            if attempt < s.retries:
                                logger.warning("Stage '%s' timed out, retrying", s.name)
                                continue
                            return s.name, None, f"timeout after {s.retries + 1} attempts"
                        except Exception as exc:
                            if attempt < s.retries:
                                logger.warning("Stage '%s' failed: %s, retrying", s.name, exc)
                                continue
                            return s.name, None, str(exc)
                    return s.name, None, "max retries exceeded"

                parallel_results = await asyncio.gather(
                    *[_run_stage(s) for s in parallel_group]
                )
                for name, result, error in parallel_results:
                    if error:
                        errors.append(f"{name}: {error}")
                    else:
                        executed.append(name)
                        results[name] = result
                        if isinstance(result, dict):
                            ctx.update(result)
                i = j
            else:
                # Sequential stage
                error = None
                for attempt in range(stage.retries + 1):
                    try:
                        result = await asyncio.wait_for(
                            stage.func(ctx), timeout=stage.timeout
                        )
                        executed.append(stage.name)
                        results[stage.name] = result
                        if isinstance(result, dict):
                            ctx.update(result)
                        error = None
                        break
                    except asyncio.TimeoutError:
                        if attempt < stage.retries:
                            logger.warning("Stage '%s' timed out, retrying", stage.name)
                            continue
                        error = f"timeout after {stage.retries + 1} attempts"
                    except Exception as exc:
                        if attempt < stage.retries:
                            logger.warning("Stage '%s' failed: %s, retrying", stage.name, exc)
                            continue
                        error = str(exc)
                if error:
                    errors.append(f"{stage.name}: {error}")
                i += 1

        total_time = time.monotonic() - start
        final_output = ctx.get("output", ctx.get("final_output", ""))

        return PipelineResult(
            success=len(errors) == 0,
            stages_executed=executed,
            stages_skipped=skipped,
            stage_results=results,
            final_output=final_output,
            total_time=total_time,
            errors=errors,
            metadata={"pipeline": self.name, "stages_total": len(self._stages)},
        )

    def stage_names(self) -> list[str]:
        return [s.name for s in self._stages]
