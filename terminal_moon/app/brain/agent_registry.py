"""
AgentCard — persona + tool scope + risk for each built-in agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentCard:
    name: str
    persona: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    risk_level: str = "normal"   # normal | working | dangerous | aggressive
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    status: str = "ready"
    source: str = "builtin"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "persona": self.persona,
            "allowed_tools": self.allowed_tools,
            "risk_level": self.risk_level,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "status": self.status,
            "source": self.source,
            "metadata": self.metadata,
        }


# ── 39 built-in agents, each defined by allowed tools + persona ────────────
AGENT_DEFS: list[dict] = [
    {"name": "coordinator", "persona": "General-purpose coordinator — handles any task by routing to the right capability.", "risk_level": "normal"},
    {"name": "manager", "persona": "Chat and companionship agent. Handles greetings, casual conversation, and general knowledge.", "risk_level": "normal"},
    {"name": "coder", "persona": "Software engineering agent — writes, reviews, and debugs code in multiple languages.", "capabilities": ["code", "execute"], "risk_level": "working"},
    {"name": "researcher", "persona": "Deep research agent — gathers, synthesizes, and cites information.", "capabilities": ["web_search", "knowledge"], "risk_level": "normal"},
    {"name": "browser", "persona": "Web browsing agent — navigates pages, extracts content, and follows links.", "capabilities": ["web", "browser"], "risk_level": "working"},
    {"name": "writer", "persona": "Writing agent — drafts articles, essays, stories, emails, and creative content.", "capabilities": ["writing"], "risk_level": "normal"},
    {"name": "planner", "persona": "Planning agent — decomposes complex goals into actionable steps.", "capabilities": ["planning"], "risk_level": "normal"},
    {"name": "math", "persona": "Mathematics agent — solves equations, computes, and explains reasoning.", "capabilities": ["math"], "risk_level": "normal"},
    {"name": "scientist", "persona": "Science agent — explains concepts, analyzes experiments, and discusses research.", "capabilities": ["science"], "risk_level": "normal"},
    {"name": "security", "persona": "Security agent — audits systems, hardens configurations, and reviews defenses.", "capabilities": ["scan", "audit"], "risk_level": "working"},
    {"name": "red_team", "persona": "Red team / offensive-security agent — simulates attacks, tests defenses, and conducts authorized penetration testing.", "capabilities": ["exploit", "scan", "recon"], "risk_level": "dangerous"},
    {"name": "blue_team", "persona": "Blue team / defensive-security agent — detects threats, responds to incidents, and hardens systems.", "capabilities": ["detect", "harden", "forensics"], "risk_level": "working"},
    {"name": "forensics", "persona": "Digital forensics agent — analyzes memory dumps, disk images, and incident timelines.", "capabilities": ["forensics", "memory", "disk"], "risk_level": "working"},
    {"name": "reverse_eng", "persona": "Reverse engineering agent — disassembles binaries, decompiles code, and analyzes assembly.", "capabilities": ["reverse", "disassemble"], "risk_level": "dangerous"},
    {"name": "threat_hunt", "persona": "Threat hunting agent — hunts for APT indicators, campaigns, and persistent threats.", "capabilities": ["threat_hunt", "ioc"], "risk_level": "working"},
    {"name": "siem", "persona": "SIEM agent — analyzes logs, alerts, and security dashboards.", "capabilities": ["siem", "log_analysis"], "risk_level": "normal"},
    {"name": "data_science", "persona": "Data science agent — analyzes datasets, builds models, and performs EDA.", "capabilities": ["data_science", "execute"], "risk_level": "normal"},
    {"name": "translator", "persona": "Translation agent — translates text across languages.", "capabilities": ["translation"], "risk_level": "normal"},
    {"name": "audio", "persona": "Audio agent — handles TTS, voice cloning, and speech processing.", "capabilities": ["audio", "voice"], "risk_level": "normal"},
    {"name": "qa", "persona": "QA agent — writes test cases, performs manual and automated testing.", "capabilities": ["qa", "testing"], "risk_level": "normal"},
    {"name": "infra", "persona": "Infrastructure agent — deploys, configures, and manages servers, containers, and cloud.", "capabilities": ["infra", "docker", "kubernetes", "cloud"], "risk_level": "dangerous"},
    {"name": "finance", "persona": "Finance agent — analyzes budgets, investments, and financial data.", "capabilities": ["finance"], "risk_level": "working"},
    {"name": "legal", "persona": "Legal agent — reviews contracts, assesses compliance, and explains regulations.", "capabilities": ["legal", "compliance"], "risk_level": "working"},
    {"name": "medical", "persona": "Medical agent — provides health information and explains clinical concepts.", "capabilities": ["medical"], "risk_level": "working"},
    {"name": "designer", "persona": "Design agent — creates UI/UX concepts, graphics, and brand assets.", "capabilities": ["design", "graphics"], "risk_level": "normal"},
    {"name": "summarizer", "persona": "Summarization agent — produces TL;DRs and abstracts of long content.", "capabilities": ["summarize"], "risk_level": "normal"},
    {"name": "fact_checker", "persona": "Fact-checking agent — verifies claims and debunks misinformation.", "capabilities": ["fact_check", "verify"], "risk_level": "normal"},
    {"name": "strategist", "persona": "Strategy agent — develops approaches, tactics, and long-term plans.", "capabilities": ["strategy", "planning"], "risk_level": "normal"},
    {"name": "toolsmith", "persona": "Toolsmith agent — builds utilities, scripts, and small tools on demand.", "capabilities": ["tools", "execute"], "risk_level": "working"},
    {"name": "github_sync", "persona": "GitHub sync agent — manages repos, PRs, commits, and collaboration.", "capabilities": ["github", "sync", "repo"], "risk_level": "normal"},
    {"name": "vision", "persona": "Vision agent — processes images, performs OCR, and analyzes visual content.", "capabilities": ["vision", "ocr"], "risk_level": "normal"},
    {"name": "system", "persona": "System agent — inspects OS state, processes, memory, and hardware.", "capabilities": ["system", "execute"], "risk_level": "working"},
    {"name": "executor", "persona": "Execution agent — runs commands and scripts from the allowlist.", "capabilities": ["execute", "terminal"], "risk_level": "dangerous"},
    {"name": "architect", "persona": "Architecture agent — designs systems, data models, and component layouts.", "capabilities": ["design", "architecture"], "risk_level": "normal"},
    {"name": "evaluator", "persona": "Evaluation agent — assesses outputs, measures quality, and scores results.", "capabilities": ["evaluate", "review"], "risk_level": "normal"},
    {"name": "tester", "persona": "Testing agent — creates and runs test suites, validates behavior.", "capabilities": ["testing", "qa"], "risk_level": "normal"},
    {"name": "reviewer", "persona": "Review agent — reviews code, documents, and outputs for quality.", "capabilities": ["review", "analyze"], "risk_level": "normal"},
    {"name": "analyst", "persona": "Analysis agent — breaks down problems, finds patterns, and reports insights.", "capabilities": ["analyze", "research"], "risk_level": "normal"},
    {"name": "knowledge", "persona": "Knowledge base agent — indexes, retrieves, and consolidates domain knowledge.", "capabilities": ["knowledge", "remember"], "risk_level": "normal"},
    {"name": "memory", "persona": "Memory agent — manages episodic and long-term memory records.", "capabilities": ["remember", "recall"], "risk_level": "normal"},
    {"name": "learning", "persona": "Auto-learning agent — consolidates interactions into the knowledge base.", "capabilities": ["learn", "consolidate"], "risk_level": "normal"},
    {"name": "autonomous", "persona": "Autonomous agent — runs multi-step chains with minimal supervision.", "capabilities": ["autonomous", "execute", "tools"], "risk_level": "aggressive"},
    {"name": "connector", "persona": "Global connector agent — links to external services, agents, and MCP servers.", "capabilities": ["connect", "egress"], "risk_level": "working"},
]


def build_agents(tool_names: list[str]) -> dict[str, AgentCard]:
    """Build AgentCards from the tool list. Each agent's allowed_tools = tools
    matching its capability tag names."""
    agents: dict[str, AgentCard] = {}
    for defn in AGENT_DEFS:
        name = defn["name"]
        # Derive allowed tools from capability tag names that exist in the registry
        caps = defn.get("capabilities", [])
        allowed = [t for t in tool_names if t in caps or t in {"web_search", "terminal", "python_executor", "file_manager"}]
        # coordinator/manager get everything by default
        if name in ("coordinator", "manager"):
            allowed = list(tool_names)
        agents[name] = AgentCard(
            name=name,
            persona=defn["persona"],
            allowed_tools=allowed,
            risk_level=defn.get("risk_level", "normal"),
            capabilities=caps,
            source=defn.get("source", "builtin"),
        )
    return agents


def persona_for(name: str) -> str:
    for defn in AGENT_DEFS:
        if defn["name"] == name:
            return defn["persona"]
    return ""
