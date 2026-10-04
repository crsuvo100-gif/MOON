"""Build the MOON model registry (main brain + every agent) at a 1M context
window, then a qwen-family variant.

Generated from the REAL roster in app/brain/agent_model_manager.py so the agent
list is never invented. Writes two files into app/config/.

Run from the repo root:  .venv/bin/python gen_model_registry.py
"""

import json
from pathlib import Path

from app.brain.agent_model_manager import (
    AGENT_MODELS,
    AGENT_MULTIMODAL,
    RECOMMENDED_FOR_CAPABLE_HW,
)

CONTEXT_1M = 1_000_000
DEFAULT_MODEL = "qwen2.5:1.5b"
OUT = Path(__file__).resolve().parent / "app" / "config"


def _model_entry(model_id, role, agent=None, ctx=CONTEXT_1M):
    return {
        "model_id": model_id,
        "role": role,
        "agent": agent,
        "context_window": ctx,
        "max_output_tokens": 8192,
        "supports_tools": True,
        "supports_system_messages": True,
    }


def build(family: str, resolve) -> dict:
    """family: label; resolve(agent, mapped) -> model_id."""
    agents = {}
    for agent, mapped in sorted(AGENT_MODELS.items()):
        agents[agent] = _model_entry(resolve(agent, mapped), "agent", agent)

    multimodal = {}
    for agent, spec in sorted(AGENT_MULTIMODAL.items()):
        multimodal[agent] = {
            "modality_model": spec.get("vision") or spec.get("audio"),
            "fallback_text_model": resolve(agent, spec.get("fallback_text")),
            "context_window": CONTEXT_1M,
        }

    return {
        "family": family,
        "context_window": CONTEXT_1M,
        "main_brain": {
            "default": _model_entry(resolve(None, None), "main_brain_default"),
            "strong": _model_entry(resolve(None, None), "main_brain_strong_accuracy_gate"),
        },
        "agents": agents,
        "agents_multimodal": multimodal,
        "agent_count": len(agents),
        "recommended_for_capable_hw": dict(sorted(RECOMMENDED_FOR_CAPABLE_HW.items())),
    }


def main() -> None:
    # 1M-context baseline: keep each agent's CURRENT mapped model, just widen ctx.
    baseline = build("moon-1m", lambda agent, mapped: mapped or DEFAULT_MODEL)

    # qwen-family variant: force every agent onto the qwen family.
    def qwen(agent, mapped):
        if mapped and "qwen" in mapped:
            return mapped
        if agent in ("math", "science", "manager"):
            return "qwen3:8b"
        return "qwen2.5:3b"

    qwen_variant = build("moon-1m-qwen", qwen)

    p1 = OUT / "moon_models_1m.json"
    p2 = OUT / "moon_models_1m_qwen.json"
    p1.write_text(json.dumps(baseline, indent=2) + "\n")
    p2.write_text(json.dumps(qwen_variant, indent=2) + "\n")
    print(f"wrote {p1} ({baseline['agent_count']} agents)")
    print(f"wrote {p2} ({qwen_variant['agent_count']} agents)")


if __name__ == "__main__":
    main()
