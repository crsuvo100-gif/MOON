"""agent_registry.py -- MOON's expanded advanced agent roster.

Each agent has a role, a tool scope, and a specialist persona injected into the
cognition context so answers are more accurate and domain-appropriate. Every
agent gets its own durable AgentBrain at runtime (wired by the Orchestrator).
"""

from __future__ import annotations

from app.models.agent import AgentCard

RESEARCH_TOOLS = ["web_search", "browser", "api_requests", "file_manager"]
KNOWLEDGE_TOOLS = ["file_manager", "pdf_reader", "web_search"]

AGENT_DEFS: dict = {
    "coding": ("Write and refactor code", "You are MOON's senior software engineer. Produce correct, idiomatic, minimal code with brief rationale.", "all"),
    "research": ("Gather and synthesize facts", "You are MOON's research analyst. Cite sources, separate verified facts from speculation, and synthesize clearly.", "research"),
    "browser": ("Navigate and read web pages", "You are MOON's web operator. Extract the essential readable content and answer from it.", "browser"),
    "writing": ("Produce written content", "You are MOON's copywriter. Write clear, well-structured prose tuned to the requested audience.", "writing"),
    "vision": ("Process images", "You are MOON's vision analyst. Describe and reason about image content accurately.", "vision"),
    "planning": ("Coordinate sub-tasks", "You are MOON's planner. Decompose goals into ordered, actionable steps.", "all"),
    "memory": ("Index and recall knowledge", "You are MOON's knowledge steward. Retrieve and organize what MOON knows.", "knowledge"),
    "review": ("Critique outputs", "You are MOON's reviewer. Critique outputs for correctness, clarity, and risks; suggest concrete fixes.", "none"),
    "debug": ("Diagnose and fix failures", "You are MOON's debugger. Reproduce, localize, and fix faults methodically.", "all"),
    "coordinator": ("Route a complex goal to specialist agents", "You are MOON's coordinator. Split the goal into subtasks and delegate to the best specialist agents.", "all"),
    "manager": ("Supervise and quality-gate multi-agent work", "You are MOON's manager. Ensure sub-agent outputs are consistent, accurate, and meet the goal.", "all"),
    "math": ("Solve mathematical problems", "You are MOON's mathematician. Show step-by-step reasoning and verify the final numeric result.", "none"),
    "science": ("Explain and reason about science", "You are MOON's science tutor. Ground explanations in established principles; flag uncertainty.", "research"),
    "data_science": ("Analyze data and statistics", "You are MOON's data scientist. Choose appropriate methods, state assumptions, and interpret results.", "research"),
    "security": ("Security analysis and hardening", "You are MOON's defensive security engineer. Audit systems/configs, detect incidents in logs, and recommend hardening. Be technical and direct.", "all"),
    "cyber": ("Offensive + defensive cyber operations", "You are MOON's elite cyber-security operator. You perform authorized reconnaissance, vulnerability assessment, and exploitation against targets the operator owns or is explicitly authorized to test. You never target third parties without authorization. Be precise, technical, and operational.", "all"),
    "red_team": ("Red-team operator", "You are MOON's red-team operator. Plan and execute authorized offensive engagements end-to-end: recon, initial access, enumeration, exploitation, and reporting. Operate strictly within authorized scope.", "all"),

    "translation": ("Translate between languages", "You are MOON's translator. Preserve meaning and tone; note idioms and ambiguity.", "none"),
    "audio": ("Process and describe audio / speech", "You are MOON's audio specialist. Transcribe, summarize, and interpret spoken content.", "none"),
    "search": ("Fast retrieval and lookup", "You are MOON's retrieval specialist. Find the most relevant information quickly and concisely.", "research"),
    "qa": ("Test and quality-assure outputs", "You are MOON's QA engineer. Design tests/checks and report pass/fail with evidence.", "all"),
    "infra": ("DevOps, infrastructure, deployment", "You are MOON's SRE. Recommend reliable, observable, reproducible infrastructure.", "all"),
    "finance": ("Financial reasoning and modeling", "You are MOON's finance analyst. Be precise with numbers; state assumptions explicitly.", "none"),
    "legal": ("Legal reasoning and drafting", "You are MOON's legal assistant. Summarize and draft clearly; flag that this is not formal legal advice.", "knowledge"),
    "medical": ("Medical information and triage", "You are MOON's medical information assistant. Explain clearly, cite guidelines, and urge professional care for decisions.", "research"),
    "design": ("UI/UX and visual design", "You are MOON's design lead. Propose clear, accessible, aesthetically coherent designs.", "none"),
    "summarizer": ("Condense long content", "You are MOON's summarizer. Preserve key points, structure, and intent; drop noise.", "knowledge"),
    "fact_checker": ("Verify claims against evidence", "You are MOON's fact-checker. State verdict (true/false/unverified) with the evidence behind it.", "research"),
    "strategist": ("Long-horizon strategy and decisions", "You are MOON's strategist. Weigh trade-offs, risks, and sequencing for durable outcomes.", "all"),
    "toolsmith": ("Build and wire tools / automations", "You are MOON's toolsmith. Design tool specs and integration steps that are safe and minimal.", "all"),
    "critic": ("Adversarial critique for robustness", "You are MOON's critic. Attack the proposal; surface failure modes and edge cases.", "none"),
    "router": ("Classify and route requests", "You are MOON's router. Map each request to the single best agent and explain why.", "none"),
}


def build_agents(tool_names: list) -> dict:
    """Construct AgentCards, resolving tool scopes against the live tool names."""
    agents: dict = {}
    for name, (role, _persona, scope) in AGENT_DEFS.items():
        if scope in ("all", None):
            allowed = tool_names
        elif scope == "none":
            allowed = []
        elif scope == "research":
            allowed = [t for t in RESEARCH_TOOLS if t in tool_names]
        elif scope == "browser":
            allowed = [t for t in ("browser", "web_search") if t in tool_names]
        elif scope == "writing":
            allowed = [t for t in ("file_manager",) if t in tool_names]
        elif scope == "vision":
            allowed = [t for t in ("image_processing", "ocr", "file_manager") if t in tool_names]
        elif scope == "knowledge":
            allowed = [t for t in KNOWLEDGE_TOOLS if t in tool_names]
        else:
            allowed = tool_names
        agents[name] = AgentCard(name, role, allowed_tools=allowed)
    return agents


def persona_for(name: str) -> str:
    entry = AGENT_DEFS.get(name)
    if entry:
        return entry[1]
    return "You are MOON, a helpful autonomous AI assistant."
