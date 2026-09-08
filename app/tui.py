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
from typing import Any

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
        """Build the widget layout: chat panel, HUD bar, input bar."""
        yield Header()
        yield ChatPanel(id="chat-panel")
        yield StatusHUD(id="hud")
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

        # Wire HUD reactive vars
        hud = self.query_one(StatusHUD)
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

    def _tick_hud(self) -> None:
        """Update HUD stats from system info."""
        hud = self.query_one(StatusHUD)
        try:
            import resource
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            hud.memory_mb = rss_kb / 1024
        except Exception:
            hud.memory_mb = 0

        hud.refresh_hud()

    async def _handle_input(self, text: str) -> None:
        """Dispatch user input — mirrors CLI dispatch but in TUI context."""
        text = text.strip()
        if not text:
            return

        # Add user message to chat
        self._chat_messages.append({"role": "user", "content": text})
        self.query_one(ChatPanel).messages = self._chat_messages
        self.query_one(StatusHUD).set_tokens(len(text.split()))

        # Check for lock
        if self._state and getattr(self._state, "locked", False):
            if text.strip() == UNLOCK_PHRASE:
                self._state.locked = False
                self.query_one(StatusHUD).locked = False
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
        self.query_one(StatusHUD).set_tokens(len(prompt_text.split()))

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
        """Quit the TUI."""
        self.exit()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    """Launch moonscope TUI."""
    app = Moonscope()
    app.run()


if __name__ == "__main__":
    main()
