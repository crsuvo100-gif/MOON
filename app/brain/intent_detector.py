"""intent_detector.py -- classify a user prompt into one of MOON's intents.

This powers intent detection / routing. It is lightweight and robust:
a keyword/regex classifier for fast, offline routing, with an optional LLM
refinement when the signal is ambiguous. Returns an intent label that the
orchestrator maps to the right agent + pipeline path.

Intents (aligned with MOON's 39 agents and the capability list):
  code, research, web, writing, vision, planning, math, science, security,
  cyber, red_team, blue_team, forensics, reverse_eng, threat_hunt, siem,
  data_science, translation, audio, qa, infra, finance, legal, medical,
  design, summarizer, fact_check, strategy, tools, github_sync, voice,
  system, chat, unknown.
"""

from __future__ import annotations

import re

# intent -> list of trigger tokens (lowercased). Order = priority.
_INTENT_RULES: dict[str, list[str]] = {
    "github_sync": ["github", "repo sync", "push to github", "sync repo", "deploy to github"],
    "voice": ["speak", "say this", "read aloud", "female voice", "dictate", "tts", "speech"],
    "vision": ["image", "picture", "photo", "see this", "describe the image", "screenshot", "ocr", "read text from"],
    "security": ["vulnerability", "hardening", "audit", "secure this", "cve", "exploit intel", "log analysis", "malware"],
    "red_team": ["red team", "offensive", "exploit", "attack", "penetration", "payload", "recon"],
    "blue_team": ["blue team", "defend", "detection", "incident response", "soc"],
    "forensics": ["forensic", "disk image", "memory dump", "timeline"],
    "reverse_eng": ["reverse engineer", "decompile", "disassembl", "binary analysis"],
    "threat_hunt": ["threat hunt", "hunting", "ioc", "anomaly"],
    "siem": ["siem", "splunk", "elastic alert", "log correlation"],
    "code": ["code", "function", "script", "bug", "refactor", "python", "compile", "debug"],
    "research": ["research", "paper", "study", "literature", "survey", "find sources"],
    "web": ["browse", "website", "url", "scrape", "fetch page", "search the web"],
    "writing": ["write", "article", "blog", "email", "story", "draft", "rewrite"],
    "math": ["calculate", "math", "equation", "integral", "derivative", "solve for"],
    "science": ["physics", "chemistry", "biology", "scientific"],
    "data_science": ["dataset", "pandas", "data analysis", "csv", "train model", "statistics"],
    "translation": ["translate", "in french", "to spanish", "language"],
    "audio": ["audio", "music", "sound", "transcribe", "song"],
    "qa": ["test", "qa", "verify behavior", "regression"],
    "infra": ["deploy", "server", "kubernetes", "docker", "ci/cd", "infrastructure"],
    "finance": ["finance", "stock", "budget", "invoice", "accounting"],
    "legal": ["legal", "contract", "law", "clause", "compliance"],
    "medical": ["medical", "diagnosis", "patient", "clinical"],
    "design": ["design", "ui", "ux", "mockup", "logo", "css"],
    "summarizer": ["summarize", "summary", "tl;dr", "condense"],
    "fact_check": ["fact check", "is it true", "verify claim"],
    "strategy": ["strategy", "roadmap", "plan of action", "strategize"],
    "tools": ["install tool", "new tool", "tool for", "add capability"],
    "system": ["system info", "run command", "terminal", "powershell", "host"],
    "planning": ["plan", "break down", "steps to", "how do i", "roadmap"],
    "chat": ["hi", "hello", "how are you", "thanks", "who are you"],
}

# tokens that strongly imply a planning / decomposition request
_DECOMPOSE_HINT = re.compile(r"(break (this|it|that) (down|into)|step[s]? by step|sub-?tasks?|decompose|how (do|would) i|plan (for|to)|roadmap)", re.I)


def detect_intent(prompt: str) -> tuple[str, float]:
    """Return (intent, confidence 0..1). Fast, offline, no LLM needed."""
    p = (prompt or "").lower().strip()
    if not p:
        return "unknown", 0.0
    # strong decomposition signal -> planning regardless of topic
    if _DECOMPOSE_HINT.search(p):
        return "planning", 0.9
    best, score = "chat", 0.3
    for intent, keys in _INTENT_RULES.items():
        for k in keys:
            if k in p:
                # longer key = more specific = higher confidence
                conf = min(0.95, 0.5 + len(k.split()) * 0.12)
                if conf > score:
                    best, score = intent, conf
                break
    return best, score


async def detect_intent_llm(prompt: str, llm=None) -> tuple[str, float]:
    """Optional LLM refinement when the keyword signal is weak/ambiguous."""
    intent, conf = detect_intent(prompt)
    if llm is not None and conf < 0.6:
        try:
            from app.services.llm_service import ChatMessage
            resp = await llm.complete(
                [ChatMessage(role="user", content=(
                    "Classify this request into exactly one intent from this list: "
                    + ", ".join(_INTENT_RULES.keys())
                    + ". Respond with only the intent word.\n\nRequest: " + prompt
                ))],
                max_tokens=24, temperature=0.0,
            )
            label = (resp.content or "").strip().lower().split()[0].strip(".,:")
            if label in _INTENT_RULES:
                return label, 0.85
        except Exception:  # noqa: BLE001
            pass
    return intent, conf
