"""Result Synthesis Pipeline (spec 39).

After agents finish:
    RAW RESULTS -> RESULT NORMALIZATION -> EVIDENCE EXTRACTION ->
    CONFLICT DETECTION -> VERIFICATION -> SYNTHESIS -> FINAL RESPONSE

Final response should represent the verified combined result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.config.logging import get_logger

logger = get_logger(__name__)


class SynthesisStage(str, Enum):
    RAW_RESULTS = "raw_results"
    NORMALIZATION = "normalization"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    CONFLICT_DETECTION = "conflict_detection"
    VERIFICATION = "verification"
    SYNTHESIS = "synthesis"
    FINAL_RESPONSE = "final_response"


@dataclass
class SynthesisResult:
    """Result of the synthesis pipeline (spec 39)."""
    final_response: str = ""
    stages_completed: list[str] = field(default_factory=list)
    stages_skipped: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    verification_status: str = "unverified"
    contributing_agents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_response": self.final_response,
            "stages_completed": self.stages_completed,
            "stages_skipped": self.stages_skipped,
            "evidence": self.evidence,
            "conflicts": self.conflicts,
            "verification_status": self.verification_status,
            "contributing_agents": self.contributing_agents,
            "metadata": self.metadata,
        }


class ResultSynthesisPipeline:
    """Multi-stage synthesis pipeline (spec 39).

    Takes raw agent results and produces ONE coherent final response.
    The pipeline is composable: each stage is a callable that transforms
    the context dict.
    """

    def __init__(self) -> None:
        self._stages: list[tuple[str, Any]] = []

    def add_stage(self, name: str, func: Any) -> ResultSynthesisPipeline:
        """Add a synthesis stage."""
        self._stages.append((name, func))
        return self

    async def execute(
        self,
        raw_results: list[dict[str, Any]],
        *,
        llm: Any = None,
        query: str = "",
    ) -> SynthesisResult:
        """Execute the synthesis pipeline.

        Args:
            raw_results: List of agent result dicts (from ResultAggregator).
            llm: Optional LLM service for synthesis stage.
            query: Original user query.

        Returns:
            SynthesisResult with final response and metadata.
        """
        ctx: dict[str, Any] = {
            "raw_results": raw_results,
            "query": query,
            "llm": llm,
            "evidence": [],
            "conflicts": [],
            "contributing_agents": [],
        }

        completed: list[str] = []
        skipped: list[str] = []

        for name, func in self._stages:
            try:
                result = func(ctx)
                if hasattr(result, "__await__"):
                    result = await result
                if result is not None:
                    ctx.update(result if isinstance(result, dict) else {"_stage_result": result})
                completed.append(name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("synthesis stage '%s' failed: %s", name, exc)
                skipped.append(name)

        # Build final result
        final_response = ctx.get("final_response", "")
        if not final_response and raw_results:
            # Fallback: concatenate primary results
            final_response = "\n\n".join(
                r.get("result", r.get("primary", "")) for r in raw_results
                if r.get("result") or r.get("primary")
            )

        return SynthesisResult(
            final_response=final_response,
            stages_completed=completed,
            stages_skipped=skipped,
            evidence=ctx.get("evidence", []),
            conflicts=ctx.get("conflicts", []),
            verification_status=ctx.get("verification_status", "unverified"),
            contributing_agents=ctx.get("contributing_agents", []),
            metadata={
                "total_stages": len(self._stages),
                "completed_stages": len(completed),
                "skipped_stages": len(skipped),
            },
        )


# -------------------------------------------------------------------------- #
# Built-in synthesis stages
# -------------------------------------------------------------------------- #

def normalize_results(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stage 1: Normalize raw results into a consistent format."""
    raw = ctx.get("raw_results", [])
    normalized = []
    for r in raw:
        normalized.append({
            "agent_id": r.get("agent_id", "unknown"),
            "result": r.get("result", r.get("primary", "")),
            "confidence": r.get("confidence", 0.5),
            "evidence": r.get("evidence", []),
            "status": r.get("status", "unknown"),
        })
    return {"normalized_results": normalized}


def extract_evidence(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stage 2: Extract and deduplicate evidence from all results."""
    normalized = ctx.get("normalized_results", [])
    evidence: list[str] = []
    seen: set[str] = set()
    for r in normalized:
        for ev in r.get("evidence", []):
            if ev not in seen:
                seen.add(ev)
                evidence.append(ev)
    return {"evidence": evidence}


def detect_conflicts(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stage 3: Detect conflicts between agent results."""
    normalized = ctx.get("normalized_results", [])
    conflicts: list[dict[str, Any]] = []

    # Simple conflict detection: opposite polarity
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            a, b = normalized[i], normalized[j]
            # Check for negation patterns
            a_text = a.get("result", "").lower()
            b_text = b.get("result", "").lower()
            negators = ("not ", "no ", "never", "cannot", "failed", "false")
            a_neg = any(n in a_text for n in negators)
            b_neg = any(n in b_text for n in negators)
            if a_neg != b_neg:
                conflicts.append({
                    "agents": [a["agent_id"], b["agent_id"]],
                    "type": "contradiction",
                    "detail": f"{a['agent_id']} vs {b['agent_id']}",
                })

    return {"conflicts": conflicts}


def verify_results(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stage 4: Verify results (placeholder for LLM-based verification)."""
    normalized = ctx.get("normalized_results", [])
    evidence = ctx.get("evidence", [])
    conflicts = ctx.get("conflicts", [])

    if not normalized:
        return {"verification_status": "failed"}

    if conflicts:
        return {"verification_status": "partially_verified"}

    # Check if we have evidence for all results
    has_evidence = all(r.get("evidence") for r in normalized)
    if has_evidence and not conflicts:
        return {"verification_status": "verified"}

    return {"verification_status": "partially_verified"}


def synthesize_final(ctx: dict[str, Any]) -> dict[str, Any]:
    """Stage 5: Synthesize final response from verified results."""
    normalized = ctx.get("normalized_results", [])
    evidence = ctx.get("evidence", [])
    conflicts = ctx.get("conflicts", [])
    query = ctx.get("query", "")

    if not normalized:
        return {"final_response": "No results to synthesize."}

    # Build a coherent response
    parts: list[str] = []

    # Primary result
    primary = normalized[0].get("result", "")
    if primary:
        parts.append(primary)

    # Additional results (if not duplicates)
    seen_texts = {primary.lower()}
    for r in normalized[1:]:
        text = r.get("result", "")
        if text and text.lower() not in seen_texts:
            parts.append(f"\n\n[{r['agent_id']}]: {text}")
            seen_texts.add(text.lower())

    # Evidence summary
    if evidence:
        parts.append(f"\n\nEvidence: {'; '.join(evidence[:5])}")

    # Conflict warning
    if conflicts:
        parts.append(
            f"\n\nWarning: {len(conflicts)} conflict(s) detected between agents."
        )

    final = "".join(parts) if parts else "No results to synthesize."

    return {
        "final_response": final,
        "contributing_agents": [r["agent_id"] for r in normalized],
    }


def create_default_pipeline() -> ResultSynthesisPipeline:
    """Create a default synthesis pipeline with all standard stages."""
    pipeline = ResultSynthesisPipeline()
    pipeline.add_stage("normalize_results", normalize_results)
    pipeline.add_stage("extract_evidence", extract_evidence)
    pipeline.add_stage("detect_conflicts", detect_conflicts)
    pipeline.add_stage("verify_results", verify_results)
    pipeline.add_stage("synthesize_final", synthesize_final)
    return pipeline


__all__ = [
    "SynthesisStage", "SynthesisResult", "ResultSynthesisPipeline",
    "normalize_results", "extract_evidence", "detect_conflicts",
    "verify_results", "synthesize_final", "create_default_pipeline",
]
