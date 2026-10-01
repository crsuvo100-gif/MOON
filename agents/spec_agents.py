"""MOON 40-Agent spec roster (additive).

Registers the 40 functional agent roles from the MOON Multi-Agent Team
specification into the structured ``AgentRegistry`` (spec 8) with full metadata:
capabilities, required_tools, permissions, risk_level, dependencies, status.

This is NON-DESTRUCTIVE: it does NOT touch the existing 39 persona agents in
``app.brain.agent_registry.AGENT_DEFS``. The spec agents are registered
alongside them and the orchestrator can select them by capability.

Each ``required_tools`` entry is a capability keyword understood by the live
``CapabilityManager`` / tool registry, so dispatch resolves to a real tool at
runtime (spec 16/17).
"""

from __future__ import annotations

from typing import Iterable

from app.agents.registry import AgentMetadata, get_registry

# (id, name, capabilities, required_tools, permissions, risk, deps, role_group)
_SPEC_AGENTS: list[tuple] = [
    # ---------------- CORE 12 ----------------
    ("master_orchestrator", "Master Orchestrator",
     ["orchestrate", "task_planning", "agent_selection", "monitoring"],
     ["task_executor", "agent_registry"], ["core:manage"], "high",
     ["task_analyzer", "planner"], "core"),
    ("task_analyzer", "Task Analyzer",
     ["analyze_task", "extract_requirements"],
     ["nlp_analysis"], ["read:task"], "low", [], "core"),
    ("planner", "Planner",
     ["decompose_task", "build_plan", "dependency_graph"],
     ["task_executor"], ["read:task", "write:plan"], "low", ["task_analyzer"], "core"),
    ("researcher", "Researcher",
     ["web_research", "doc_search", "github_search", "file_search"],
     ["web_search", "fetch_url", "github_feed", "read_file"], ["web:read", "fs:read"], "low", [], "core"),
    ("knowledge_memory", "Knowledge & Memory Agent",
     ["knowledge_extraction", "memory_store", "semantic_search", "episodic_recall"],
     ["knowledge_base", "memory_store", "vector_search"], ["kb:write", "mem:write"], "low", ["researcher"], "core"),
    ("learner", "Learning Agent",
     ["learn", "curriculum", "practice", "mastery"],
     ["knowledge_base", "memory_store", "learning_tool"], ["learn:run"], "low", ["knowledge_memory"], "core"),
    ("skill_builder", "Skill Builder Agent",
     ["build_skill", "update_skill", "test_skill"],
     ["skill_system", "python_executor"], ["skill:write"], "medium", [], "core"),
    ("tool_manager", "Tool Discovery & Manager Agent",
     ["tool_discovery", "tool_install", "tool_configure", "tool_update", "tool_remove"],
     ["capability_manager", "python_executor", "system_command"], ["tool:install", "tool:remove"], "high", [], "core"),
    ("executor", "Executor Agent",
     ["execute_task", "run_pipeline"],
     ["task_executor", "python_executor"], ["exec:run"], "medium", [], "core"),
    ("verifier", "Verifier Agent",
     ["verify_result", "check_evidence"],
     ["verification_engine", "python_executor"], ["verify:run"], "low", [], "core"),
    ("debugger_recovery", "Debugger & Recovery Agent",
     ["debug", "failure_recovery", "retry", "alternate_strategy"],
     ["python_executor", "log_analyzer", "system_info"], ["debug:run"], "medium", ["executor"], "core"),
    ("security_sandbox", "Security & Sandbox Agent",
     ["security_review", "sandbox_run", "policy_check"],
     ["sandbox_executor", "security_audit"], ["security:review"], "high", [], "core"),

    # ---------------- ADVANCED ----------------
    ("coder", "Coding Agent",
     ["write_code", "refactor", "modify_code"],
     ["python_executor", "file_manager"], ["code:write"], "medium", [], "advanced"),
    ("git_agent", "Git Agent",
     ["git_ops", "github_ops", "repo_management"],
     ["git", "github_sync", "github_feed"], ["git:write"], "medium", [], "advanced"),
    ("terminal_agent", "Terminal Agent",
     ["terminal_ops", "shell_exec"],
     ["system_command", "powershell"], ["shell:run"], "high", [], "advanced"),
    ("browser_agent", "Browser Agent",
     ["browser_control", "web_scrape", "web_interaction"],
     ["browser", "web_search"], ["web:write"], "medium", [], "advanced"),
    ("api_agent", "API Agent",
     ["api_discover", "api_call", "api_manage"],
     ["api_requests", "web_search"], ["api:call"], "medium", [], "advanced"),
    ("database_agent", "Database Agent",
     ["db_query", "db_storage", "db_maintain"],
     ["database"], ["db:write"], "medium", [], "advanced"),
    ("data_agent", "Data Agent",
     ["data_process", "data_extract", "data_transform"],
     ["python_executor", "file_manager"], ["data:process"], "low", [], "advanced"),
    ("vision_agent", "Vision Agent",
     ["image_analysis", "screenshot_analysis", "video_analysis"],
     ["image_processing", "ocr", "pdf_reader"], ["vision:read"], "low", [], "advanced"),
    ("voice_agent", "Voice Agent",
     ["speech_to_text", "text_to_speech"],
     ["tts", "stt"], ["voice:run"], "low", [], "advanced"),
    ("communication_agent", "Communication Agent",
     ["telegram", "whatsapp", "email"],
     ["telegram", "email_send"], ["comm:send"], "medium", [], "advanced"),
    ("monitoring_agent", "Monitoring Agent",
     ["monitor_process", "monitor_service", "system_health"],
     ["system_info", "log_analyzer"], ["monitor:read"], "low", [], "advanced"),
    ("scheduler_agent", "Scheduler Agent",
     ["schedule_task", "periodic_task", "background_task"],
     ["task_executor", "cron"], ["sched:write"], "low", [], "advanced"),
    ("documentation_agent", "Documentation Agent",
     ["write_docs", "readme", "tech_notes"],
     ["file_manager", "markdown"], ["doc:write"], "low", [], "advanced"),
    ("evaluation_agent", "Evaluation Agent",
     ["score_agent", "score_skill", "score_tool"],
     ["evaluation_engine"], ["eval:run"], "low", [], "advanced"),
    ("reflection_agent", "Reflection Agent",
     ["self_reflect", "performance_analysis"],
     ["memory_store", "knowledge_base"], ["reflect:run"], "low", [], "advanced"),
    ("self_improvement_agent", "Self-Improvement Agent",
     ["propose_improvement", "generate_patch", "safe_deploy"],
     ["self_evolve", "python_executor"], ["improve:propose"], "critical", ["verifier"], "advanced"),
    ("model_router_agent", "Model Router Agent",
     ["model_selection", "complexity_routing"],
     ["model_management", "model_pull"], ["model:select"], "low", [], "advanced"),
    ("resource_manager_agent", "Resource / Cost Agent",
     ["cpu_optimize", "ram_optimize", "gpu_optimize", "cost_optimize"],
     ["system_info", "model_management"], ["resource:read"], "low", [], "advanced"),
    ("audit_agent", "Audit Agent",
     ["log_action", "audit_trail"],
     ["audit_log"], ["audit:read"], "low", [], "advanced"),
    ("goal_agent", "Goal Agent",
     ["track_goal", "long_term_goal"],
     ["memory_store", "knowledge_base"], ["goal:track"], "low", [], "advanced"),
    ("context_manager_agent", "Context Manager Agent",
     ["context_optimize", "token_optimize"],
     ["memory_store"], ["ctx:manage"], "low", [], "advanced"),
    ("agent_router", "Agent Router",
     ["route_agent", "capability_match"],
     ["agent_registry"], ["route:run"], "medium", [], "advanced"),
    ("failure_recovery_agent", "Failure Recovery Agent",
     ["diagnose_failure", "retry_strategy"],
     ["log_analyzer", "system_command"], ["recover:run"], "medium", ["debugger_recovery"], "advanced"),
    ("knowledge_maintenance_agent", "Knowledge Maintenance Agent",
     ["detect_stale_knowledge", "update_knowledge"],
     ["knowledge_base", "web_search"], ["kb:maintain"], "low", ["knowledge_memory"], "advanced"),
    ("messaging_agent", "Communication/Messaging Agent",
     ["agent_messaging", "message_route"],
     ["event_bus"], ["msg:route"], "low", [], "advanced"),
    ("sandbox_agent", "Sandbox Agent",
     ["isolate_run", "resource_limit"],
     ["sandbox_executor"], ["sandbox:run"], "medium", ["security_sandbox"], "advanced"),
]


def register_spec_agents() -> int:
    """Register all 40 spec agents into the structured registry (idempotent)."""
    reg = get_registry()
    count = 0
    for aid, name, caps, tools, perms, risk, deps, group in _SPEC_AGENTS:
        if reg.get(aid):
            continue
        reg.register(AgentMetadata(
            id=aid, name=name, version="1.0.0",
            description=f"MOON 40-agent spec role: {name}",
            capabilities=caps, required_tools=tools, permissions=perms,
            risk_level=risk, dependencies=deps, status="active",
            source="spec40", role_group=group,
        ))
        count += 1
    return count


def spec_agent_ids() -> list[str]:
    return [a[0] for a in _SPEC_AGENTS]


__all__ = ["register_spec_agents", "spec_agent_ids", "_SPEC_AGENTS"]
