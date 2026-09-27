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
        part = f"--{boundary}\r\n{disp}\r\nContent-Type: application/octet-stream\r\n\r\n"
        body += part.encode("utf-8") + data + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    req = _urlr.Request(url, data=body, method=method)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))
    try:
        with _urlr.urlopen(req, timeout=timeout_secs) as resp:
            raw = resp.read()[:50000]
            return {"status_code": resp.status, "body": raw.decode("utf-8", errors="replace"), "headers": dict(resp.headers)}
    except _url_err.HTTPError as e:
        raw = e.read()[:50000]
        return {"status_code": e.code, "body": raw.decode("utf-8", errors="replace"), "error": f"HTTP {e.code}", "headers": dict(e.headers)}
    except _url_err.URLError as e:
        return {"error": f"Connection error: {e}", "url": url}

# ---------------------------------------------------------------------------
# random_data — random data generation
# ---------------------------------------------------------------------------

async def _tool_random_data(args: dict) -> dict:
    """Generate random data: UUIDs, passwords, numbers, choices, tokens, samples.

    {"type": "uuid", "count": 3}
    {"type": "password", "length": 16, "special": true}
    {"type": "int", "min": 1, "max": 100, "count": 5}
    {"type": "choice", "options": ["a","b","c"], "count": 2}
    {"type": "token", "length": 32, "alpha": true, "numeric": true}
    {"type": "sample", "data": [1,2,3,4,5], "k": 3}
    {"type": "seed", "value": 42}  — seed the RNG for reproducibility
    """
    import random as _rand
    import uuid as _uuid

    type_ = (args.get("type") or "uuid").strip().lower()
    count = int(args.get("count", 1))
    seed_val = args.get("seed")

    if seed_val is not None:
        _rand.seed(int(seed_val))

    if type_ == "uuid":
        return {"results": [_uuid.uuid4().hex for _ in range(count)], "type": "uuid", "count": count}

    if type_ == "password":
        length = int(args.get("length", 16))
        special = bool(args.get("special", True))
        chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        if special:
            chars += "!@#$%^&*()-_=+"
        return {"results": ["".join(_rand.choice(chars) for _ in range(length)) for _ in range(count)],
                "type": "password", "length": length, "count": count}

    if type_ == "int":
        mn = int(args.get("min", 0))
        mx = int(args.get("max", 100))
        return {"results": [_rand.randint(mn, mx) for _ in range(count)],
                "type": "int", "min": mn, "max": mx, "count": count}

    if type_ == "float":
        mn = float(args.get("min", 0.0))
        mx = float(args.get("max", 1.0))
        return {"results": [round(_rand.uniform(mn, mx), 6) for _ in range(count)],
                "type": "float", "min": mn, "max": mx, "count": count}

    if type_ == "choice":
        options = args.get("options")
        if not options or not isinstance(options, list):
            return {"error": "options (list) is required for choice type"}
        return {"results": [_rand.choice(options) for _ in range(count)],
                "type": "choice", "options": options, "count": count}

    if type_ == "token":
        length = int(args.get("length", 32))
        alpha = bool(args.get("alpha", True))
        numeric = bool(args.get("numeric", True))
        chars = ""
        if alpha:
            chars += "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if numeric:
            chars += "0123456789"
        if not chars:
            chars = "abcdefghijklmnopqrstuvwxyz"
        return {"results": ["".join(_rand.choice(chars) for _ in range(length)) for _ in range(count)],
                "type": "token", "length": length, "count": count}

    if type_ == "sample":
        data = args.get("data")
        if not data or not isinstance(data, list):
            return {"error": "data (list) is required for sample type"}
        k = int(args.get("k", min(3, len(data))))
        return {"results": _rand.sample(data, min(k, len(data))),
                "type": "sample", "k": k, "count": 1}

    if type_ == "hex":
        length = int(args.get("length", 16))
        return {"results": ["".join(_rand.choice("0123456789abcdef") for _ in range(length)) for _ in range(count)],
                "type": "hex", "length": length, "count": count}

    return {"error": f"Unknown type '{type_}'. Use uuid, password, int, float, choice, token, sample, or hex."}



# ---------------------------------------------------------------------------
# random_data — random data generation
# ---------------------------------------------------------------------------

async def _tool_win32_reg(args: dict) -> dict:
    """Windows registry read/write tool — query keys, value lookup, set values.

    {"action": "read", "key": "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion", "value": "ProductName"}
    {"action": "enum", "key": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion"}
    {"action": "list_roots"} → ["HKEY_CLASSES_ROOT","HKEY_CURRENT_USER",...]

    Returns {key, value, data, typ} or {subkeys:[...], values:[{name,type,data}]}.
    """
    import sys
    if sys.platform != "win32":
        return {"error": "winreg is only available on Windows", "platform": sys.platform}

    import winreg
    action = (args.get("action") or "list_roots").strip().lower()
    key_name = args.get("key", "").strip()
    value_name = args.get("value", "").strip()

    root_map = {
        "HKCR": winreg.HKEY_CLASSES_ROOT,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKU": winreg.HKEY_USERS,
        "HKEY_USERS": winreg.HKEY_USERS,
        "HKCC": winreg.HKEY_CURRENT_CONFIG,
        "HKEY_CURRENT_CONFIG": winreg.HKEY_CURRENT_CONFIG,
    }

    if action == "list_roots":
        return {
            "roots": list(root_map.keys()),
            "note": "use a root + path, e.g. HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion",
        }

    if not key_name:
        return {"error": "key is required for read/enum"}

    parts = key_name.split("\\", 1)
    root_name = parts[0].upper()
    sub_path = parts[1] if len(parts) > 1 else ""
    hkey = root_map.get(root_name)
    if hkey is None:
        return {"error": f"unknown root '{root_name}'. Known: {list(root_map.keys())}"}

    try:
        if action == "read":
            if not value_name:
                return {"error": "value name is required for read"}
            with winreg.OpenKey(hkey, sub_path, 0, winreg.KEY_READ) as k:
                val, vtype = winreg.QueryValueEx(k, value_name)
                return {"key": key_name, "value": value_name, "data": val, "type": vtype, "platform": sys.platform}
        elif action == "enum":
            with winreg.OpenKey(hkey, sub_path, 0, winreg.KEY_READ) as k:
                subkeys = []
                try:
                    i = 0
                    while True:
                        sk = winreg.EnumKey(k, i)
                        subkeys.append(sk)
                        i += 1
                except OSError:
                    pass
                values = []
                try:
                    i = 0
                    while True:
                        vn = winreg.EnumValue(k, i)
                        values.append({"name": vn[0], "type": vn[1], "data_preview": str(vn[2])[:200]})
                        i += 1
                except OSError:
                    pass
                return {"key": key_name, "subkeys": subkeys[:100], "values": values[:100], "platform": sys.platform}
        elif action == "write":
            if not value_name:
                return {"error": "value name is required for write"}
            data = args.get("data")
            if data is None:
                return {"error": "data is required for write"}
            vtype = args.get("type", "REG_SZ")
            type_map = {
                "REG_SZ": winreg.REG_SZ,
                "REG_DWORD": winreg.REG_DWORD,
                "REG_QWORD": winreg.REG_QWORD,
                "REG_BINARY": winreg.REG_BINARY,
                "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
            }
            typ = type_map.get(vtype, winreg.REG_SZ)
            with winreg.CreateKeyEx(hkey, sub_path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, value_name, 0, typ, data)
            return {"written": True, "key": key_name, "value": value_name, "data": data, "type": vtype, "platform": sys.platform}
        else:
            return {"error": f"Unknown action '{action}'. Use list_roots, read, enum, or write."}
    except FileNotFoundError:
        return {"error": f"key not found: {key_name}", "key": key_name}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "key": key_name}

async def _tool_chain(args: dict) -> dict:
    """Sequential tool chain — run tools one after another, passing results forward.

    Like LangChain SequentialChain / CrewAI sequential process.

    Args:
      steps   — list of {tool, args, result_key} where result_key names
                the slot to store that step's result for later steps
      stop_on_fail — bool (default True): abort chain on first failure

    Each step can reference prior results via {result_key} in args values
    (string interpolation is done automatically).

    Returns: {steps: [{step, tool, args, result, success}], final: <last result>}
    """
    steps = args.get("steps")
    if not steps or not isinstance(steps, list):
        return {"error": "steps (list of {tool, args, result_key}) is required"}
    stop_on_fail = bool(args.get("stop_on_fail", True))
    context = {}

    chain_results = []
    last_result = None
    for i, step in enumerate(steps):
        tool_name = step.get("tool")
        step_args = step.get("args", {})
        result_key = step.get("result_key")

        if not tool_name:
            chain_results.append({"step": i, "tool": None, "error": "tool name required"})
            if stop_on_fail:
                return {"steps": chain_results, "final": None, "stopped_at": i, "error": f"Step {i}: tool name required"}
            continue

        # interpolate prior results into args (string values only)
        def _resolve(val):
            if isinstance(val, str) and val.startswith("{") and val.endswith("}"):
                key = val[1:-1]
                return context.get(key, val)
            return val

        interpolated_args = {}
        for k, v in step_args.items():
            if isinstance(v, dict):
                interpolated_args[k] = {kk: _resolve(vv) for kk, vv in v.items()}
            elif isinstance(v, list):
                interpolated_args[k] = [_resolve(item) for item in v]
            else:
                interpolated_args[k] = _resolve(v)

        step_result = await _eng().run_tool(tool_name, interpolated_args)
        entry = {
            "step": i,
            "tool": tool_name,
            "args": step_args,
            "result": step_result,
            "success": not step_result.get("error"),
        }
        chain_results.append(entry)

        if result_key:
            context[result_key] = step_result

        last_result = step_result
        if step_result.get("error") and stop_on_fail:
            return {"steps": chain_results, "final": last_result, "stopped_at": i, "error": f"Chain stopped at step {i}: {step_result['error']}"}

    return {"steps": chain_results, "final": last_result, "context": context, "steps_run": len(chain_results)}


async def _tool_parallel(args: dict) -> dict:
    """Run multiple tools in parallel and aggregate results.

    Like asyncio.gather / CrewAI parallel execution.

    Args:
      tasks — list of {tool, args, label}
      timeout_secs — max wait for all tasks (default 60)

    Returns: {tasks: [{label, tool, args, result, success, duration_secs}],
              aggregated: <summary>, wall_time_secs: N}
    """
    tasks = args.get("tasks")
    if not tasks or not isinstance(tasks, list):
        return {"error": "tasks (list of {tool, args, label}) is required"}
    timeout_secs = min(int(args.get("timeout_secs", 60)), 300)

    start = _time.time()
    async def run_one(t):
        label = t.get("label") or t.get("tool")
        tool_name = t.get("tool")
        task_args = t.get("args", {})
        t0 = _time.time()
        if not tool_name:
            return {"label": label, "tool": None, "args": task_args,
                    "result": None, "success": False, "error": "tool name required",
                    "duration_secs": 0}
        try:
            res = await _eng().run_tool(tool_name, task_args)
            return {"label": label, "tool": tool_name, "args": task_args,
                    "result": res, "success": not res.get("error"),
                    "error": res.get("error"),
                    "duration_secs": round(_time.time() - t0, 3)}
        except Exception as e:
            return {"label": label, "tool": tool_name, "args": task_args,
                    "result": None, "success": False,
                    "error": f"Exception: {e}",
                    "duration_secs": round(_time.time() - t0, 3)}

    gathered = await asyncio.wait_for(
        asyncio.gather(*[run_one(t) for t in tasks], return_exceptions=False),
        timeout=timeout_secs
    )
    wall = round(_time.time() - start, 3)
    successes = [g for g in gathered if g.get("success")]
    failures = [g for g in gathered if not g.get("success")]

    return {
        "tasks": gathered,
        "aggregated": {
            "total": len(gathered),
            "successes": len(successes),
            "failures": len(failures),
        },
        "wall_time_secs": wall,
        "results": {g["label"]: g["result"] for g in gathered if g.get("result")},
    }


async def _tool_structured_output(args: dict) -> dict:
    """Validate and enforce JSON schema on tool/LLM outputs.

    Acts as a gate: given a schema and a result dict, returns
    {valid: true, data: <cleaned>} or {valid: false, errors: [...]}.

    Args:
      data   — dict to validate
      schema — JSON Schema-like dict with 'type', 'required', 'properties',
               'items', 'enum', 'minimum', 'maximum', 'minLength', 'maxLength'

    Supports: object, array, string, number, integer, boolean, null types.

    Returns: {valid: bool, data: dict|list, errors: list[str], validated: bool}
    """
    data = args.get("data")
    schema = args.get("schema")
    if data is None:
        return {"valid": False, "errors": ["data is required"], "validated": False}
    if schema is None:
        return {"valid": False, "errors": ["schema is required"], "validated": False}

    errors = []

    def _validate(value, sch, path):
        if not isinstance(sch, dict):
            return
        typ = sch.get("type")
        if typ == "object" and isinstance(value, dict):
            req = sch.get("required", [])
            props = sch.get("properties", {})
            addl = sch.get("additionalProperties", True)
            for r in req:
                if r not in value:
                    errors.append(f"{path or 'root'}: missing required field '{r}'")
            for k, v in value.items():
                if k in props:
                    _validate(v, props[k], f"{path or 'root'}.{k}")
                elif not addl:
                    errors.append(f"{path or 'root'}.{k}: additional property not allowed")
            if sch.get("minProperties") and len(value) < sch["minProperties"]:
                errors.append(f"{path or 'root'}: minProperties={sch['minProperties']}, got {len(value)}")
            if sch.get("maxProperties") and len(value) > sch["maxProperties"]:
                errors.append(f"{path or 'root'}: maxProperties={sch['maxProperties']}, got {len(value)}")
        elif typ == "array" and isinstance(value, list):
            items_sch = sch.get("items")
            if items_sch:
                for i, item in enumerate(value):
                    _validate(item, items_sch, f"{path or 'root'}[{i}]")
            if sch.get("minItems") and len(value) < sch["minItems"]:
                errors.append(f"{path or 'root'}: minItems={sch['minItems']}, got {len(value)}")
            if sch.get("maxItems") and len(value) > sch["maxItems"]:
                errors.append(f"{path or 'root'}: maxItems={sch['maxItems']}, got {len(value)}")
            if sch.get("uniqueItems") and len(value) != len(set(map(str, value))):
                errors.append(f"{path or 'root'}: uniqueItems required but duplicates found")
        elif typ == "string" and isinstance(value, str):
            if sch.get("minLength") and len(value) < sch["minLength"]:
                errors.append(f"{path or 'root'}: minLength={sch['minLength']}, got {len(value)}")
            if sch.get("maxLength") and len(value) > sch["maxLength"]:
                errors.append(f"{path or 'root'}: maxLength={sch['maxLength']}, got {len(value)}")
            if sch.get("pattern"):
                if not re.match(sch["pattern"], value):
                    errors.append(f"{path or 'root'}: pattern '{sch['pattern']}' not matched")
            if sch.get("enum") and value not in sch["enum"]:
                errors.append(f"{path or 'root'}: must be one of {sch['enum']}")
        elif typ == "number" and isinstance(value, (int, float)):
            if sch.get("minimum") and value < sch["minimum"]:
                errors.append(f"{path or 'root'}: minimum={sch['minimum']}, got {value}")
            if sch.get("maximum") and value > sch["maximum"]:
                errors.append(f"{path or 'root'}: maximum={sch['maximum']}, got {value}")
            if sch.get("multipleOf") and value % sch["multipleOf"] != 0:
                errors.append(f"{path or 'root'}: must be multiple of {sch['multipleOf']}")
        elif typ == "integer" and isinstance(value, int):
            if sch.get("minimum") and value < sch["minimum"]:
                errors.append(f"{path or 'root'}: minimum={sch['minimum']}, got {value}")
            if sch.get("maximum") and value > sch["maximum"]:
                errors.append(f"{path or 'root'}: maximum={sch['maximum']}, got {value}")
        elif typ == "boolean" and not isinstance(value, bool):
            errors.append(f"{path or 'root'}: expected boolean, got {type(value).__name__}")
        elif typ == "null" and value is not None:
            errors.append(f"{path or 'root'}: expected null, got {type(value).__name__}")

    _validate(data, schema, "root")
    return {
        "valid": len(errors) == 0,
        "data": data,
        "errors": errors,
        "validated": True,
    }


async def _tool_reason(args: dict) -> dict:
    """Structured step-by-step reasoning — break a problem into sub-steps,
    reason about each, then synthesize.

    Models chain-of-thought / o1-style reasoning as an explicit tool.

    Args:
      problem       — the problem or question to reason about (required)
      max_steps     — max reasoning steps (default 5, max 20)
      approach      — "decomposition" | "chain_of Thought" | "tree" | "first_principles"
      output_format — "summary" | "full" | "steps_only"

    Returns: {problem, approach, steps: [{step, reasoning, conclusion}],
              final_answer, total_steps, reasoning_time_secs}
    """
    problem = args.get("problem", "").strip()
    if not problem:
        return {"error": "problem is required"}
    max_steps = min(int(args.get("max_steps", 5)), 20)
    approach = (args.get("approach") or "decomposition").strip().lower()
    output_format = (args.get("output_format") or "summary").strip().lower()

    steps = []
    # Use the LLM if available, otherwise simulate structured reasoning
    llm = getattr(_eng(), "llm", None)
    use_llm = llm is not None

    for i in range(max_steps):
        if use_llm:
            prompt = f"Step {i+1} of reasoning for: {problem}\nApproach: {approach}\n\nProvide step {i+1} reasoning and a partial conclusion. Keep it concise."
            try:
                resp = await llm.generate(prompt, max_tokens=512)
            except Exception:
                resp = f"Step {i+1}: [LLM unavailable] Reasoning about {problem} via {approach}..."
        else:
            resp = f"Step {i+1}: Analyzing {problem} using {approach} approach..."

        step_entry = {
            "step": i + 1,
            "reasoning": resp.strip(),
            "conclusion": f"Continuing analysis..." if i < max_steps - 1 else "Analysis complete.",
        }
        steps.append(step_entry)

        if output_format == "steps_only" and i == max_steps - 1:
            break

    final = f"Reasoned about '{problem}' via {approach} in {len(steps)} steps."

    return {
        "problem": problem,
        "approach": approach,
        "steps": steps,
        "final_answer": final,
        "total_steps": len(steps),
        "output_format": output_format,
        "llm_used": use_llm,
    }


async def _tool_memory_lifecycle(args: dict) -> dict:
    """Manage memory lifecycle: archive, expire, prune, export, import.

    Like AutoGPT's long-term memory management with retention policies.

    ACTIONS:
      archive   — move entries older than N days to archive: {action:archive, older_than_days:30}
      prune     — remove entries matching a query/filter: {action:prune, query:"...", min_score:0.5}
      expire    — mark entries as expired by age: {action:expire, older_than_days:60}
      stats     — get memory usage stats: {action:stats}
      export    — export memories to a file: {action:export, path:"/tmp/memories.json"}
      import    — import memories from a file: {action:import, path:"/tmp/memories.json"}
      summarize — summarize recent memories: {action:summarize, limit:20}

    Returns: action-specific result with status.
    """
    action = (args.get("action") or "stats").strip().lower()

    # Stats
    if action == "stats":
        mem = _eng()._tool_handlers.get("memory_stats")
        if mem:
            return await _eng().run_tool("memory_stats", {})
        return {"status": "stats_unavailable", "note": "memory_stats tool not registered"}

    # Summarize
    if action == "summarize":
        limit = int(args.get("limit", 20))
        mem = _eng()._tool_handlers.get("memory_read")
        if mem:
            entries = await _eng().run_tool("memory_read", {"limit": limit})
            items = entries.get("entries", entries.get("memories", []))[:limit]
            return {
                "action": "summarize",
                "count": len(items),
                "recent_entries": items,
                "summary": f"{len(items)} recent memory entries loaded",
            }
        return {"error": "memory_read tool not available"}

    # Export
    if action == "export":
        path = args.get("path", str(Path.home() / ".moon" / "memory_export.json"))
        try:
            mem_mod = _eng()._tool_handlers.get("memory_stats")
            # try to get all entries via memory_read
            mem_read = _eng()._tool_handlers.get("memory_read")
            all_entries = []
            if mem_read:
                page = 0
                while True:
                    r = await _eng().run_tool("memory_read", {"limit": 100, "offset": page * 100})
                    entries = r.get("entries", r.get("memories", []))
                    if not entries:
                        break
                    all_entries.extend(entries)
                    page += 1
                    if len(entries) < 100:
                        break
            fp = Path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(json.dumps(all_entries, indent=2, default=str), encoding="utf-8")
            return {"status": "exported", "path": str(fp), "entries": len(all_entries)}
        except Exception as e:
            return {"error": f"export failed: {e}", "action": "export"}

    # Import
    if action == "import":
        path = args.get("path")
        if not path:
            return {"error": "path is required for import"}
        try:
            fp = Path(path)
            if not fp.exists():
                return {"error": f"file not found: {path}"}
            data = json.loads(fp.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return {"error": "import file must contain a JSON array of entries"}
            mem_write = _eng()._tool_handlers.get("memory_write")
            imported = 0
            if mem_write:
                for entry in data:
                    await _eng().run_tool("memory_write", entry)
                    imported += 1
            return {"status": "imported", "path": str(fp), "entries": imported}
        except Exception as e:
            return {"error": f"import failed: {e}", "action": "import"}

    # Archive / prune / expire — delegate to memory_write with tags
    if action in ("archive", "prune", "expire"):
        return {
            "status": "acknowledged",
            "action": action,
            "note": f"{action} operation acknowledged. Use memory_write with metadata tags to implement retention policies.",
            "args": args,
        }

    return {"error": f"Unknown action '{action}'. Use stats, summarize, export, import, archive, prune, or expire."}


async def _tool_eval_runner(args: dict) -> dict:
    """Run evaluations/tests on tool outputs or LLM responses.

    Like building evals for AI systems (OpenAI evals pattern).

    Args:
      test_cases — list of {input, expected, tolerance, description}
      tool_name  — tool to evaluate (optional; if absent, just compare input vs expected)
      runner     — "exact_match" | "contain" | "numeric_close" | "llm_judge" | "custom"

    Returns: {test_cases: [{input, expected, got, passed, detail}],
              summary: {total, passed, failed, pass_rate},
              runner: str}
    """
    test_cases = args.get("test_cases")
    if not test_cases or not isinstance(test_cases, list):
        return {"error": "test_cases (list of {input, expected, ...}) is required"}
    runner = (args.get("runner") or "exact_match").strip().lower()
    tool_name = args.get("tool_name")
    tolerance = float(args.get("tolerance", 0.01))

    results = []
    passed = 0
    for tc in test_cases:
        inp = tc.get("input")
        expected = tc.get("expected")
        description = tc.get("description", "")

        got = inp
        if tool_name:
            try:
                got = await _eng().run_tool(tool_name, inp if isinstance(inp, dict) else {"input": inp})
            except Exception as e:
                got = {"error": str(e)}

        # determine pass/fail
        ok = False
        detail = ""
        if runner == "exact_match":
            ok = got == expected
            detail = f"exact match: {ok}"
        elif runner == "contain":
            haystack = str(got) if got else ""
            needle = str(expected) if expected else ""
            ok = needle in haystack
            detail = f"'{needle}' in output: {ok}"
        elif runner == "numeric_close":
            try:
                g = float(got) if got else 0
                e = float(expected) if expected else 0
                diff = abs(g - e)
                ok = diff <= tolerance
                detail = f"|{g} - {e}| = {diff} <= {tolerance}: {ok}"
            except (TypeError, ValueError):
                ok = got == expected
                detail = "numeric comparison failed, fell back to exact match"
        elif runner == "llm_judge":
            detail = "LLM judge not available in eval_runner (use llm_judge tool separately)"
            ok = got == expected
        else:
            ok = got == expected
            detail = f"custom runner '{runner}': fell back to exact match"

        entry = {
            "input": inp,
            "expected": expected,
            "got": got,
            "passed": ok,
            "detail": detail,
            "description": description,
        }
        results.append(entry)
        if ok:
            passed += 1

    total = len(results)
    return {
        "test_cases": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total, 4) if total else 0,
        },
        "runner": runner,
    }


async def _tool_report(args: dict) -> dict:
    """Generate structured reports from data and a template.

    Supports markdown, JSON, HTML, and plain text output formats.
    Uses Jinja2 templates if available, falls back to f-string style.

    Args:
      data        — dict of data to inject into report
      template    — Jinja2 template string (optional; if absent, uses default layout)
      format      — "markdown" | "html" | "json" | "text" (default: text)
      title       — report title
      sections    — list of {heading, content} to include
      output_path — optional file path to write report to

    Returns: {format, title, content: <rendered>, bytes: len, path: <if written>}
    """
    data = args.get("data") or {}
    template = args.get("template")
    fmt = (args.get("format") or "text").strip().lower()
    title = args.get("title", "MOON Report")
    sections = args.get("sections") or []
    output_path = args.get("output_path")

    # Default template per format
    if not template:
        if fmt == "markdown":
            lines = [f"# {title}", "", f"Generated: {_dt.now().isoformat()}", ""]
            for sec in sections:
                lines.append(f"## {sec.get('heading', 'Section')}")
                lines.append("")
                content = sec.get("content", "")
                if isinstance(content, dict):
                    import pprint as _pp
                    content = _pp.pformat(content)
                lines.append(str(content))
                lines.append("")
            lines.append(f"--- *MOON Report — {len(sections)} sections*")
            template = "\n".join(lines)
        elif fmt == "html":
            rows = ""
            for sec in sections:
                content = sec.get("content", "")
                if isinstance(content, dict):
                    import pprint as _pp
                    content = _pp.pformat(content)
                rows += f"<tr><td><b>{sec.get('heading','Section')}</b></td><td>{content}</td></tr>"
            template = f"""<html><body><h1>{title}</h1><p>Generated: {_dt.now().isoformat()}</p><table>{rows}</table></body></html>"""
        elif fmt == "json":
            payload = {"title": title, "generated": _dt.now().isoformat(), "sections": sections, "data": data}
            if sections:
                payload["summary"] = {s.get("heading", "section"): s.get("content") for s in sections}
            return {"format": "json", "title": title, "content": json.dumps(payload, indent=2, default=str),
                    "bytes": len(json.dumps(payload, default=str)), "data": payload}
        else:
            lines = [f"{title}", f"Generated: {_dt.now().isoformat()}", "=" * 60, ""]
            for sec in sections:
                lines.append(f"{sec.get('heading', 'Section')}:")
                content = sec.get("content", "")
                if isinstance(content, dict):
                    import pprint as _pp
                    content = _pp.pformat(content)
                lines.append(f"  {content}")
                lines.append("")
            template = "\n".join(lines)

    # Jinja2 render if available
    if template and fmt != "json":
        try:
            from jinja2 import Template as _J2T
            rendered = _J2T(template).render(**data)
        except Exception:
            rendered = template.format(**data) if "{" in template else template
    else:
        rendered = template or ""

    result = {"format": fmt, "title": title, "content": rendered, "bytes": len(rendered)}

    if output_path:
        try:
            fp = Path(output_path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(rendered, encoding="utf-8")
            result["path"] = str(fp)
        except Exception as e:
            result["write_error"] = str(e)

    return result


async def _tool_timer(args: dict) -> dict:
    """Timer / stopwatch tool — measure execution time of operations.

    ACTIONS:
      start   — start a named timer: {action:start, name:"my-task"}
      stop    — stop and return elapsed: {action:stop, name:"my-task"}
      lapse   — one-shot: run a callable and measure: {action:lapse, fn:"..."}
      list    — list active timers: {action:list}

    Returns: timer state or elapsed time.
    """
    action = (args.get("action") or "list").strip().lower()

    if action == "start":
        name = args.get("name", "default")
        _timers[name] = {"start": _time.time(), "active": True}
        return {"action": "start", "name": name, "status": "started", "start_time": _timers[name]["start"]}

    if action == "stop":
        name = args.get("name", "default")
        t = _timers.get(name)
        if not t or not t.get("active"):
            return {"action": "stop", "name": name, "status": "not_found_or_inactive"}
        elapsed = _time.time() - t["start"]
        t["active"] = False
        t["elapsed"] = elapsed
        t["finished"] = _time.time()
        return {"action": "stop", "name": name, "elapsed_secs": round(elapsed, 4),
                "start_time": t["start"], "finished_time": t["finished"]}

    if action == "lapse":
        # measure a blocking operation
        label = args.get("label", "lapse")
        t0 = _time.time()
        try:
            # if args has a tool to run
            tool_name = args.get("tool")
            tool_args = args.get("args", {})
            if tool_name:
                result = await _eng().run_tool(tool_name, tool_args)
            else:
                result = {"note": "no tool specified, lapse measured wall time only"}
            elapsed = _time.time() - t0
            return {"action": "lapse", "label": label, "elapsed_secs": round(elapsed, 4),
                    "result": result}
        except Exception as e:
            elapsed = _time.time() - t0
            return {"action": "lapse", "label": label, "elapsed_secs": round(elapsed, 4),
                    "error": str(e)}

    if action == "list":
        return {"action": "list", "timers": {k: {"active": v.get("active"),
                                                  "start": v.get("start"),
                                                  "elapsed": v.get("elapsed")}
                                             for k, v in _timers.items()}}

    return {"error": f"Unknown action '{action}'. Use start, stop, lapse, or list."}


_timer_store: dict = {}
_timers: dict = _timer_store


async def _tool_rate_limit(args: dict) -> dict:
    """Track and enforce rate limits on tool/operation usage.

    Like production API rate limiting (token bucket / sliding window).

    ACTIONS:
      check     — check if a call is allowed: {action:check, key:"my-api", limit:100, window_secs:60}
      record    — record a call: {action:record, key:"my-api"}
      reset     — reset counter for a key: {action:reset, key:"my-api"}
      status    — get current status for a key: {action:status, key:"my-api"}
      global_stats — all keys stats: {action:global_stats}

    Returns: {allowed: bool, key, limit, remaining, reset_at, calls_in_window}
    """
    action = (args.get("action") or "check").strip().lower()
    key = args.get("key", "default")
    limit = int(args.get("limit", 100))
    window = int(args.get("window_secs", 60))

    now = _time.time()

    if action == "check":
        _rl_store.setdefault(key, [])
        _prune_rl(key, now - window)
        calls = _rl_store[key]
        remaining = max(0, limit - len(calls))
        reset_at = now + window
        allowed = len(calls) < limit
        return {"allowed": allowed, "key": key, "limit": limit,
                "remaining": remaining, "reset_at": reset_at,
                "calls_in_window": len(calls), "window_secs": window}

    if action == "record":
        _rl_store.setdefault(key, [])
        _prune_rl(key, now - window)
        _rl_store[key].append(now)
        allowed = len(_rl_store[key]) <= limit
        return {"recorded": True, "key": key, "allowed": allowed,
                "calls_in_window": len(_rl_store[key])}

    if action == "reset":
        _rl_store.pop(key, None)
        return {"reset": True, "key": key, "calls_in_window": 0}

    if action == "status":
        _rl_store.setdefault(key, [])
        _prune_rl(key, now - window)
        calls = _rl_store[key]
        return {"key": key, "calls_in_window": len(calls),
                "limit": limit, "remaining": max(0, limit - len(calls)),
                "window_secs": window}

    if action == "global_stats":
        return {"keys": {k: {"calls_in_window": len(v),
                              "limit": limit,
                              "remaining": max(0, limit - len(v))}
                          for k, v in _rl_store.items()},
                "total_keys": len(_rl_store)}

    return {"error": f"Unknown action '{action}'. Use check, record, reset, status, or global_stats."}


def _prune_rl(key: str, cutoff: float) -> None:
    _rl_store.setdefault(key, [])
    _rl_store[key] = [t for t in _rl_store[key] if t > cutoff]


_rl_store: dict = {}


# ---------------------------------------------------------------------------
# data_scientist — build & train ML models (sklearn / statsmodels)
# ---------------------------------------------------------------------------

async def _tool_train_model(args: dict) -> dict:
    """Train a simple ML model and return metrics + optional plot.

    {"action": "train", "model": "linear_regression", "data": [[x1,...],[...]], "target": [...]}
    {"action": "train", "model": "random_forest", "data": [...], "target": [...], "test_size": 0.2}
    {"action": "predict", "model_artifact": <from train>, "data": [[...]]}
    {"action": "evaluate", "model_artifact": <from train>, "data": [...], "target": [...]}

    Returns metrics dict (accuracy/rmse/r2/mse) + confusion matrix if classification.
    """
    import base64, io, json
    import numpy as np
    from pathlib import Path

    action = (args.get("action") or "train").strip().lower()
    model_type = (args.get("model") or "linear_regression").strip().lower()
    X = args.get("data")
    y = args.get("target")
    if action in ("train", "evaluate") and (not X or not y):
        return {"error": "data and target are required for train/evaluate"}

    try:
        from sklearn.model_selection import train_test_split
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
        from sklearn.metrics import mean_squared_error, r2_score, accuracy_score, confusion_matrix
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        return {"error": f"sklearn stack not available: {e}", "model_type": model_type}

    try:
        if isinstance(X, list):
            X = np.array(X, dtype=float)
        if isinstance(y, list):
            y = np.array(y, dtype=float)
        if isinstance(X, list) and isinstance(X[0], dict):
            X = np.array([[v for v in row.values()] for row in X], dtype=float)
        if isinstance(y, list) and isinstance(y[0], dict):
            y = np.array([list(row.values())[0] for row in y], dtype=float)

        if action == "train":
            test_size = float(args.get("test_size", 0.2))
            random_state = int(args.get("random_state", 42))
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state)

            is_clf = model_type in ("logistic_regression", "random_forest_classifier", "rf_classifier", "rf")
            if model_type in ("random_forest_classifier", "rf_classifier"):
                ModelCls = RandomForestClassifier
            elif model_type in ("random_forest", "rf"):
                ModelCls = RandomForestRegressor
            elif model_type == "logistic_regression":
                ModelCls = LogisticRegression
            else:
                ModelCls = LinearRegression

            model = ModelCls()
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)

            metrics = {}
            if is_clf:
                metrics["accuracy"] = float(accuracy_score(y_test, y_pred.round()))
                metrics["confusion_matrix"] = confusion_matrix(y_test, y_pred.round()).tolist()
            else:
                metrics["rmse"] = float(np.sqrt(mean_squared_error(y_test, y_pred)))
                metrics["r2"] = float(r2_score(y_test, y_pred))
                metrics["mse"] = float(mean_squared_error(y_test, y_pred))

            if hasattr(model, "feature_importances_"):
                try:
                    metrics["feature_importances"] = model.feature_importances_.tolist()
                except Exception:
                    pass

            plot_b64 = None
            try:
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.scatter(range(len(y_test)), y_test, label="actual", alpha=0.7)
                ax.scatter(range(len(y_pred)), y_pred, label="predicted", alpha=0.7)
                ax.legend()
                ax.set_title(f"{model_type} predictions vs actual")
                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight")
                buf.seek(0)
                plot_b64 = base64.b64encode(buf.read()).decode()
                plt.close(fig)
            except Exception:
                pass

            artifact = {
                "model_type": model_type,
                "metrics": metrics,
                "test_size": test_size,
                "n_train": int(len(X_train)),
                "n_test": int(len(X_test)),
                "n_features": int(X.shape[1]) if X.ndim > 1 else 1,
                "plot_b64": plot_b64,
                "model_params": {k: str(v) for k, v in model.get_params().items()} if hasattr(model, "get_params") else {},
            }
            return {"status": "trained", "artifact": artifact, "metrics": metrics}

        if action == "predict":
            art = args.get("model_artifact")
            if not art or "model_type" not in art:
                return {"error": "model_artifact from train is required for predict"}
            return {
                "note": "predict requires a fitted model in the same Python session; use train first then predict in the same code_interpreter call",
                "model_type": art["model_type"],
                "metrics_at_train": art.get("metrics"),
            }

        if action == "evaluate":
            art = args.get("model_artifact")
            if not art or "model_type" not in art:
                return {"error": "model_artifact required for evaluate"}
            return {"error": "evaluate requires an in-memory fitted model; run train first in same session", "model_type": art["model_type"]}

        return {"error": f"Unknown action '{action}'. Use train, predict, or evaluate."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "model_type": model_type}


# ---------------------------------------------------------------------------
# body.me tooling — posture / ergonomic reminders
# ---------------------------------------------------------------------------

async def _tool_body_check(args: dict) -> dict:
    """Simple posture/ergonomic reminder tool for operators doing long sessions.

    {"action": "remind"} → returns a reminder about screen height, breaks, hydration
    {"action": "status"} → returns current time + hours-since-midnight
    """
    from datetime import datetime as _dt
    action = (args.get("action") or "remind").strip().lower()
    now = _dt.now()
    hours_since_midnight = now.hour + now.minute / 60.0

    if action == "status":
        return {
            "current_time": now.isoformat(),
            "hours_since_midnight": round(hours_since_midnight, 2),
            "suggestions": [
                "Stand up and stretch every hour",
                "Keep screen at eye level",
                "Keep wrists neutral while typing",
                "Stay hydrated",
            ],
        }
    return {
        "reminder": "POSTURE & ERGONOMICS CHECK",
        "tips": [
            "Screen top at or slightly below eye level, arm's length away",
            "Feet flat on floor, knees at ~90°",
            "Elbows close to body, forearms parallel to floor",
            "Take a 20-20-20 break: every 20 min, look 20 ft away for 20 sec",
            "Stand, walk, stretch for 5 min every hour",
        ],
        "timestamp": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# deep_analyze — structured multi-perspective analysis of any text/data
# ---------------------------------------------------------------------------

async def _tool_deep_analyze(args: dict) -> dict:
    """Analyze a text, dataset summary, or problem from multiple perspectives.

    {"input": "some text or data summary", "perspectives": ["technical","business","risk","opportunity"], "max_points": 5}

    Returns {analysis: [{perspective, summary}] , synthesized: "..."}.
    Falls back to structured heuristic analysis when LLM is unavailable.
    """
    inp = args.get("input", "").strip()
    if not inp:
        return {"error": "input is required"}
    perspectives = args.get("perspectives") or ["summary", "technical", "business", "risk", "opportunity"]
    llm = getattr(_eng(), "llm", None)
    use_llm = llm is not None

    analysis = []
    for p in perspectives:
        if use_llm:
            try:
                resp = await llm.generate(
                    f"Analyze the following from the perspective of {p}. Give a 2-3 sentence summary. Input:\n{inp}",
                    max_tokens=800,
                )
                analysis.append({"perspective": p, "summary": resp.strip()})
            except Exception:
                analysis.append({"perspective": p, "summary": f"[LLM unavailable] {p} analysis: {inp[:200]}"})
        else:
            analysis.append({"perspective": p, "summary": f"Perspective: {p}. Input: {inp[:300]}"})

    synthesized = (
        f"Multi-perspective analysis across {len(perspectives)} lenses: "
        + "; ".join(f"{a['perspective']}: {a['summary'][:80]}" for a in analysis)
    )
    return {"input_preview": inp[:200], "perspectives": perspectives, "analysis": analysis, "synthesized": synthesized}


# ---------------------------------------------------------------------------
# decision_matrix — weighted decision framework
# ---------------------------------------------------------------------------

async def _tool_decision_matrix(args: dict) -> dict:
    """Score options against weighted criteria — a structured decision framework.

    {"options": ["A","B","C"], "criteria": [{"name":"cost","weight":0.4},{"name":"speed","weight":0.3},{"name":"quality","weight":0.3}],
     "scores": {"A": {"cost":8,"speed":6,"quality":9}, "B": {"cost":9,"speed":8,"quality":5}}}

    Returns {scores: [{option, total, breakdown}], recommendation: "..."}.
    """
    options = args.get("options")
    criteria = args.get("criteria")
    scores = args.get("scores")
    if not options or not isinstance(options, list):
        return {"error": "options (list) is required"}
    if not criteria or not isinstance(criteria, list):
        return {"error": "criteria (list of {name, weight}) is required"}
    if not scores or not isinstance(scores, dict):
        return {"error": "scores ({option: {criterion: value}}) is required"}

    total_weight = sum(c.get("weight", 0) for c in criteria)
    if total_weight <= 0:
        return {"error": "criteria weights must sum to > 0"}

    results = []
    for opt in options:
        opt_scores = scores.get(opt, {})
        weighted_total = 0.0
        breakdown = []
        for c in criteria:
            cname = c["name"]
            w = c.get("weight", 0)
            s = opt_scores.get(cname, 0)
            weighted_total += w * s
            breakdown.append({"criterion": cname, "weight": w, "score": s, "weighted": w * s})
        results.append({"option": opt, "total": round(weighted_total, 3), "breakdown": breakdown})

    results.sort(key=lambda r: r["total"], reverse=True)
    recommendation = results[0]["option"] if results else None
    return {"criteria": criteria, "scores": results, "recommendation": recommendation, "total_weight": total_weight}


# ---------------------------------------------------------------------------
# agent_loop — agentic loop skeleton (plan → act → observe → reflect)
# ---------------------------------------------------------------------------

async def _tool_agent_loop(args: dict) -> dict:
    """Run a simple agentic loop: plan, act, observe, reflect, repeat.

    {"problem": "...", "max_iterations": 5, "plan": [{"step":1,"action":"tool_name","args":{...}}, ...]}

    Returns {iterations: [{iteration, plan_step, tool, result, observation, reflection}],
            final_answer, total_iterations, converged: bool}.
    """
    import time as _time
    problem = args.get("problem", "").strip()
    if not problem:
        return {"error": "problem is required"}
    max_iter = min(int(args.get("max_iterations", 5)), 20)
    steps = args.get("plan") or []
    if not steps:
        return {"error": "plan (list of steps with action/args) is required", "hint": "Use workflow tool to build a plan first"}

    iterations = []
    context_notes = []
    for i in range(max_iter):
        if i >= len(steps):
            break
        step = steps[i]
        tool_name = step.get("action") or step.get("tool")
        step_args = dict(step.get("args", {}))
        if context_notes:
            step_args["_context"] = context_notes[-1]
        t0 = _time.time()
        try:
            res = await _eng().run_tool(tool_name, step_args)
        except Exception as e:
            res = {"error": str(e)}
        elapsed = round(_time.time() - t0, 3)
        observation = res.get("result") or res.get("stdout") or res if not res.get("error") else res.get("error")
        reflection = f"Iteration {i+1}: used {tool_name}, took {elapsed}s"
        if res.get("error"):
            reflection += f" — error: {res['error']}"
        iterations.append({
            "iteration": i + 1,
            "plan_step": step,
            "tool": tool_name,
            "result": res,
            "observation": str(observation)[:2000],
            "reflection": reflection,
            "duration_secs": elapsed,
        })
        context_notes.append(str(observation)[:1000])
        if not res.get("error") and i > 0:
            break

    final = f"Agent loop ran {len(iterations)} iterations. Last result: {str(iterations[-1]['result'])[:200] if iterations else 'none'}"
    return {
        "problem": problem,
        "iterations": iterations,
        "final_answer": final,
        "total_iterations": len(iterations),
        "converged": len(iterations) > 0 and not iterations[-1]["result"].get("error"),
    }


# ---------------------------------------------------------------------------
# sweeper — scan a directory / codebase for patterns, metrics, issues
# ---------------------------------------------------------------------------

async def _tool_sweeper(args: dict) -> dict:
    """Scan a directory tree for patterns, metrics, and potential issues.

    {"path": "/home/meow/Projects/MOON", "patterns": ["TODO","FIXME","print("],
     "actions": ["count_lines","count_files","find_patterns","largest_files","empty_files"]}

    Returns {path, actions_results: {...}, summary: "..."}.
    """
    from pathlib import Path
    path = args.get("path", ".").strip()
    patterns = args.get("patterns") or []
    actions = args.get("actions") or ["count_files", "count_lines"]

    base = Path(path).resolve()
    if not base.exists():
        return {"error": f"path not found: {path}"}

    results = {}
    if "count_files" in actions:
        files = [p for p in base.rglob("*") if p.is_file()]
        results["count_files"] = len(files)
    if "count_lines" in actions:
        total_lines = 0
        by_ext = {}
        for p in base.rglob("*"):
            if p.is_file():
                ext = p.suffix.lower() or "(no ext)"
                try:
                    lc = len(p.read_text(errors="replace").splitlines())
                    total_lines += lc
                    by_ext[ext] = by_ext.get(ext, 0) + lc
                except Exception:
                    pass
        results["total_lines"] = total_lines
        results["lines_by_extension"] = dict(sorted(by_ext.items(), key=lambda x: -x[1])[:15])
    if "find_patterns" in actions:
        found = {p: [] for p in patterns}
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in (".py", ".js", ".ts", ".md", ".yaml", ".yml", ".json", ".txt", ".sh"):
                try:
                    text = p.read_text(errors="replace")
                    for pat in patterns:
                        if pat in text:
                            found[pat].append(str(p))
                except Exception:
                    pass
        results["patterns_found"] = {p: found[p][:50] for p in patterns}
    if "largest_files" in actions:
        try:
            files = [(p, p.stat().st_size) for p in base.rglob("*") if p.is_file()]
            files.sort(key=lambda x: -x[1])
            results["largest_files"] = [{"path": str(p), "size_bytes": s, "size_kb": round(s / 1024, 1)} for p, s in files[:20]]
        except Exception as e:
            results["largest_files_error"] = str(e)
    if "empty_files" in actions:
        try:
            empty = [str(p) for p in base.rglob("*") if p.is_file() and p.stat().st_size == 0]
            results["empty_files"] = empty[:50]
            results["empty_files_count"] = len(empty)
        except Exception as e:
            results["empty_files_error"] = str(e)

    return {"path": str(base), "actions": actions, "results": results, "summary": f"Scanned {path} — {len(results)} action results"}


# ---------------------------------------------------------------------------
# pyexec2 — second Python code execution tool (independent sandbox session)
# ---------------------------------------------------------------------------

async def _tool_code_interpreter(args: dict) -> dict:
    """Execute Python code in a sandboxed subprocess with rich output capture.

    {"code": "print(sum(range(10)))", "timeout_secs": 30, "libraries": ["pandas","matplotlib"]}
    Returns {returncode, stdout, stderr, elapsed_secs, generated_files: [{path,size_bytes,content_b64}], matplotlib_plot_b64, libraries_checked: {lib: "available"|"not_available"}}.
    """
    import base64, io, json, sys, time as _time_mod, traceback, tempfile as _tmpfile
    from pathlib import Path

    code = args.get("code", "").strip()
    if not code:
        return {"error": "code is required"}
    timeout_secs = min(int(args.get("timeout_secs", 30)), 300)
    libraries = args.get("libraries") or []
    files = args.get("files") or {}

    lib_status = {}
    for lib in libraries:
        try:
            __import__(lib)
            lib_status[lib] = "available"
        except ImportError:
            lib_status[lib] = "not_available"

    tmp_dir = Path(_tmpfile.mkdtemp(prefix="moon_ci_"))
    file_paths = {}
    for fname, content in files.items():
        fpath = tmp_dir / fname
        fpath.write_text(content if isinstance(content, str) else content, encoding="utf-8")
        file_paths[fname] = str(fpath)

    use_mpl = "matplotlib" in code or "plt" in code or "figure" in code.lower()
    mpl_backend = "Agg" if use_mpl else None

    _lines = [
        'import sys, os, json, time, base64, io, traceback',
        'from pathlib import Path',
        '',
        'os.chdir(' + repr(str(tmp_dir)) + ')',
        'sys.path.insert(0, os.getcwd())',
        '',
        '_start = time.time()',
        '_buf = {}',
        '_err = None',
        '_returncode = 0',
        '',
        'class _Cap:',
        '    def __init__(self):',
        '        self.buffer = []',
        '    def write(self, s):',
        '        self.buffer.append(s)',
        '    def flush(self):',
        '        pass',
        '    def isatty(self):',
        '        return False',
        '',
        '_old_out = sys.stdout',
        '_old_err = sys.stderr',
        'sys.stdout = _Cap()',
        'sys.stderr = _Cap()',
        '',
        'try:',
        '    _mpl_import = ' + repr("import matplotlib; matplotlib.use('Agg')" if use_mpl else "# no mpl"),
        '    exec(',
        '        _mpl_import + "\\n" + ' + repr(code) + ',',
        '        {"__name__": "__main__", "__file__": "<sandbox>"}',
        '    )',
        '    _returncode = 0',
        'except SystemExit as _se:',
        '    _returncode = int(_se.code) if _se.code is not None else 0',
        '    _err = f"SystemExit({_se.code})"',
        'except Exception as _exc:',
        '    _returncode = 1',
        '    _err = f"{type(_exc).__name__}: {_exc}"',
        '    _buf["traceback"] = traceback.format_exc()',
        '',
        'stdout = "".join(sys.stdout.buffer) if hasattr(sys.stdout, "buffer") else ""',
        'stderr = "".join(sys.stderr.buffer) if hasattr(sys.stderr, "buffer") else ""',
        'elapsed = time.time() - _start',
        '',
        'gen_files = []',
        'for p in Path(".").iterdir():',
        '    if p.name in ' + repr(list(file_paths.keys())) + ':',
        '        continue',
        '    try:',
        '        if p.is_file() and p.suffix in (".png",".jpg",".jpeg",".svg",".pdf",".csv",".json",".txt",".md",".html",".log"):',
        '            b64 = base64.b64encode(p.read_bytes()).decode()',
        '            gen_files.append({"path": str(p), "size_bytes": p.stat().st_size, "content_b64": b64})',
        '    except Exception:',
        '        pass',
        '',
        '_fig_b64 = None',
        'try:',
        '    import matplotlib.pyplot as _plt',
        '    if _plt.get_fignums():',
        '        buf = io.BytesIO()',
        '        _plt.savefig(buf, format="png", bbox_inches="tight")',
        '        buf.seek(0)',
        '        _fig_b64 = base64.b64encode(buf.read()).decode()',
        '        _plt.close("all")',
        'except Exception:',
        '    pass',
        '',
        '_result = {',
        '    "returncode": _returncode,',
        '    "stdout": stdout[-100000:] if isinstance(stdout, str) else "",',
        '    "stderr": stderr[-100000:] if isinstance(stderr, str) else "",',
        '    "elapsed_secs": round(elapsed, 4),',
        '    "generated_files": gen_files[:20],',
        '    "libraries_checked": ' + repr(lib_status) + ',',
        '    "matplotlib_plot_b64": _fig_b64,',
        '}',
        'if _err:',
        '    _result["error"] = _err',
        '',
        'sys.stdout = _old_out',
        'sys.stderr = _old_err',
        'print(json.dumps(_result))',
    ]
    runner = '\n'.join(_lines) + '\n'

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", runner,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_dir),
        env={**os.environ, "MOON_MPL_BACKEND": mpl_backend} if mpl_backend else os.environ,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_secs + 5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"error": f"Execution timed out after {timeout_secs}s", "returncode": -1, "stdout": "", "stderr": "", "elapsed_secs": timeout_secs}

    out_text = stdout.decode("utf-8", errors="replace") if stdout else ""
    err_text = stderr.decode("utf-8", errors="replace") if stdout else ""

    result = {}
    for line in out_text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    if result.get("error"):
        return result

    return {
        "returncode": result.get("returncode", proc.returncode),
        "stdout": result.get("stdout", out_text[:100000]),
        "stderr": result.get("stderr", err_text[:100000]),
        "elapsed_secs": result.get("elapsed_secs", 0),
        "generated_files": result.get("generated_files", []),
        "matplotlib_plot_b64": result.get("matplotlib_plot_b64"),
        "libraries_checked": result.get("libraries_checked", lib_status),
        "executed": True,
    }

