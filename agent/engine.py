"""
MOON Agent — standalone agent engine with persona injection,
per-prompt agent selection (agent: prefix), intent→agent routing,
and /api/moon-agent integration endpoint.
"""

from __future__ import annotations

import asyncio
import re
import json
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
                    "command": {"type": "string", "description": "Shell command to execute."},
                },
                "required": ["command"],
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

        for name in tool_names:
            handler = self._tool_handlers.get(name)
            if handler:
                schema = schemas.get(name, {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                })
                defs.append(
                    tool_def(
                        name=name,
                        description=f"Execute the '{name}' tool. {schema.get('description', '')}",
                        parameters=schema,
                    )
                )
        return defs

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
            steps = [s.strip("0123456789. )-") for s in text.splitlines()]
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


# Register built-in tools
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


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

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
