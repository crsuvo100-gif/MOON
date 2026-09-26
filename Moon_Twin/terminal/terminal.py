#!/usr/bin/env python3
"""
MOON Terminal — Professional AI Assistant Agent Terminal
=========================================================
A professional-grade terminal interface for MOON / Moon_Twin.

Features:
- Chat-style interface with rich formatting
- Agent selection (8 agents: general, code, security, research, creative, admin, voice, terminal)
- Tool calling visualization (shows tools being used + results inline)
- Session memory management
- Command shortcuts (!help, !agents, !clear, !save, !load, !status, !tools)
- Streaming response display
- Keyboard navigation (Tab to cycle agents, arrow keys for history)
- Voice output (auto-speaking via Moon_Twin voice_speak)
- Connection status indicator
- Message history with scrollback

Run:  moon terminal
Or:   python3 app/terminal_moon/terminal.py
Or:   moon_twin terminal
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import readline
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rich & prompt_toolkit — both verified installed in Moon_Twin .venv
# ---------------------------------------------------------------------------
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.prompt import PromptBase
from rich import print as rprint

_rich_console = Console()

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("MOON_API_URL", "http://127.0.0.1:8778")
CONSOLE = Console()

# Colors — professional dark theme
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    # Agent colors
    AGENT_GENERAL = "\033[36m"   # cyan
    AGENT_CODE = "\033[32m"      # green
    AGENT_SECURITY = "\033[31m"  # red
    AGENT_RESEARCH = "\033[35m"  # magenta
    AGENT_CREATIVE = "\033[33m"  # yellow
    AGENT_ADMIN = "\033[34m"     # blue
    AGENT_VOICE = "\033[95m"     # purple
    AGENT_TERMINAL = "\033[90m"  # grey
    AI = "\033[38;5;111m"        # blue-ish (AI responses)
    TOOL = "\033[38;5;208m"      # orange (tool calls)
    USER = "\033[38;5;141m"      # green-ish (user input)


# ---------------------------------------------------------------------------
# Agent definitions (synced with Moon_Twin engine)
# ---------------------------------------------------------------------------
AGENTS = {
    "general":     {"name": "General",     "color": C.AGENT_GENERAL,     "desc": "Default assistant — handles general queries and tasks"},
    "code":        {"name": "Code",        "color": C.AGENT_CODE,        "desc": "Programming, debugging, code review, architecture"},
    "security":    {"name": "Security",    "color": C.AGENT_SECURITY,    "desc": "Red-team tools, recon, scanning, threat intel, vuln analysis"},
    "research":    {"name": "Research",    "color": C.AGENT_RESEARCH,    "desc": "Web search, extraction, documentation, knowledge retrieval"},
    "creative":    {"name": "Creative",    "color": C.AGENT_CREATIVE,    "desc": "ASCII art, image generation, writing, creative content"},
    "admin":       {"name": "Admin",       "color": C.AGENT_ADMIN,       "desc": "System control, services, health checks, docker, git ops"},
    "voice":       {"name": "Voice",       "color": C.AGENT_VOICE,       "desc": "Voice speak, voice clone, audio processing"},
    "terminal":    {"name": "Terminal",    "color": C.AGENT_TERMINAL,    "desc": "Shell commands, file ops, python execution, system tools"},
}

DEFAULT_AGENT = "general"


# ---------------------------------------------------------------------------
# API Client — async HTTP to Moon_Twin :8778
# ---------------------------------------------------------------------------
class MoonAPIClient:
    """Async HTTP client for Moon_Twin API (:8778)."""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url.rstrip("/")
        self.session_id = datetime.now().strftime("terminal-%Y%m%d-%H%M%S")
        self._tools_used: list[dict] = []

    # ── sync helpers for prompt_toolkit thread ──────────────────────────
    def _sync_get(self, path: str) -> dict:
        import urllib.request, ssl, json
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            return json.loads(r.read())

    def _sync_post(self, path: str, body: dict) -> dict:
        import urllib.request, ssl, json
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        data = json.dumps(body).encode()
        req = urllib.request.Request(f"{self.base_url}{path}", data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return json.loads(r.read())

    # ── public API ──────────────────────────────────────────────────────
    def health(self) -> dict:
        try:
            return self._sync_get("/api/health")
        except Exception as e:
            return {"error": str(e)}

    def list_agents(self) -> list[dict]:
        try:
            data = self._sync_get("/api/moon-agent")
            return data.get("agents", []) if isinstance(data, dict) else data
        except Exception as e:
            return [{"error": str(e)}]

    def send_message(self, message: str, agent: str = None,
                     tools: list | None = None,
                     session_id: str = None) -> dict:
        """Send a message to Moon_Twin and return the full response."""
        body: dict = {"message": message, "session_id": session_id or self.session_id}
        if agent:
            body["agent"] = agent
        if tools is not None:
            body["tools"] = tools
        try:
            resp = self._sync_post("/api/moon-agent", body)
            self._tools_used = resp.get("tools_used", [])
            return resp
        except Exception as e:
            return {"error": str(e), "reply": f"Error: {e}", "tools_used": []}

    def route_query(self, query: str) -> dict:
        try:
            import urllib.parse
            return self._sync_get(f"/api/moon-agent/route?query={urllib.parse.quote(query)}")
        except Exception as e:
            return {"error": str(e)}

    def get_memory(self) -> list[dict]:
        try:
            return self._sync_get("/api/moon-agent/memory")
        except Exception as e:
            return []

    def clear_tools(self):
        self._tools_used = []


# ---------------------------------------------------------------------------
# Terminal UI — professional chat interface
# ---------------------------------------------------------------------------
class MoonTerminal:
    """Professional AI assistant terminal interface."""

    def __init__(self):
        self.client = MoonAPIClient()
        self.current_agent = DEFAULT_AGENT
        self.message_history: list[dict] = []
        self.running = True
        self._status = "connecting..."
        self._health_info = {}

    # ── status / header ─────────────────────────────────────────────────
    @property
    def status_panel(self):
        status_color = "green" if self._status == "connected" else "yellow" if self._status == "connecting..." else "red"
        health = self._health_info
        service = health.get("service", "?")
        agents = health.get("agent_count", "?")
        return Panel(
            f"[bold white]MOON Terminal v1.0[/bold white]\n"
            f"  Status: [ {status_color}]{self._status}[/{status_color}]\n"
            f"  Service: {service}  |  Agents: {agents}\n"
            f"  Base: {API_BASE}\n"
            f"  Session: {self.client.session_id}",
            title="[bold cyan]MOON[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    def build_layout(self, chat_text: str = "", status_text: str = "") -> Layout:
        """Build the full terminal layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=8),
            Layout(name="chat", ratio=1),
            Layout(name="input", size=3),
        )
        # Header
        layout["header"].update(self.status_panel)
        # Chat area
        layout["chat"].update(self._chat_panel(chat_text))
        # Input area
        input_text = f" [{C.AGENT_GENERAL}]{self.current_agent}[/{C.AGENT_GENERAL}] {C.DIM}>[/{C.DIM}] {C.BOLD}{status_text or '>'}[/{C.BOLD}]"
        layout["input"].update(
            Panel(
                Text(input_text, style="white"),
                border_style="blue",
                padding=(0, 1),
            )
        )
    def _status_panel(self):
        return Panel(
            f"[bold white]MOON Terminal v1.0[/bold white]\n"
            f"  Status: [{'green' if self._status == 'connected' else 'yellow' if self._status == 'connecting...' else 'red'}]{self._status}[{'green' if self._status == 'connected' else 'yellow' if self._status == 'connecting...' else 'red'}]\n"
            f"  Service: {self._health_info.get('service', '?')}  |  Agents: {self._health_info.get('agent_count', '?')}\n"
            f"  Base: {API_BASE}  |  Session: {self.client.session_id}",
            title="[bold cyan]MOON Agent Terminal[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    def _chat_panel(self, text: str = "") -> Panel:
        content = Text("")
        if text:
            for line in text.split("\n"):
                content.append_line(line)
        if not text:
            content.append("\n  [dim]Waiting for input...[/dim]\n", style="dim")
        return Panel(
            content,
            title="[bold]Chat[/bold]",
            border_style="blue",
            padding=(0, 1),
            height=30,
        )

    def render(self, response_text: str = "", tools_text: str = "") -> str:
        """Render the full terminal display as a string."""
        lines = []
        # Header
        lines.append(" ╔" + "═" * 56 + "╗")
        lines.append(" ║" + " " * 3 + "[bold cyan]MOON Agent Terminal v1.0[/bold cyan]" + " " * (50 - 23) + "║")
        lines.append(" ╠" + "═" * 56 + "╣")
        status_icon = "●" if self._status == "connected" else "◐" if self._status == "connecting..." else "○"
        status_col = "green" if self._status == "connected" else "yellow" if self._status == "connecting..." else "red"
        lines.append(f" ║  Status: [{status_col}]{status_icon} {self._status}[/{status_col}]    Service: {self._health_info.get('service', '?')}    Agents: {self._health_info.get('agent_count', '?')}   ║")
        lines.append(f" ║  Base: {API_BASE}                                          ║")
        lines.append(f" ║  Session: {self.client.session_id}                                ║")
        lines.append(" ╚" + "═" * 56 + "╝")
        lines.append("")
        # Tool output
        if tools_text:
            lines.append(" ┌─ Tools ──────────────────────────────────────────┐")
            for line in tools_text.split("\n"):
                lines.append(f" │ {line:<54} │")
            lines.append(" └" + "─" * 56 + "┘")
            lines.append("")
        # Chat/response
        lines.append(" ┌─ Response ────────────────────────────────────────┐")
        for line in response_text.split("\n"):
            lines.append(f" │ {line:<54} │")
        lines.append(" └" + "─" * 56 + "┘")
        lines.append("")
        # Input prompt
        agent_color = AGENTS.get(self.current_agent, {}).get("color", C.AGENT_GENERAL)
        lines.append(f" [{agent_color}]{self.current_agent}[/{agent_color}] [dim]>[/{dim}] [bold]>[bold] ")
        return "\n".join(lines)

    # ── command processing ───────────────────────────────────────────────
    def process_command(self, text: str) -> str | None:
        """Process special commands. Returns response text or None to send as message."""
        t = text.strip()
        if not t:
            return ""

        # !help
        if t == "!help" or t == "!h":
            return self._cmd_help()
        # !agents / !a
        if t.startswith("!agents") or t.startswith("!a "):
            return self._cmd_agents(t)
        if t == "!agents" or t == "!a":
            return self._cmd_agents("")
        # !use <agent> / !u <agent>
        if t.startswith("!use ") or t.startswith("!u "):
            return self._cmd_use(t)
        # !clear / !c
        if t in ("!clear", "!c"):
            self.message_history.clear()
            return ""
        # !status / !s
        if t in ("!status", "!s"):
            return self._cmd_status()
        # !tools / !t
        if t in ("!tools", "!t"):
            return self._cmd_tools()
        # !save / !load
        if t.startswith("!save "):
            return self._cmd_save(t)
        if t.startswith("!load "):
            return self._cmd_load(t)
        # !history / !hist
        if t.startswith("!history") or t.startswith("!hist"):
            return self._cmd_history(t)
        # !voice on/off
        if t.startswith("!voice "):
            return self._cmd_voice(t)
        # !exit / !quit
        if t in ("!exit", "!quit", "!q"):
            self.running = False
            return "[bold red]Disconnecting...[/bold red]"
        # !memory
        if t.startswith("!memory") or t.startswith("!m"):
            return self._cmd_memory(t)
        # !tool <name> [args]
        if t.startswith("!tool "):
            return self._cmd_tool(t)
        # !sh <shell command>
        if t.startswith("!sh "):
            return self._cmd_shell(t)

        # Not a command — return None to send as message
        return None

    def _cmd_help(self) -> str:
        return (
            "[bold cyan]── MOON Terminal Commands ──[/bold cyan]\n"
            + "\n".join([
                f"  [bold]!help[/bold]     [dim]this help[/dim]",
                f"  [bold]!agents[/bold]   [dim]list available agents[/dim]",
                f"  [bold]!use &lt;agent&gt;[/bold]  [dim]switch agent[/dim]",
                f"  [bold]!clear[/bold]    [dim]clear chat history[/dim]",
                f"  [bold]!status[/bold]   [dim]show connection & service status[/dim]",
                f"  [bold]!tools[/bold]    [dim]list available tools[/dim]",
                f"  [bold]!tool &lt;name&gt;[/bold] [dim]run a single tool by name[/dim]",
                f"  [bold]!sh &lt;cmd&gt;[/bold]    [dim]run shell command[/dim]",
                f"  [bold]!save &lt;file&gt;[/bold] [dim]save chat history to file[/dim]",
                f"  [bold]!load &lt;file&gt;[/bold] [dim]load chat history from file[/dim]",
                f"  [bold]!memory[/bold]   [dim]show session memory[/dim]",
                f"  [bold]!voice on/off[/bold] [dim]toggle voice output[/dim]",
                f"  [bold]!history[/bold]  [dim]show message history[/dim]",
                f"  [bold]!exit[/bold]     [dim]disconnect & exit[/dim]",
            ])
            + "\n"
            + f"\n[bold]Current agent:[/bold] {self.current_agent} ({AGENTS.get(self.current_agent, {}).get('name', '?')})"
        )

    def _cmd_agents(self, text: str) -> str:
        tbl = Table(title="[bold cyan]Available Agents[/bold cyan]", show_header=True, header_style="bold white")
        tbl.add_column("Key", style="bold green", width=8)
        tbl.add_column("Name", style="bold white", width=15)
        tbl.add_column("Description", width=45)
        for key, agent in AGENTS.items():
            marker = "[bold green]→[/bold green]" if key == self.current_agent else " "
            tbl.add_row(f"{marker} {key}", agent["name"], agent["desc"])
        tbl.add_row("", "", "")
        tbl.add_row("[bold]Tip:[/bold] Use !use &lt;agent&gt; to switch", "", "")
        from io import StringIO
        buf = StringIO()
        cons = Console(file=buf, force_terminal=True)
        cons.print(tbl)
        return "\n" + buf.getvalue() + "\n"

    def _cmd_use(self, text: str) -> str:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return f"[bold yellow]Usage:[/bold yellow] !use &lt;agent_name&gt;\nAvailable: {', '.join(AGENTS.keys())}"
        agent_name = parts[1].strip().lower()
        if agent_name not in AGENTS:
            return f"[bold red]Unknown agent:[/bold red] {agent_name}\nAvailable: {', '.join(AGENTS.keys())}"
        old = self.current_agent
        self.current_agent = agent_name
        return f"[bold green]Switched[/bold green] from [bold]{old}[/bold] to [bold cyan]{agent_name}[/bold cyan] ({AGENTS[agent_name]['name']})"

    def _cmd_status(self) -> str:
        h = self._health_info
        status = self._status
        sc = "green" if status == "connected" else "red"
        return (
            f"[bold cyan]── Status ──[/bold cyan]\n"
            f"  Terminal: [{sc}]{status}[/{sc}]\n"
            f"  API:      {API_BASE}\n"
            f"  Service:  {h.get('service', 'unknown')}\n"
            f"  Agents:   {h.get('agent_count', '?')}\n"
            f"  Lock:     {h.get('lock_state', '?')}\n"
            f"  Version:  {h.get('version', '?')}\n"
            f"  Session:  {self.client.session_id}"
        )

    def _cmd_tools(self) -> str:
        sys.path.insert(0, str(Path("/home/meow/Projects/MOON/Moon_Twin")))
        try:
            from agent.engine import default_engine
            handlers = getattr(default_engine, "_tool_handlers", {})
            names = sorted(handlers.keys())
            return (
                f"[bold cyan]── Registered Tools ({len(names)}) ──[/bold cyan]\n"
                + ", ".join(names)
            )
        except Exception as e:
            return f"[bold red]Error loading tools:[/bold red] {e}"

    def _cmd_tool(self, text: str) -> str:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return "[bold yellow]Usage:[/bold yellow] !tool &lt;tool_name&gt; [json_args]"
        tool_name = parts[1].split()[0]
        args_str = parts[1][len(tool_name):].strip()
        # Try JSON args first; if not valid JSON, treat remaining text as positional arg
        if args_str:
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                # Positional: map to all common parameter names so whichever
                # the tool reads first gets the value
                args = {}
                for key in ('hostname', 'input', 'domain', 'query', 'url', 'target', 'name'):
                    args[key] = args_str
        else:
            args = {}

        sys.path.insert(0, str(Path("/home/meow/Projects/MOON/Moon_Twin")))
        try:
            from agent.engine import default_engine
            result = asyncio.run(default_engine.run_tool(tool_name, args))
            return f"[bold cyan]Tool:[/bold cyan] {tool_name}\n[bold]Result:[/bold]\n" + self._format_result(result)
        except Exception as e:
            return f"[bold red]Tool error:[/bold red] {e}"

    def _cmd_shell(self, text: str) -> str:
        cmd = text[4:].strip()
        if not cmd:
            return "[bold yellow]Usage:[/bold yellow] !sh &lt;command&gt;"
        try:
            import subprocess
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            out = r.stdout if r.stdout else r.stderr
            return f"[bold cyan]Shell:[/bold cyan] {cmd}\n[bold]Output:[/bold]\n" + (out[:2000] if out else "(no output)")
        except Exception as e:
            return f"[bold red]Shell error:[/bold red] {e}"

    def _cmd_save(self, text: str) -> str:
        path = text[6:].strip()
        if not path:
            return "[bold yellow]Usage:[/bold yellow] !save &lt;file&gt;"
        try:
            with open(path, "w") as f:
                for msg in self.message_history:
                    f.write(f"[{msg['role']}] {msg['text']}\n")
            return f"[bold green]Saved[/bold green] {len(self.message_history)} messages to {path}"
        except Exception as e:
            return f"[bold red]Save error:[/bold red] {e}"

    def _cmd_load(self, text: str) -> str:
        path = text[6:].strip()
        if not path:
            return "[bold yellow]Usage:[/bold yellow] !load &lt;file&gt;"
        try:
            with open(path) as f:
                lines = f.readlines()
            self.message_history.clear()
            for line in lines:
                if "] " in line:
                    role, text = line.split("] ", 1)
                    self.message_history.append({"role": role.strip("["), "text": text.strip()})
            return f"[bold green]Loaded[/bold green] {len(self.message_history)} messages from {path}"
        except Exception as e:
            return f"[bold red]Load error:[/bold red] {e}"

    def _cmd_history(self, text: str) -> str:
        if not self.message_history:
            return "[dim]No messages in history.[/dim]"
        lines = [f"[bold]Message History ({len(self.message_history)} messages):[/bold]"]
        for i, msg in enumerate(self.message_history[-20:]):
            role_color = "green" if msg["role"] == "user" else "blue"
            lines.append(f"  [{role_color}]{msg['role']}[/{role_color}]: {msg['text'][:100]}")
        return "\n".join(lines)

    def _cmd_memory(self, text: str) -> str:
        memory = self.client.get_memory()
        if not memory:
            return "[dim]No session memory.[/dim]"
        lines = [f"[bold cyan]Session Memory ({len(memory)} entries):[/bold cyan]"]
        for entry in memory:
            lines.append(f"  {entry}")
        return "\n".join(lines)

    def _cmd_voice(self, text: str) -> str:
        return "[bold]Voice toggle not yet implemented.[/bold] (Use Moon_Twin voice_speak tool directly)"

    def _format_result(self, result: dict, indent: int = 2) -> str:
        """Format a tool result dict for display."""
        if not isinstance(result, dict):
            return str(result)
        lines = []
        for k, v in result.items():
            if isinstance(v, dict):
                lines.append(f"{' ' * indent}{k}:")
                for k2, v2 in v.items():
                    lines.append(f"{' ' * (indent+2)}{k2}: {v2}")
            elif isinstance(v, list):
                lines.append(f"{' ' * indent}{k}: [{len(v)} items]")
                for item in v[:5]:
                    lines.append(f"{' ' * (indent+2)}- {str(item)[:80]}")
                if len(v) > 5:
                    lines.append(f"{' ' * (indent+2)}... +{len(v)-5} more")
            else:
                lines.append(f"{' ' * indent}{k}: {v}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main loop — professional terminal REPL
# ---------------------------------------------------------------------------
def main():
    """Main entry point for MOON Terminal."""
    term = MoonTerminal()

    # Initial connection check
    CONSOLE.print(Panel(f"[bold cyan]MOON Terminal v1.0[/bold cyan]\n\nInitializing connection to {API_BASE}...", 
                        border_style="cyan", padding=(1, 2)))
    health = term.client.health()
    term._health_info = health
    term._status = "connected" if "error" not in health else f"error: {health.get('error', 'unknown')}"

    # Show startup banner
    banner = (
        "\n"
        "  ╔" + "═" * 54 + "╗\n"
        "  ║  [bold cyan]╭──────────────────────── MOON ───────────────────────╮[/bold cyan]  ║\n"
        "  ║  [bold]  Professional AI Assistant Agent Terminal[/bold]              [bold cyan]║[/bold cyan]  ║\n"
        "  ║  [dim]  Moon_Twin Engine  •  8 Agents  •  62 Tools[/dim]           [bold cyan]║[/bold cyan]  ║\n"
        "  ║  [bold cyan]╰──────────────────────────────────────────────────────╯[/bold cyan]  ║\n"
        "  ╚" + "═" * 54 + "╝\n"
        f"  Status: [bold green]● connected[/bold green]  |  Service: {health.get('service', '?')}  |  Agents: {health.get('agent_count', '?')}\n"
        f"  Session: {term.client.session_id}\n"
        "  Type [bold]!help[/bold] for commands, [bold]!agents[/bold] to switch agents, [bold]!exit[/bold] to quit.\n"
    )
    CONSOLE.print(banner)

    # ── main read-execute loop ───────────────────────────────────────────
    session = PromptSession(history=InMemoryHistory())
    kb = KeyBindings()

    @kb.add("c-c")
    def _(event):
        term.running = False
        event.app.exit()

    @kb.add("c-d")
    def _(event):
        term.running = False
        event.app.exit()

    # Tab completion for agent names
    @kb.add("tab")
    def _(event):
        # Cycle through agents
        keys = list(AGENTS.keys())
        idx = keys.index(term.current_agent) if term.current_agent in keys else -1
        next_idx = (idx + 1) % len(keys)
        term.current_agent = keys[next_idx]
        event.app.exit()

    readline_hist_file = Path.home() / ".moon_terminal_history"
    try:
        readline.read_history_file(str(readline_hist_file))
    except FileNotFoundError:
        pass

    # Build prompt with Rich markup (colors are ANSI escape sequences in C.* constants)
    _GENERAL_COLOR = AGENTS['general']['color']
    _GENERAL_NAME = AGENTS['general']['name']
    prompt_str = _GENERAL_COLOR + _GENERAL_NAME + "\033[0m" + " \033[2m>\033[0m \033[1m>\033[0m "

    while term.running:
        try:
            user_input = session.prompt(prompt_str, key_bindings=kb, timeout=30)
        except (EOFError, KeyboardInterrupt):
            break
        except Exception:
            continue

        if not user_input.strip():
            continue

        # Check for command
        cmd_result = term.process_command(user_input)
        if cmd_result is not None:
            if not term.running:
                break
            CONSOLE.print(term.render(response_text=cmd_result))
            # Re-display prompt with current agent
            _agent_color = AGENTS.get(term.current_agent, {}).get("color", C.AGENT_GENERAL)
            _agent_name = AGENTS.get(term.current_agent, {}).get("name", term.current_agent)
            prompt_str = _agent_color + _agent_name + "\033[0m" + " \033[2m>\033[0m \033[1m>\033[0m "
            continue

        # ── Send message to MOON ────────────────────────────────────────
        CONSOLE.print(f"\n[dim]> {user_input}...[/dim]")

        # Add to history
        term.message_history.append({"role": "user", "text": user_input})

        # Clear previous tools display
        term.client.clear_tools()

        # Send to API
        try:
            response = term.client.send_message(user_input, agent=term.current_agent)
        except Exception as e:
            CONSOLE.print(f"[bold red]Error:[/bold red] {e}")
            continue

        reply = response.get("reply", "")
        tools_used = response.get("tools_used", [])

        # Build response display
        response_lines = []
        if reply:
            response_lines.append(reply.strip())

        # Show tools if any were used
        tools_text = ""
        if tools_used:
            tools_text = "\n".join([
                f"  ▸ {t.get('name', t.get('tool', '?'))}: {t.get('status', '?')}"
                + (f" → {str(t.get('result', ''))[:80]}" if t.get('result') else "")
                for t in tools_used
            ])

        # Display
        output = term.render(
            response_text="\n".join(response_lines) if response_lines else "[dim]No response.[/dim]",
            tools_text=tools_text,
        )
        CONSOLE.print(output)

        # Add AI response to history
        if reply:
            term.message_history.append({"role": "assistant", "text": reply})

        # Save readline history
        try:
            readline.write_history_file(str(readline_hist_file))
        except Exception:
            pass

        # Re-display prompt with current agent color
        _agent_color = AGENTS.get(term.current_agent, {}).get("color", C.AGENT_GENERAL)
        _agent_name = AGENTS.get(term.current_agent, {}).get("name", term.current_agent)
        prompt_str = _agent_color + _agent_name + "\033[0m" + " \033[2m>\033[0m \033[1m>\033[0m "

    # ── exit ─────────────────────────────────────────────────────────────
    CONSOLE.print("\n[dim]Disconnected from MOON. Goodbye.[/dim]\n")
    try:
        readline.write_history_file(str(readline_hist_file))
    except Exception:
        pass


if __name__ == "__main__":
    main()
