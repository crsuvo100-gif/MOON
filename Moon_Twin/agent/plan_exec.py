# MOON Plan-and-Execute Orchestrator
# Inspired by Devin, Claude's Plan Mode, and iterative execution patterns.
#
# Provides a structured workflow for complex tasks:
#  1. PLAN  — decompose the task into ordered steps with success criteria
#  2. EXECUTE — run each step via the best agent/tool, collecting evidence
#  3. VERIFY — check each step's output against success criteria
#  4. ITERATE — fix failed steps and re-verify (up to a limit)
#  5. REPORT — produce a structured final report

import asyncio
import re as _re
import json as _json

from agent.engine import _eng

# ---------------------------------------------------------------------------
# Step decomposition
# ---------------------------------------------------------------------------

async def _decompose_task(task: str, context: str = "") -> list[dict]:
    """Ask the LLM to break a task into ordered execution steps.

    Returns a list of step dicts: [{'step': int, 'description': str,
    'agent': str, 'tool_hint': str, 'success_criteria': str}, ...]
    """
    prompt = (
        f"Task: {task}\n"
        f"Context: {context}\n\n"
        "Break this task into 3-8 ordered steps. For each step provide:\n"
        "- step number\n"
        "- description: what to do, concrete and actionable\n"
        "- agent: which MOON agent is best (general, code, security, research, "
        "voice, admin, creative, monitor), or 'auto' if unclear\n"
        "- tool_hint: optional hint about which tool to use\n"
        "- success_criteria: how to know this step succeeded\n\n"
        "Return ONLY a JSON list. Example:\n"
        '[{"step": 1, "description": "...", "agent": "code", '
        '"tool_hint": "python_executor", "success_criteria": "..."}, ...]'
    )
    try:
        resp = await _eng()._llm.chat(
            message=prompt,
            system="You decompose complex tasks into ordered execution steps. "
                   "Return ONLY a JSON list of step objects.",
        )
        raw = (resp.get("content") or "[]")
        raw = _re.sub(r"^```\w*?\n?", "", raw)
        raw = _re.sub(r"\n?```$", "", raw)
        steps = _json.loads(raw)
        if not isinstance(steps, list) or not steps:
            return [{"step": 1, "description": task, "agent": "auto",
                     "tool_hint": "", "success_criteria": "task completed"}]
        # Normalize
        for s in steps:
            s.setdefault("step", steps.index(s) + 1)
            s.setdefault("agent", "auto")
            s.setdefault("tool_hint", "")
            s.setdefault("success_criteria", "step completed successfully")
        return steps
    except Exception as e:
        return [{"step": 1, "description": task, "agent": "auto",
                 "tool_hint": "", "success_criteria": "task completed",
                 "decomposition_note": f"auto-fallback: {e}"}]


# ---------------------------------------------------------------------------
# Single step execution
# ---------------------------------------------------------------------------

async def _execute_step(step: dict, context: str = "") -> dict:
    """Execute a single step using the engine's LLM + tool dispatch."""
    description = step.get("description", "")
    agent = step.get("agent", "auto")
    tool_hint = step.get("tool_hint", "")
    success_criteria = step.get("success_criteria", "completed")

    if agent == "auto":
        from agent.engine import route_intent
        agent = route_intent(description)

    user_msg = f"Context from previous steps:\n{context}\n\nStep to execute:\n{description}\n\n"
    if tool_hint:
        user_msg += f"Hinted tool: {tool_hint}\n"
    user_msg += f"Success criteria: {success_criteria}\n\n"
    user_msg += "Execute this step. Use tools if helpful. Report what you did and the result."

    try:
        resp = await _eng()._llm.chat(
            message=user_msg,
            system=f"You are the MOON {agent} agent. Execute the step precisely. "
                   f"Use your tools when helpful. Be concise but complete.",
            tools=_eng()._build_tool_defs(_eng().personas.get(agent, {}).get("tools", [])),
        )
        content = (resp.get("content") or "").strip()
        # Check if the LLM called any tools
        tool_calls = resp.get("tool_calls") or []
        return {
            "step": step.get("step"),
            "description": description,
            "agent": agent,
            "output": content[:3000],
            "tool_calls_made": len(tool_calls),
            "status": "ok",
        }
    except Exception as e:
        return {
            "step": step.get("step"),
            "description": description,
            "agent": agent,
            "output": "",
            "error": str(e)[:500],
            "status": "error",
        }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

async def _verify_step(step: dict, exec_result: dict) -> dict:
    """Ask the LLM to verify whether a step's output meets its success criteria."""
    criteria = step.get("success_criteria", "completed")
    output = exec_result.get("output", "")
    error = exec_result.get("error", "")

    if exec_result.get("status") == "error":
        return {"status": "fail", "reason": f"execution error: {error[:200]}"}

    if not output.strip():
        return {"status": "fail", "reason": "empty output"}

    prompt = (
        f"Step: {step.get('description','')}\n"
        f"Success criteria: {criteria}\n\n"
        f"Actual output:\n{output}\n\n"
        "Does this output meet the success criteria? Answer ONLY with "
        "'PASS' or 'FAIL' followed by a brief reason."
    )
    try:
        resp = await _eng()._llm.chat(
            message=prompt,
            system="You verify whether execution results meet success criteria. "
                   "Answer PASS or FAIL with a short reason.",
        )
        verdict = (resp.get("content") or "PASS").strip().upper()
        passed = verdict.startswith("PASS")
        return {
            "status": "pass" if passed else "fail",
            "verdict": verdict,
            "reason": (resp.get("content") or "")[6:].strip()[:300],
        }
    except Exception:
        # If LLM verification fails, fall back to heuristic
        if exec_result.get("status") == "ok" and output.strip():
            return {"status": "pass", "reason": "heuristic: output present"}
        return {"status": "fail", "reason": "verification unavailable"}


# ---------------------------------------------------------------------------
# Main plan-and-execute
# ---------------------------------------------------------------------------

async def _tool_plan_and_execute(args: dict) -> dict:
    """Structured plan → execute → verify → iterate → report loop.

    Usage:
      plan_and_execute(task="build a Python web scraper with error handling")
      plan_and_execute(task="analyze this log file and find anomalies",
                       context="Log file is at /var/log/app.log",
                       max_iterations=3)

    Returns a structured report with plan, per-step results, verification,
    fixes applied, and final summary.
    """
    task = args.get("task", "").strip()
    if not task:
        return {"error": "task is required"}

    context = args.get("context", "").strip()
    max_iterations = int(args.get("max_iterations", 3))
    verify_each_step = args.get("verify_each_step", True)

    # Phase 1: Plan
    steps = await _decompose_task(task, context)
    report = {
        "task": task,
        "context": context,
        "plan": steps,
        "phases": {"plan": "done", "execute": [], "verify": [], "iterate": [], "final": ""},
        "status": "in_progress",
    }

    # Phase 2+3: Execute + verify loop
    context_accumulator = context
    failed_steps: list[dict] = []
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        report["phases"]["iterate"].append({"iteration": iteration})

        # Execute all remaining steps
        step_results = []
        for step in steps:
            # Skip already-passed steps
            if any(ps.get("step") == step["step"] and ps.get("verified") for ps in report["phases"]["verify"]):
                continue
            res = await _execute_step(step, context_accumulator)
            step_results.append(res)
            context_accumulator += f"\n--- Step {step['step']} result ---\n{res.get('output', res.get('error', ''))[:500]}\n"

        report["phases"]["execute"].extend(step_results)

        # Verify
        verify_results = []
        still_failed = []
        for res in step_results:
            v = await _verify_step(steps[res["step"] - 1], res) if verify_each_step else {"status": "pass", "reason": "skipped"}
            v["step"] = res["step"]
            verify_results.append(v)
            report["phases"]["verify"].append(v)
            if v["status"] == "fail":
                still_failed.append(steps[res["step"] - 1])

        if not still_failed:
            break  # All passed

        # Iterate: fix failed steps
        if still_failed and iteration < max_iterations:
            fix_prompt = (
                f"These steps failed verification:\n"
                + "\n".join(f"Step {s['step']}: {s['description']} — {s.get('success_criteria','')}\n"
                            f"Previous output: {prev.get('output','')[:200]}\n"
                            for s, prev in zip(still_failed,
                                [r for r in step_results if r["step"] in [sf['step'] for sf in still_failed]]))
                + "\nRe-execute these steps with fixes. Describe what you changed."
            )
            try:
                fix_resp = await _eng()._llm.chat(
                    message=fix_prompt,
                    system="You fix failed execution steps. Describe the fix and re-execute.",
                )
                context_accumulator += f"\n--- Fix iteration {iteration} ---\n{(fix_resp.get('content') or '')[:500]}\n"
                report["phases"]["iterate"][-1]["fix_applied"] = (fix_resp.get("content") or "")[:500]
            except Exception:
                report["phases"]["iterate"][-1]["fix_error"] = "LLM fix unavailable"

        steps = still_failed  # Only retry failed steps next iteration

    # Phase 5: Final report
    all_verify = report["phases"]["verify"]
    passed = sum(1 for v in all_verify if v.get("status") == "pass")
    failed = sum(1 for v in all_verify if v.get("status") == "fail")
    total = len(all_verify) or len(steps)

    final_prompt = (
        f"Task: {task}\n\n"
        f"Plan had {len(steps)} steps. {passed} passed verification, {failed} failed.\n\n"
        f"Final context:\n{context_accumulator[:3000]}\n\n"
        "Write a concise final report: what was accomplished, any remaining issues, "
        "and key outputs."
    )
    try:
        final_resp = await _eng()._llm.chat(
            message=final_prompt,
            system="You write a concise final report summarizing the plan-and-execute result.",
        )
        final_report = (final_resp.get("content") or "").strip()
    except Exception:
        final_report = f"Plan completed: {passed}/{total} steps passed."

    report["phases"]["final"] = final_report
    report["summary"] = {
        "total_steps": len(steps),
        "passed": passed,
        "failed": failed,
        "iterations_used": iteration,
        "status": "completed" if failed == 0 else "completed_with_failures",
    }
    report["status"] = "done"
    return report


# ---------------------------------------------------------------------------
# Standalone plan tool (just decompose, don't execute)
# ---------------------------------------------------------------------------

async def _tool_plan(args: dict) -> dict:
    """Create a structured plan for a task without executing it.

    Returns a step-by-step plan that can be reviewed before execution.
    """
    task = args.get("task", "").strip()
    context = args.get("context", "").strip()
    if not task:
        return {"error": "task is required"}
    steps = await _decompose_task(task, context)
    return {
        "task": task,
        "context": context,
        "plan": steps,
        "step_count": len(steps),
        "estimated_complexity": "high" if len(steps) > 5 else "medium" if len(steps) > 3 else "low",
    }
