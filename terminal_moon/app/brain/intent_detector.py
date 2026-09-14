"""
Intent detector — keyword-based classify → agent routing.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("moontm.intent")


INTENT_MAP: dict[str, Tuple[list[str], str]] = {
    "code": (["code", "program", "implement", "script", "function", "class", "api", "python", "javascript", "bash", "shell script"], "coder"),
    "research": (["research", "investigate", "find out", "explore", "study", "look into"], "researcher"),
    "web": (["web", "search", "browse", "website", "url", "link", "scrape", "online"], "browser"),
    "writing": (["write", "draft", "compose", "author", "article", "essay", "story", "poem", "email", "letter"], "writer"),
    "vision": (["image", "photo", "picture", "vision", "see", "look", "ocr", "visual"], "vision"),
    "planning": (["plan", "break down", "decompose", "steps", "roadmap", "strategy", "outline", "organize"], "planner"),
    "math": (["math", "calculate", "compute", "equation", "solve", "formula", "algebra", "statistics"], "math"),
    "science": (["science", "physics", "chemistry", "biology", "experiment", "hypothesis", "lab"], "scientist"),
    "security": (["security", "secure", "hardening", "audit", "protect", "defend", "firewall", "encryption"], "security"),
    "cyber": (["cyber", "cve", "exploit", "vulnerability", "pentest", "red team", "offensive", "hack", "crack", "malware", "reverse", "recon", "payload", "attack", "privilege escalation", "lateral movement", "scan"], "red_team"),
    "red_team": (["red team", "offensive", "exploit", "attack", "pentest", "crack", "malware", "reverse shell"], "red_team"),
    "blue_team": (["blue team", "defend", "harden", "detect", "response", "incident", "forensics", "triaging", "malware analysis"], "blue_team"),
    "forensics": (["forensic", "investigate incident", "memory dump", "disk image", "triage", "timeline"], "forensics"),
    "reverse_eng": (["reverse engineer", "disassemble", "decompile", "decompiler", "ghidra", "ida", "binary", "assembly"], "reverse_eng"),
    "threat_hunt": (["threat hunt", "apt", "indicator", "ioc", "ttsc", "attacker", "campaign"], "threat_hunt"),
    "siem": (["siem", "log analysis", "alert", "dashboard", "splunk", "wazuh", "monitoring"], "siem"),
    "data_science": (["data science", "data analysis", "pandas", "eda", "machine learning", "model", "training", "dataframe"], "data_science"),
    "translation": (["translate", "translation", "language", "translator"], "translator"),
    "audio": (["audio", "voice", "speech", "sound", "tts", "clone"], "audio"),
    "qa": (["qa", "test", "quality", "qa engineer", "manual testing", "test case"], "qa"),
    "infra": (["infra", "infrastructure", "deploy", "docker", "kubernetes", "server", "cloud", "devops", "ci/cd"], "infra"),
    "finance": (["finance", "budget", "investment", "stock", "accounting", "financial"], "finance"),
    "legal": (["legal", "law", "contract", "compliance", "regulation", "gdpr", "terms"], "legal"),
    "medical": (["medical", "health", "doctor", "diagnosis", "clinical", "patient"], "medical"),
    "design": (["design", "graphic", "ui", "ux", "logo", "brand"], "designer"),
    "summarizer": (["summarize", "summary", "tl;dr", "abstract", "digest"], "summarizer"),
    "fact_check": (["fact check", "verify", "true or false", "is this accurate", "debunk", "fact-check"], "fact_checker"),
    "strategy": (["strategy", "strategic", "plan", "approach", "method", "tactic"], "strategist"),
    "toolsmith": (["tool", "build tool", "create tool", "utility", "script tool", "make a tool"], "toolsmith"),
    "github_sync": (["github", "sync", "repo", "pull request", "commit", "push", "clone"], "github_sync"),
    "voice": (["voice", "speak", "tts", "audio", "talk"], "audio"),
    "system": (["system", "os", "kernel", "process", "memory", "cpu", "disk", "network"], "infra"),
    "chat": (["chat", "hi", "hello", "hey", "talk", "converse", "chatting"], "manager"),
}


def detect_intent(prompt: str) -> Tuple[str, float]:
    """Return (intent, confidence). Confidence is heuristic: keyword density."""
    if not prompt:
        return "coordinator", 0.0

    low = prompt.lower()
    scores: dict[str, int] = {}
    for intent, (tokens, _) in INTENT_MAP.items():
        for tok in tokens:
            if tok in low:
                scores[intent] = scores.get(intent, 0) + 1

    if not scores:
        return "coordinator", 0.0

    best_intent = max(scores, key=scores.get)
    confidence = min(scores[best_intent] / max(len(prompt.split()), 1), 1.0)

    # decomposition boost: if prompt asks to break/plan → planning
    if re.search(r"\b(break|decompose|plan|steps|roadmap|organize)\b", low):
        if best_intent != "planning" and scores.get("planning", 0) == 0:
            return "planning", confidence

    return best_intent, round(confidence, 2)


def intent_to_agent(intent: str) -> str:
    """Map detected intent to an agent name."""
    return INTENT_MAP.get(intent, ("", "coordinator"))[1] or "coordinator"
