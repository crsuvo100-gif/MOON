#!/usr/bin/env python3
"""MOON TUI — Hermes-style Textual terminal (moonscope).

A Jarvis/HUD-style interactive terminal for MOON that mirrors the Hermes Agent
TUI aesthetic: chat/conversation panel, command input bar, live status HUD
(memory, CPU, tokens/s, latency, uptime), yellow accents on deep-black
background.

Usage:
    moon           — boots moonscope TUI (default; was REPL, now TUI)
    moon cli       — boots readline REPL (fallback, unchanged)
    moon terminal  — boots moonscope TUI
    moon run       — runs one-shot task or boots moonscope if no task

The TUI provides:
    * Chat panel: conversation history + AI responses, rendered top-to-bottom
    * Input bar: > prompt at bottom, Enter to send, /slash commands supported
    * Status HUD: model, agent, session, memory, CPU%, tokens/s, latency, uptime
    * Yellow accent palette on dark background (matches Hermes screenshot)
    * Session lock: awaiting 'MOON love you 3000' to unlock (unchanged)

Integrates with Moon's existing:
    * CLIState (model, agent, session, messages)
    * CLICommandsMixin (all /slash handlers)
    * LLMService (oneshot/chat queries)
    * ConsoleEngine (panel/table/spinner primitives, reused for fallback print)
"""

from __future__ import annotations

import asyncio
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Static, Input, Label, RichLog, Footer, Header,
)
from textual.reactive import reactive
from textual.timer import Timer
from textual import events
from textual.message import Message

from app.cli.colors import Colors, color
from app.cli.console_engine import ConsoleEngine, get_console, print_panel
from app.cli.commands import CLIState, COMMAND_REGISTRY, resolve_command
from app.cli.cli_commands_mixin import CLICommandsMixin

# ── Moonscape palette — Hermes screenshot aesthetic ──────────────────────────
MOONSCAPE = {
    "background": "#0a0a0a",
    "surface": "#111111",
    "surface-light": "#1a1a1a",
    "yellow": "#f1c40f",
    "yellow-dim": "#a89000",
    "green": "#2ecc71",
    "green-dim": "#1a7a3a",
    "orange": "#e67e22",
    "cyan": "#27ae60",
    "red": "#e74c3c",
    "white": "#e0e0e0",
    "dim": "#666666",
    "border": "#333333",
    "panel-bg": "#0d0d0d",
}

UNLOCK_PHRASE = os.environ.get("MOON_TUI_UNLOCK", "MOON love you 3000")


# ── Status HUD widget ─────────────────────────────────────────────────────────
class StatusHUD(Static):
    """Bottom status bar mirroring Hermes screenshot HUD."""

    model_name = reactive("qwen2.5:1.5b")
    agent_name = reactive("auto")
    session_id = reactive("live")
    memory_mb = reactive(0.0)
    cpu_pct = reactive(0.0)
    tokens_per_sec = reactive(0.0)
    latency_ms = reactive(0.0)
    uptime_s = reactive(0.0)
    locked = reactive(True)

    _start_time: float = 0.0
    _last_tokens: int = 0
    _token_timestamp: float = 0.0

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._start_time = time.time()
        self._token_timestamp = time.time()

    def watch_model_name(self, old: str, new: str) -> None:
        self.refresh_hud()

    def watch_agent_name(self, old: str, new: str) -> None:
        self.refresh_hud()

    def watch_locked(self, old: bool, new: bool) -> None:
        self.refresh_hud()

    def refresh_hud(self) -> None:
        """Re-render the HUD with current stats."""
        elapsed = time.time() - self._start_time
        uptime = int(elapsed)
        mins, secs = divmod(uptime, 60)
        hours, mins = divmod(mins, 60)

        mem_str = f"{self.memory_mb:.1f} MB" if self.memory_mb > 0 else "—"
        cpu_str = f"{self.cpu_pct:.1f}%" if self.cpu_pct > 0 else "—"
        tps = (self.tokens_per_sec or 0)
        tps_str = f"{tps:.1f}" if tps > 0 else "—"
        lat_str = f"{self.latency_ms:.0f} ms" if self.latency_ms > 0 else "—"

        lock_icon = "🔒" if self.locked else "🔓"
        lock_color = "yellow" if self.locked else "green"

        left = f"model {self.model_name}"
        mid = f"agent {self.agent_name} session {self.session_id}"
        right = f"mem {mem_str} cpu {cpu_str} ↑ {tps_str} lat {lat_str} uptime {hours:02d}:{mins:02d}:{secs:02d}"
        lock = f"{lock_icon} {'locked' if self.locked else 'unlocked'}"

        from rich.text import Text
        t = Text()
        t.append(left, "yellow")
        t.append(" │ ", "dim")
        t.append(mid, "white")
        t.append(" │ ", "dim")
        t.append(right, "dim")
        t.append(" │ ", "dim")
        t.append(lock, lock_color)
        self.update(t)

    def set_tokens(self, n: int) -> None:
        """Record token count for tps calculation."""
        now = time.time()
        dt = now - self._token_timestamp
        if dt > 0.5 and self._last_tokens > 0:
            self.tokens_per_sec = (n - self._last_tokens) / dt
        self._last_tokens = n
        self._token_timestamp = now


# ── Status panel widget (Hermes-style scoped sections) — cosmetic reuse of
# Hermes CLI status.py visual language: box-drawing borders, cyan ◆ headers,
# ✓/✗ checkmarks. Not wired into moonscope TUI yet; kept for future /status
# command integration when the TUI supports a full status display.
# ──────────────────────────────────────────────────────────────────────────────

def _box_top(title: str, width: int = 70) -> str:
    """Return a box-drawing top border with a centered title."""
    left = "┌" + "─" * ((width - len(title)) // 2)
    right = "─" * (width - len(left) - len(title) - 2) + "┐"
    return f"{left} {title} {right}"


def _box_bottom(width: int = 70) -> str:
    """Return a box-drawing bottom border."""
    return "└" + "─" * (width - 2) + "┘"


def _section_header(name: str, width: int = 70) -> str:
    """Return a cyan ◆ section header banner."""
    pad = width - len(name) - 2
    left = "├" + "─" * (pad // 2)
    right = "─" * (pad - pad // 2 - 1) + "┤"
    return f"{left} ◆ {name} {right}"


def _status_line(label: str, value: str, width: int = 70) -> str:
    """Return a status line: │ label     value."""
    pad = width - len(label) - len(value) - 5
    if pad < 2:
        pad = 2
    return f"│ {label:<{12}} {value:<{pad}}"


def _status_line_check(ok: bool, label: str, detail: str, width: int = 70) -> str:
    """Return a status line with ✓/✗ indicator: │ ✓ label     detail."""
    icon = "✓" if ok else "✗"
    ok_color = "green" if ok else "red"
    rest = f"{detail}"
    pad = max(width - 4 - 12 - len(label) - len(rest) - 1, 2)
    return f"│ {ok_color}{icon}{'dim'} ✓ {label:<12} {rest:<{pad}}"


# ── Chat panel widget ─────────────────────────────────────────────────────────
class ChatPanel(Static):
    """Conversation/chat panel widget — top-to-bottom message history."""

    messages = reactive([], init=list)

    def watch_messages(self, old: list, new: list) -> None:
        self._render_messages(new)

    def _render_messages(self, messages: list[dict]) -> None:
        from rich.text import Text

        if not messages:
            t = Text()
            t.append("No messages yet. Type below and press Enter.", "dim")
            self.update(t)
            return

        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "system")
            content = msg.get("content", "")
            if role == "user":
                parts.append(f"\n[bold white]You:[/bold white] {content}")
            elif role == "agent":
                parts.append(f"\n[bold green]MOON:[/bold green] {content}")
            elif role == "system":
                parts.append(f"\n[dim]{content}[/dim]")
            else:
                parts.append(f"\n[dim]{content}[/dim]")

        combined = "\n".join(parts).strip()
        self.update(combined)


# ── Main TUI app ──────────────────────────────────────────────────────────────
class Moonscope(App):
    """Hermes-style Textual TUI for MOON.

    Layout (top-to-bottom):
        * Header (minimal, just clock)
        * Chat panel (conversation history, scrolls)
        * Status HUD (live metrics bar)
        * Input bar (> prompt, Enter to send)

    All /slash commands from CLICommandsMixin are supported.
    """

    CSS = f"""
    Screen {{
        background: {MOONSCAPE["background"]};
        color: {MOONSCAPE["white"]};
    }}
    Header {{
        background: {MOONSCAPE["surface"]};
        color: {MOONSCAPE["dim"]};
        height: 1;
    }}
    Footer {{
        background: {MOONSCAPE["surface"]};
        color: {MOONSCAPE["dim"]};
        height: 1;
    }}
    #chat-panel {{
        background: {MOONSCAPE["panel-bg"]};
        border: solid {MOONSCAPE["border"]};
        border-title-color: {MOONSCAPE["yellow-dim"]};
        height: 1fr;
        padding: 1 2;
    }}
    #hud {{
        background: {MOONSCAPE["surface"]};
        border: solid {MOONSCAPE["border"]};
        border-title-color: {MOONSCAPE["yellow-dim"]};
        height: 3;
        padding: 0 2;
    }}
    #input-bar {{
        background: {MOONSCAPE["surface-light"]};
        border: solid {MOONSCAPE["border"]};
        border-title-color: {MOONSCAPE["yellow-dim"]};
        height: 3;
        padding: 0 2;
    }}
    """

    TITLE = "MOON — moonscope"

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    _cli: CLICommandsMixin | None = None
    _state: CLIState | None = None
    _chat_messages: list[dict[str, str]] = []
    _sessions_start: float = 0.0
    _hud_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        """Build the widget layout: chat panel, brain-core panel, HUD bar, input bar."""
        yield Header()
        yield ChatPanel(id="chat-panel")
        yield BrainCorePanel(id="brain-panel")
        yield BrainHUD(id="hud")
        yield Input(id="input-bar", placeholder="> ")

    def on_mount(self) -> None:
        """Initialise state, wire HUD, start timer, focus input."""

        # Build CLI state from settings
        from app.config.settings import Settings
        s = Settings()
        session_id = f"moonscope-{int(time.time())}"
        self._state = CLIState(
            model_name=s.model_name,
            agent_name="auto",
            session_id=session_id,
        )
        self._cli = CLICommandsMixin()
        self._cli.state = self._state

        # Wire HUD reactive vars (BrainHUD — extended with brain-core orb + pipeline)
        hud = self.query_one(BrainHUD)
        hud.model_name = s.model_name
        hud.agent_name = "auto"
        hud.session_id = session_id
        hud.locked = True

        # Start HUD update timer (every 2s)
        self._hud_timer = self.set_interval(2, self._tick_hud)

        # Focus the input
        self.query_one("#input-bar").focus()

        # Push welcome message
        welcome = (
            f"MOON moonscope — Hermes-style TUI. "
            f"Model: {s.model_name}. "
            f"Type /help for commands. "
            f"Unlock: '{UNLOCK_PHRASE}'"
        )
        self._chat_messages.append({"role": "system", "content": welcome})
        self.query_one(ChatPanel).messages = self._chat_messages

        # ── Wire brain-core backend (WS + HTTP) ─────────────────────────────
        # Start the WebSocket client for live /ws/events stream
        self._ws_client = WSEventClient(
            "ws://127.0.0.1:8777/ws/events",
            on_event=self._on_ws_event,
        )
        asyncio.create_task(self._ws_client.start())

        # Fetch initial brain status from backend
        asyncio.create_task(self._fetch_brain_status())

    def _tick_hud(self) -> None:
        """Update HUD stats: poll /api/brain-status + /api/telemetry from backend."""
        try:
            import httpx
            brain = httpx.get(
                "http://127.0.0.1:8777/api/brain-status",
                timeout=5.0,
            )
            if brain.status_code == 200:
                data = brain.json()
                # Update BrainHUD reactives
                hud = self.query_one(BrainHUD)
                if "model" in data:
                    hud.model_name = data["model"]
                if "memory" in data:
                    mem = data["memory"]
                    hud.memory_mb = float(mem.get("long_term", 0)) * 0.01
                if "system" in data:
                    sys_ = data["system"]
                    hud.cpu_pct = float(sys_.get("cpu", 0))
                if "uptime_fmt" in data:
                    pass  # HUD computes uptime from _start_time
                # Update BrainCorePanel
                panel = self.query_one(BrainCorePanel)
                panel.brain_data = data
                # Update emotion/severity on HUD
                if "emotion" in data:
                    hud.brain_emotion = data["emotion"]
                if "pipeline" in data:
                    active = [p["key"] for p in data["pipeline"] if p.get("active")]
                    hud.pipeline_active = active
        except Exception:
            # Backend not reachable — keep showing last known state
            pass

    async def _handle_input(self, text: str) -> None:
        """Dispatch user input — mirrors CLI dispatch but in TUI context."""
        text = text.strip()
        if not text:
            return

        # Add user message to chat
        self._chat_messages.append({"role": "user", "content": text})
        self.query_one(ChatPanel).messages = self._chat_messages
        self.query_one(BrainHUD).set_tokens(len(text.split()))

        # Check for lock
        if self._state and getattr(self._state, "locked", False):
            if text.strip() == UNLOCK_PHRASE:
                self._state.locked = False
                self.query_one(BrainHUD).locked = False
                self._chat_messages.append({
                    "role": "system",
                    "content": "\U0001f513 Unlocked. MOON is now active."
                })
                self.query_one(ChatPanel).messages = self._chat_messages
                return
            else:
                self._chat_messages.append({
                    "role": "system",
                    "content": f"\U0001f512 Locked. Say '{UNLOCK_PHRASE}' to unlock."
                })
                self.query_one(ChatPanel).messages = self._chat_messages
                return

        # Dispatch slash commands
        if text.startswith("/"):
            line = text[1:]
            if line == "":
                await self._dispatch_command("/help", "")
            else:
                parts = line.split(maxsplit=1)
                cmd_name = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                await self._dispatch_command(cmd_name, args)
            return

        # Regular message → LLM query (oneshot-style)
        await self._chat_with_llm(text)

    async def _dispatch_command(self, cmd_name: str, args: str) -> None:
        """Dispatch a slash command using CLICommandsMixin, capturing output to chat."""
        from app.cli.cli_output import (
            print_info, print_success, print_warning, print_error,
        )
        from rich.console import Console as RichConsole

        cmd = resolve_command(cmd_name)
        if not cmd:
            self._chat_messages.append({
                "role": "system",
                "content": f"Unknown command: /{cmd_name}. Type /help for commands."
            })
            self.query_one(ChatPanel).messages = self._chat_messages
            return

        handler_name = f"_handle_{cmd_name.replace('-', '_')}"
        handler = getattr(self._cli, handler_name, None)
        if handler is None:
            self._chat_messages.append({
                "role": "system",
                "content": f"Command /{cmd_name} has no handler yet."
            })
            self.query_one(ChatPanel).messages = self._chat_messages
            return

        # Capture console output to string
        capture_console = RichConsole(
            file=io.StringIO(), force_terminal=True, width=80,
        )
        import app.cli.console_engine as ce
        old_console = ce._console
        ce._console = capture_console
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(args)
            else:
                handler(args)
        finally:
            ce._console = old_console

        output = capture_console.file.getvalue()
        if output.strip():
            for line in output.strip().split("\n"):
                if line.strip():
                    self._chat_messages.append({
                        "role": "system",
                        "content": line.strip()
                    })
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _chat_with_llm(self, prompt_text: str) -> None:
        """Send prompt to LLM and show response in chat panel."""
        from app.services.llm_service import LLMService, ChatMessage
        from app.config.settings import Settings

        s = Settings()
        llm = LLMService(
            base_url=s.model_base_url,
            model_name=s.model_name,
            timeout=s.model_timeout,
        )
        messages = [ChatMessage(role="user", content=prompt_text)]

        self._chat_messages.append({"role": "system", "content": "thinking..."})
        self.query_one(ChatPanel).messages = list(self._chat_messages)
        self.query_one(BrainHUD).set_tokens(len(prompt_text.split()))

        try:
            result = await llm.complete(messages=messages)
            content = getattr(result, "content", None) or ""
            if content:
                self._chat_messages.append({
                    "role": "agent",
                    "content": content
                })
                self.query_one(StatusHUD).set_tokens(len(content.split()))
            else:
                self._chat_messages.append({
                    "role": "system",
                    "content": "(no response from model)"
                })
        except asyncio.TimeoutError:
            self._chat_messages.append({
                "role": "system",
                "content": "[red]LLM timed out[/red]"
            })
        except Exception as exc:
            self._chat_messages.append({
                "role": "system",
                "content": f"[red]Error: {exc}[/red]"
            })
        self.query_one(ChatPanel).messages = self._chat_messages

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in InputBar."""
        asyncio.create_task(self._handle_input(event.value))
        event.value = ""

def action_quit(self) -> None:
        """Quit the TUI — stop WS client first."""
        if hasattr(self, "_ws_client") and self._ws_client is not None:
            asyncio.create_task(self._ws_client.stop())
        self.exit()



# ── Brain-core status panel widget ──────────────────────────────────────────
# Mirrors the brain-core dashboard from the Hermes screenshot: 8-stage pipeline,
# agent/tool/memory/knowledge/system/voice/sensors/emotion display, live event
# stream from /ws/events. Wired to MOON's backend at 127.0.0.1:8777.
# ──────────────────────────────────────────────────────────────────────────────

class BrainCorePanel(Static):
    """Full brain-core dashboard panel — renders _moon_status_impl data.

    Shows pipeline stages (INPUT/MEMORY/KNOWLEDGE/REASONING/PLANNER/TOOLS/
    EXECUTION/VERIFY), agent count + list, tool count + list, memory stats,
    knowledge stats, system metrics, voice mode, sensors with ✓/✗, and the
    emotion/severity orb. Updates from HTTP poll + WS event stream.
    """

    brain_data = reactive({}, init=dict)

    def watch_brain_data(self, old: dict, new: dict) -> None:
        self._render(new)

    def _render(self, bs: dict) -> None:
        """Render the brain-core panel from a _moon_status_impl dict."""
        from rich.text import Text

        W = 70
        lines: list[Text] = []

        def _box(title: str) -> Text:
            t = Text()
            t.append(_box_top(title, W), "dim")
            return t

        def _close() -> Text:
            t = Text()
            t.append(_box_bottom(W), "dim")
            return t

        def _sec(name: str) -> Text:
            t = Text()
            t.append(_section_header(name, W), "cyan bold")
            return t

        def _row(key: str, value: str) -> Text:
            t = Text()
            t.append(_status_line(key, value, W), "")
            return t

        # ── Header ────────────────────────────────────────────────────────
        lines.append(_box("  MOON BRAIN STATUS  "))
        lines.append(_row("model", bs.get("model", "—")))
        lines.append(_row("version", bs.get("version", "—")))
        lines.append(_row("uptime", bs.get("uptime_fmt", "—")))
        lines.append(_close())
        lines.append(Text())

        # ── Pipeline (8 stages) ────────────────────────────────────────────
        pipeline = bs.get("pipeline", [])
        lines.append(_sec("Pipeline"))
        for stage in pipeline:
            key = stage.get("key", "?")
            label = stage.get("label", key)
            active = stage.get("active", False)
            icon = "▶" if active else "○"
            col = "yellow" if active else "dim"
            t = Text()
            t.append(f"│ ", "dim")
            t.append(f"{icon} ", col)
            t.append(f"{label:<12} ", "white")
            t.append(key, "dim")
            lines.append(t)
        lines.append(_close())
        lines.append(Text())

        # ── Agents ─────────────────────────────────────────────────────────
        n_agents = bs.get("agents", 0)
        agent_list = bs.get("agent_list", [])
        lines.append(_sec("Agents"))
        lines.append(_row("count", str(n_agents)))
        for name in agent_list[:8]:
            t = Text()
            t.append("│   ", "dim")
            t.append(name, "white")
            lines.append(t)
        if len(agent_list) > 8:
            t = Text()
            t.append(f"│   ... +{len(agent_list) - 8} more", "dim")
            lines.append(t)
        lines.append(_close())
        lines.append(Text())

        # ── Tools ──────────────────────────────────────────────────────────
        n_tools = bs.get("n_tools", 0)
        tool_list = bs.get("tools", [])
        lines.append(_sec("Tools"))
        lines.append(_row("count", str(n_tools)))
        for name in tool_list[:10]:
            t = Text()
            t.append("│   ", "dim")
            t.append(name, "white")
            lines.append(t)
        if len(tool_list) > 10:
            t = Text()
            t.append(f"│   ... +{len(tool_list) - 10} more", "dim")
            lines.append(t)
        lines.append(_close())
        lines.append(Text())

        # ── Memory ─────────────────────────────────────────────────────────
        mem = bs.get("memory", {})
        lines.append(_sec("Memory"))
        lines.append(_row("episodic", str(mem.get("episodic", 0))))
        lines.append(_row("long_term", str(mem.get("long_term", 0))))
        lines.append(_row("short_term", str(mem.get("short_term", 0))))
        lines.append(_row("vector", str(mem.get("vector", 0))))
        lines.append(_row("kb_docs", str(mem.get("kb_docs", 0))))
        lines.append(_row("integrity", f"{mem.get('integrity', 0)}%"))
        lines.append(_close())
        lines.append(Text())

        # ── Knowledge ──────────────────────────────────────────────────────
        kn = bs.get("knowledge", {})
        lines.append(_sec("Knowledge"))
        lines.append(_row("graph", f"{kn.get('graph', 0)}%"))
        lines.append(_row("doc_store", f"{kn.get('doc_store', 0)}%"))
        lines.append(_row("rt", f"{kn.get('rt', 0)}%"))
        lines.append(_row("context", f"{kn.get('context', 0)}%"))
        lines.append(_close())
        lines.append(Text())

        # ── System ─────────────────────────────────────────────────────────
        sys_ = bs.get("system", {})
        lines.append(_sec("System"))
        lines.append(_row("cpu", f"{sys_.get('cpu', 0)}%"))
        lines.append(_row("ram", f"{sys_.get('ram_pct', 0)}%"))
        lines.append(_row("gpu", f"{sys_.get('gpu', 0)}%"))
        lines.append(_row("net", f"{sys_.get('net', 0)} MB/s"))
        lines.append(_close())
        lines.append(Text())

        # ── Voice ──────────────────────────────────────────────────────────
        voice = bs.get("voice", {})
        mode = voice.get("mode", "—")
        available = voice.get("available", False)
        auto_voice = voice.get("auto_voice", False)
        lines.append(_sec("Voice"))
        lines.append(_status_line_check(available, "engine", "ready" if available else "unavailable"))
        lines.append(_row("mode", mode))
        lines.append(_status_line_check(auto_voice, "auto_voice", "on" if auto_voice else "off"))
        lines.append(_close())
        lines.append(Text())

        # ── Sensors ────────────────────────────────────────────────────────
        sensors = bs.get("sensors", {})
        sensor_items = [
            ("voice", "Voice input"),
            ("text", "Text input"),
            ("vision", "Vision / OCR"),
            ("file", "File access"),
            ("system", "System ops"),
        ]
        lines.append(_sec("Sensors"))
        for key, label in sensor_items:
            ok = sensors.get(key, False)
            lines.append(_status_line_check(ok, label, "active" if ok else "off"))
        lines.append(_close())
        lines.append(Text())

        # ── Emotion / severity ─────────────────────────────────────────────
        emotion = bs.get("emotion", "—")
        sev_map = {
            "calm": "● calm",
            "normal": "◉ normal",
            "working": "◎ working",
            "dangerous": "◉ dangerous",
            "aggressive": "◉ aggressive",
        }
        sev_str = sev_map.get(emotion, f"● {emotion}")
        lines.append(_sec("Emotion"))
        lines.append(_row("current", sev_str))
        lines.append(_close())

        # Combine into output
        combined = Text()
        for lt in lines:
            combined.append(lt.plain, lt.style if lt.style else "")
            combined.append("\n")
        self.update(combined)


# ── WebSocket event stream client ─────────────────────────────────────────────
# Connects to MOON's /ws/events endpoint and feeds live events into the brain-
# core panel + HUD orb. Mirrors the Hermes screenshot's live ring buffer stream.
# ──────────────────────────────────────────────────────────────────────────────

class WSEventClient:
    """Thin websockets client that streams /ws/events into a callback."""

    def __init__(self, url: str, on_event: Callable[[dict], None]) -> None:
        self._url = url
        self._on_event = on_event
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start the WS connection loop (fire-and-forget)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Close the WS connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        """Connect and stream events until cancelled."""
        try:
            import websockets
            async with websockets.connect(self._url) as ws:
                # Read ready frame
                try:
                    ready = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    if isinstance(ready, str):
                        import json as _json
                        ready_data = _json.loads(ready)
                        if ready_data.get("type") != "ready":
                            # Not a ready frame — try to continue anyway
                            pass
                except (asyncio.TimeoutError, Exception):
                    pass
                # Stream events
                async for raw in ws:
                    if not self._running:
                        break
                    try:
                        msg = raw if isinstance(raw, dict) else _json_loads(raw)
                        if msg and msg.get("type") == "event":
                            self._on_event(msg)
                    except Exception:
                        pass
        except Exception:
            # Connection dropped — will retry on next start
            pass

    async def reconnect(self) -> None:
        """Stop then restart the WS connection."""
        await self.stop()
        await self.start()


def _json_loads(raw) -> dict:
    """Safe JSON parse for WS frames."""
    try:
        import json as _json
        return _json.loads(raw)
    except Exception:
        return {}


# ── Brain-core HUD panel (extended StatusHUD with orb + pipeline) ────────────
# Extends the existing StatusHUD to show the brain-core orb (severity tier) and
# the 8-stage pipeline + live metrics from /api/brain-status + /api/telemetry.
# ──────────────────────────────────────────────────────────────────────────────

class BrainHUD(Static):
    """Extended status HUD: model/agent/session + brain-core orb + pipeline + live metrics.

    Shows:
      - model, agent, session (from moonscope CLI state)
      - brain-core orb: severity tier (calm/normal/working/dangerous/aggressive) with color
      - pipeline: 8 stages with ▶/○ active indicators
      - live system metrics: memory MB, CPU%, tokens/s, latency ms, uptime
      - lock state: 🔒/🔓 with unlock phrase hint
    """

    model_name = reactive("qwen2.5:1.5b")
    agent_name = reactive("auto")
    session_id = reactive("live")
    memory_mb = reactive(0.0)
    cpu_pct = reactive(0.0)
    tokens_per_sec = reactive(0.0)
    latency_ms = reactive(0.0)
    uptime_s = reactive(0.0)
    locked = reactive(True)
    brain_emotion = reactive("normal")
    pipeline_active = reactive([])  # list of active pipeline stage keys

    _start_time: float = 0.0
    _last_tokens: int = 0
    _token_timestamp: float = 0.0

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._start_time = time.time()
        self._token_timestamp = time.time()

    def watch_model_name(self, old: str, new: str) -> None:
        self.refresh_hud()

    def watch_agent_name(self, old: str, new: str) -> None:
        self.refresh_hud()

    def watch_locked(self, old: bool, new: bool) -> None:
        self.refresh_hud()

    def watch_brain_emotion(self, old: str, new: str) -> None:
        self.refresh_hud()

    def watch_pipeline_active(self, old: list, new: list) -> None:
        self.refresh_hud()

    def refresh_hud(self) -> None:
        """Re-render the brain-core HUD."""
        elapsed = time.time() - self._start_time
        uptime = int(elapsed)
        mins, secs = divmod(uptime, 60)
        hours, mins = divmod(mins, 60)

        mem_str = f"{self.memory_mb:.1f} MB" if self.memory_mb > 0 else "—"
        cpu_str = f"{self.cpu_pct:.1f}%" if self.cpu_pct > 0 else "—"
        tps = (self.tokens_per_sec or 0)
        tps_str = f"{tps:.1f}" if tps > 0 else "—"
        lat_str = f"{self.latency_ms:.0f} ms" if self.latency_ms > 0 else "—"

        lock_icon = "🔒" if self.locked else "🔓"
        lock_color = "yellow" if self.locked else "green"

        # Orb color by severity
        emotion = self.brain_emotion or "normal"
        orb_colors = {
            "calm": "green",
            "normal": "cyan",
            "working": "yellow",
            "dangerous": "red",
            "aggressive": "orange",
        }
        orb = orb_colors.get(emotion, "dim")
        orb_icon = {
            "calm": "●",
            "normal": "◉",
            "working": "◎",
            "dangerous": "◉",
            "aggressive": "◉",
        }.get(emotion, "●")

        # Pipeline: show active stages
        pipeline_active = self.pipeline_active or []
        pipeline_labels = {
            "input": "INPUT",
            "memory": "MEMORY",
            "knowledge": "KNOWLEDGE",
            "reasoning": "REASONING",
            "planner": "PLANNER",
            "tools": "TOOLS",
            "execution": "EXECUTION",
            "verify": "VERIFY",
        }
        pipeline_str = " ".join(
            f"{pipeline_labels.get(k, k):<12}" for k in pipeline_active
        ) or "—all stages idle—"

        left = f"model {self.model_name}"
        mid = f"agent {self.agent_name} session {self.session_id}"
        right = f"mem {mem_str} cpu {cpu_str} ↑ {tps_str} lat {lat_str} uptime {hours:02d}:{mins:02d}:{secs:02d}"
        lock = f"{lock_icon} {'locked' if self.locked else 'unlocked'}"
        orb_colored = f"{orb_icon} {emotion}"
        pipeline_colored = f"pipeline: {pipeline_str}"

        from rich.text import Text
        t = Text()
        t.append(left, "yellow")
        t.append(" │ ", "dim")
        t.append(mid, "white")
        t.append(" │ ", "dim")
        t.append(right, "dim")
        t.append(" │ ", "dim")
        t.append(orb_colored, orb)
        t.append(" │ ", "dim")
        t.append(lock, lock_color)
        t.append(" │ ", "dim")
        t.append(pipeline_colored, "dim")
        self.update(t)

    def set_tokens(self, n: int) -> None:
        """Record token count for tps calculation."""
        now = time.time()
        dt = now - self._token_timestamp
        if dt > 0.5 and self._last_tokens > 0:
            self.tokens_per_sec = (n - self._last_tokens) / dt
        self._last_tokens = n
        self._token_timestamp = now
