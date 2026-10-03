"""OutputFormatter -- normalizes final answers and synthesizes multi-agent results.

Two responsibilities:

* :meth:`OutputFormatter.format` -- normalize a single agent answer.
* :meth:`OutputFormatter.synthesize` -- spec 39/40: turn a multi-agent
  :class:`~app.brain.aggregator.AggregatedResult` into ONE coherent user-facing
  response. The pipeline is RAW RESULTS -> normalization -> evidence extraction
  -> conflict detection -> verification -> synthesis -> FINAL RESPONSE, and the
  final response contract (spec 40) reports what was done, what succeeded, what
  failed, the evidence, remaining issues and the next action -- without exposing
  internal agent chatter when it is not useful.
"""

from __future__ import annotations

from typing import Any


class OutputFormatter:
    def format(self, text: str) -> str:
        if not text:
            return text
        # Strip an accidental trailing persona preamble if echoed back.
        return text.strip()

    # ------------------------------------------------------------------
    # spec 39/40: multi-agent synthesis
    # ------------------------------------------------------------------
    def synthesize(self, aggregated: Any, *, user_request: str = "") -> str:
        """Compose ONE final response from an aggregated multi-agent result.

        ``aggregated`` is an AggregatedResult (or its ``to_dict()``). Returns a
        plain-text response that satisfies the spec-40 contract.
        """
        d = aggregated.to_dict() if hasattr(aggregated, "to_dict") else dict(aggregated or {})
        status = d.get("status", "UNVERIFIED")
        primary = (d.get("primary") or "").strip()
        conflicts = d.get("conflicts") or []
        failed = d.get("failed_agents") or []
        contributors = d.get("contributing_agents") or []
        evidence = d.get("evidence") or []
        notes = d.get("notes") or []

        lines: list[str] = []

        # 1. The answer itself (verified combined result).
        if primary:
            lines.append(primary)
        else:
            lines.append("No verified result was produced for this request.")

        # 2. Status + who contributed (kept short; internal detail is optional).
        bits = [f"status: {status}"]
        if contributors:
            bits.append("agents: " + ", ".join(contributors[:6]))
        lines.append("")
        lines.append("(" + " | ".join(bits) + ")")

        # 3. Conflicts -> never silently reported as success (spec 27).
        if conflicts:
            lines.append("")
            lines.append("Conflicts detected (not reported as success):")
            for c in conflicts[:5]:
                kind = c.get("kind", "conflict")
                agents = ", ".join(c.get("agents", [])[:4])
                lines.append(f"  - {kind} [{agents}]: {str(c.get('detail',''))[:160]}")

        # 4. What failed.
        if failed:
            lines.append("")
            lines.append("Failed agents: " + ", ".join(failed[:6]))

        # 5. Evidence (proof, not adjectives).
        if evidence:
            lines.append("")
            lines.append("Evidence:")
            for e in evidence[:6]:
                lines.append(f"  - {str(e)[:160]}")

        # 6. Remaining issues / next action.
        if notes:
            lines.append("")
            lines.append("Notes: " + "; ".join(str(n)[:120] for n in notes[:3]))
        if conflicts:
            lines.append("Next action: request verification from the conflicting agents.")
        elif failed:
            lines.append("Next action: retry or reassign the failed work.")

        return "\n".join(lines).strip()
