"""
MOON Hermes Tools Integration — wraps all 24 Hermes agent tools as MOON tools.

Each wrapper calls model_tools.handle_function_call(name, args) and returns
the parsed JSON result as a dict, matching MOON's tool contract.

Hermes tools integrated:
  browser_exec, browser_vault_enter_code, browser_vault_fill,
  browser_vault_list, browser_vault_save_login, browser_vault_unlock,
  clarify, delegate_task, execute_code, memory, patch, read_file,
  search_files, skill_manage, skill_view, skills_list, terminal,
  vision_analyze, web_extract, web_search, write_file, tool_search,
  tool_describe, tool_call
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Dict

# Import Hermes model_tools (lazy — only when Hermes tools are actually used)
_hermes_mt = None
_hermes_path = '/home/meow/.hermes/hermes-agent'


def _get_hermes_mt():
    """Lazy import of Hermes model_tools."""
    global _hermes_mt
    if _hermes_mt is None:
        sys.path.insert(0, _hermes_path)
        import model_tools as _mt
        _hermes_mt = _mt
    return _hermes_mt


def _hf_call(function_name: str, function_args: Dict[str, Any]) -> Dict[str, Any]:
    """Call a Hermes tool and return parsed result as dict."""
    mt = _get_hermes_mt()
    result_str = mt.handle_function_call(function_name, function_args)
    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        result = {"raw": result_str, "error": "Failed to parse Hermes tool result"}
    return result


# ── Browser tools ────────────────────────────────────────────────────────────

async def _tool_browser_exec(args: Dict[str, Any]) -> Dict[str, Any]:
    """Drive a real web browser via the Browser Use CLI. code runs as full Python."""
    return _hf_call("browser_exec", {
        "code": args.get("code", ""),
        "session": args.get("session", None),
        "timeout_s": args.get("timeout_s", None),
    })


async def _tool_browser_vault_enter_code(args: Dict[str, Any]) -> Dict[str, Any]:
    """Enter a one-time/2FA code after password fill."""
    return _hf_call("browser_vault_enter_code", {
        "handle": args.get("handle", ""),
    })


async def _tool_browser_vault_fill(args: Dict[str, Any]) -> Dict[str, Any]:
    """Fill the current browser page from a vault handle."""
    return _hf_call("browser_vault_fill", {
        "handle": args.get("handle", ""),
    })


async def _tool_browser_vault_list(args: Dict[str, Any]) -> Dict[str, Any]:
    """List saved website logins, payment cards, and addresses."""
    return _hf_call("browser_vault_list", {})


async def _tool_browser_vault_save_login(args: Dict[str, Any]) -> Dict[str, Any]:
    """Save a login for the current page origin."""
    return _hf_call("browser_vault_save_login", {
        "label": args.get("label", None),
    })


async def _tool_browser_vault_unlock(args: Dict[str, Any]) -> Dict[str, Any]:
    """Unlock a password manager (1Password/Bitwarden) for this session."""
    return _hf_call("browser_vault_unlock", {
        "backend": args.get("backend", ""),
    })


# ── Clarify ───────────────────────────────────────────────────────────────────

async def _tool_clarify(args: Dict[str, Any]) -> Dict[str, Any]:
    """Ask the user one or more questions when a decision is needed."""
    return _hf_call("clarify", {
        "questions": args.get("questions", []),
    })


# ── Delegate task ─────────────────────────────────────────────────────────────

async def _tool_delegate_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """Spawn subagents in isolated contexts for parallel workstreams."""
    return _hf_call("delegate_task", {
        "tasks": args.get("tasks", []),
        "action": args.get("action", "spawn"),
        "subagent_id": args.get("subagent_id", None),
        "message": args.get("message", None),
    })


# ── Execute code ──────────────────────────────────────────────────────────────

async def _tool_execute_code(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run Python that calls Hermes tools programmatically."""
    return _hf_call("execute_code", {
        "code": args.get("code", ""),
        "reset": args.get("reset", False),
    })


# ── Memory ────────────────────────────────────────────────────────────────────

async def _tool_hermes_memory(args: Dict[str, Any]) -> Dict[str, Any]:
    """Save durable facts to persistent memory across sessions."""
    action = args.get("action", "add")
    if action == "add":
        return _hf_call("memory", {
            "action": "add",
            "target": args.get("target", "memory"),
            "content": args.get("content", ""),
        })
    elif action == "replace":
        return _hf_call("memory", {
            "action": "replace",
            "old_text": args.get("old_text", ""),
            "new_text": args.get("new_text", ""),
        })
    elif action == "remove":
        return _hf_call("memory", {
            "action": "remove",
            "content": args.get("content", ""),
        })
    elif action == "clear":
        return _hf_call("memory", {
            "action": "clear",
            "target": args.get("target", "memory"),
        })
    else:
        return _hf_call("memory", {
            "action": action,
            "target": args.get("target", "memory"),
            "content": args.get("content", ""),
            "old_text": args.get("old_text", ""),
            "new_text": args.get("new_text", ""),
            "operations": args.get("operations", []),
        })


# ── Patch ─────────────────────────────────────────────────────────────────────

async def _tool_patch(args: Dict[str, Any]) -> Dict[str, Any]:
    """Targeted find-and-replace edits in files."""
    return _hf_call("patch", {
        "path": args.get("path", ""),
        "old_string": args.get("old_string", ""),
        "new_string": args.get("new_string", ""),
        "replace_all": args.get("replace_all", False),
    })


# ── Read file ────────────────────────────────────────────────────────────────

async def _tool_read_file(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read a text file with line numbers and pagination."""
    return _hf_call("read_file", {
        "path": args.get("path", ""),
        "offset": args.get("offset", 1),
        "limit": args.get("limit", 2000),
    })


# ── Search files ──────────────────────────────────────────────────────────────

async def _tool_search_files(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search file contents or find files by name."""
    return _hf_call("search_files", {
        "pattern": args.get("pattern", ""),
        "target": args.get("target", "content"),
        "path": args.get("path", "."),
        "file_glob": args.get("file_glob", None),
        "limit": args.get("limit", 50),
        "offset": args.get("offset", 0),
        "order": args.get("order", "discovery"),
        "output_mode": args.get("output_mode", "content"),
        "context": args.get("context", 0),
    })


# ── Skill manage ─────────────────────────────────────────────────────────────

async def _tool_skill_manage(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create, update, or delete skills — procedural memory for recurring tasks."""
    return _hf_call("skill_manage", {
        "operations": args.get("operations", []),
    })


# ── Skill view ───────────────────────────────────────────────────────────────

async def _tool_skill_view(args: Dict[str, Any]) -> Dict[str, Any]:
    """Load a skill's full content or a linked file."""
    return _hf_call("skill_view", {
        "name": args.get("name", ""),
        "file_path": args.get("file_path", None),
    })


# ── Skills list ──────────────────────────────────────────────────────────────

async def _tool_skills_list(args: Dict[str, Any]) -> Dict[str, Any]:
    """List available skills (name + description)."""
    return _hf_call("skills_list", {
        "category": args.get("category", None),
    })


# ── Terminal ────────────────────────────────────────────────────────────────

async def _tool_terminal(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute shell commands with timeout, background, PTY support."""
    return _hf_call("terminal", {
        "command": args.get("command", ""),
        "background": args.get("background", False),
        "timeout": args.get("timeout", None),
        "workdir": args.get("workdir", None),
        "pty": args.get("pty", False),
        "notify": args.get("notify", None),
    })


# ── Vision analyze ───────────────────────────────────────────────────────────

async def _tool_vision_analyze(args: Dict[str, Any]) -> Dict[str, Any]:
    """Load an image into the conversation for analysis."""
    return _hf_call("vision_analyze", {
        "image_url": args.get("image_url", ""),
        "question": args.get("question", None),
        "region": args.get("region", None),
    })


# ── Web extract ──────────────────────────────────────────────────────────────

async def _tool_web_extract(args: Dict[str, Any]) -> Dict[str, Any]:
    """Extract content from web page URLs as clean markdown."""
    return _hf_call("web_extract", {
        "urls": args.get("urls", []),
        "char_limit": args.get("char_limit", None),
    })


# ── Web search ──────────────────────────────────────────────────────────────

async def _tool_web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search the web for information."""
    return _hf_call("web_search", {
        "query": args.get("query", ""),
        "limit": args.get("limit", 5),
    })


# ── Write file ──────────────────────────────────────────────────────────────

async def _tool_write_file(args: Dict[str, Any]) -> Dict[str, Any]:
    """Write content to a file, completely replacing existing content."""
    return _hf_call("write_file", {
        "path": args.get("path", ""),
        "content": args.get("content", ""),
    })


# ── Tool search ──────────────────────────────────────────────────────────────

async def _tool_tool_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search 17 additional tools that are loaded on demand."""
    return _hf_call("tool_search", {
        "queries": args.get("queries", []),
        "limit": args.get("limit", 5),
    })


# ── Tool describe ────────────────────────────────────────────────────────────

async def _tool_tool_describe(args: Dict[str, Any]) -> Dict[str, Any]:
    """Load the full JSON schemas for tools returned by tool_search."""
    return _hf_call("tool_describe", {
        "names": args.get("names", []),
    })


# ── Tool call ────────────────────────────────────────────────────────────────

async def _tool_tool_call(args: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke deferred tools by name with arguments."""
    return _hf_call("tool_call", {
        "calls": args.get("calls", []),
    })
