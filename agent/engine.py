"""
MOON Agent — standalone agent engine with persona injection,
per-prompt agent selection (agent: prefix), intent→agent routing,
and /api/moon-agent integration endpoint.
"""

from __future__ import annotations

import asyncio
import re
import json
import math
import os
import socket
from datetime import datetime as dt
import urllib.request
import urllib.parse
import urllib.error
import ssl
from pathlib import Path
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field

from agent.llm import OllamaClient, create_client, tool_def

# ---------------------------------------------------------------------------
# Agent persona definitions
# ---------------------------------------------------------------------------

@dataclass
class AgentPersona:
    """A named agent persona with a system prompt and optional tools."""
    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "enabled": self.enabled,
        }


# ---------------------------------------------------------------------------
# Built-in agent personas
# ---------------------------------------------------------------------------

BUILTIN_AGENTS: list[AgentPersona] = [
    AgentPersona(
        name="general",
        description="General-purpose assistant — handles everyday questions, conversation, and broad tasks.",
        system_prompt=(
            "You are MOON, a helpful AI assistant. Answer clearly and concisely. "
            "You have access to tools when needed. Be direct and useful."
        ),
        tools=["system_info", "memory_read", "memory_write", "python_executor", "github_feed", "plan", "reflect"],
    ),
    AgentPersona(
        name="code",
        description="Code specialist — writes, reviews, debugs, and explains code across languages.",
        system_prompt=(
            "You are MOON Code Agent. You excel at writing, reviewing, debugging, and explaining code. "
            "Provide complete, runnable examples. Explain your reasoning. Use tools to inspect files when needed."
        ),
        tools=["system_info", "file_read", "file_write", "shell", "python_executor", "tool_acquire", "self_evolve"],
    ),
    AgentPersona(
        name="security",
        description="Security & red-team agent — offensive security, penetration testing, and threat analysis.",
        system_prompt=(
            "You are MOON Security Agent. You specialize in offensive security, penetration testing methodology, "
            "vulnerability analysis, and red-team operations. Always stay within authorized targets. "
            "Be thorough, technical, and practical."
        ),
        tools=["system_info", "network_scan", "security_tools"],
    ),
    AgentPersona(
        name="research",
        description="Research agent — searches, summarizes, and synthesizes external information.",
        system_prompt=(
            "You are MOON Research Agent. You excel at finding, verifying, and synthesizing information "
            "from multiple sources. Cite your sources. Prefer primary sources. Be rigorous."
        ),
        tools=["web_search", "web_extract", "memory_read", "github_feed"],
    ),
    AgentPersona(
        name="voice",
        description="Voice & TTS agent — handles speech synthesis, voice cloning, and audio tasks.",
        system_prompt=(
            "You are MOON Voice Agent. You manage speech synthesis, voice cloning, and audio processing. "
            "You coordinate with the voice engine to produce natural speech."
        ),
        tools=["voice_speak", "voice_clone"],
    ),
    AgentPersona(
        name="admin",
        description="System administration agent — manages services, configurations, and infrastructure.",
        system_prompt=(
            "You are MOON Admin Agent. You handle system administration, service management, "
            "configuration changes, and infrastructure operations. Be precise and cautious with destructive actions."
        ),
        tools=["system_info", "shell", "service_control"],
    ),
    AgentPersona(
        name="creative",
        description="Creative agent — generates content, designs, ascii art, and creative writing.",
        system_prompt=(
            "You are MOON Creative Agent. You produce original creative content: writing, ASCII art, "
            "design concepts, and visual descriptions. Be imaginative and distinctive."
        ),
        tools=["ascii_art", "image_gen"],
    ),
    AgentPersona(
        name="monitor",
        description="Monitoring & diagnostics agent — checks system health, logs, and performance.",
        system_prompt=(
            "You are MOON Monitor Agent. You diagnose system health, analyze logs, check service status, "
            "and report on performance. Be systematic and data-driven."
        ),
        tools=["system_info", "log_read", "health_check"],
    ),
]

# ---------------------------------------------------------------------------
# Intent→agent routing
# ---------------------------------------------------------------------------

# Simple keyword-based routing (extendable)
INTENT_ROUTING: list[tuple[str, str]] = [
    # (keyword pattern, agent name)
    (r"\b(code|program|script|debug|function|class|import|def |write code|refactor|algorithm|bug|fix|error|exception|traceback|syntax|compile|python|py |pip|module|package)\b", "code"),
    (r"\b(security|penetration|exploit|vulnerability|vulnerabilities|hack|red.?team|payload|audit|nmap|port.?scan|network.?scan|scan|recon|osint|pen.?test)\b", "security"),
    (r"\b(search|research|find|wiki|google|article|paper|source|citation|web|news|summary|summarize|explain|quantum|information|learn)\b", "research"),
    (r"\b(speak|voice|tts|audio|sound|talk|say|pronounce)\b", "voice"),
    (r"\b(health|status|monitor|log|check|up|down|crash|ping|uptime|load|disk|memory|cpu)\b", "monitor"),
    (r"\b(install|service|services|config|deploy|restart|kill|process|daemon|systemd|firewall|dns|network|mount|storage|nginx|systemctl|manage)\b", "admin"),
    (r"\b(draw|ascii|art|design|create|generate|logo|image|visual|paint)\b", "creative"),
    (r"\b(hello|hi|help|status|what|who|how|why|when|where|cancel|reservation|dinner|lunch)\b", "general"),
]


def route_intent(query: str) -> str:
    """Route a query to the best agent based on intent keywords."""
    query_lower = query.lower()
    for pattern, agent_name in INTENT_ROUTING:
        if re.search(pattern, query_lower):
            return agent_name
    return "general"


# ---------------------------------------------------------------------------
# Agent Engine
# ---------------------------------------------------------------------------

class AgentEngine:
    """
    MOON Agent Engine.

    Features:
    - Per-prompt agent selection via `agent:<name>` prefix
    - Agent persona injection into chat (system prompts)
    - Intent→agent routing (keyword-based)
    - Tool dispatch to registered tools
    - Integration endpoint compatible with /api/moon-agent
    """

    def __init__(
        self,
        personas: list[AgentPersona] | None = None,
        llm: OllamaClient | None = None,
    ):
        self.personas: dict[str, AgentPersona] = {}
        for p in (personas or BUILTIN_AGENTS):
            self.personas[p.name] = p
        self._tool_handlers: dict[str, Callable[[dict], Awaitable[dict]]] = {}
        self._memory: list[dict] = []
        self._session_id: str | None = None
        self._llm = llm or create_client()

    # -- Persona management --

    def list_agents(self) -> list[dict]:
        """Return all registered agent personas (for /agent listing)."""
        return [p.to_dict() for p in self.personas.values()]

    def get_agent(self, name: str) -> AgentPersona | None:
        """Get a specific agent persona by name."""
        return self.personas.get(name)

    def add_agent(self, persona: AgentPersona) -> None:
        """Register a new agent persona."""
        self.personas[persona.name] = persona

    def remove_agent(self, name: str) -> bool:
        """Remove an agent persona. Returns True if it existed."""
        if name in self.personas:
            del self.personas[name]
            return True
        return False

    # -- Tool registration --

    def register_tool(self, name: str, handler: Callable[[dict], Awaitable[dict]]) -> None:
        """Register a tool handler callable."""
        self._tool_handlers[name] = handler

    async def run_tool(self, name: str, args: dict) -> dict:
        """Execute a registered tool."""
        handler = self._tool_handlers.get(name)
        if handler:
            return await handler(args)
        return {"error": f"Tool '{name}' not found", "tool": name}

    # -- Agent selection --

    def parse_agent_prefix(self, message: str) -> tuple[str | None, str]:
        """
        Parse `agent:<name>` prefix from a message.
        Returns (agent_name, remaining_message).
        If no prefix, returns (None, message).
        """
        m = re.match(r"^agent:(\w+)\s+(.+)", message, re.IGNORECASE)
        if m:
            agent_name = m.group(1).lower()
            remaining = m.group(2)
            if agent_name in self.personas:
                return agent_name, remaining
            # Unknown agent → fall through to intent routing
            return None, message
        return None, message

    def select_agent(self, message: str, explicit_agent: str | None = None) -> AgentPersona:
        """
        Select the appropriate agent for a message.
        Priority: explicit agent > agent: prefix > intent routing > general.
        """
        # 1. Explicit override
        if explicit_agent and explicit_agent in self.personas:
            return self.personas[explicit_agent]

        # 2. Parse agent: prefix
        agent_name, _ = self.parse_agent_prefix(message)
        if agent_name:
            return self.personas[agent_name]

        # 3. Intent routing
        routed = route_intent(message)
        if routed in self.personas:
            return self.personas[routed]

        # 4. Default
        return self.personas.get("general", list(self.personas.values())[0])

    # -- Chat processing --

    async def process_message(
        self,
        message: str,
        session_id: str | None = None,
        explicit_agent: str | None = None,
    ) -> dict:
        """
        Process an incoming message through the agent system.

        Returns a dict with:
        - agent: the agent name used
        - persona: the agent persona dict
        - response: the processed response (placeholder — integrate with LLM)
        - tools_used: list of tools invoked
        """
        self._session_id = session_id or self._session_id or "default"

        # Select agent
        agent = self.select_agent(message, explicit_agent)
        _, clean_message = self.parse_agent_prefix(message)

        result = {
            "agent": agent.name,
            "persona": agent.to_dict(),
            "message": clean_message,
            "session_id": self._session_id,
            "tools_used": [],
            "response": "",  # LLM integration point
        }

        # Store in memory
        self._memory.append({
            "session": self._session_id,
            "agent": agent.name,
            "message": clean_message,
            "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
        })

        return result

    # -- Memory --

    def get_memory(self, session_id: str | None = None, limit: int = 50) -> list[dict]:
        """Get conversation memory, optionally filtered by session."""
        if session_id:
            return [m for m in self._memory if m.get("session") == session_id][-limit:]
        return self._memory[-limit:]

    def clear_memory(self, session_id: str | None = None) -> None:
        """Clear memory, optionally for a specific session."""
        if session_id:
            self._memory = [m for m in self._memory if m.get("session") != session_id]
        else:
            self._memory.clear()

    # -- LLM integration (real Ollama-backed) --

    def _build_tool_defs(self, tool_names: list[str]) -> list[dict]:
        """Build OpenAI-style tool definitions for the given tool names."""
        defs = []
        # Known tool parameter schemas
        schemas = {
            "system_info": {
                "type": "object",
                "properties": {},
                "description": "Get system information (OS, hostname, Python version).",
            },
            "memory_read": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session ID to read memory for."},
                    "limit": {"type": "integer", "description": "Max entries to return."},
                },
            },
            "memory_write": {
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "Data to store."},
                    "session_id": {"type": "string", "description": "Session ID."},
                },
            },
            "network_scan": {
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of host IPs to scan, e.g. ['127.0.0.1'].",
                    },
                    "ports": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of port numbers to scan, e.g. [22, 80, 443].",
                    },
                },
            },
            "security_tools": {
                "type": "object",
                "properties": {
                    "technique": {
                        "type": "string",
                        "description": "Security technique to run: info, audit, vulnerability-scan, port-scan.",
                    },
                },
            },
            "file_read": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                },
                "required": ["path"],
            },
            "file_write": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Content to write."},
                },
                "required": ["path", "content"],
            },
            "shell": {
                "type": "object",
                "properties": {
                    "command": {"type..."
                },
                "required": ["command"],
            },
            "log_reader": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: tail, search, linewidth. Defaults to tail."},
                    "path": {"type": "string", "description": "Path to the log file."},
                    "pattern": {"type": "string", "description": "Regex to search for (search action)."},
                    "lines": {"type": "integer", "description": "Number of lines for tail (default 50)."},
                    "max_text": {"type": "integer", "description": "Max text length (default 8192)."},
                },
                "required": [],
            },
            "http_request": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to send the request to."},
                    "method": {"type": "string", "description": "HTTP method: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS. Defaults to GET."},
                    "headers": {"type": "object", "description": "Optional dict of headers."},
                    "params": {"type": "object", "description": "Optional query parameters dict."},
                    "data": {"type": "object", "description": "Request body data (JSON)."},
                    "raw": {"type": "integer", "description": "If set to 1, returns raw text instead of parsed JSON."},
                },
                "required": ["url"],
            },
            "git_ops": {
                "type": "object",
                "properties": {
                    "subcommand": {"type": "string", "description": "Git operation: status, log, clone, commit, push, pull, branch, diff, stash."},
                    "directory": {"type": "string", "description": "Working directory for the git command (defaults to /tmp/moon_git_ops)."},
                    "url": {"type": "string", "description": "Repository URL (required for clone)."},
                    "message": {"type": "string", "description": "Commit message (required for commit)."},
                    "remote": {"type": "string", "description": "Remote name for push/pull (default origin)."},
                    "branch": {"type": "string", "description": "Branch name for branch or checkout operations."},
                },
                "required": ["subcommand"],
            },
            "email_sender": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: send (default) or test."},
                    "to": {"type": "string", "description": "Recipient email address(es), comma-separated."},
                    "from_addr": {"type": "string", "description": "Sender email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body (plain text)."},
                    "smtp_host": {"type": "string", "description": "SMTP server hostname (e.g., smtp.gmail.com)."},
                    "smtp_port": {"type": "integer", "description": "SMTP port (587 for TLS, 465 for SSL, 25 for plaintext). Defaults to 587."},
                    "smtp_user": {"type": "string", "description": "SMTP username."},
                    "smtp_pass": {"type": "string", "description": "SMTP password."},
                    "use_tls": {"type": "boolean", "description": "Use TLS (default True for port 587)."},
                },
                "required": [],
            },
            "archive": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: create, extract, list."},
                    "source": {"type": "string", "description": "Source path (file or directory) for create; archive path for extract/list."},
                    "destination": {"type": "string", "description": "Archive path for create; extraction destination for extract (defaults to current directory)."},
                    "format": {"type": "string", "description": "Archive format: zip, tar.gz, tar. Required for create."},
                    "file_list": {"type": "object", "description": "List of files to include (for create); if not provided, source is used."},
                },
                "required": [],
            },
            "dns_lookup": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: lookup (A/AAAA), mx, txt, ns, all, reverse."},
                    "hostname": {"type": "string", "description": "Hostname to look up (e.g., example.com)."},
                    "ip": {"type": "string", "description": "IP address for reverse lookup."},
                    "record_type": {"type": "string", "description": "DNS record type for lookup: A, AAAA, MX, TXT, NS, CNAME, SOA, PTR. Ignored for 'all' and 'reverse'."},
                },
                "required": ["hostname"],
            },
            "template_render": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "description": "Jinja2 template string."},
                    "variables": {"type": "object", "description": "Variables dict for template rendering."},
                },
                "required": ["template"],
            },
            "data_viz": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: bar, line, pie, scatter, histogram. Defaults to bar."},
                    "title": {"type": "string", "description": "Chart title."},
                    "output": {"type": "string", "description": "Output path (PNG). Defaults to /tmp/moon_chart.png."},
                    "x": {"type": "object", "description": "List of x-axis labels or categories."},
                    "y": {"type": "object", "description": "List of y-axis values."},
                    "series": {"type": "object", "description": "Multiple series as dict of name→list for line charts."},
                    "width": {"type": "integer", "description": "Chart width in pixels (default 800)."},
                    "height": {"type": "integer", "description": "Chart height in pixels (default 600)."},
                },
                "required": ["action"],
            },
            "encryption": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: encrypt, decrypt, generate_key, encrypt_file, decrypt_file, encrypt_text, decrypt_text."},
                    "data": {"type": "string", "description": "Text to encrypt/decrypt (for encrypt_text/decrypt_text)."},
                    "file_path": {"type": "string", "description": "File path for encrypt_file/decrypt_file."},
                    "output_path": {"type": "string", "description": "Output path for file operations (default: adds .enc to input path)."},
                    "key": {"type": "string", "description": "Fernet key (base64). Auto-generated if not provided for encrypt operations."},
                },
                "required": [],
            },
            "data_export": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: csv, json, excel."},
                    "data": {"type": "object", "description": "List of dicts (rows) or single dict to export."},
                    "output": {"type": "string", "description": "Output file path (defaults to /tmp/moon_export.csv/json/xlsx)."},
                    "sheet_name": {"type": "string", "description": "Excel sheet name (default Sheet1)."},
                },
                "required": [],
            },
            "yaml_ops": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: dump (Serialize Python data to YAML string), load (Deserialize YAML string to Python object), parse (Parse YAML file)."},
                    "data": {"type": "object", "description": "Python data to serialize to YAML (dump action)."},
                    "yaml_str": {"type": "string", "description": "YAML string to deserialize (load action)."},
                    "file_path": {"type": "string", "description": "Path to YAML file (parse action)."},
                },
                "required": ["action"],
            },
            "qr_generator": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Data to encode in the QR code (URL, text, etc.)."},
                    "output": {"type": "string", "description": "Output file path (PNG). Defaults to /tmp/moon_qr.png."},
                    "size": {"type": "integer", "description": "Size of the QR code in pixels (default 300)."},
                    "border": {"type": "integer", "description": "Border width in modules (default 4)."},
                    "error_correction": {"type": "string", "description": "Error correction level: L (default), M, Q, H."},
                },
                "required": ["data"],
            },
            "rest_api_framework": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Action: info (Show information about the ai_rest_api handler and its capabilities as an MCP server with FastAPI)."},
                },
                "required": ["action"],
            },
            "web_search": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                },
                "required": ["query"],
            },
            "web_extract": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch and extract text from."},
                },
                "required": ["url"],
            },
            "python_executor": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."},
                },
                "required": ["code"],
            },
            "system_command": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "System command to run (guarded)."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."},
                },
                "required": ["command"],
            },
            "docker": {
                "type": "object",
                "properties": {
                    "subcommand": {"type": "string", "description": "Docker subcommand: ps, images, run, exec, logs, build."},
                    "args": {"type": "string", "description": "Arguments for the subcommand."},
                },
                "required": ["subcommand"],
            },
            "github_feed": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "Capability keyword: youtube, web scraping, pdf, image, ocr, etc."},
                },
                "required": ["capability"],
            },
            "tool_acquire": {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "Capability to install: youtube, web scraping, pdf, image, data, chart, translate, excel, yaml, qr."},
                },
                "required": ["capability"],
            },
            "self_evolve": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "URL or local file path to ingest into knowledge base."},
                    "max_chars": {"type": "integer", "description": "Max chars to ingest (default 8000)."},
                },
                "required": ["source"],
            },
            "reflect": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The original prompt/question."},
                    "answer": {"type": "string", "description": "The answer to critique."},
                },
                "required": ["prompt", "answer"],
            },
            "plan": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "The goal to decompose into steps."},
                },
                "required": ["goal"],
            },
        }
    }

    # ---------------------------------------------------------------------------
    # ADVANCED OPERATIONAL TOOL FUNCTIONS
    # ---------------------------------------------------------------------------

    async def _tool_log_reader(args: dict) -> dict:
        """Read log files: tail, search by regex, get linewidth."""
        import re
        action = args.get("action", "tail")
        path = args.get("path", "")
        pattern = args.get("pattern", "")
        lines = args.get("lines", 50)
        max_text = args.get("max_text", 8192)
        if not path:
            return {"error": "path is required"}
        try:
            with open(path, errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return {"error": str(e), "path": path}
        if action == "search":
            if not pattern:
                return {"error": "pattern required for search action"}
            try:
                rx = re.compile(pattern)
                matches = [l.rstrip("\n") for l in all_lines if rx.search(l)]
                return {"action": "search", "path": path, "pattern": pattern,
                        "matches": matches[:500], "count": len(matches)}
            except re.error as e:
                return {"error": f"invalid regex: {e}"}
        elif action == "linewidth":
            return {"action": "linewidth", "path": path,
                    "max_width": max((len(l.rstrip()) for l in all_lines), default=0)}
        else:
            tail = all_lines[-lines:] if lines > 0 else all_lines
            text = "".join(tail)
            return {"action": "tail", "path": path, "lines": len(tail),
                    "content": text[:max_text]}

    async def _tool_http_request(args: dict) -> dict:
        """Make HTTP requests: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS."""
        import urllib.request
        import urllib.parse
        import json as _json
        url = args.get("url", "")
        method = (args.get("method") or "GET").upper()
        headers = args.get("headers") or {}
        params = args.get("params") or {}
        data = args.get("data") or None
        raw = args.get("raw", 0)
        if not url:
            return {"error": "url is required"}
        try:
            if params:
                url = url + "?" + urllib.parse.urlencode(params)
            body_bytes = None
            if data is not None:
                if isinstance(data, dict):
                    body_bytes = _json.dumps(data).encode()
                    headers.setdefault("Content-Type", "application/json")
                else:
                    body_bytes = str(data).encode()
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
            if method == "HEAD":
                req.get_method = lambda: "HEAD"
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                body = resp.read().decode(errors="replace")
                content_type = resp.headers.get("Content-Type", "")
                if raw:
                    return {"status": status, "url": url, "raw": body[:10000],
                            "content_type": content_type}
                try:
                    parsed = _json.loads(body)
                    return {"status": status, "url": url, "json": parsed,
                            "content_type": content_type}
                except (_json.JSONDecodeError, ValueError):
                    return {"status": status, "url": url, "text": body[:10000],
                            "content_type": content_type}
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.reason}", "url": url,
                    "status": e.code, "body": e.read().decode(errors="replace")[:2000]}
        except Exception as e:
            return {"error": str(e), "url": url}

    async def _tool_git_ops(args: dict) -> dict:
        """Git operations: status, log, clone, commit, push, pull, branch, diff, stash."""
        import subprocess
        import shutil
        subcommand = args.get("subcommand", "")
        directory = args.get("directory") or "/tmp/moon_git_ops"
        url = args.get("url", "")
        message = args.get("message", "")
        remote = args.get("remote", "origin")
        branch = args.get("branch", "")
        workdir = shutil.which("git") and directory
        if not subcommand:
            return {"error": "subcommand required (status, log, clone, commit, push, pull, branch, diff, stash)"}
        try:
            ctx = subprocess.run(["git", "config", "--global", "user.email"],
                                 capture_output=True, text=True)
            subprocess.run(["git", "config", "--global", "user.email",
                            "moon@local"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "MOON"],
                            capture_output=True)
            if subcommand == "clone":
                if not url:
                    return {"error": "url required for clone"}
                import os
                os.makedirs(directory, exist_ok=True)
                r = subprocess.run(["git", "clone", url, directory],
                                   capture_output=True, text=True, timeout=60)
                return {"subcommand": "clone", "url": url, "directory": directory,
                        "stdout": r.stdout[:2000], "stderr": r.stderr[:500],
                        "returncode": r.returncode}
            if subcommand == "init":
                import os
                os.makedirs(directory, exist_ok=True)
                r = subprocess.run(["git", "init"], cwd=directory,
                                   capture_output=True, text=True, timeout=30)
                return {"subcommand": "init", "directory": directory,
                        "stdout": r.stdout[:2000], "returncode": r.returncode}
            if subcommand == "branch":
                r = subprocess.run(["git", "branch"] + ([branch] if branch else []),
                                   cwd=directory, capture_output=True, text=True, timeout=30)
                return {"subcommand": "branch", "branch": branch,
                        "stdout": r.stdout[:2000], "returncode": r.returncode}
            if subcommand == "diff":
                r = subprocess.run(["git", "diff"], cwd=directory,
                                   capture_output=True, text=True, timeout=30)
                return {"subcommand": "diff", "stdout": r.stdout[:5000],
                        "returncode": r.returncode}
            if subcommand == "stash":
                r = subprocess.run(["git", "stash"], cwd=directory,
                                   capture_output=True, text=True, timeout=30)
                return {"subcommand": "stash", "stdout": r.stdout[:2000],
                        "returncode": r.returncode}
            r = subprocess.run(["git", subcommand] +
                               ([url] if subcommand in ("clone",) else
                                [remote] if subcommand in ("push", "pull") else
                                [branch] if subcommand == "branch" else
                                []),
                               cwd=directory if subcommand != "clone" else None,
                               capture_output=True, text=True, timeout=60)
            if subcommand == "commit" and message:
                r = subprocess.run(["git", "commit", "-m", message],
                                   cwd=directory, capture_output=True, text=True, timeout=30)
            return {"subcommand": subcommand, "stdout": r.stdout[:2000],
                    "stderr": r.stderr[:500], "returncode": r.returncode}
        except Exception as e:
            return {"error": str(e), "subcommand": subcommand}

    async def _tool_email_sender(args: dict) -> dict:
        """Send email via SMTP (TLS/SSL supported)."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        action = args.get("action", "send")
        to = args.get("to", "")
        from_addr = args.get("from_addr", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        smtp_host = args.get("smtp_host", "")
        smtp_port = args.get("smtp_port", 587)
        smtp_user = args.get("smtp_user", "")
        smtp_pass = args.get("smtp_pass", "")
        use_tls = args.get("use_tls", None)
        if action == "test":
            return {"status": "configured",
                    "smtp_host": smtp_host, "smtp_port": smtp_port,
                    "from_addr": from_addr, "to": to,
                    "note": "use action='send' to actually send"}
        if not all([to, from_addr, subject, body, smtp_host]):
            return {"error": "to, from_addr, subject, body, smtp_host required for send",
                    "configured": bool(smtp_host)}
        try:
            msg = MIMEMultipart()
            msg["From"] = from_addr
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            if use_tls is None:
                use_tls = smtp_port == 587
            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
                if use_tls:
                    server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()
            return {"status": "sent", "to": to, "subject": subject,
                    "smtp_host": smtp_host, "smtp_port": smtp_port}
        except Exception as e:
            return {"error": f"send failed: {e}", "smtp_host": smtp_host,
                    "smtp_port": smtp_port}

    async def _tool_archive(args: dict) -> dict:
        """Create, extract, and list archive files (zip, tar.gz, tar)."""
        import os
        import zipfile
        import tarfile
        import shutil
        action = args.get("action", "list")
        source = args.get("source", "")
        destination = args.get("destination", "")
        fmt = args.get("format", "zip")
        file_list = args.get("file_list") or None
        if action == "create":
            if not source:
                return {"error": "source required for create"}
            dest = destination or f"/tmp/moon_archive_{os.path.basename(str(source))}.{fmt}"
            try:
                if fmt == "zip":
                    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                        if file_list:
                            for f in file_list:
                                if os.path.exists(f):
                                    zf.write(f, os.path.basename(f))
                        elif os.path.isfile(source):
                            zf.write(source, os.path.basename(source))
                        elif os.path.isdir(source):
                            for root, _, files in os.walk(source):
                                for f in files:
                                    full = os.path.join(root, f)
                                    zf.write(full, os.path.relpath(full, source))
                    size = os.path.getsize(dest)
                    return {"action": "create", "archive": dest, "format": "zip",
                            "source": source, "size_bytes": size}
                else:
                    mode = "w:gz" if fmt == "tar.gz" else "w"
                    with tarfile.open(dest, mode) as tf:
                        if file_list:
                            for f in file_list:
                                if os.path.exists(f):
                                    tf.add(f, os.path.basename(f))
                        elif os.path.isfile(source):
                            tf.add(source, os.path.basename(source))
                        elif os.path.isdir(source):
                            tf.add(source, os.path.basename(source))
                    size = os.path.getsize(dest)
                    return {"action": "create", "archive": dest, "format": fmt,
                            "source": source, "size_bytes": size}
            except Exception as e:
                return {"error": str(e), "action": "create"}
        elif action == "extract":
            if not source:
                return {"error": "source archive path required for extract"}
            dest = destination or "."
            try:
                if source.endswith(".zip"):
                    with zipfile.ZipFile(source) as zf:
                        zf.extractall(dest)
                        names = zf.namelist()
                else:
                    with tarfile.open(source) as tf:
                        tf.extractall(dest)
                        names = tf.getnames()
                return {"action": "extract", "archive": source, "destination": dest,
                        "files_extracted": len(names), "files": names[:100]}
            except Exception as e:
                return {"error": str(e), "action": "extract"}
        else:
            if not source:
                return {"error": "source archive path required for list"}
            try:
                if source.endswith(".zip"):
                    with zipfile.ZipFile(source) as zf:
                        names = zf.namelist()
                        size = sum(zf.getinfo(n).file_size for n in names)
                else:
                    with tarfile.open(source) as tf:
                        names = tf.getnames()
                        size = sum(m.size for m in tf.getmembers())
                return {"action": "list", "archive": source, "format": fmt or "auto",
                        "file_count": len(names), "total_size": size,
                        "files": names[:100]}
            except Exception as e:
                return {"error": str(e), "action": "list"}

    async def _tool_dns_lookup(args: dict) -> dict:
        """DNS lookups: A, AAAA, MX, TXT, NS, CNAME, SOA, PTR, reverse, all."""
        import socket
        action = args.get("action", "lookup")
        hostname = args.get("hostname", "")
        ip = args.get("ip", "")
        record_type = (args.get("record_type") or "A").upper()
        if action == "reverse":
            if not ip:
                return {"error": "ip required for reverse lookup"}
            try:
                hosts = socket.gethostbyaddr(ip)
                return {"action": "reverse", "ip": ip, "hostname": hosts[0],
                        "aliases": hosts[1], "addresses": hosts[2]}
            except socket.herror as e:
                return {"error": str(e), "action": "reverse", "ip": ip}
        if not hostname:
            return {"error": "hostname required for lookup"}
        results = {}
        types_to_try = {
            "all": ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"],
            "A": ["A"], "AAAA": ["AAAA"], "MX": ["MX"],
            "TXT": ["TXT"], "NS": ["NS"], "CNAME": ["CNAME"], "SOA": ["SOA"],
        }
        to_query = types_to_try.get(action, [record_type])
        for rt in to_query:
            try:
                import dns.resolver as _dr
                answers = _dr.resolve(hostname, rt)
                results[rt] = [str(a) for a in answers]
            except Exception:
                try:
                    if rt == "A":
                        addr = socket.gethostbyname(hostname)
                        results["A"] = [addr]
                    elif rt == "AAAA":
                        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET6)
                        results["AAAA"] = [a[4][0] for a in addrs]
                    else:
                        results[rt] = []
                except Exception:
                    results[rt] = []
        return {"action": action, "hostname": hostname, "results": results}

    async def _tool_template_render(args: dict) -> dict:
        """Render a Jinja2 template string with provided variables."""
        from jinja2 import Environment, BaseLoader, TemplateError
        template_str = args.get("template", "")
        variables = args.get("variables") or {}
        if not template_str:
            return {"error": "template required"}
        try:
            env = Environment(loader=BaseLoader())
            tmpl = env.from_string(template_str)
            rendered = tmpl.render(**variables)
            return {"template": template_str[:200], "rendered": rendered,
                    "variables": list(variables.keys())}
        except TemplateError as e:
            return {"error": f"template error: {e}", "template": template_str[:200]}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_data_viz(args: dict) -> dict:
        """Generate charts: bar, line, pie, scatter, histogram (PNG output)."""
        import io
        import base64
        action = args.get("action", "bar")
        title = args.get("title", "")
        output = args.get("output", "/tmp/moon_chart.png")
        x = args.get("x") or []
        y = args.get("y") or []
        series = args.get("series") or {}
        width = args.get("width", 800)
        height = args.get("height", 600)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(width / 100, height / 100))
            fig.suptitle(title or f"{action.title()} Chart")
            if action == "bar":
                if y and not isinstance(y[0], (list, tuple)):
                    ax.bar(range(len(y)), y, tick_label=x or [str(i) for i in range(len(y))])
                else:
                    for name, vals in (series or {}).items():
                        ax.bar(range(len(vals)), vals, label=name)
                    ax.legend()
            elif action == "line":
                if series:
                    for name, vals in series.items():
                        ax.plot(vals, label=name)
                    ax.legend()
                elif y:
                    ax.plot(y, marker="o")
            elif action == "pie":
                ax.pie(y, labels=x, autopct="%1.1f%%")
            elif action == "scatter":
                ax.scatter(x or list(range(len(y))), y)
            elif action == "histogram":
                ax.hist(y, bins=args.get("bins", 10))
            ax.set_xlabel(args.get("xlabel", ""))
            ax.set_ylabel(args.get("ylabel", ""))
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=100)
            plt.close()
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            import os as _os
            with open(output, "wb") as f:
                f.write(buf.read())
            return {"action": action, "output": output,
                    "size_bytes": _os.path.getsize(output),
                    "base64_preview": b64[:500]}
        except ImportError:
            return {"error": "matplotlib not installed. Use tool_acquire ('chart') to install."}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_encryption(args: dict) -> dict:
        """Encrypt/decrypt text and files using Fernet symmetric encryption."""
        from cryptography.fernet import Fernet
        import base64
        import os
        action = args.get("action", "generate_key")
        data = args.get("data", "")
        file_path = args.get("file_path", "")
        output_path = args.get("output_path", "")
        key = args.get("key", "")
        if action == "generate_key":
            k = Fernet.generate_key().decode()
            return {"key": k, "note": "store this key securely — required for decryption"}
        if not key:
            return {"error": "key required for encrypt/decrypt operations (use generate_key first)"}
        try:
            f = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            return {"error": f"invalid key: {e}"}
        if action in ("encrypt_text", "decrypt_text"):
            payload = data
            if action == "encrypt_text":
                result = f.encrypt(payload.encode()).decode()
            else:
                result = f.decrypt(payload.encode()).decode()
            return {"action": action, "input": payload[:100], "output": result[:200]}
        if action in ("encrypt_file", "decrypt_file"):
            if not file_path:
                return {"error": "file_path required"}
            out = output_path or file_path + (".enc" if action == "encrypt_file" else "")
            try:
                with open(file_path, "rb") as fh:
                    raw = fh.read()
                if action == "encrypt_file":
                    out_data = f.encrypt(raw)
                else:
                    out_data = f.decrypt(raw)
                with open(out, "wb") as fh:
                    fh.write(out_data)
                return {"action": action, "input_file": file_path,
                        "output_file": out, "size_bytes": os.path.getsize(out)}
            except Exception as e:
                return {"error": f"file operation failed: {e}"}
        return {"error": f"unknown action: {action}. Use: generate_key, encrypt_text, decrypt_text, encrypt_file, decrypt_file"}

    async def _tool_data_export(args: dict) -> dict:
        """Export data to CSV, JSON, or Excel formats."""
        import os
        import json as _json
        import csv
        action = args.get("action", "csv")
        data = args.get("data") or []
        output = args.get("output", "")
        sheet_name = args.get("sheet_name", "Sheet1")
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return {"error": "data must be a list of dicts or a single dict"}
        ext = (output or f"/tmp/moon_export.{action}").rsplit(".", 1)[-1]
        default_out = {
            "csv": "/tmp/moon_export.csv",
            "json": "/tmp/moon_export.json",
            "excel": "/tmp/moon_export.xlsx",
        }.get(action, f"/tmp/moon_export.{action}")
        out = output or default_out
        try:
            if action == "json":
                with open(out, "w") as f:
                    _json.dump(data, f, indent=2, default=str)
                return {"action": "json", "output": out,
                        "records": len(data), "size_bytes": os.path.getsize(out)}
            if action == "csv":
                if not data:
                    return {"error": "no data to export"}
                keys = set().union(*(d.keys() for d in data if isinstance(d, dict)))
                with open(out, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=sorted(keys), extrasaction="ignore")
                    w.writeheader()
                    for row in data:
                        if isinstance(row, dict):
                            w.writerow(row)
                        else:
                            w.writerow({"value": row})
                return {"action": "csv", "output": out,
                        "records": len(data), "fields": sorted(keys),
                        "size_bytes": os.path.getsize(out)}
            if action == "excel":
                try:
                    from openpyxl import Workbook
                    from openpyxl.utils import get_column_letter
                except ImportError:
                    return {"error": "openpyxl not installed. tool_acquire('excel') to install."}
                wb = Workbook()
                ws = wb.active
                ws.title = sheet_name
                if data:
                    keys = set().union(*(d.keys() for d in data if isinstance(d, dict)))
                    fields = sorted(keys)
                    ws.append(fields)
                    for row in data:
                        ws.append([row.get(k, "") if isinstance(row, dict) else row for k in fields])
                wb.save(out)
                return {"action": "excel", "output": out, "sheet": sheet_name,
                        "records": len(data), "size_bytes": os.path.getsize(out)}
            return {"error": f"unknown action: {action}. Use: csv, json, excel"}
        except Exception as e:
            return {"error": str(e), "action": action}

    async def _tool_yaml_ops(args: dict) -> dict:
        """YAML operations: dump (serialize), load (deserialize), parse (file)."""
        import yaml as _yaml
        action = args.get("action", "")
        data = args.get("data")
        yaml_str = args.get("yaml_str", "")
        file_path = args.get("file_path", "")
        if action == "dump":
            try:
                result = _yaml.dump(data, default_flow_style=False, sort_keys=False)
                return {"action": "dump", "yaml": result, "keys": len(data) if isinstance(data, dict) else "N/A"}
            except Exception as e:
                return {"error": f"dump failed: {e}"}
        if action == "load":
            if not yaml_str:
                return {"error": "yaml_str required for load"}
            try:
                result = _yaml.safe_load(yaml_str)
                return {"action": "load", "python_object": result,
                        "type": type(result).__name__}
            except Exception as e:
                return {"error": f"load failed: {e}"}
        if action == "parse":
            if not file_path:
                return {"error": "file_path required for parse"}
            try:
                with open(file_path) as f:
                    result = _yaml.safe_load(f)
                return {"action": "parse", "file": file_path,
                        "python_object": result, "type": type(result).__name__}
            except Exception as e:
                return {"error": f"parse failed: {e}"}
        return {"error": f"unknown action: {action}. Use: dump, load, parse"}

    async def _tool_qr_generator(args: dict) -> dict:
        """Generate QR code images (PNG)."""
        import os
        data = args.get("data", "")
        output = args.get("output", "/tmp/moon_qr.png")
        size = args.get("size", 300)
        border = args.get("border", 4)
        ec = args.get("error_correction", "L")
        ec_map = {"L": "L", "M": "M", "Q": "Q", "H": "H"}
        if not data:
            return {"error": "data required"}
        try:
            import qrcode
            from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
            ec_const = {
                "L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
                "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H,
            }.get(ec.upper(), ERROR_CORRECT_L)
            qr = qrcode.QRCode(error_correction=ec_const, box_size=size // 30 or 10,
                                border=border)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(output)
            return {"action": "generate", "data": data[:100], "output": output,
                    "size_bytes": os.path.getsize(output),
                    "error_correction": ec, "border": border}
        except ImportError:
            return {"error": "qrcode not installed. tool_acquire('qr') to install."}
        except Exception as e:
            return {"error": str(e)}

    async def _tool_rest_api_framework(args: dict) -> dict:
        """Info about the ai_rest_api handler and its MCP server capabilities."""
        return {
            "name": "ai_rest_api",
            "description": "FastAPI-based REST API server for MOON agent with MCP-compatible tool endpoints.",
            "endpoints": {
                "/api/health": "GET - Health check",
                "/api/moon-agent": "POST - Process message via MOON agent",
                "/api/tools": "GET - List available tools",
                "/api/tools/<name>": "POST - Execute a specific tool",
            },
            "capabilities": [
                "REST API server on configurable port",
                "MCP-compatible tool protocol",
                "Real Ollama LLM backend",
                "Multi-agent routing (code, security, research, system, support, creative, terminal)",
                "13+ registered tools with parameter schemas",
                "Conversation memory per session",
                "Tool-calling loop with LLM",
            ],
            "note": "Run via: python -m agent.engine --port 8778 or via systemd moon.service",
        }

    async def generate_response(
        self,
        agent: AgentPersona,
        message: str,
    ) -> str:
        """
        Generate a response using the engine's Ollama-backed LLM client.

        Injects the agent's system_prompt, supports tool-calling if the agent
        has tools registered, and feeds tool results back to the LLM.

        Args:
            agent: The selected agent persona.
            message: The user's message (after prefix removal).
            model: Optional model name override.

        Returns:
            The generated response text.
        """
        system = agent.system_prompt
        tool_names = agent.tools or []
        tool_defs = self._build_tool_defs(tool_names) if tool_names else None

        if tool_defs:
            # Use tool-calling loop
            result = await self._llm.chat_with_tools(
                message=message,
                system=system,
                tools=tool_defs,
                tool_executor=self._execute_tool_call,
                max_iterations=5,
            )
            return result.get("content", "")
        else:
            # Simple chat
            result = await self._llm.chat(
                message=message,
                system=system,
            )
            return result.get("content", "")

    async def _execute_tool_call(self, tool_call: dict) -> dict:
        """Execute a single tool call from the LLM."""
        func = tool_call.get("function", {})
        name = func.get("name", "")
        args_str = func.get("arguments", "{}")
        try:
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except (json.JSONDecodeError, TypeError):
            args = {}
        # Post-process: some LLMs send arrays/objects as JSON strings
        # Deep-parse any string values that look like JSON
        if isinstance(args, dict):
            for key, value in args.items():
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, (dict, list)):
                            args[key] = parsed
                    except (json.JSONDecodeError, ValueError):
                        pass  # Not JSON, leave as string
        return await self.run_tool(name, args)


# ---------------------------------------------------------------------------
# Default engine instance
# ---------------------------------------------------------------------------

default_engine = AgentEngine()


# ---------------------------------------------------------------------------
# CLI /agent listing
# ---------------------------------------------------------------------------

def cmd_agent_list() -> None:
    """Print all registered agents (for /agent command)."""
    agents = default_engine.list_agents()
    print("╔══════════════════════════════════════════╗")
    print("║  MOON AGENTS                         ║")
    print("╠══════════════════════════════════════════╣")
    for a in agents:
        status = "✓" if a["enabled"] else "✗"
        print(f"  {status} {a['name']:<12} {a['description'][:45]}")
    print("╚══════════════════════════════════════════╝")
    print()
    print("Usage: agent:<name> <your message>")
    print("Example: agent:code write a python function")
    print("         agent:security analyze this traffic")


def cmd_agent_route(query: str) -> None:
    """Show which agent would handle a query."""
    agent_name = route_intent(query)
    persona = default_engine.get_agent(agent_name)
    print(f"Query: {query}")
    print(f"Routed to: {agent_name}")
    if persona:
        print(f"Description: {persona.description}")


# ---------------------------------------------------------------------------
# API endpoint helpers (for /api/moon-agent)
# ---------------------------------------------------------------------------

def api_agent_process(request_data: dict) -> dict:
    """
    Process an incoming API request for /api/moon-agent.

    Expected request format:
    {
        "message": "your message here",
        "session_id": "optional-session-id",
        "agent": "optional-explicit-agent-name",
        "tools": ["tool1", "tool2"]  # optional tool list to invoke
    }

    Returns:
    {
        "agent": "selected-agent-name",
        "persona": {...},
        "response": "...",
        "tools_used": [...],
        "session_id": "..."
    }
    """
    msg = request_data.get("message", "")
    session_id = request_data.get("session_id")
    explicit_agent = request_data.get("agent")

    # Parse agent: prefix if no explicit agent given
    if not explicit_agent:
        parsed_agent, msg = default_engine.parse_agent_prefix(msg)
        if parsed_agent:
            explicit_agent = parsed_agent

    # Select and process
    result = asyncio.run(default_engine.process_message(
        msg, session_id=session_id, explicit_agent=explicit_agent
    ))

    # Optionally invoke tools
    tools_requested = request_data.get("tools", [])
    if tools_requested:
        for tool_name in tools_requested:
            tool_result = asyncio.run(default_engine.run_tool(tool_name, {}))
            result["tools_used"].append({
                "tool": tool_name,
                "result": tool_result,
            })

    return result


def api_agent_list() -> list[dict]:
    """API endpoint: list all agents."""
    return default_engine.list_agents()


def api_agent_router(query: str) -> dict:
    """API endpoint: route a query to an agent."""
    agent_name = route_intent(query)
    persona = default_engine.get_agent(agent_name)
    return {
        "query": query,
        "agent": agent_name,
        "persona": persona.to_dict() if persona else None,
    }


# ---------------------------------------------------------------------------
# Tool stubs (to be wired to real implementations)
# ---------------------------------------------------------------------------

async def _tool_system_info(args: dict) -> dict:
    import platform
    import socket
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "timestamp": asyncio.get_event_loop().time(),
    }


async def _tool_memory_read(args: dict) -> dict:
    session = args.get("session_id")
    limit = args.get("limit", 20)
    return {"memory": default_engine.get_memory(session_id=session, limit=limit)}


async def _tool_memory_write(args: dict) -> dict:
    data = args.get("data", {})
    default_engine._memory.append({
        "session": default_engine._session_id or "default",
        "data": data,
        "timestamp": asyncio.get_event_loop().time(),
    })
    return {"status": "written", "count": len(default_engine._memory)}



async def _tool_network_scan(args: dict) -> dict:
    """Scan network hosts and ports (simplified)."""
    import socket, subprocess
    targets = args.get("targets", ["127.0.0.1"])
    ports = args.get("ports", [22, 80, 443, 8777, 8778])
    results = []
    for target in targets:
        for port in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect((target, port))
                results.append({"host": target, "port": port, "status": "open"})
                s.close()
            except (socket.timeout, socket.error, OSError):
                results.append({"host": target, "port": port, "status": "closed"})
    return {"scanned": len(results), "results": results, "targets": targets, "ports": ports}

async def _tool_security_tools(args: dict) -> dict:
    """Run security analysis tools (simplified)."""
    import platform, subprocess
    technique = args.get("technique", "info")
    if technique == "info":
        return {
            "system": platform.system(),
            "hostname": subprocess.getoutput("hostname 2>/dev/null") or "unknown",
            "kernel": platform.release(),
            "techniques_supported": ["info", "audit", "vulnerability-scan", "port-scan"],
        }
    return {"technique": technique, "status": "not_implemented", "message": "Security tool stub — wire to real implementation"}

async def _tool_file_read(args: dict) -> dict:
    """Read a file."""
    path = args.get("path", "")
    try:
        with open(path) as f:
            content = f.read()
        return {"path": path, "content": content[:10000], "bytes": len(content)}
    except Exception as e:
        return {"error": str(e), "path": path}

async def _tool_file_write(args: dict) -> dict:
    """Write to a file."""
    path = args.get("path", "")
    content = args.get("content", "")
    try:
        with open(path, "w") as f:
            f.write(content)
        return {"status": "written", "path": path, "bytes": len(content)}
    except Exception as e:
        return {"error": str(e), "path": path}

async def _tool_shell(args: dict) -> dict:
    """Execute a shell command."""
    import subprocess
    cmd = args.get("command", "")
    if not cmd:
        return {"error": "No command provided"}
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {"command": cmd, "stdout": result.stdout[:10000], "stderr": result.stderr[:10000], "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out", "command": cmd}
    except Exception as e:
        return {"error": str(e), "command": cmd}

async def _tool_web_search(args: dict) -> dict:
    """Search using Wikipedia's free API (no API key needed). Returns articles matching the query."""
    import urllib.request
    import urllib.parse
    import json
    import re as _re
    query = args.get("query", "")
    if not query:
        return {"error": "No query provided"}
    try:
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": "5",
        })
        req = urllib.request.Request(url, headers={"User-Agent": "MOON/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = []
        for item in data.get("query", {}).get("search", []):
            snippet = item.get("snippet", "")
            snippet = _re.sub(r"<[^>]+>", "", snippet).strip()
            results.append({
                "title": item.get("title", ""),
                "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(item.get("title", ""), safe=""),
                "snippet": snippet[:300],
            })
        return {"query": query, "results": results, "count": len(results), "source": "wikipedia"}
    except Exception as e:
        return {"error": str(e), "query": query}


async def _tool_web_extract(args: dict) -> dict:
    """Fetch a URL and extract readable text content."""
    import urllib.request
    import re
    url = args.get("url", "")
    if not url:
        return {"error": "No URL provided"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MOON/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"url": url, "content": text[:10000], "chars": len(text)}
    except Exception as e:
        return {"error": str(e), "url": url}


# ---------------------------------------------------------------------------
# ADVANCED TOOLS
# ---------------------------------------------------------------------------

async def _tool_python_executor(args: dict) -> dict:
    """Run a bounded Python snippet and return stdout (async, time-limited)."""
    import asyncio as _asyncio
    import sys as _sys
    code = args.get("code", "")
    timeout = args.get("timeout", 30)
    if not code:
        return {"output": "[no code provided]"}
    try:
        proc = await _asyncio.create_subprocess_exec(
            _sys.executable, "-c", code,
            stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
        )
        out, err = await _asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout = (out or b"").decode(errors="replace")[:2000]
        stderr = (err or b"").decode(errors="replace")[:500]
        return {
            "output": stdout + ("\n" + stderr if stderr else ""),
            "returncode": proc.returncode,
        }
    except Exception as exc:
        return {"error": f"[python error: {exc}]"}


async def _tool_system_command(args: dict) -> dict:
    """Run a controlled system command (guarded against dangerous ops)."""
    import asyncio as _asyncio
    command = args.get("command", "")
    timeout = args.get("timeout", 30)
    _REFUSE = ("rm -rf", "shutdown", "reboot", "dd if=", "mkfs", "chmod 777 /")
    if not command:
        return {"output": "[no command provided]"}
    low = command.lower()
    if any(d in low for d in _REFUSE):
        return {"output": "[refused: potentially dangerous command]", "refused": True}
    try:
        proc = await _asyncio.create_subprocess_shell(
            command, stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE,
        )
        out, err = await _asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout = (out or b"").decode(errors="replace")[:2000]
        stderr = (err or b"").decode(errors="replace")[:500]
        return {
            "output": stdout + ("\n" + stderr if stderr else ""),
            "returncode": proc.returncode,
        }
    except Exception as exc:
        return {"error": f"[system_command error: {exc}]"}


async def _tool_docker(args: dict) -> dict:
    """Docker operations: ps, images, run, exec, logs, build (if docker CLI available)."""
    import shutil
    import subprocess
    subcommand = args.get("subcommand", "ps")
    docker_args = args.get("args", "")
    if not shutil.which("docker"):
        return {"output": "[docker] docker CLI not found on this host.", "available": False}
    try:
        r = subprocess.run(
            ["docker", subcommand] + (docker_args.split() if docker_args else []),
            capture_output=True, text=True, timeout=120,
        )
        output = (r.stdout or r.stderr or "(no output)")[:2000]
        return {"output": output, "available": True, "returncode": r.returncode}
    except Exception as exc:
        return {"error": f"[docker] error: {exc}", "available": True}


async def _tool_github_feed(args: dict) -> dict:
    """Search public GitHub for tools matching a capability keyword and pull the best match.

    Usage: github_feed with capability="youtube downloader", "web scraper", etc.
    Returns the best-matching repo info and a download URL.
    """
    import json
    import urllib.request
    import urllib.parse
    capability = args.get("capability", "")
    search_queries = {
        "youtube": "youtube downloader in:name,readme language:python",
        "video": "video downloader in:name language:python",
        "audio download": "audio downloader in:name language:python",
        "web scraping": "web scraper in:name language:python",
        "html parse": "html parser in:name language:python",
        "browser automation": "browser automation playwright in:name language:python",
        "image": "image processing in:name language:python",
        "ocr": "ocr tesseract in:name language:python",
        "pdf": "pdf parser in:name language:python",
        "data": "data analysis pandas in:name language:python",
        "csv": "csv toolkit in:name language:python",
        "plot": "chart plotting in:name language:python",
        "chart": "chart generator in:name language:python",
        "speech": "speech recognition in:name language:python",
        "translate": "translation api in:name language:python",
        "excel": "excel xlsx in:name language:python",
        "qr": "qr code generator in:name language:python",
        "scraper": "scraper in:name language:python",
    }
    query = search_queries.get(capability.lower(), capability)
    if not query:
        return {"error": "No capability specified. Try: youtube, web scraping, pdf, image, ocr, etc."}
    try:
        url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&per_page=3"
        req = urllib.request.Request(url, headers={"User-Agent": "MOON/1.0", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        items = data.get("items", [])
        results = []
        for item in items[:3]:
            results.append({
                "name": item.get("name", ""),
                "full_name": item.get("full_name", ""),
                "description": (item.get("description") or "")[:200],
                "stars": item.get("stargazers_count", 0),
                "url": item.get("html_url", ""),
                "clone_url": item.get("clone_url", ""),
            })
        return {"results": results, "count": len(results), "query": query}
    except Exception as exc:
        return {"error": f"[github_feed error: {exc}]"}


# ---------------------------------------------------------------------------
# ADVANCED FEATURES (ported from original MOON's advanced subsystems)
# ---------------------------------------------------------------------------

TOOL_CATALOG: dict[str, dict] = {
    "youtube": {"pip": "yt-dlp", "import": "yt_dlp", "cap": "download audio/video from YouTube"},
    "video": {"pip": "yt-dlp", "import": "yt_dlp", "cap": "download/process video"},
    "web scraping": {"pip": "beautifulsoup4", "import": "bs4", "cap": "parse HTML"},
    "html parse": {"pip": "beautifulsoup4", "import": "bs4", "cap": "parse HTML"},
    "image": {"pip": "Pillow", "import": "PIL", "cap": "image processing"},
    "pdf": {"pip": "pypdf", "import": "pypdf", "cap": "read PDFs"},
    "data": {"pip": "pandas", "import": "pandas", "cap": "data analysis"},
    "chart": {"pip": "matplotlib", "import": "matplotlib", "cap": "charts/plots"},
    "translate": {"pip": "deep-translator", "import": "deep_translator", "cap": "translation"},
    "excel": {"pip": "openpyxl", "import": "openpyxl", "cap": "xlsx files"},
    "yaml": {"pip": "pyyaml", "import": "yaml", "cap": "YAML config"},
    "qr": {"pip": "qrcode", "import": "qrcode", "cap": "generate QR codes"},
}


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


async def _tool_tool_acquire(args: dict) -> dict:
    """Install a Python package from catalog and optionally generate a tool.

    Usage: tool_acquire with capability="web scraping" (installs beautifulsoup4).
    Returns what was installed and whether it's usable.
    """
    capability = args.get("capability", "")
    cap = capability.lower()
    for key, spec in TOOL_CATALOG.items():
        if key in cap:
            already = _importable(spec["import"])
            if not already:
                import subprocess as _sp
                import sys as _sys
                try:
                    _sp.run(
                        [_sys.executable, "-m", "pip", "install", "--quiet", spec["pip"]],
                        check=False, timeout=180,
                        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
                    )
                except Exception as exc:
                    return {"installed": False, "capability": capability, "error": str(exc)}
            now = _importable(spec["import"])
            return {
                "installed": now,
                "capability": capability,
                "package": spec["pip"],
                "import": spec["import"],
                "already_available": already,
            }
    return {"installed": False, "capability": capability, "error": "No catalog match. Try: youtube, web scraping, pdf, image, data, chart, translate, excel, yaml, qr"}


async def _tool_self_evolve(args: dict) -> dict:
    """Ingest a URL or local file into MOON's knowledge base (bounded self-evolution).

    Usage: self_evolve with source="https://example.com/article" or source="/path/to/file.md"
    """
    import re as _re
    from urllib.parse import urlparse as _urlparse
    source = args.get("source", "")
    max_chars = args.get("max_chars", 8000)
    if not source:
        return {"status": "error", "message": "supply a URL or local path to learn from"}
    text = ""
    if _urlparse(source).scheme in ("http", "https"):
        try:
            import urllib.request as _ur
            req = _ur.Request(source, headers={"User-Agent": "MOON/1.0"})
            with _ur.urlopen(req, timeout=20) as resp:
                text = _re.sub(r"<[^>]+>", " ", resp.read().decode(errors="replace"))
                text = _re.sub(r"\s+", " ", text).strip()
        except Exception as exc:
            return {"status": "error", "message": f"fetch failed: {exc}"}
    else:
        try:
            from pathlib import Path as _Path
            p = _Path(source)
            if p.is_file():
                text = p.read_text(errors="replace")
            elif p.is_dir():
                text = "\n".join(f.read_text(errors="replace") for f in list(p.glob("*.md"))[:10] if f.is_file())
        except Exception as exc:
            return {"status": "error", "message": f"read failed: {exc}"}
    if not text:
        return {"status": "error", "message": "no text extracted"}
    text = text[:max_chars]
    default_engine._memory.append({
        "session": "self_evolve",
        "data": {"source": source, "chars": len(text), "learned": text[:500]},
        "timestamp": __import__("asyncio").get_event_loop().time(),
    })
    return {
        "status": "learned",
        "source": source,
        "chars": len(text),
        "message": f"Ingested {len(text)} chars from {source} into MOON's knowledge.",
    }


async def _tool_reflect(args: dict) -> dict:
    """Self-reflect: critique an answer against a prompt, suggest improvements.

    Usage: reflect with prompt="..." and answer="..."
    Uses LLM when available, heuristic fallback when not.
    """
    prompt = args.get("prompt", "")
    answer = args.get("answer", "")
    if default_engine._llm is not None and answer:
        try:
            resp = await default_engine._llm.chat(
                message=(
                    "Critique the ANSWER against the PROMPT. List concrete "
                    "problems only (missing parts, factual errors, vagueness). "
                    "If it is good, reply exactly SATISFACTORY. Otherwise list "
                    "each issue on its own line.\n\nPROMPT: " + prompt
                    + "\n\nANSWER: " + answer
                ),
                system="You are a critical reviewer. Be concise.",
            )
            text = (resp.get("content") or "").strip()
            if text.upper().startswith("SATISFACTORY"):
                return {"satisfactory": True, "improvements": []}
            improvements = [l.strip("-*1234567890. )") for l in text.splitlines() if l.strip()]
            return {"satisfactory": not improvements, "improvements": improvements[:10]}
        except Exception:
            pass
    improvements = []
    if not answer or len(answer) < 5:
        improvements.append("answer is too short / empty")
    if not prompt:
        improvements.append("no prompt to reflect against")
    return {"satisfactory": len(improvements) == 0, "improvements": improvements}


async def _tool_plan(args: dict) -> dict:
    """Decompose a goal into an ordered plan of sub-steps.

    Usage: plan with goal="write a web scraper that extracts product prices"
    Uses LLM when available, generic fallback when not.
    """
    goal = args.get("goal", "")
    if not goal:
        return {"steps": [], "error": "no goal specified"}
    if default_engine._llm is not None:
        try:
            resp = await default_engine._llm.chat(
                message=(
                    "Break the following goal into a concise, ordered list of "
                    "actionable sub-steps (each one line, no numbering symbols). "
                    "Keep it under 8 steps. Goal: " + goal
                ),
                system="You are a planner. Be practical and concise.",
            )
            text = (resp.get("content") or "").strip()
            steps = [s.strip("0123456789. )−") for s in text.splitlines()]
            steps = [s for s in steps if s]
            if steps:
                return {"steps": steps, "goal": goal}
        except Exception:
            pass
    return {
        "steps": [
            f"Analyze: {goal}",
            "Identify required tools and information",
            "Execute sub-tasks in order",
            "Validate the result",
            "Report final answer",
        ],
        "goal": goal,
    }


# ---------------------------------------------------------------------------
# NEW ADVANCED TOOL FUNCTIONS (Phase 2 — 13 tools)
# ---------------------------------------------------------------------------

async def _tool_log_reader(args: dict) -> dict:
    """Read log files: tail, search by regex, get linewidth."""
    import re
    action = args.get("action", "tail")
    path = args.get("path", "")
    pattern = args.get("pattern", "")
    lines = args.get("lines", 50)
    max_text = args.get("max_text", 8192)
    if not path:
        return {"error": "path is required"}
    try:
        with open(path, errors="replace") as f:
            all_lines = f.readlines()
    except Exception as e:
        return {"error": str(e), "path": path}
    if action == "search":
        if not pattern:
            return {"error": "pattern required for search action"}
        try:
            rx = re.compile(pattern)
            matches = [l.rstrip("\n") for l in all_lines if rx.search(l)]
            return {"action": "search", "path": path, "pattern": pattern,
                    "matches": matches[:500], "count": len(matches)}
        except re.error as e:
            return {"error": f"invalid regex: {e}"}
    elif action == "linewidth":
        return {"action": "linewidth", "path": path,
                "max_width": max((len(l.rstrip()) for l in all_lines), default=0)}
    else:
        tail = all_lines[-lines:] if lines > 0 else all_lines
        text = "".join(tail)


async def _tool_http_request(args: dict) -> dict:
    """Make an HTTP request (GET/POST/PUT/DELETE) with headers and optional body."""
    import json
    import urllib.request
    import urllib.error
    method = args.get("method", "GET").upper()
    url = args.get("url", "")
    headers = args.get("headers", {})
    body = args.get("body", "")
    timeout = args.get("timeout", 30)
    if not url:
        return {"error": "url is required"}
    try:
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str) and body:
            body = body.encode()
        else:
            body = None
        req = urllib.request.Request(url, data=body, headers=headers or None, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode(errors="replace")[:5000]
            try:
                json_data = json.loads(text)
                return {"status": resp.status, "url": url, "json": json_data,
                        "headers": {k: v for k, v in resp.headers.items()}}
            except json.JSONDecodeError:
                return {"status": resp.status, "url": url, "text": text,
                        "headers": {k: v for k, v in resp.headers.items()}}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "status": e.code, "url": url}
    except Exception as e:
        return {"error": f"http_request error: {e}", "url": url}


async def _tool_git_ops(args: dict) -> dict:
    """Git operations: clone, status, log, pull, push, branch, diff."""
    import shutil
    import subprocess
    action = args.get("action", "status")
    path = args.get("path", ".")
    remote = args.get("remote", "origin")
    branch = args.get("branch", "")
    extra = args.get("extra", "")
    if not shutil.which("git"):
        return {"error": "git CLI not found", "available": False}
    try:
        cmd = ["git", "-C", path]
        if action == "clone":
            repo = args.get("repo", "")
            if not repo:
                return {"error": "repo URL required for clone"}
            out = subprocess.run(cmd + ["clone", repo] + (branch and [branch] or []),
                                 capture_output=True, text=True, timeout=300)
            return {"output": out.stdout + out.stderr, "returncode": out.returncode}
        if action in ("push", "pull"):
            if not branch:
                return {"error": "branch required for push/pull"}
            out = subprocess.run(cmd + [action, remote, branch],
                                 capture_output=True, text=True, timeout=120)
            return {"output": out.stdout + out.stderr, "returncode": out.returncode}
        if action == "diff":
            out = subprocess.run(cmd + ["diff", extra] if extra else cmd + ["diff"],
                                 capture_output=True, text=True, timeout=30)
            return {"output": out.stdout[:3000], "returncode": out.returncode}
        if action == "log":
            n = args.get("n", 10)
            out = subprocess.run(cmd + ["log", f"-{n}", "--oneline"],
                                 capture_output=True, text=True, timeout=30)
            return {"output": out.stdout, "returncode": out.returncode}
        if action == "branch":
            opt = args.get("opt", "-a")
            out = subprocess.run(cmd + ["branch", opt], capture_output=True, text=True, timeout=30)
            return {"output": out.stdout, "returncode": out.returncode}
        out = subprocess.run(cmd + [action] + (extra.split() if extra else []),
                             capture_output=True, text=True, timeout=60)
        return {"output": out.stdout + out.stderr, "returncode": out.returncode}
    except Exception as e:
        return {"error": f"git_ops error: {e}"}


async def _tool_email_sender(args: dict) -> dict:
    """Send an email via SMTP."""
    import smtplib
    import email.utils
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    host = args.get("host", "localhost")
    port = args.get("port", 587)
    user = args.get("user", "")
    password = args.get("password", "")
    from_addr = args.get("from", "")
    to = args.get("to", "")
    subject = args.get("subject", "")
    body = args.get("body", "")
    use_tls = args.get("use_tls", True)
    if not all([from_addr, to, subject, body]):
        return {"error": "from, to, subject, and body are required"}
    try:
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP(host, port, timeout=30)
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)
        server.quit()
        return {"status": "sent", "to": to, "subject": subject}
    except Exception as e:
        return {"error": f"email_send error: {e}", "to": to}


async def _tool_archive(args: dict) -> dict:
    """Create or extract archives (zip, tar, tar.gz, tar.bz2)."""
    import shutil
    import tarfile
    import zipfile
    action = args.get("action", "create")
    path = args.get("path", "")
    output = args.get("output", "")
    fmt = args.get("format", "zip")
    if action == "create":
        if not path or not output:
            return {"error": "path and output are required for create"}
        try:
            if fmt == "zip":
                with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, dirs, files in os.walk(path):
                        for f in files:
                            full = os.path.join(root, f)
                            zf.write(full, os.path.relpath(full, os.path.dirname(path)))
                size = os.path.getsize(output)
                return {"action": "create", "format": "zip", "output": output, "size": size}
            with tarfile.open(output, f"w:{fmt.replace('tar', '') or 'gz'}") as tf:
                tf.add(path, arcname=os.path.basename(path))
            size = os.path.getsize(output)
            return {"action": "create", "format": fmt, "output": output, "size": size}
        except Exception as e:
            return {"error": f"archive create error: {e}"}
    if action == "extract":
        if not path or not output:
            return {"error": "path and output are required for extract"}
        try:
            os.makedirs(output, exist_ok=True)
            if path.endswith(".zip"):
                with zipfile.ZipFile(path) as zf:
                    zf.extractall(output)
            else:
                with tarfile.open(path) as tf:
                    tf.extractall(output)
            extracted = []
            for root, dirs, files in os.walk(output):
                for f in files:
                    extracted.append(os.path.relpath(os.path.join(root, f), output))
            return {"action": "extract", "archive": path, "output": output,
                    "files_extracted": len(extracted)}
        except Exception as e:
            return {"error": f"archive extract error: {e}"}
    return {"error": f"unknown archive action: {action}"}


async def _tool_dns_lookup(args: dict) -> dict:
    """DNS lookup: resolve hostnames, reverse DNS, list records."""
    import socket
    import dns.resolver
    import dns.reversename
    action = args.get("action", "resolve")
    hostname = args.get("hostname", "")
    ip = args.get("ip", "")
    record_type = args.get("record_type", "A")
    if action == "resolve":
        if not hostname:
            return {"error": "hostname required"}
        try:
            answers = dns.resolver.resolve(hostname, record_type)
            return {"action": "resolve", "hostname": hostname,
                    "record_type": record_type,
                    "records": [str(r) for r in answers]}
        except dns.resolver.NoAnswer:
            return {"action": "resolve", "hostname": hostname,
                    "record_type": record_type, "records": []}
        except Exception as e:
            return {"error": f"dns lookup error: {e}"}
    if action == "reverse":
        if not ip:
            return {"error": "ip required for reverse lookup"}
        try:
            name = socket.gethostbyaddr(ip)[0]
            return {"action": "reverse", "ip": ip, "hostname": name}
        except Exception as e:
            return {"error": f"reverse DNS error: {e}", "ip": ip}
    if action == "nameservers":
        try:
            ns = dns.resolver.resolve(hostname, "NS")
            return {"action": "nameservers", "hostname": hostname,
                    "nameservers": [str(r) for r in ns]}
        except Exception as e:
            return {"error": f"NS lookup error: {e}"}
    return {"error": f"unknown dns action: {action}"}


async def _tool_template_render(args: dict) -> dict:
    """Render a Jinja2 template string with provided context variables."""
    from jinja2 import Template, Environment, BaseLoader
    template = args.get("template", "")
    context = args.get("context", {})
    if not template:
        return {"error": "template is required"}
    try:
        env = Environment(loader=BaseLoader())
        t = env.from_string(template)
        rendered = t.render(context)
        return {"rendered": rendered, "template_length": len(template),
                "context_keys": list(context.keys())}
    except Exception as e:
        return {"error": f"template_render error: {e}"}


async def _tool_data_viz(args: dict) -> dict:
    """Generate charts (bar, line, pie, scatter, histogram) and save as PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    action = args.get("action", "bar")
    title = args.get("title", "")
    output = args.get("output", "/tmp/moon_chart.png")
    x = args.get("x", [])
    y = args.get("y", [])
    series = args.get("series", {})
    width = args.get("width", 800)
    height = args.get("height", 600)
    try:
        fig, ax = plt.subplots(figsize=(width/100, height/100))
        if action == "bar":
            if series:
                for name, vals in series.items():
                    ax.bar(x, vals, label=name)
                ax.legend()
            else:
                ax.bar(x, y)
        elif action == "line":
            if series:
                for name, vals in series.items():
                    ax.plot(x, vals, label=name)
                ax.legend()
            else:
                ax.plot(x, y)
        elif action == "pie":
            ax.pie(y, labels=x, autopct="%1.1f%%")
        elif action == "scatter":
            ax.scatter(x, y)
        elif action == "histogram":
            ax.hist(y, bins=args.get("bins", 10))
        else:
            return {"error": f"unknown chart action: {action}"}
        if title:
            ax.set_title(title)
        plt.tight_layout()
        plt.savefig(output, dpi=100)
        plt.close()
        size = os.path.getsize(output)
        return {"action": action, "output": output, "size": size,
                "title": title}
    except Exception as e:
        return {"error": f"data_viz error: {e}"}


async def _tool_encryption(args: dict) -> dict:
    """Encrypt/decrypt data and files using Fernet symmetric encryption."""
    from cryptography.fernet import Fernet
    action = args.get("action", "generate_key")
    data = args.get("data", "")
    file_path = args.get("file_path", "")
    output_path = args.get("output_path", "")
    key = args.get("key", "")
    if action == "generate_key":
        k = Fernet.generate_key().decode()
        return {"action": "generate_key", "key": k}
    if action in ("encrypt_text", "decrypt_text"):
        if not data:
            return {"error": "data required"}
        if not key:
            return {"error": "key required"}
        try:
            f = Fernet(key.encode())
            if action == "encrypt_text":
                result = f.encrypt(data.encode()).decode()
            else:
                result = f.decrypt(data.encode()).decode()
            return {"action": action, "result": result}
        except Exception as e:
            return {"error": f"encryption error: {e}"}
    if action in ("encrypt_file", "decrypt_file"):
        if not file_path:
            return {"error": "file_path required"}
        if not key:
            return {"error": "key required"}
        try:
            f = Fernet(key.encode())
            with open(file_path, "rb") as fh:
                content = fh.read()
            if action == "encrypt_file":
                result = f.encrypt(content)
            else:
                result = f.decrypt(content)
            out = output_path or (file_path + ".enc" if action == "encrypt_file" else file_path + ".dec")
            with open(out, "wb") as fh:
                fh.write(result)
            return {"action": action, "input": file_path, "output": out,
                    "size": len(result)}
        except Exception as e:
            return {"error": f"file encryption error: {e}"}
    return {"error": f"unknown encryption action: {action}"}


async def _tool_data_export(args: dict) -> dict:
    """Export data to CSV, JSON, or Excel formats."""
    import csv
    import json
    import openpyxl
    action = args.get("action", "csv")
    data = args.get("data", [])
    output = args.get("output", "/tmp/moon_export.csv")
    sheet_name = args.get("sheet_name", "Sheet1")
    if not isinstance(data, list):
        data = [data] if data else []
    if not data:
        return {"error": "no data to export", "action": action}
    if not output:
        return {"error": "output path required"}
    try:
        if action == "csv":
            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            return {"action": "csv", "output": output, "rows": len(data),
                    "size": os.path.getsize(output)}
        if action == "json":
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return {"action": "json", "output": output, "rows": len(data),
                    "size": os.path.getsize(output)}
        if action == "excel":
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = sheet_name
            if data:
                ws.append(list(data[0].keys()))
                for row in data:
                    ws.append(list(row.values()))
            wb.save(output)
            return {"action": "excel", "output": output, "sheet": sheet_name,
                    "rows": len(data), "size": os.path.getsize(output)}
        return {"error": f"unknown export action: {action}"}
    except Exception as e:
        return {"error": f"data_export error: {e}"}


async def _tool_yaml_ops(args: dict) -> dict:
    """YAML operations: dump (serialize), load (deserialize), parse file."""
    action = args.get("action", "dump")
    data = args.get("data", "")
    yaml_str = args.get("yaml_str", "")
    file_path = args.get("file_path", "")
    if action == "dump":
        try:
            result = yaml.dump(data, default_flow_style=False, allow_unicode=True)
            return {"action": "dump", "yaml": result}
        except Exception as e:
            return {"error": f"yaml dump error: {e}"}
    if action == "load":
        if not yaml_str:
            return {"error": "yaml_str required for load"}
        try:
            result = yaml.safe_load(yaml_str)
            return {"action": "load", "data": result}
        except Exception as e:
            return {"error": f"yaml load error: {e}"}
    if action == "parse":
        if not file_path:
            return {"error": "file_path required for parse"}
        try:
            with open(file_path, encoding="utf-8") as f:
                result = yaml.safe_load(f)
            return {"action": "parse", "file": file_path, "data": result}
        except Exception as e:
            return {"error": f"yaml parse error: {e}"}
    return {"error": f"unknown yaml action: {action}"}


async def _tool_qr_generator(args: dict) -> dict:
    """Generate QR codes and save as PNG images."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
    data = args.get("data", "")
    output = args.get("output", "/tmp/moon_qr.png")
    size = args.get("size", 300)
    border = args.get("border", 4)
    ec = args.get("error_correction", "L")
    ec_map = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
    if not data:
        return {"error": "data is required"}
    try:
        qr = qrcode.QRCode(version=None, box_size=size//50 or 5, border=border,
                            error_correction=ec_map.get(ec, ERROR_CORRECT_L))
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output)
        size_bytes = os.path.getsize(output)
        return {"action": "generate", "output": output, "size": size_bytes,
                "data_length": len(data), "error_correction": ec}
    except Exception as e:
        return {"error": f"qr_generator error: {e}"}


async def _tool_rest_api_framework(args: dict) -> dict:
    """Show information about the ai_rest_api handler and its capabilities as an MCP server with FastAPI."""
    return {
        "action": "info",
        "handler": "ai_rest_api",
        "capabilities": [
            "MCP server protocol over FastAPI",
            "Tool discovery and registration",
            "Agent session management",
            "Message processing with tool-calling",
            "Conversation memory per session",
            "Multi-agent routing",
            "REST API + WebSocket support",
        ],
        "endpoints": [
            {"path": "/api/health", "method": "GET", "description": "Health check"},
            {"path": "/api/moon-agent", "method": "POST", "description": "Process message"},
            {"path": "/api/moon-agent/stream", "method": "POST", "description": "Stream agent response"},
            {"path": "/api/tools", "method": "GET", "description": "List available tools"},
            {"path": "/api/tools/{name}", "method": "POST", "description": "Execute a tool"},
            {"path": "/api/agents", "method": "GET", "description": "List agents"},
            {"path": "/api/agents/{name}", "method": "POST", "description": "Process with specific agent"},
        ],
        "note": "This handler bridges external clients to MOON's agent engine."
    }


# ---------------------------------------------------------------------------
# ORIGINAL MOON TOOLS (ported from /home/meow/Projects/MOON/app/tools/)
# ---------------------------------------------------------------------------

async def _tool_pdf_reader(args: dict) -> dict:
    """Read text from PDF files using pypdf. Extracts all page text."""
    action = args.get("action", "read")
    file_path = args.get("file_path", "")
    max_pages = args.get("max_pages", 50)
    if not file_path:
        return {"error": "file_path is required"}
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"error": "pypdf not installed. Install: pip install pypdf"}
    try:
        reader = PdfReader(file_path)
        pages = len(reader.pages)
        limit = min(max_pages, pages)
        text_parts = []
        for i in range(limit):
            page = reader.pages[i]
            text = page.extract_text() or ""
            text_parts.append(f"--- Page {i+1} ---\n{text}")
        full = "\n\n".join(text_parts)
        return {
            "action": "read",
            "file": file_path,
            "pages_total": pages,
            "pages_read": limit,
            "text": full[:10000],
            "text_truncated": len(full) > 10000,
        }
    except Exception as e:
        return {"error": f"pdf_reader error: {e}", "file": file_path}


async def _tool_ocr(args: dict) -> dict:
    """Extract text from images using pytesseract OCR."""
    action = args.get("action", "extract")
    image_path = args.get("image_path", "")
    lang = args.get("lang", "eng")
    if not image_path:
        return {"error": "image_path is required"}
    try:
        from PIL import Image
    except ImportError:
        return {"error": "Pillow not installed. Install: pip install Pillow"}
    try:
        import pytesseract
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return {
            "action": "extract",
            "image": image_path,
            "language": lang,
            "text": text.strip(),
            "text_length": len(text.strip()),
        }
    except ImportError:
        return {"error": "pytesseract not installed. Install: pip install pytesseract, and ensure tesseract-ocr system package is installed"}
    except Exception as e:
        return {"error": f"ocr error: {e}", "image": image_path}


async def _tool_image_processing(args: dict) -> dict:
    """Image processing operations: info, resize, convert, grayscale, flip, rotate."""
    import os as _os
    action = args.get("action", "info")
    image_path = args.get("image_path", "")
    output_path = args.get("output_path", "")
    width = args.get("width", 0)
    height = args.get("height", 0)
    rotate = args.get("rotate", 0)
    flip = args.get("flip", "")
    grayscale = args.get("grayscale", False)
    format_out = args.get("format", "")
    if not image_path:
        return {"error": "image_path is required"}
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return {"error": "Pillow not installed. Install: pip install Pillow"}
    try:
        img = Image.open(image_path)
        info = {
            "format": img.format,
            "mode": img.mode,
            "size": img.size,
            "width": img.width,
            "height": img.height,
        }
        if action == "info":
            return {"action": "info", "image": image_path, **info}
        result = img
        if action == "resize" and (width or height):
            if width and height:
                result = img.resize((width, height))
            elif width:
                ratio = width / img.width
                result = img.resize((width, int(img.height * ratio)))
            elif height:
                ratio = height / img.height
                result = img.resize((int(img.width * ratio), height))
        elif action == "convert" and format_out:
            result = img.convert("RGB" if format_out.lower() in ("jpg", "jpeg") else img.mode)
        elif action == "grayscale":
            result = ImageOps.grayscale(img)
        elif action == "flip":
            if flip == "horizontal":
                result = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            elif flip == "vertical":
                result = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elif action == "rotate" and rotate:
            result = img.rotate(rotate, expand=True)
        out = output_path or f"/tmp/moon_img_{action}_{_os.path.basename(image_path)}"
        save_fmt = format_out.upper() if format_out else None
        if save_fmt == "JPG":
            if result.mode in ("RGBA", "P"):
                result = result.convert("RGB")
        result.save(out, format=save_fmt)
        return {
            "action": action,
            "input": image_path,
            "output": out,
            "original": info,
            "size": _os.path.getsize(out),
        }
    except Exception as e:
        return {"error": f"image_processing error: {e}", "image": image_path}


async def _tool_browser(args: dict) -> dict:
    """Browser operations: fetch page HTML/text, get status, extract title and links."""
    action = args.get("action", "fetch")
    url = args.get("url", "")
    timeout = args.get("timeout", 30)
    if not url:
        return {"error": "url is required"}
    try:
        import urllib.request
        import urllib.error
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MOON/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            html = resp.read().decode(errors="replace")
            status = resp.status
            title = ""
            links = []
            import re as _re
            m = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
            if m:
                title = _re.sub(r"<[^>]+>", "", m.group(1)).strip()
            for m in _re.finditer(r'href=["\']([^"\']+)["\']', html):
                links.append(m.group(1))
            text = _re.sub(r"<[^>]+>", " ", html)
            text = _re.sub(r"\s+", " ", text).strip()
            return {
                "action": "fetch",
                "url": url,
                "status": status,
                "title": title,
                "links": links[:50],
                "links_count": len(links),
                "text": text[:5000],
                "text_truncated": len(text) > 5000,
            }
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "url": url, "status": e.code}
    except Exception as e:
        return {"error": f"browser error: {e}", "url": url}


async def _tool_preprocess(args: dict) -> dict:
    """Text/data preprocessing: clean, tokenize, normalize, deduplicate, filter."""
    action = args.get("action", "clean")
    text = args.get("text", "")
    data = args.get("data", [])
    lower = args.get("lowercase", True)
    remove_punct = args.get("remove_punctuation", True)
    remove_stopwords = args.get("remove_stopwords", False)
    dedup = args.get("dedup", False)
    min_length = args.get("min_length", 1)
    if action == "clean":
        if not text:
            return {"error": "text required for clean action"}
        import re as _re
        result = text
        if lower:
            result = result.lower()
        if remove_punct:
            result = _re.sub(r"[^\w\s]", " ", result)
        result = _re.sub(r"\s+", " ", result).strip()
        if remove_stopwords:
            stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                         "being", "have", "has", "had", "do", "does", "did", "will",
                         "would", "could", "should", "may", "might", "must", "shall",
                         "can", "need", "dare", "ought", "used", "to", "of", "in",
                         "for", "on", "with", "at", "by", "from", "as", "into",
                         "through", "during", "before", "after", "above", "below",
                         "between", "under", "again", "further", "then", "once",
                         "here", "there", "when", "where", "why", "how", "all",
                         "each", "few", "more", "most", "other", "some", "such",
                         "no", "nor", "not", "only", "own", "same", "so", "than",
                         "too", "very", "just", "and", "but", "if", "or", "because",
                         "until", "while", "about", "against", "between", "into",
                         "through", "during", "before", "after", "above", "below",
                         "up", "down", "out", "off", "over", "under", "again",
                         "further", "then", "once", "i", "me", "my", "myself",
                         "we", "our", "ours", "ourselves", "you", "your", "yours",
                         "yourself", "yourselves", "he", "him", "his", "himself",
                         "she", "her", "hers", "herself", "it", "its", "itself",
                         "they", "them", "their", "theirs", "themselves", "what",
                         "which", "who", "whom", "this", "that", "these", "those",
                         "am", "isn't", "aren't", "wasn't", "weren't", "hasn't",
                         "haven't", "hadn't", "doesn't", "don't", "didn't",
                         "won't", "wouldn't", "shan't", "shouldn't", "can't",
                         "cannot", "couldn't", "mustn't", "let's", "that's",
                         "who's", "what's", "here's", "there's", "when's",
                         "where's", "why's", "how's"}
            words = result.split()
            result = " ".join(w for w in words if w not in stopwords and len(w) >= min_length)
        return {"action": "clean", "original_length": len(text),
                "cleaned_length": len(result), "text": result}
    if action == "tokenize":
        if not text:
            return {"error": "text required for tokenize"}
        import re as _re
        tokens = _re.findall(r"\b\w+\b", text.lower() if lower else text)
        if remove_stopwords:
            stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                         "being", "have", "has", "had", "do", "does", "did", "will",
                         "would", "could", "should", "may", "might", "must", "shall",
                         "can", "need", "dare", "ought", "used", "to", "of", "in",
                         "for", "on", "with", "at", "by", "from", "as", "into",
                         "through", "during", "before", "after", "above", "below",
                         "between", "under", "again", "further", "then", "once",
                         "here", "there", "when", "where", "why", "how", "all",
                         "each", "few", "more", "most", "other", "some", "such",
                         "no", "nor", "not", "only", "own", "same", "so", "than",
                         "too", "very", "just", "and", "but", "if", "or", "because",
                         "until", "while", "about", "i", "me", "my", "myself",
                         "we", "our", "ours", "ourselves", "you", "your", "yours",
                         "yourself", "yourselves", "he", "him", "his", "himself",
                         "she", "her", "hers", "herself", "it", "its", "itself",
                         "they", "them", "their", "theirs", "themselves", "what",
                         "which", "who", "whom", "this", "that", "these", "those",
                         "am", "isn't", "aren't", "wasn't", "weren't", "hasn't",
                         "haven't", "hadn't", "doesn't", "don't", "didn't",
                         "won't", "wouldn't", "shan't", "shouldn't", "can't",
                         "cannot", "couldn't", "mustn't", "let's", "that's",
                         "who's", "what's", "here's", "there's", "when's",
                         "where's", "why's", "how's"}
            tokens = [t for t in tokens if t not in stopwords and len(t) >= min_length]
        if dedup:
            seen = set()
            tokens = [t for t in tokens if not (t in seen or seen.add(t))]
        return {"action": "tokenize", "tokens": tokens, "count": len(tokens)}
    if action == "normalize":
        if not data:
            return {"error": "data required for normalize"}
        if isinstance(data, list) and all(isinstance(x, (int, float)) for x in data):
            mn = min(data)
            mx = max(data)
            if mx == mn:
                return {"action": "normalize", "normalized": [0.5] * len(data)}
            normalized = [(x - mn) / (mx - mn) for x in data]
            return {"action": "normalize", "min": mn, "max": mx,
                    "normalized": normalized}
        return {"error": "normalize requires a list of numbers"}
    if action == "dedupe":
        if not data:
            return {"error": "data required for dedupe"}
        if isinstance(data, list):
            seen = set()
            result = []
            for item in data:
                key = str(item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return {"action": "dedupe", "original_count": len(data),
                    "deduped_count": len(result), "data": result}
        return {"error": "dedupe requires a list"}
    return {"error": f"unknown preprocess action: {action}"}


# ---------------------------------------------------------------------------
# ADDITIONAL CYBER/RED-TEAM TOOL FUNCTIONS
# ---------------------------------------------------------------------------


async def _tool_geoip_lookup(args: dict) -> dict:
    """IP geolocation and ASN intelligence via ip-api.com (free, no key)."""
    ip = args.get("ip", "")
    fields = args.get("fields", "continent,continentCode,country,countryCode,region,regionName,city,district,zip,lat,lon,timezone,isp,org,as,query")
    if not ip:
        return {"error": "ip is required"}
    try:
        url = f"http://ip-api.com/json/{ip}?fields={fields}"
        req = urllib.request.Request(url, headers={"User-Agent": "MOON/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "success":
            return {"error": data.get("message", "ip-api failed"), "ip": ip}
        return {"ip": ip, "status": "success", "data": data}
    except Exception as e:
        return {"error": f"geoip_lookup error: {e}", "ip": ip}


async def _tool_password_strength(args: dict) -> dict:
    """Analyze password strength: entropy, zxcvbn score, breach check hint."""
    password = args.get("password", "")
    check_breach = args.get("check_breach", False)
    if not password:
        return {"error": "password is required"}
    length = len(password)
    has_upper = bool(re.search(r"[A-Z]", password))
    has_lower = bool(re.search(r"[a-z]", password))
    has_digit = bool(re.search(r"\d", password))
    has_special = bool(re.search(r"[^A-Za-z0-9]", password))
    pool = 0
    pool += 26 if has_lower else 0
    pool += 26 if has_upper else 0
    pool += 10 if has_digit else 0
    pool += 33 if has_special else 0
    if pool == 0:
        entropy = 0
    else:
        entropy = length * math.log2(pool)
    entropy_bits = round(entropy, 1)
    if entropy_bits >= 60:
        rating = "very_strong"
    elif entropy_bits >= 40:
        rating = "strong"
    elif entropy_bits >= 30:
        rating = "moderate"
    elif entropy_bits >= 20:
        rating = "weak"
    else:
        rating = "very_weak"
    zxcvbn_score = None
    zxcvbn_feedback = None
    try:
        import zxcvbn
        z = zxcvbn.zxcvbn(password)
        zxcvbn_score = z["score"]
        zxcvbn_feedback = z["feedback"]
        if zxcvbn_score is not None and zxcvbn_score > 2:
            rating = max(rating, ["very_weak", "weak", "moderate", "strong", "very_strong"][zxcvbn_score])
    except ImportError:
        pass
    breach_info = None
    if check_breach:
        breach_info = {"note": "HIBP k-anonymity check requires API key. Set breach_api_key in config."}
    return {
        "password_length": length,
        "entropy_bits": entropy_bits,
        "char_sets": {"upper": has_upper, "lower": has_lower, "digit": has_digit, "special": has_special},
        "rating": rating,
        "zxcvbn_score": zxcvbn_score,
        "zxcvbn_feedback": zxcvbn_feedback,
        "breach_check": breach_info,
    }


async def _tool_steganography(args: dict) -> dict:
    """LSB steganography: hide or extract text in PNG images using Pillow."""
    action = args.get("action", "hide")
    image_path = args.get("image_path", "")
    message = args.get("message", "")
    output_path = args.get("output_path", "")
    extract_bits = args.get("extract_bits", 1)
    if action == "hide":
        if not image_path or not message:
            return {"error": "image_path and message required for hide"}
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            pixels = img.load()
            msg_bits = "".join(f"{ord(c):08b}" for c in message) + "00000000"
            max_bytes = (img.width * img.height * 3) // 8
            if len(msg_bits) > max_bytes:
                return {"error": f"message too long: {len(msg_bits)} bits, max {max_bytes}"}
            bit_idx = 0
            for y in range(img.height):
                for x in range(img.width):
                    if bit_idx >= len(msg_bits):
                        break
                    r, g, b = pixels[x, y]
                    r = (r & 0xFE) | int(msg_bits[bit_idx])
                    bit_idx += 1
                    if bit_idx < len(msg_bits):
                        g = (g & 0xFE) | int(msg_bits[bit_idx])
                        bit_idx += 1
                    if bit_idx < len(msg_bits):
                        b = (b & 0xFE) | int(msg_bits[bit_idx])
                        bit_idx += 1
                    pixels[x, y] = (r, g, b)
            out = output_path or "/tmp/moon_stego_hidden.png"
            img.save(out)
            return {"action": "hide", "message_length": len(message), "output": out}
        except Exception as e:
            return {"error": f"steganography hide error: {e}"}
    elif action == "extract":
        if not image_path:
            return {"error": "image_path required for extract"}
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            pixels = img.load()
            bits = []
            for y in range(img.height):
                for x in range(img.width):
                    r, g, b = pixels[x, y]
                    if extract_bits >= 1:
                        bits.append(str(r & 1))
                    if extract_bits >= 2:
                        bits.append(str(g & 1))
                    if extract_bits >= 3:
                        bits.append(str(b & 1))
            bit_str = "".join(bits)
            chars = []
            for i in range(0, len(bit_str) - 7, 8):
                byte = bit_str[i:i+8]
                if byte == "00000000":
                    break
                chars.append(chr(int(byte, 2)))
            text = "".join(chars)
            return {"action": "extract", "extracted_text": text, "bits_collected": len(bits)}
        except Exception as e:
            return {"error": f"steganography extract error: {e}"}
    return {"error": f"unknown stego action: {action}"}


async def _tool_cve_search(args: dict) -> dict:
    """Search CVE database by keyword/product via NVD API (free, no key)."""
    keyword = args.get("keyword", "")
    cve_id = args.get("cve_id", "")
    limit = min(args.get("limit", 20), 200)
    try:
        if cve_id:
            url = f"https://services.nvd.nist.gov/rest/json/cves?cveId={cve_id}"
        elif keyword:
            url = f"https://services.nvd.nist.gov/rest/json/cves?keywordSearch={urllib.parse.quote(keyword)}&resultsPerPage={limit}"
        else:
            return {"error": "keyword or cve_id required"}
        req = urllib.request.Request(url, headers={"User-Agent": "MOON/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        total = data.get("totalResults", 0)
        cves = []
        for vuln in data.get("vulnerabilities", [])[:limit]:
            cve = vuln.get("cve", {})
            cve_id_v = cve.get("id", "")
            desc = ""
            for ds in cve.get("descriptions", []):
                if ds.get("lang") == "en":
                    desc = ds.get("value", "")
                    break
            severity = ""
            for metric in cve.get("metrics", {}).get("cvssMetricV31", []) + cve.get("metrics", {}).get("cvssMetricV30", []):
                severity = metric.get("cvssData", {}).get("baseSeverity", "")
                break
            cves.append({"id": cve_id_v, "description": desc[:500], "severity": severity})
        return {"keyword": keyword, "cve_id": cve_id, "total": total, "cves": cves, "count": len(cves)}
    except Exception as e:
        return {"error": f"cve_search error: {e}", "keyword": keyword}


async def _tool_malware_scan(args: dict) -> dict:
    """Malware scanning: compute file hash, check against known hash lists, YARA-rule scan."""
    action = args.get("action", "scan")
    file_path = args.get("file_path", "")
    yara_rules = args.get("yara_rules", "")
    known_hashes = args.get("known_hashes", "")
    if action == "hash":
        if not file_path:
            return {"error": "file_path required for hash"}
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            sha256 = h.hexdigest()
            md5 = hashlib.md5(open(file_path, "rb").read()).hexdigest()
            sha1 = hashlib.sha1(open(file_path, "rb").read()).hexdigest()
            return {"file": file_path, "sha256": sha256, "md5": md5, "sha1": sha1, "size": os.path.getsize(file_path)}
        except Exception as e:
            return {"error": f"hash error: {e}"}
    if action == "scan":
        if not file_path and not yara_rules:
            return {"error": "file_path or yara_rules required for scan"}
        results = {"file": file_path, "checks": []}
        if known_hashes:
            try:
                hash_set = {h.strip().lower() for h in known_hashes.split(",") if h.strip()}
                h = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                file_hash = h.hexdigest().lower()
                if file_hash in hash_set:
                    results["checks"].append({"check": "known_hash_match", "result": "FOUND", "hash": file_hash})
                else:
                    results["checks"].append({"check": "known_hash_match", "result": "clean", "hash": file_hash})
            except Exception as e:
                results["checks"].append({"check": "known_hash_match", "error": str(e)})
        if yara_rules and file_path:
            try:
                import yara
                rules = yara.compile(source=yara_rules)
                matches = rules.match(file_path)
                results["checks"].append({"check": "yara", "matches": [str(m) for m in matches], "count": len(matches)})
            except ImportError:
                results["checks"].append({"check": "yara", "error": "yara-python not installed"})
            except Exception as e:
                results["checks"].append({"check": "yara", "error": str(e)})
        if not results["checks"]:
            return {"error": "no scans performed", "file": file_path}
        return results
    return {"error": f"unknown malware_scan action: {action}"}


async def _tool_threat_intel(args: dict) -> dict:
    """Threat intelligence lookup: IP reputation via AbuseIPDB (requires key)."""
    ip = args.get("ip", "")
    api_key = args.get("api_key", "")
    api_url = args.get("api_url", "https://api.abuseipdb.com/api/v2")
    if not ip:
        return {"error": "ip is required"}
    if not api_key:
        return {"error": "api_key required for AbuseIPDB. Use 'demo' for limited testing."}
    try:
        headers = {"Key": api_key, "Accept": "application/json"}
        url = f"{api_url}/check"
        data = urllib.parse.urlencode({"ipAddress": ip, "maxAgeInDays": "90"}).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        data_v = result.get("data", {})
        return {
            "ip": ip,
            "abuse Confidence": data_v.get("abuseConfidenceScore"),
            "reputation": data_v.get("reputation"),
            "isWhitelisted": data_v.get("isWhitelisted"),
            "totalReports": data_v.get("totalReports"),
            "numReports": len(data_v.get("reports", [])),
        }
    except Exception as e:
        return {"error": f"threat_intel error: {e}", "ip": ip}


async def _tool_authorized_scan(args: dict) -> dict:
    """Authorized network scan: port scan with explicit target authorization and config.

    IMPORTANT: Only use against targets you OWN or have explicit written permission to scan.
    Unauthorized scanning is illegal in most jurisdictions.
    """
    target = args.get("target", "")
    ports = args.get("ports", "22,80,443,8080,8443")
    scan_type = args.get("scan_type", "connect")
    config = args.get("config", "{}")
    confirmation = args.get("confirmation", "")
    if not target:
        return {"error": "target is required", "legal": "Only scan targets you own or have explicit written permission for."}
    if confirmation != "I_CONFIRM_AUTHORIZED":
        return {"error": "confirmation='I_CONFIRM_AUTHORIZED' required to proceed", "legal": "Unauthorized scanning is illegal."}
    try:
        config_obj = json.loads(config) if config else {}
        timeout = config_obj.get("timeout", 2)
        results = {"target": target, "ports_requested": ports, "scan_type": scan_type, "authorized": True, "open_ports": []}
        port_list = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
        for port in port_list:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock_err = sock.connect_ex((target, port))
                if sock_err == 0:
                    results["open_ports"].append({"port": port, "state": "open"})
                sock.close()
            except Exception:
                pass
        return results
    except Exception as e:
        return {"error": f"authorized_scan error: {e}", "target": target}


async def _tool_recon_report(args: dict) -> dict:
    """Generate recon/vulnerability scan report in markdown or HTML format."""
    action = args.get("action", "generate")
    findings = args.get("findings", "[]")
    format_type = args.get("format", "markdown")
    title = args.get("title", "MOON Recon Report")
    output_path = args.get("output_path", "")
    try:
        items = json.loads(findings) if isinstance(findings, str) else findings
    except Exception:
        items = []
    timestamp = dt.now().isoformat()
    if format_type == "markdown":
        md = f"# {title}\n\n**Generated**: {timestamp}\n\n## Summary\n\n| Category | Count |\n|----------|-------|\n"
        cats = {}
        for f in items:
            cat = f.get("category", "general")
            cats[cat] = cats.get(cat, 0) + 1
        for cat, cnt in cats.items():
            md += f"| {cat} | {cnt} |\n"
        md += "\n## Findings\n\n"
        for i, f in enumerate(items, 1):
            sev = f.get("severity", "info")
            md += f"### {i}. {f.get('title', 'Finding')} `[{sev}]`\n\n"
            md += f"**Host**: {f.get('host', 'N/A')}  \n"
            md += f"**Port**: {f.get('port', 'N/A')}  \n"
            md += f"**Description**: {f.get('description', '')}\n\n"
            md += f"**Recommendation**: {f.get('recommendation', '')}\n\n---\n\n"
        md += f"\n## Footer\n\nReport generated by MOON Agent on {timestamp}.\n"
        if output_path:
            with open(output_path, "w") as f:
                f.write(md)
            return {"action": "generate", "format": "markdown", "output": output_path, "size": os.path.getsize(output_path), "findings": len(items)}
        return {"action": "generate", "format": "markdown", "report": md, "findings": len(items)}
    elif format_type == "html":
        html = f"<html><head><title>{title}</title><style>body{{font-family:sans-serif;}} table{{border-collapse:collapse;}} th,td{{border:1px solid #333;padding:4px;}}</style></head><body>"
        html += f"<h1>{title}</h1><p><i>Generated: {timestamp}</i></p>"
        html += "<h2>Summary</h2><table><tr><th>Category</th><th>Count</th></tr>"
        for cat, cnt in cats.items():
            html += f"<tr><td>{cat}</td><td>{cnt}</td></tr>"
        html += "</table><h2>Findings</h2>"
        for i, f in enumerate(items, 1):
            sev = f.get("severity", "info")
            html += f"<h3>{i}. {f.get('title', 'Finding')} <span style='color:red'>[{sev}]</span></h3>"
            html += f"<p><b>Host:</b> {f.get('host', 'N/A')}<br><b>Port:</b> {f.get('port', 'N/A')}<br><b>Description:</b> {f.get('description', '')}<br><b>Recommendation:</b> {f.get('recommendation', '')}</p>"
        html += f"<hr><p>Report generated by MOON Agent on {timestamp}.</p></body></html>"
        if output_path:
            with open(output_path, "w") as f:
                f.write(html)
            return {"action": "generate", "format": "html", "output": output_path, "size": os.path.getsize(output_path)}
        return {"action": "generate", "format": "html", "report": html, "findings": len(items)}
    return {"error": f"unknown report format: {format_type}"}


async def _tool_packet_capture(args: dict) -> dict:
    """Live packet capture via scapy: capture N packets, filter by protocol, save to PCAP.

    Requires root/elevated privileges for full packet capture.
    """
    action = args.get("action", "capture")
    count = args.get("count", 100)
    filter_expr = args.get("filter", "")
    output_path = args.get("output_path", "")
    interface = args.get("interface", "")
    if action == "capture":
        try:
            from scapy.all import sniff, wrpcap, TCP, UDP, IP
            caps = []
            def pkt_handler(p):
                caps.append(p)
                if len(caps) >= count:
                    raise StopCapture()
            class StopCapture(Exception):
                pass
            try:
                sniff(iface=interface or None, filter=filter_expr, prn=pkt_handler, count=count, timeout=args.get("timeout", 30))
            except StopCapture:
                pass
            summary = []
            for p in caps:
                info = {"summary": p.summary()}
                if IP in p:
                    info["src_ip"] = p[IP].src
                    info["dst_ip"] = p[IP].dst
                    if TCP in p:
                        info["proto"] = "TCP"
                        info["src_port"] = p[TCP].sport
                        info["dst_port"] = p[TCP].dport
                    elif UDP in p:
                        info["proto"] = "UDP"
                        info["src_port"] = p[UDP].sport
                        info["dst_port"] = p[UDP].dport
                    else:
                        info["proto"] = "IP"
                summary.append(info)
            out = output_path or "/tmp/moon_capture.pcap"
            wrpcap(out, caps)
            return {"action": "capture", "packets": len(caps), "output": out, "filter": filter_expr, "summary": summary[:100]}
        except ImportError:
            return {"error": "scapy not installed. Install: pip install scapy", "action": "capture"}
        except PermissionError:
            return {"error": "Permission denied — packet capture requires root/sudo privileges", "action": "capture"}
        except Exception as e:
            return {"error": f"packet_capture error: {e}", "action": "capture"}
    elif action == "read":
        if not file_path:
            return {"error": "file_path required for read"}
        try:
            from scapy.all import rdpcap
            pkts = rdpcap(file_path)
            summary = [{"index": i, "summary": p.summary()} for i, p in enumerate(pkts[:100])]
            return {"action": "read", "file": file_path, "packets": len(pkts), "summary": summary}
        except ImportError:
            return {"error": "scapy not installed"}
        except Exception as e:
            return {"error": f"pcap read error: {e}"}
    return {"error": f"unknown packet_capture action: {action}"}


async def _tool_port_scanner(args: dict) -> dict:
    """Port scanning via python-nmap: TCP connect scan, service detection, OS guess.

    Requires nmap installed on the system. Only scan targets you own or have permission to scan.
    """
    target = args.get("target", "")
    ports = args.get("ports", "22,80,443,8080,8443")
    scan_type = args.get("scan_type", "connect")
    service_detect = args.get("service_detect", False)
    os_detect = args.get("os_detect", False)
    confirmation = args.get("confirmation", "")
    if not target:
        return {"error": "target is required"}
    if confirmation != "I_CONFIRM_AUTHORIZED":
        return {"error": "confirmation='I_CONFIRM_AUTHORIZED' required to proceed"}
    try:
        import nmap
        nm = nmap.PortScanner()
        port_spec = ports if ports else "22,80,443"
        args_nmap = f"-p {port_spec}"
        if service_detect:
            args_nmap += " -sV"
        if os_detect and target.count(".") == 3:
            args_nmap += " -O"
        if scan_type == "syn":
            args_nmap += " -sS"
        elif scan_type == "udp":
            args_nmap += " -sU"
        nm.scan(target, ports, arguments=args_nmap)
        hosts = []
        for host in nm.all_hosts():
            h_info = {"host": host, "state": nm[host].state(), "protocols": {}}
            for proto in nm[host].all_protocols():
                ports_v = nm[host][proto].keys()
                proto_ports = []
                for port in sorted(ports_v):
                    port_info = nm[host][proto][port]
                    proto_ports.append({
                        "port": port,
                        "state": port_info.get("state", ""),
                        "service": port_info.get("name", ""),
                        "version": port_info.get("version", ""),
                    })
                h_info["protocols"][proto] = proto_ports
            hosts.append(h_info)
        return {"target": target, "scan_type": scan_type, "hosts": hosts, "scan_time": nm.scanstats().get("elapsed", "")}
    except ImportError:
        return {"error": "python-nmap not installed. Install: pip install python-nmap", "target": target}
    except Exception as e:
        return {"error": f"port_scanner error: {e}", "target": target}


# ---------------------------------------------------------------------------
# Register built-in tools
# ---------------------------------------------------------------------------
default_engine.register_tool("system_info", _tool_system_info)
default_engine.register_tool("memory_read", _tool_memory_read)
default_engine.register_tool("memory_write", _tool_memory_write)
default_engine.register_tool("network_scan", _tool_network_scan)
default_engine.register_tool("security_tools", _tool_security_tools)
default_engine.register_tool("file_read", _tool_file_read)
default_engine.register_tool("file_write", _tool_file_write)
default_engine.register_tool("shell", _tool_shell)
default_engine.register_tool("web_search", _tool_web_search)
default_engine.register_tool("web_extract", _tool_web_extract)
default_engine.register_tool("python_executor", _tool_python_executor)
default_engine.register_tool("system_command", _tool_system_command)
default_engine.register_tool("docker", _tool_docker)
default_engine.register_tool("github_feed", _tool_github_feed)
default_engine.register_tool("tool_acquire", _tool_tool_acquire)
default_engine.register_tool("self_evolve", _tool_self_evolve)
default_engine.register_tool("reflect", _tool_reflect)
default_engine.register_tool("plan", _tool_plan)
default_engine.register_tool("log_reader", _tool_log_reader)
default_engine.register_tool("http_request", _tool_http_request)
default_engine.register_tool("git_ops", _tool_git_ops)
default_engine.register_tool("email_sender", _tool_email_sender)
default_engine.register_tool("archive", _tool_archive)
default_engine.register_tool("dns_lookup", _tool_dns_lookup)
default_engine.register_tool("template_render", _tool_template_render)
default_engine.register_tool("data_viz", _tool_data_viz)
default_engine.register_tool("encryption", _tool_encryption)
default_engine.register_tool("data_export", _tool_data_export)
default_engine.register_tool("yaml_ops", _tool_yaml_ops)
default_engine.register_tool("qr_generator", _tool_qr_generator)
default_engine.register_tool("rest_api_framework", _tool_rest_api_framework)
default_engine.register_tool("pdf_reader", _tool_pdf_reader)
default_engine.register_tool("ocr", _tool_ocr)
default_engine.register_tool("image_processing", _tool_image_processing)
default_engine.register_tool("browser", _tool_browser)
default_engine.register_tool("preprocess", _tool_preprocess)

# Register additional red-team / offensive-security tools
default_engine.register_tool("geoip_lookup", _tool_geoip_lookup)
default_engine.register_tool("password_strength", _tool_password_strength)
default_engine.register_tool("steganography", _tool_steganography)
default_engine.register_tool("cve_search", _tool_cve_search)
default_engine.register_tool("malware_scan", _tool_malware_scan)
default_engine.register_tool("threat_intel", _tool_threat_intel)
default_engine.register_tool("authorized_scan", _tool_authorized_scan)
default_engine.register_tool("recon_report", _tool_recon_report)
default_engine.register_tool("packet_capture", _tool_packet_capture)
default_engine.register_tool("port_scanner", _tool_port_scanner)

# ---------------------------------------------------------------------------
# ADDITIONAL CYBER/RED-TEAM TOOL FUNCTIONS
# ---------------------------------------------------------------------------

async def _tool_ssh_client(args: dict) -> dict:
    """SSH remote execution: connect, run commands, transfer files via SFTP.

    Args:
        action: "connect", "exec", "sftp_upload", "sftp_download", "close"
        host: SSH server hostname or IP
        port: SSH port (default 22)
        username: SSH username
        password: SSH password (or use key_file)
        key_file: Path to private key file
        key_pass: Passphrase for encrypted key
        command: Shell command to execute (for action="exec")
        remote_path: Remote file path (for sftp operations)
        local_path: Local file path (for sftp operations)
        timeout: Connection timeout in seconds
    """
    action = args.get("action", "exec")
    host = args.get("host", "")
    port = int(args.get("port", 22))
    username = args.get("username", "")
    password = args.get("password", "")
    key_file = args.get("key_file", "")
    key_pass = args.get("key_pass", "")
    command = args.get("command", "")
    remote_path = args.get("remote_path", "")
    local_path = args.get("local_path", "")
    timeout = int(args.get("timeout", 30))

    if not host:
        return {"error": "host is required"}
    if not username:
        return {"error": "username is required"}

    import paramiko

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()

        connect_kwargs = {"hostname": host, "port": port, "username": username, "timeout": timeout}
        if key_file:
            key = paramiko.RSAKey.from_private_key_file(key_file, password=key_pass) if key_pass else paramiko.RSAKey.from_private_key_file(key_file)
            connect_kwargs["pkey"] = key
        elif password:
            connect_kwargs["password"] = password

        client.connect(**connect_kwargs)
        transport = client.get_transport()

        if action == "connect":
            return {"status": "connected", "host": host, "port": port, "username": username}
        elif action == "exec":
            if not command:
                client.close()
                return {"error": "command required for exec action"}
            stdin, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            client.close()
            return {"action": "exec", "command": command, "output": out, "error": err, "exit_code": exit_code}
        elif action == "sftp_upload":
            if not remote_path or not local_path:
                client.close()
                return {"error": "remote_path and local_path required for sftp_upload"}
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.put(local_path, remote_path)
            sftp.close()
            client.close()
            return {"action": "sftp_upload", "local": local_path, "remote": remote_path, "status": "uploaded"}
        elif action == "sftp_download":
            if not remote_path or not local_path:
                client.close()
                return {"error": "remote_path and local_path required for sftp_download"}
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.get(remote_path, local_path)
            sftp.close()
            client.close()
            return {"action": "sftp_download", "remote": remote_path, "local": local_path, "status": "downloaded"}
        elif action == "close":
            client.close()
            return {"status": "closed", "host": host}
        else:
            client.close()
            return {"error": f"unknown ssh action: {action}"}
    except paramiko.AuthenticationException:
        return {"error": "SSH authentication failed", "host": host, "username": username}
    except paramiko.SSHException as e:
        return {"error": f"SSH error: {e}", "host": host}
    except FileNotFoundError as e:
        return {"error": f"Key file not found: {e}", "key_file": key_file}
    except Exception as e:
        return {"error": f"ssh_client error: {e}", "host": host, "action": action}


default_engine.register_tool("ssh_client", _tool_ssh_client)
if __name__ == "__main__":
    import asyncio

    async def demo():
        print("╔══════════════════════════════════════════╗")
        print("║  MOON AGENT — STANDALONE DEMO        ║")
        print("╚══════════════════════════════════════════╝")
        print()

        # List agents
        print("=== Registered Agents ===")
        for a in default_engine.list_agents():
            print(f"  [{a['name']}] {a['description'][:60]}")
        print()

        # Test agent: prefix parsing
        print("=== Agent Prefix Parsing ===")
        tests = [
            "agent:code write a hello world function",
            "agent:security scan this network",
            "agent:research find information about AI",
            "hello moon_twin, how are you?",
            "agent:unknown test",
        ]
        for t in tests:
            agent_name, remaining = default_engine.parse_agent_prefix(t)
            selected = default_engine.select_agent(t)
            print(f"  '{t[:50]}' → agent={agent_name or selected.name}, remaining='{remaining[:40]}'")
        print()

        # Test intent routing
        print("=== Intent Routing ===")
        routing_tests = [
            "write a python script to scan ports",
            "find vulnerabilities in this system",
            "search for recent AI papers",
            "speak the answer out loud",
            "restart the moon_twin service",
            "draw a logo for my app",
            "check system health",
            "what is the weather today?",
        ]
        for q in routing_tests:
            agent = route_intent(q)
            print(f"  '{q[:50]}' → {agent}")
        print()

        # Test tool execution
        print("=== Tool Execution ===")
        result = await default_engine.run_tool("system_info", {})
        print(f"  system_info: {result}")
        print()

        # Test full message processing
        print("=== Full Message Processing ===")
        result = await default_engine.process_message(
            "agent:code write a function to sort a list",
            session_id="demo-session",
        )
        print(f"  Agent: {result['agent']}")
        print(f"  Message: {result['message']}")
        print(f"  Session: {result['session_id']}")
        print()

        # Test API endpoint
        print("=== API Endpoint Simulation ===")
        api_result = api_agent_process({
            "message": "agent:research find information about quantum computing",
            "session_id": "api-test",
        })
        print(f"  API result: agent={api_result['agent']}, session={api_result['session_id']}")
        print()

    asyncio.run(demo())
