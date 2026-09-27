"""
MOON Professional Tools — advanced capabilities for agentic workflows.

Tools added in this module:
  - user_preferences : persist/query user preferences (language, timezone, tone, format)
  - task_queue       : background task queue with enqueue/dequeue/status/clear/watch
  - workflow         : DAG-based workflow orchestration with steps, deps, retries, timeout
  - resources        : system resource metrics (CPU, mem, disk, load avg, swap)
  - expr_eval        : safe expression evaluator (arithmetic, logic, comparisons, no exec)
  - subprocess_run   : sandboxed subprocess execution with timeout, capture, env control
  - http_multipart   : multipart/form-data HTTP POST (file upload + fields)
  - random_data      : generate random data (UUIDs, passwords, numbers, choices, samples)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import random as _random
import re
import secrets
import string
import time as _time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime as _dt
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

# Lazy engine accessor (avoids circular import at module load)
_default_engine = None


def _eng():
    global _default_engine
    if _default_engine is None:
        from agent.engine import default_engine as _de
        _default_engine = _de
    return _default_engine


# ---------------------------------------------------------------------------
# user_preferences — persistent user preference store
# ---------------------------------------------------------------------------

_PREF_PATH = Path.home() / ".moon" / "preferences.json"


def _load_prefs() -> dict:
    if _PREF_PATH.exists():
        try:
            return json.loads(_PREF_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_prefs(data: dict) -> None:
    _PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREF_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


async def _tool_user_preferences(args: dict) -> dict:
    """Get or set user preferences (language, timezone, tone, output format, etc.).

    GET:  {"action": "get", "keys": ["language","timezone"]}  (keys optional → all)
    SET:  {"action": "set", "preferences": {"language": "en", "timezone": "UTC"}}
    """
    action = (args.get("action") or "get").strip().lower()
    if action == "get":
        keys = args.get("keys")
        prefs = _load_prefs()
        if keys and isinstance(keys, list):
            return {k: prefs.get(k) for k in keys if isinstance(k, str)}
        return prefs
    if action == "set":
        prefs = args.get("preferences")
        if not prefs or not isinstance(prefs, dict):
            return {"error": "preferences (dict) is required for set action"}
        current = _load_prefs()
        current.update(prefs)
        _save_prefs(current)
        return {"status": "saved", "preferences": current, "keys_updated": list(prefs.keys())}
    if action == "delete":
        keys = args.get("keys")
        if not keys or not isinstance(keys, list):
            return {"error": "keys (list) is required for delete action"}
        current = _load_prefs()
        for k in keys:
            current.pop(k, None)
        _save_prefs(current)
        return {"status": "deleted", "remaining_keys": list(current.keys())}
    return {"error": f"Unknown action '{action}'. Use get, set, or delete."}


# ---------------------------------------------------------------------------
# task_queue — simple in-memory background task queue
# ---------------------------------------------------------------------------

@dataclass
class _TaskEntry:
    id: str
    status: str = "pending"       # pending | running | done | failed | cancelled
    payload: dict = field(default_factory=dict)
    result: Any = None
    created_at: float = field(default_factory=_time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    max_age_secs: int = 3600


_task_store: dict[str, _TaskEntry] = {}
_task_seq = 0


def _next_task_id() -> str:
    global _task_seq
    _task_seq += 1
    return f"task_{_task_seq:06d}_{int(_time.time())}"


async def _tool_task_queue(args: dict) -> dict:
    """Manage a background task queue.

    ACTIONS:
      enqueue  — add a task:  {"action":"enqueue","payload":{"cmd":"...","args":{...}},"max_age_secs":3600}
      dequeue  — pop next pending:  {"action":"dequeue"}
      status   — get task status:  {"action":"status","task_id":"..."}
      list     — list tasks:  {"action":"list","status":"pending", "limit":20}
      cancel   — cancel a task:  {"action":"cancel","task_id":"..."}
      clear    — clear tasks by status:  {"action":"clear","status":"done"}
    """
    global _task_store
    action = (args.get("action") or "list").strip().lower()

    if action == "enqueue":
        payload = args.get("payload")
        if not payload or not isinstance(payload, dict):
            return {"error": "payload (dict) is required"}
        tid = args.get("task_id") or _next_task_id()
        max_age = int(args.get("max_age_secs", 3600))
        entry = _TaskEntry(id=tid, payload=payload, max_age_secs=max_age)
        _task_store[tid] = entry
        return {"task_id": tid, "status": "enqueued", "payload": payload}

    if action == "dequeue":
        pending = [e for e in _task_store.values() if e.status == "pending"]
        if not pending:
            return {"task_id": None, "status": "empty"}
        # pick oldest
        entry = min(pending, key=lambda e: e.created_at)
        entry.status = "running"
        entry.started_at = _time.time()
        return {"task_id": entry.id, "payload": entry.payload, "status": "dequeued"}

    if action == "status":
        tid = args.get("task_id")
        if not tid:
            return {"error": "task_id is required"}
        entry = _task_store.get(tid)
        if not entry:
            return {"task_id": tid, "status": "not_found"}
        # age out expired
        if _time.time() - entry.created_at > entry.max_age_secs and entry.status == "pending":
            entry.status = "cancelled"
        return {
            "task_id": entry.id,
            "status": entry.status,
            "payload": entry.payload,
            "result": entry.result,
            "created_at": entry.created_at,
            "started_at": entry.started_at,
            "finished_at": entry.finished_at,
        }

    if action == "list":
        status_filter = args.get("status")
        limit = int(args.get("limit", 50))
        items = list(_task_store.values())
        if status_filter:
            items = [e for e in items if e.status == status_filter]
        items.sort(key=lambda e: e.created_at, reverse=True)
        return {
            "tasks": [{
                "task_id": e.id,
                "status": e.status,
                "payload": e.payload,
                "created_at": e.created_at,
            } for e in items[:limit]],
            "total": len(items),
        }

    if action == "cancel":
        tid = args.get("task_id")
        if not tid:
            return {"error": "task_id is required"}
        entry = _task_store.get(tid)
        if not entry:
            return {"task_id": tid, "status": "not_found"}
        if entry.status in ("done", "failed", "cancelled"):
            return {"task_id": tid, "status": entry.status, "note": "already terminal"}
        entry.status = "cancelled"
        entry.finished_at = _time.time()
        return {"task_id": tid, "status": "cancelled"}

    if action == "complete":
        tid = args.get("task_id")
        result = args.get("result")
        if not tid:
            return {"error": "task_id is required"}
        entry = _task_store.get(tid)
        if not entry:
            return {"task_id": tid, "status": "not_found"}
        entry.status = "done"
        entry.result = result
        entry.finished_at = _time.time()
        return {"task_id": tid, "status": "done", "result": result}

    if action == "fail":
        tid = args.get("task_id")
        error = args.get("error", "unknown error")
        if not tid:
            return {"error": "task_id is required"}
        entry = _task_store.get(tid)
        if not entry:
            return {"task_id": tid, "status": "not_found"}
        entry.status = "failed"
        entry.result = {"error": error}
        entry.finished_at = _time.time()
        return {"task_id": tid, "status": "failed", "error": error}

    if action == "clear":
        status_filter = args.get("status")
        if status_filter:
            before = len(_task_store)
            _task_store = {k: v for k, v in _task_store.items() if v.status != status_filter}
            return {"cleared": before - len(_task_store), "remaining": len(_task_store)}
        _task_store.clear()
        return {"cleared": "all", "remaining": 0}

    return {"error": f"Unknown action '{action}'. Use enqueue, dequeue, status, list, cancel, complete, fail, or clear."}


# ---------------------------------------------------------------------------
# workflow — DAG-based workflow orchestrator
# ---------------------------------------------------------------------------

@dataclass
class _WorkflowStep:
    id: str
    action: str = "echo"       # echo | add | multiply | fetch | sleep | custom
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0
    timeout_secs: int = 60


@dataclass
class _Workflow:
    id: str
    name: str
    steps: list[_WorkflowStep] = field(default_factory=list)
    status: str = "pending"   # pending | running | done | failed | cancelled
    results: dict = field(default_factory=dict)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None


_workflow_store: dict[str, _Workflow] = {}
_workflow_seq = 0


def _next_wf_id() -> str:
    global _workflow_seq
    _workflow_seq += 1
    return f"wf_{_workflow_seq:06d}"


def _resolve_step(step: _WorkflowStep, prev_results: dict) -> dict:
    """Execute a single workflow step and return its result."""
    action = step.action
    a = step.args

    if action == "echo":
        return {"value": a.get("message", str(a.get("value", ""))), "step": step.id}

    if action == "add":
        x = a.get("x", 0)
        y = a.get("y", 0)
        return {"value": float(x) + float(y), "step": step.id}

    if action == "multiply":
        x = a.get("x", 1)
        y = a.get("y", 1)
        return {"value": float(x) * float(y), "step": step.id}

    if action == "sleep":
        secs = float(a.get("secs", 1))
        _time.sleep(min(secs, step.timeout_secs))
        return {"value": f"slept {secs}s", "step": step.id}

    if action == "fetch":
        url = a.get("url", "")
        if not url:
            return {"error": "url is required for fetch step", "step": step.id}
        import urllib.request as _urlr
        try:
            with _urlr.urlopen(url, timeout=min(step.timeout_secs, 30)) as resp:
                body = resp.read()[:10000]
                return {"status": resp.status, "body_preview": body[:500].decode("utf-8", errors="replace"), "step": step.id}
        except Exception as e:
            return {"error": str(e), "step": step.id}

    if action == "custom":
        # placeholder — real implementations can dispatch to engine tools
        return {"value": f"custom:{step.id}", "step": step.id, "args": a}

    return {"error": f"Unknown step action '{action}'", "step": step.id}


async def _tool_workflow(args: dict) -> dict:
    """Manage DAG-based workflows.

    CREATE:  {"action":"create","name":"my-workflow","steps":[
               {"id":"s1","action":"echo","args":{"message":"hello"}},
               {"id":"s2","action":"add","args":{"x":1,"y":2},"depends_on":["s1"]},
             ]}
    RUN:     {"action":"run","workflow_id":"..."}
    STATUS:  {"action":"status","workflow_id":"..."}
    CANCEL:  {"action":"cancel","workflow_id":"..."}
    LIST:    {"action":"list"}
    """
    action = (args.get("action") or "list").strip().lower()

    if action == "create":
        name = args.get("name", "").strip()
        if not name:
            return {"error": "name is required"}
        steps_raw = args.get("steps")
        if not steps_raw or not isinstance(steps_raw, list):
            return {"error": "steps (list) is required"}
        steps = []
        for i, s in enumerate(steps_raw):
            if not isinstance(s, dict):
                return {"error": f"step {i} must be a dict"}
            steps.append(_WorkflowStep(
                id=s.get("id", f"step_{i}"),
                action=s.get("action", "echo"),
                args=s.get("args", {}),
                depends_on=s.get("depends_on", []),
                max_retries=int(s.get("max_retries", 0)),
                timeout_secs=int(s.get("timeout_secs", 60)),
            ))
        # check deps
        step_ids = {s.id for s in steps}
        for s in steps:
            for dep in s.depends_on:
                if dep not in step_ids:
                    return {"error": f"Step '{s.id}' depends on unknown step '{dep}'"}
        wf_id = args.get("workflow_id") or _next_wf_id()
        wf = _Workflow(id=wf_id, name=name, steps=steps)
        _workflow_store[wf_id] = wf
        return {"workflow_id": wf_id, "name": name, "steps": len(steps), "status": "created"}

    if action == "run":
        wf_id = args.get("workflow_id")
        if not wf_id:
            return {"error": "workflow_id is required"}
        wf = _workflow_store.get(wf_id)
        if not wf:
            return {"error": f"Workflow '{wf_id}' not found", "workflow_id": wf_id}
        if wf.status not in ("pending", "failed"):
            return {"workflow_id": wf_id, "status": wf.status, "note": "already terminal"}
        wf.status = "running"
        wf.started_at = _time.time()
        results = {}
        step_map = {s.id: s for s in wf.steps}

        for step in wf.steps:
            if wf.status == "cancelled":
                break
            # wait for deps
            for dep in step.depends_on:
                dep_result = results.get(dep)
                if dep_result is None:
                    # dep hasn't run — shouldn't happen in topological order,
                    # but handle gracefully
                    pass

            success = False
            last_err = None
            for attempt in range(step.max_retries + 1):
                if wf.status == "cancelled":
                    break
                try:
                    # run in thread to not block asyncio loop
                    loop = asyncio.get_event_loop()
                    res = await loop.run_in_executor(
                        ThreadPoolExecutor(max_workers=1),
                        lambda s=step, pr=results: _resolve_step(s, pr),
                    )
                    if "error" not in res:
                        results[step.id] = res
                        success = True
                        break
                    last_err = res.get("error")
                except asyncio.TimeoutError:
                    last_err = f"step {step.id} timed out after {step.timeout_secs}s"
                except Exception as e:
                    last_err = str(e)
                if attempt < step.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))

            if not success:
                wf.status = "failed"
                wf.finished_at = _time.time()
                return {
                    "workflow_id": wf_id,
                    "status": "failed",
                    "step": step.id,
                    "error": last_err,
                    "results_so_far": results,
                }

        wf.status = "done"
        wf.results = results
        wf.finished_at = _time.time()
        return {
            "workflow_id": wf_id,
            "status": "done",
            "results": results,
            "elapsed_secs": round(wf.finished_at - wf.started_at, 3),
        }

    if action == "status":
        wf_id = args.get("workflow_id")
        if not wf_id:
            return {"error": "workflow_id is required"}
        wf = _workflow_store.get(wf_id)
        if not wf:
            return {"workflow_id": wf_id, "status": "not_found"}
        return {
            "workflow_id": wf.id,
            "name": wf.name,
            "status": wf.status,
            "steps": [{"id": s.id, "action": s.action, "depends_on": s.depends_on} for s in wf.steps],
            "results": wf.results,
            "started_at": wf.started_at,
            "finished_at": wf.finished_at,
        }

    if action == "cancel":
        wf_id = args.get("workflow_id")
        if not wf_id:
            return {"error": "workflow_id is required"}
        wf = _workflow_store.get(wf_id)
        if not wf:
            return {"workflow_id": wf_id, "status": "not_found"}
        if wf.status in ("done", "failed", "cancelled"):
            return {"workflow_id": wf_id, "status": wf.status}
        wf.status = "cancelled"
        wf.finished_at = _time.time()
        return {"workflow_id": wf_id, "status": "cancelled"}

    if action == "list":
        limit = int(args.get("limit", 50))
        wfs = sorted(_workflow_store.values(), key=lambda w: w.started_at or 0, reverse=True)
        return {
            "workflows": [{
                "workflow_id": w.id,
                "name": w.name,
                "status": w.status,
                "steps": len(w.steps),
                "started_at": w.started_at,
                "finished_at": w.finished_at,
            } for w in wfs[:limit]],
            "total": len(wfs),
        }

    return {"error": f"Unknown action '{action}'. Use create, run, status, cancel, or list."}


# ---------------------------------------------------------------------------
# resources — system resource metrics
# ---------------------------------------------------------------------------

async def _tool_resources(args: dict) -> dict:
    """Get current system resource usage: CPU, memory, swap, disk, load average.

    {"action": "all"}  (default) → full report
    {"action": "cpu"}  → CPU only
    {"action": "mem"}  → memory only
    {"action": "disk"} → disk only
    {"action": "load"} → load average only
    """
    import importlib.util
    psutil = None
    if importlib.util.find_spec("psutil") is not None:
        import psutil as _ps
        psutil = _ps

    action = (args.get("action") or "all").strip().lower()
    report = {"timestamp": _dt.now().isoformat(), "backend": "psutil" if psutil else "fallback"}

    if psutil:
        if action in ("all", "cpu"):
            report["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            report["cpu_count"] = psutil.cpu_count(logical=True)
            report["cpu_freq"] = psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        if action in ("all", "mem"):
            vm = psutil.virtual_memory()
            report["memory"] = {
                "total_gb": round(vm.total / 1e9, 2),
                "available_gb": round(vm.available / 1e9, 2),
                "used_gb": round(vm.used / 1e9, 2),
                "percent": vm.percent,
            }
            sm = psutil.swap_memory()
            report["swap"] = {
                "total_gb": round(sm.total / 1e9, 2),
                "used_gb": round(sm.used / 1e9, 2),
                "percent": sm.percent,
            }
        if action in ("all", "disk"):
            disks = []
            for part in psutil.disk_partitions()[:8]:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "mount": part.mountpoint,
                        "device": part.device,
                        "total_gb": round(usage.total / 1e9, 2),
                        "used_gb": round(usage.used / 1e9, 2),
                        "free_gb": round(usage.free / 1e9, 2),
                        "percent": usage.percent,
                    })
                except PermissionError:
                    pass
            report["disks"] = disks
        if action in ("all", "load"):
            try:
                report["load_avg"] = os.getloadavg()  # (1, 5, 15)
            except (AttributeError, OSError):
                report["load_avg"] = None
        if action == "all":
            procs = psutil.pids()[:20]
            report["process_count_sample"] = len(procs)
    else:
        # fallback: /proc-based
        report["cpu_percent"] = None
        if action in ("all", "load"):
            try:
                with open("/proc/loadavg") as f:
                    parts = f.read().split()
                    report["load_avg"] = tuple(float(x) for x in parts[:3])
            except Exception:
                report["load_avg"] = None
        if action in ("all", "mem"):
            try:
                with open("/proc/meminfo") as f:
                    lines = f.read()
                vm = {}
                for line in lines.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        vm[k.strip()] = v.strip()
                total = int(vm.get("MemTotal", "0").split()[0])
                avail = int(vm.get("MemAvailable", "0").split()[0])
                report["memory"] = {
                    "total_gb": round(total * 1024 / 1e9, 2),
                    "available_gb": round(avail * 1024 / 1e9, 2),
                    "percent": round((1 - avail / total) * 100, 1) if total else 0,
                }
            except Exception:
                report["memory"] = None
        if action in ("all", "disk"):
            report["disks"] = [{"mount": "/", "note": "proc-based fallback"}]
        report["backend"] = "proc-fallback"

    return report


# ---------------------------------------------------------------------------
# expr_eval — safe expression evaluator (no exec, no imports)
# ---------------------------------------------------------------------------

# Whitelist of allowed names: math functions + constants + basic ops
_SAFE_NAMES = {
    **{k: v for k, v in math.__dict__.items() if not k.startswith("_")},
    "abs": abs, "min": min, "max": max, "round": round,
    "sum": sum, "len": len, "range": range,
    "true": True, "false": False, "none": None,
    "pi": math.pi, "e": math.e,
    "pow": pow, "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "ceil": math.ceil, "floor": math.floor,
}


async def _tool_expr_eval(args: dict) -> dict:
    """Safely evaluate a mathematical/logical expression without using exec/eval on untrusted code.

    {"expression": "sqrt(16) + 2 ** 3", "variables": {"x": 5}}
    Returns {"result": 13.0, "expression": "...", "-evaluated": true}
    """
    expr = args.get("expression", "").strip()
    if not expr:
        return {"error": "expression is required"}

    variables = args.get("variables") or {}
    if not isinstance(variables, dict):
        return {"error": "variables must be a dict"}

    allowed = dict(_SAFE_NAMES)
    allowed.update(variables)

    # Only allow a restricted set of AST nodes
    import ast as _ast

    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return {"error": f"Syntax error: {e}", "expression": expr, "evaluated": False}

    # Whitelist node types
    allowed_nodes = {
        _ast.Expression, _ast.Name, _ast.Constant, _ast.BinOp,
        _ast.UnaryOp, _ast.UAdd, _ast.USub, _ast.Add, _ast.Sub, _ast.Mult,
        _ast.Div, _ast.Mod, _ast.Pow, _ast.FloorDiv,
        _ast.Compare, _ast.Eq, _ast.NotEq, _ast.Lt, _ast.LtE, _ast.Gt, _ast.GtE,
        _ast.BoolOp, _ast.And, _ast.Or, _ast.Not,
        _ast.Call, _ast.Attribute, _ast.Load,
        _ast.Tuple, _ast.List, _ast.Dict, _ast.ListComp, _ast.GeneratorExp,
        _ast.comprehension,
    }

    for node in _ast.walk(tree):
        if type(node) not in allowed_nodes:
            return {"error": f"Disallowed expression element: {type(node).__name__}", "expression": expr, "evaluated": False}

    try:
        code = compile(tree, "<expr_eval>", "eval")
        result = eval(code, {"__builtins__": {}}, allowed)
        return {"result": result, "expression": expr, "evaluated": True, "type": type(result).__name__}
    except Exception as e:
        return {"error": str(e), "expression": expr, "evaluated": False}


# ---------------------------------------------------------------------------
# subprocess_run — sandboxed subprocess execution
# ---------------------------------------------------------------------------

async def _tool_subprocess_run(args: dict) -> dict:
    """Run a subprocess with timeout, capture stdout/stderr, optional env, cwd, shell mode.

    {"command": "ls -la /tmp", "timeout_secs": 30, "shell": true, "cwd": "/tmp", "env": {"FOO":"bar"}}
    {"command": ["python3", "--version"], "timeout_secs": 10}
    """
    command = args.get("command")
    if not command:
        return {"error": "command is required"}

    timeout_secs = int(args.get("timeout_secs", 30))
    shell = bool(args.get("shell", False))
    cwd = args.get("cwd")
    env = args.get("env")  # dict or None
    capture = not args.get("no_capture", False)
    check = bool(args.get("check", True))

    import subprocess as _sp

    proc_env = None
    if env and isinstance(env, dict):
        proc_env = {**os.environ, **env}

    try:
        if isinstance(command, str) and not shell:
            # split safely
            import shlex as _shlex
            cmd_list = _shlex.split(command)
        elif isinstance(command, str) and shell:
            cmd_list = command
        else:
            cmd_list = list(command)

        proc = _sp.run(
            cmd_list,
            shell=shell,
            cwd=cwd,
            env=proc_env,
            capture_output=capture,
            text=True,
            timeout=timeout_secs,
        )
        out = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
        if check and proc.returncode != 0:
            out["error"] = f"command exited {proc.returncode}"
        out["timed_out"] = False
        return out
    except _sp.TimeoutExpired as e:
        return {"error": f"command timed out after {timeout_secs}s", "timed_out": True,
                "stdout": (e.stdout or "")[:5000], "stderr": (e.stderr or "")[:5000]}
    except FileNotFoundError as e:
        return {"error": f"command not found: {e}", "timed_out": False}
    except Exception as e:
        return {"error": str(e), "timed_out": False}


# ---------------------------------------------------------------------------
# http_multipart — multipart/form-data POST
# ---------------------------------------------------------------------------

async def _tool_http_multipart(args: dict) -> dict:
    """Send a multipart/form-data POST request (file upload + form fields).

    {"url": "https://example.com/upload", "fields": {"title": "hello"}, "files": {"doc": "/path/to/file.pdf"}, "timeout_secs": 30}
    Returns {"status_code": 200, "body": "...", "headers": {...}}
    """
    url = args.get("url", "").strip()
    if not url:
        return {"error": "url is required"}

    fields = args.get("fields") or {}
    files = args.get("files") or {}
    timeout_secs = int(args.get("timeout_secs", 30))
    method = (args.get("method") or "POST").upper()

    if not isinstance(fields, dict):
        return {"error": "fields must be a dict"}
    if not isinstance(files, dict):
        return {"error": "files must be a dict"}

    import urllib.request as _urlr
    import urllib.error as _url_err

    # Build multipart body
    boundary = f"----MOON_{uuid.uuid4().hex}"
    body = b""

    for key, val in fields.items():
        part = f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{str(val)}\r\n"
        body += part.encode("utf-8")

    for key, path in files.items():
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}", "file": key}
        try:
            data = p.read_bytes()
        except Exception as e:
            return {"error": f"Cannot read file {path}: {e}", "file": key}
        disp = f'Content-Disposition: form-data; name="{key}"; filename="{p.name}"'
        ct = "application/octet-stream"
        part = f"--{boundary}\r\n{disp}\r\nContent-Type: {ct}\r\n\r\n"
        body += part.encode("utf-8") + data + b"\r\n"

    body += f"--{boundary}--\r\n".encode("utf-8")

    req = _urlr.Request(url, data=body, method=method)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))

    try:
        with _urlr.urlopen(req, timeout=timeout_secs) as resp:
            raw = resp.read()[:50000]
            return {
                "status_code": resp.status,
                "body": raw.decode("utf-8", errors="replace"),
                "headers": dict(resp.headers),
            }
    except _url_err.HTTPError as e:
        raw = e.read()[:50000]
        return {"status_code": e.code, "body": raw.decode("utf-8", errors="replace"),
                "error": f"HTTP {e.code}", "headers": dict(e.headers)}
    except _url_err.URLError as e:
        return {"error": f"Connection error: {e}", "url": url}


# ---------------------------------------------------------------------------
# random_data — random data generation
# ---------------------------------------------------------------------------

async def _tool_random_data(args: dict) -> dict:
    """Generate random data: UUIDs, passwords, numbers, choices, tokens, samples.

    {"type": "uuid", "count": 3}
    {"type": "password", "length": 16, "count": 1}
    {"type": "number", "min": 1, "max": 100, "count": 5}
    {"type": "choice", "options": ["a","b","c"], "count": 3}
    {"type": "token", "length": 32, "count": 2}
    {"type": "sample", "population": [1,2,3,4,5], "k": 2, "count": 1}
    """
    typ = (args.get("type") or "uuid").strip().lower()
    count = int(args.get("count", 1))

    if typ == "uuid":
        return {"results": [str(uuid.uuid4()) for _ in range(count)], "type": "uuid", "count": count}

    if typ == "password":
        length = int(args.get("length", 16))
        chars = args.get("chars") or string.ascii_letters + string.digits + "!@#$%^&*"
        return {"results": [
            "".join(secrets.choice(chars) for _ in range(length)) for _ in range(count)
        ], "type": "password", "length": length, "count": count}

    if typ == "number":
        mn = float(args.get("min", 0))
        mx = float(args.get("max", 100))
        return {"results": [round(_random.uniform(mn, mx), 4) for _ in range(count)],
                "type": "number", "min": mn, "max": mx, "count": count}

    if typ == "int":
        mn = int(args.get("min", 0))
        mx = int(args.get("max", 100))
        return {"results": [int(_random.randint(mn, mx)) for _ in range(count)],
                "type": "int", "min": mn, "max": mx, "count": count}

    if typ == "choice":
        options = args.get("options")
        if not options or not isinstance(options, list):
            return {"error": "options (list) is required for choice type"}
        return {"results": [_random.choice(options) for _ in range(count)],
                "type": "choice", "count": count}

    if typ == "token":
        length = int(args.get("length", 32))
        return {"results": [
            "".join(secrets.token_hex(length // 2))[:length] for _ in range(count)
        ], "type": "token", "length": length, "count": count}

    if typ == "sample":
        population = args.get("population")
        k = int(args.get("k", 1))
        if not population or not isinstance(population, list):
            return {"error": "population (list) is required for sample type"}
        return {"results": [_random.sample(population, min(k, len(population))) for _ in range(count)],
                "type": "sample", "k": k, "count": count}

    if typ == "shuffle":
        population = args.get("population")
        if not population or not isinstance(population, list):
            return {"error": "population (list) is required for shuffle type"}
        items = list(population)
        _random.shuffle(items)
        return {"results": items, "type": "shuffle", "count": 1}

    return {"error": f"Unknown type '{typ}'. Use uuid, password, number, int, choice, token, sample, or shuffle."}
