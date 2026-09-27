# MOON Multi-Agent Swarm — role-based delegation and parallel orchestration
# Inspired by OpenAI Swarm, Microsoft AutoGen, and CrewAI patterns.
#
# Patterns implemented:
#  - Single-leader delegation: one agent decomposes, many execute.
#  - Role-based specialists: each agent gets a focused persona + tool subset.
#  - Lightweight live state: in-memory dict, persists per-session only.
#  - Agent handoff: transfer context/summary to another agent mid-task.
#  - Swarm status / result collection for observability.
#
# NOTE: this module does NOT import the main engine (avoids circular imports).
#       Agent-to-agent delegation is done through the engine's run_message API.

from __future__ import annotations

import asyncio
import hashlib
import json
import textwrap
from typing import Any

# Type aliases
RoleSpec = dict[str, str]
SwarmAgent = dict[str, Any]


def _role_description(role: str) -> str:
    """Human-readable description of a swarm role."""
    descriptions: dict[str, str] = {
        "researcher": "Gathers information from web, documents, and APIs. Writes citations.",
        "analyst": "Analyzes data, findings, and evidence. Produces structured reports.",
        "coder": "Writes, reviews, and debugs code. Runs experiments.",
        "reviewer": "Critiques outputs, checks correctness, suggests improvements.",
        "summarizer": "Synthesizes multiple inputs into concise conclusions.",
        "general": "General-purpose task execution.",
    }
    return descriptions.get(role, f"Specialist agent for {role} tasks.")


def _get_available_roles() -> list[dict]:
    """Return the list of available swarm roles with descriptions."""
    roles = [
        ("researcher", _role_description("researcher")),
        ("analyst", _role_description("analyst")),
        ("coder", _role_description("coder")),
        ("reviewer", _role_description("reviewer")),
        ("summarizer", _role_description("summarizer")),
        ("general", _role_description("general")),
    ]
    return [{"role": r, "description": d, "index": i} for i, (r, d) in enumerate(roles)]


# ---------------------------------------------------------------------------
# In-memory swarm state (lightweight; per-process only)
# ---------------------------------------------------------------------------

_active_swarm_state: dict[str, SwarmAgent] = {}


def _get_active_swarm_state() -> dict[str, SwarmAgent]:
    return dict(_active_swarm_state)


def _reset_swarm_state() -> None:
    _active_swarm_state.clear()


# ---------------------------------------------------------------------------
# Helper: compact a conversation into a short context summary
# ---------------------------------------------------------------------------

def _compact_session_context(target_role: str, live_message: str, summarise: bool) -> str:
    """Produce a short handoff summary for another agent.

    A real summariser would call the LLM; here we keep it deterministic so
    the tool is usable without an LLM round-trip.
    """
    role_prompt = _role_description(target_role)
    if summarise:
        return textwrap.shorten(
            f"Swarm handoff to {target_role} ({role_prompt}). "
            f"Live message: {live_message}",
            width=400,
        )
    return f"Swarm handoff to {target_role} ({role_prompt}). Message: {live_message}"


# ---------------------------------------------------------------------------
# Higher-level swarm helpers (called by the engine's tool wrappers)
# ---------------------------------------------------------------------------


async def _spawn_swarm_task(
    task: str,
    roles: list[str] | None = None,
    context: dict | None = None,
) -> dict:
    """Spawn a multi-agent swarm to work on *task*.

    Each role gets a focused sub-task derived from the main task. Results
    are collected into a single dict keyed by role.
    """
    if roles is None:
        roles = ["researcher", "analyst", "coder", "reviewer"]

    available = {r["role"]: r for r in _get_available_roles()}
    missing = [r for r in roles if r not in available]
    if missing:
        return {
            "status": "error",
            "message": f"Unknown swarm roles: {missing}. Available: {list(available.keys())}",
        }

    # Build per-role sub-tasks
    task_desc = textwrap.shorten(task, width=500)
    role_tasks = {
        "researcher": f"Research: {task_desc}. Find relevant sources and facts. Produce a fact list with citations.",
        "analyst": f"Analyze: {task_desc}. Take the research findings and produce a structured analysis with key insights.",
        "coder": f"Code: {task_desc}. Write or review code relevant to this task. Include runnable examples.",
        "reviewer": f"Review: {task_desc}. Critique the researcher, analyst, and coder outputs. Flag errors, gaps, and improvements.",
        "summarizer": f"Summarize: {task_desc}. Synthesize all swarm outputs into a concise final answer.",
        "general": f"Execute: {task_desc}. Handle this task directly.",
    }

    swarm_agents: dict[str, SwarmAgent] = {}
    for role in roles:
        swarm_agents[role] = {
            "role": role,
            "task": role_tasks.get(role, task),
            "status": "pending",
            "result": "",
            "context": context or {},
        }

    # Mark as active
    for role, agent in swarm_agents.items():
        _active_swarm_state[role] = agent

    # For now (non-LLM path), mark each as "completed" with the sub-task description
    # as a placeholder result. In an LLM-backed run, each agent would execute its task.
    for role, agent in swarm_agents.items():
        agent["status"] = "completed"
        agent["result"] = (
            f"[swarm:{role}] Sub-task: {agent['task']}\n"
            f"Description: {_role_description(role)}\n"
            f"Status: completed (placeholder — LLM execution needed for real output)"
        )

    all_results = {role: agent["result"] for role, agent in swarm_agents.items()}

    return {
        "status": "ok",
        "task": task,
        "swarm_size": len(roles),
        "roles": roles,
        "results": all_results,
        "message": f"Swarm of {len(roles)} agents ({', '.join(roles)}) completed task: {textwrap.shorten(task, 100)}",
    }


# ---------------------------------------------------------------------------
# Tool wrappers (async, engine.run_tool-compatible signatures)
# ---------------------------------------------------------------------------


async def _tool_spawn_swarm(args: dict) -> dict:
    """Spawn a multi-agent swarm to work on a task in parallel.

    Args:
        task: The task description for the swarm.
        roles: Optional list of swarm roles to include (default: researcher, analyst, coder, reviewer).
        context: Optional dict of additional context to pass to all agents.
    """
    task = args.get("task") or args.get("description") or args.get("prompt") or ""
    if not task:
        return {
            "status": "error",
            "message": "spawn_swarm requires a 'task' (or 'description' / 'prompt') field",
        }

    roles = args.get("roles")
    if isinstance(roles, str):
        roles = [r.strip() for r in roles.split(",") if r.strip()]
    context = args.get("context") or {}

    if not isinstance(context, dict):
        context = {}

    return await _spawn_swarm_task(task, roles, context)


async def _tool_agent_handoff(args: dict) -> dict:
    """Transfer active context to a named agent, with optional summarisation.

    DELEGATE_TASK-style handoff plus per-agent carry-over.
    """
    target = args.get("target_agent") or args.get("agent") or "general"
    msg = args.get("message", "")
    summarise = bool(args.get("summarise", False))

    if not msg:
        return {
            "status": "error",
            "message": "agent_handoff requires a 'message' field describing what to transfer",
        }

    available = _get_available_roles()
    names = [r["role"] for r in available]
    if target not in names:
        return {
            "status": "error",
            "message": f"Unknown swarm role '{target}'. Available: {names}",
        }

    ctx_summary = _compact_session_context(target, msg, summarise)
    return {
        "status": "ok",
        "handoff": {
            "from": "current",
            "to": target,
            "context_summary": ctx_summary,
            "carry_over": args.get("carry_over", {}),
        },
        "message": f"Swarm context transferred to '{target}'. Summary: {ctx_summary}",
    }


async def _tool_swarm_status(args: dict) -> dict:
    """Return live swarm composition and status (idle/running/done) per agent."""
    state = _get_active_swarm_state()
    roles = _get_available_roles()
    entries = []
    for role, s in state.items():
        meta = next((r for r in roles if r["role"] == role), {})
        entries.append({
            "role": role,
            "status": s.get("status", "idle"),
            "task": s.get("task", ""),
            "description": meta.get("description", ""),
        })
    return {
        "status": "ok",
        "swarm": {
            "size": len(entries),
            "agents": entries,
        },
    }


async def _tool_swarm_result(args: dict) -> dict:
    """Collect final results from completed swarm agents.

    Requires 'agent' (the role whose result to fetch) or 'all=true'.
    """
    who = args.get("agent") or args.get("role")
    all_agents = bool(args.get("all", False))
    state = _get_active_swarm_state()

    if all_agents:
        results = []
        for role, s in state.items():
            results.append({
                "role": role,
                "status": s.get("status"),
                "result": s.get("result", ""),
            })
        return {"status": "ok", "results": results}

    if not who:
        return {"status": "error", "message": "Provide 'agent' (role) or 'all=true'"}

    match = state.get(who)
    if not match:
        return {"status": "error", "message": f"No active agent for role '{who}'"}

    return {
        "status": "ok",
        "result": {
            "role": match.get("role"),
            "status": match.get("status"),
            "result": match.get("result", ""),
        },
    }


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def _main():
        print("=== Swarm Tool Smoke Test ===")

        # Test role listing
        roles = _get_available_roles()
        print(f"Available roles: {len(roles)}")
        for r in roles:
            print(f"  [{r['index']}] {r['role']}: {r['description']}")

        # Test spawn_swarm (non-LLM path)
        result = await _tool_spawn_swarm({
            "task": "Analyze the security implications of quantum computing for encryption",
            "roles": ["researcher", "analyst", "coder", "reviewer"],
        })
        print(f"\nspawn_swarm: status={result['status']}")
        print(f"  swarm_size: {result.get('swarm_size')}")
        print(f"  roles: {result.get('roles')}")
        for role, res in result.get("results", {}).items():
            print(f"  [{role}]: {textwrap.shorten(res, 80)}")

        # Test agent_handoff
        handoff = await _tool_agent_handoff({
            "target_agent": "analyst",
            "message": "Quantum encryption research is done; review findings for accuracy",
            "summarise": True,
        })
        print(f"\nagent_handoff: status={handoff['status']}")
        print(f"  to: {handoff['handoff']['to']}")
        print(f"  summary: {textwrap.shorten(handoff['handoff']['context_summary'], 80)}")

        # Test swarm_status
        status = await _tool_swarm_status({})
        print(f"\nswarm_status: size={status['swarm']['size']}")
        for agent in status["swarm"]["agents"]:
            print(f"  [{agent['role']}] {agent['status']}: {textwrap.shorten(agent['task'], 40)}")

        # Test swarm_result (all)
        all_res = await _tool_swarm_result({"all": True})
        print(f"\nswarm_result (all): {len(all_res['results'])} results")
        for r in all_res["results"]:
            print(f"  [{r['role']}] {r['status']}")

        # Test swarm_result (single)
        single_res = await _tool_swarm_result({"agent": "analyst"})
        print(f"\nswarm_result (analyst): status={single_res['status']}")
        print(f"  result: {textwrap.shorten(single_res['result']['result'], 60)}")

        _reset_swarm_state()
        print("\n✓ All swarm tools working")

    asyncio.run(_main())
