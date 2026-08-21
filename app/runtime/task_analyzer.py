"""TaskAnalyzer (spec section 10).

Converts a free-form user request into a structured GoalSpec:

  { goal, requirements[], constraints[], inputs[], outputs[],
    risk, required_capabilities[], verification_requirements[] }

Pure, deterministic, dependency-light. No model call required (the orchestrator
can still enrich it with the LLM later), so it is independently testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoalSpec:
    goal: str
    requirements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    risk: str = "low"
    required_capabilities: list[str] = field(default_factory=list)
    verification_requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "risk": self.risk,
            "required_capabilities": self.required_capabilities,
            "verification_requirements": self.verification_requirements,
        }


_RISK_WORDS = {
    "critical": ("delete", "wipe", "format", "destroy", "root", "exploit", "payload", "ddos"),
    "high": ("install", "deploy", "modify", "change", "configure", "access", "scan", "attack"),
    "medium": ("write", "create", "generate", "send", "post", "build", "refactor"),
}
_CAP_MAP = {
    "python": "coding", "code": "coding", "bug": "debug", "test": "qa",
    "research": "research", "web": "browser", "search": "search",
    "translate": "translation", "image": "vision", "audio": "audio",
    "security": "security", "network": "cyber", "github": "github_sync",
    "memory": "memory", "knowledge": "memory", "summar": "summarizer",
    "plan": "planning", "data": "data_science", "finance": "finance",
}


class TaskAnalyzer:
    def analyze(self, request: str) -> GoalSpec:
        text = (request or "").strip()
        goal = text or "(empty request)"
        reqs: list[str] = []
        caps: list[str] = []

        # capability detection
        low = text.lower()
        for kw, cap in _CAP_MAP.items():
            if re.search(rf"\b{re.escape(kw)}\b", low):
                caps.append(cap)
        # de-dupe preserve order
        seen = set()
        caps = [c for c in caps if not (c in seen or seen.add(c))]

        # requirements: verb phrases
        for verb in ("create", "build", "analyze", "fix", "test", "search",
                     "summarize", "translate", "deploy", "install", "refactor",
                     "research", "plan", "generate", "write"):
            if re.search(rf"\b{verb}\b", low):
                reqs.append(verb)

        # risk classification
        risk = "low"
        for lvl, words in _RISK_WORDS.items():
            if any(w in low for w in words):
                risk = lvl
                break

        # constraints: explicit phrases
        constraints: list[str] = []
        if "without" in low or "don't" in low or "do not" in low:
            constraints.append("operator-specified negation")
        if "secure" in low or "safe" in low:
            constraints.append("security-conscious")

        # verification
        verify: list[str] = ["evidence_present"]
        if any(k in low for k in ("test", "verify", "check", "confirm")):
            verify.append("test_pass")
        if "file" in low or "write" in low:
            verify.append("file_exists")

        return GoalSpec(
            goal=goal, requirements=reqs or ["process"],
            constraints=constraints, inputs=[text], outputs=["result"],
            risk=risk, required_capabilities=caps,
            verification_requirements=verify,
        )
