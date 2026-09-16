from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static
from textual.containers import Vertical, Container
from textual import on
from textual.message import Message
from textual.screen import ModalScreen
import asyncio
import os
import resource
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from app.config.settings import get_settings
from app.config.logging import get_logger
from app.services.llm_service import LLMService, ChatMessage
from app.brain.lock import SessionLock
from app.brain.orchestrator import Orchestrator
from app.brain.agent_registry import AGENT_DEFS, persona_for
from app.brain.intent_detector import detect_intent, _INTENT_RULES

logger = get_logger("moontm.tui")

UNLOCK_PHRASE = os.environ.get("MOON_TUI_UNLOCK", "MOON love you 3000")


# ── palette ────────────────────────────────────────────────────────────────
MOONSCAPE = {
    "background": "#0a0a0a",
    "surface": "#111111",
    "yellow": "#f1c40f",
    "green": "#2ecc71",
    "red": "#e74c3c",
    "white": "#e0e0e0",
    "dim": "#666666",
    "border": "#333333",
}


class StatusHUD(Static):
    """Live metrics bar — 3 rows."""

    model_name = ""
    agent_name = ""
    session_id = ""
    memory_mb = 0.0
    cpu_pct = 0.0
    tokens_per_sec = 0.0
    latency_ms = 0
    uptime_s = 0
    locked = False

    def render(self) -> Text:
        # Compact HUD line like moonscope: model │ agent │ session │ metrics │ lock.
        # Split across Text segments so Rich doesn't wrap mid-line; only non-empty
        # metrics are shown so the lock indicator always fits a standard 80-col
        # terminal.
        mem = f"{self.memory_mb:.0f}MB" if self.memory_mb > 0 else "—"
        cpu = f"{self.cpu_pct:.1f}%" if self.cpu_pct > 0 else "—"
        tps = f"{self.tokens_per_sec:.1f}" if self.tokens_per_sec > 0 else "—"
        lat = f"{self.latency_ms}ms" if self.latency_ms > 0 else "—"
        up = f"{self.uptime_s}s" if self.uptime_s > 0 else "—"
        parts: list[str] = []
        if self.memory_mb > 0:
            parts.append(f"{mem}")
        if self.cpu_pct > 0:
            parts.append(f"{cpu}")
        if self.tokens_per_sec > 0:
            parts.append(f"{tps}")
        if self.latency_ms > 0:
            parts.append(f"{lat}")
        if self.uptime_s > 0:
            parts.append(f"{up}")
        metrics = " ".join(parts) if parts else "—"
        lock_icon = "🔓" if not self.locked else "🔒"
        lock_state = "UNLOCKED" if not self.locked else "LOCKED"
        return Text.assemble(
            Text(f"model={self.model_name}", style="white"),
            Text("  ", style="dim"),
            Text(f"agent={self.agent_name}", style="white"),
            Text("  ", style="dim"),
            Text(f"session={self.session_id}", style="white"),
            Text("  │  ", style="dim"),
            Text(metrics, style="dim"),
            Text("  │  ", style="dim"),
            Text(f"{lock_icon} {lock_state}", style="dim"),
        )


class ChatPanel(Static):
    """Conversation history — top to bottom."""

    messages: list[tuple[str, str]] = []  # (role, text)

    def _render_messages(self) -> Text:
        out = Text()
        for role, text in self.messages[-80:]:
            if role == "user":
                out.append(f"You: {text}\n", style="white bold")
            elif role == "agent":
                out.append(f"MOON: {text}\n", style="green bold")
            elif role == "system":
                out.append(f"{text}\n", style="dim")
            elif role == "error":
                out.append(f"ERROR: {text}\n", style="red")
            else:
                out.append(f"{text}\n", style="dim")
        return out

    def watch_messages(self, messages: list[tuple[str, str]]) -> None:
        self.update(self._render_messages())


class Moonscope(App):
    """MOON Terminal TUI — moonscope."""

    TITLE = "MOON — moonscope"
    SUB_TITLE = "terminal interface"

    CSS = """
    Screen {
        background: #0a0a0a;
    }
    Header {
        background: #111111;
        color: #f1c40f;
        height: 3;
    }
    Footer {
        background: #111111;
        color: #666666;
    }
    #chat-panel {
        background: #0a0a0a;
        border: solid #333333;
        border-top: hidden;
        border-bottom: hidden;
        height: 1fr;
        padding: 1;
    }
    #hud {
        background: #111111;
        border: solid #333333;
        border-top: hidden;
        border-bottom: hidden;
        height: 3;
        padding: 0 1;
        color: #e0e0e0;
    }
    #input-bar {
        background: #111111;
        border: solid #333333;
        border-top: hidden;
        color: #f1c40f;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._state = None
        self._orc = None
        self._chat_messages: list[tuple[str, str]] = []
        self._llm: LLMService | None = None
        self._start_time = time.time()
        self._last_token_time = time.time()
        self._token_count = 0

    def compose(self) -> ComposeResult:
        """Build the widget layout: chat panel, HUD bar, input bar."""
        yield Header()
        yield ChatPanel(id="chat-panel")
        yield StatusHUD(id="hud")
        yield Input(id="input-bar", placeholder="> ")

    def on_mount(self) -> None:
        settings = get_settings()
        self._state = {
            "model_name": settings.model_name,
            "agent_name": "coordinator",
            "session_id": "main",
        }
        self._chat_messages = [
            ("system", f"MOON terminal ready. Model: {settings.model_name}"),
            ("system", "Type /help for commands."),
        ]
        self.query_one(ChatPanel).messages = self._chat_messages

        # HUD reactive vars
        hud = self.query_one(StatusHUD)
        hud.model_name = settings.model_name
        hud.agent_name = "coordinator"
        hud.session_id = "main"
        hud.locked = True  # boot locked — await 'MOON love you 3000'
        self.query_one(Input).focus()

        # start HUD ticker
        self.set_interval(2.0, self._tick_hud)

        self.query_one(Input).focus()

    def _tick_hud(self) -> None:
        hud = self.query_one(StatusHUD)
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            hud.memory_mb = usage.ru_maxrss / 1024.0
        except Exception:
            hud.memory_mb = 0
        try:
            with open("/proc/loadavg") as f:
                hud.cpu_pct = float(f.read().split()[0])
        except Exception:
            hud.cpu_pct = 0
        hud.uptime_s = int(time.time() - self._start_time)

    @on(Input.Submitted)
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()

        # Append user message BEFORE clearing input
        self._chat_messages.append({"role": "user", "content": text})
        self.query_one(ChatPanel).messages = self._chat_messages

        self.query_one(Input).value = ""
        if not text:
            return
        await self._handle_input(text)

    async def _handle_input(self, text: str) -> None:
        # append user message
        self._chat_messages.append(("user", text))
        self.query_one(ChatPanel).messages = self._chat_messages

        # lock check — block non-unlock input while locked
        if self.query_one(StatusHUD).locked:
            if text.strip().casefold() == UNLOCK_PHRASE.casefold():
                self.query_one(StatusHUD).locked = False
                self._chat_messages.append(("system", "🔓 Unlocked! MOON is now active."))
                self._chat_messages.append(("agent", "🔓 MOON is now unlocked. Active operations are enabled. Say 'moon' to wake the listening state."))
                self.query_one(ChatPanel).messages = self._chat_messages
            else:
                self._chat_messages.append(("system", "🔒 MOON is locked. Say 'MOON love you 3000' to unlock."))
                self.query_one(ChatPanel).messages = self._chat_messages
            return

        if text.startswith("/"):
            await self._dispatch_command(text)
            return

        await self._chat_with_llm(text)

    async def _dispatch_command(self, text: str) -> None:
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers: dict[str, callable] = {
            "/help": self._cmd_help,
            "/clear": self._cmd_clear,
            "/model": self._cmd_model,
            "/agent": self._cmd_agent,
            "/status": self._cmd_status,
            "/voice": self._cmd_voice,
            "/quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                await handler(args)
            except Exception as exc:
                self._chat_messages.append(("system", f"[red]Error running {cmd}: {exc}[/red]"))
                self.query_one(ChatPanel).messages = self._chat_messages
        else:
            self._chat_messages.append(("system", f"Unknown command: {cmd}. Type /help."))
            self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_help(self, args: str) -> None:
        help_text = (
            "/help       — show this help\n"
            "/clear      — clear chat\n"
            "/model NAME — switch model\n"
            "/agent NAME — switch agent\n"
            "/status     — show status\n"
            "/voice      — toggle voice\n"
            "/quit       — exit MOON"
        )
        self._chat_messages.append(("system", help_text))
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_clear(self, args: str) -> None:
        self._chat_messages = [("system", "Chat cleared.")]
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_model(self, args: str) -> None:
        if self._state is None:
            self._chat_messages.append(("system", "Not initialized yet."))
            self.query_one(ChatPanel).messages = self._chat_messages
            return
        if not args:
            self._chat_messages.append(("system", f"Current model: {self._state['model_name']}"))
        else:
            self._state["model_name"] = args
            self.query_one(StatusHUD).model_name = args
            self._chat_messages.append(("system", f"Model set to: {args}"))
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_agent(self, args: str) -> None:
        if self._state is None:
            self._chat_messages.append(("system", "Not initialized yet."))
            self.query_one(ChatPanel).messages = self._chat_messages
            return

        all_agents = sorted(AGENT_DEFS.keys())
        if not args:
            cur = self._state["agent_name"]
            avail = ", ".join(all_agents[:6]) + f" ... (+{len(all_agents)-6} more)"
            self._chat_messages.append(("system", f"Current agent: {cur}\nAvailable ({len(all_agents)}): {avail}"))
            self.query_one(ChatPanel).messages = self._chat_messages
            return

        name = args.strip().lower()
        if name in AGENT_DEFS:
            self._state["agent_name"] = name
            self.query_one(StatusHUD).agent_name = name
            persona = persona_for(name)
            self._chat_messages.append(("system", f"Agent → {name}"))
            self._chat_messages.append(("system", persona))
            self.query_one(ChatPanel).messages = self._chat_messages
        else:
            self._chat_messages.append(("system", f"Unknown agent '{name}'. Available: {', '.join(all_agents[:6])}..."))
            self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_status(self, args: str) -> None:
        hud = self.query_one(StatusHUD)
        status = (
            f"model: {hud.model_name}\n"
            f"agent: {hud.agent_name}\n"
            f"session: {hud.session_id}\n"
            f"mem: {hud.memory_mb:.0f}MB\n"
            f"cpu: {hud.cpu_pct:.1f}%\n"
            f"uptime: {hud.uptime_s}s\n"
            f"locked: {hud.locked}"
        )
        self._chat_messages.append(("system", status))
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_voice(self, args: str) -> None:
        self._chat_messages.append(("system", "Voice: available (Kokoro/F5/XTTS/OpenAI/espeak chain)"))
        self.query_one(ChatPanel).messages = self._chat_messages

    async def _cmd_quit(self, args: str) -> None:
        self.exit()

    async def _chat_with_llm(self, prompt_text: str) -> None:
        self._chat_messages.append(("system", "thinking..."))
        self.query_one(ChatPanel).messages = self._chat_messages

        try:
            settings = get_settings()
            self._llm = LLMService(
                base_url=settings.model_base_url,
                model_name=settings.model_name,
                api_key="not-required" if "127.0.0.1" in settings.model_base_url else "",
                timeout=settings.model_timeout,
            )
            await self._llm.setup()

            # ── Agent routing: explicit agent: prefix, else intent auto-detect ──
            agent_name = self._state.get("agent_name", "assistant") if self._state else "assistant"
            routed_prompt = prompt_text
            system_persona = ""
            # Explicit agent selection: "agent_name: task text"
            if ":" in prompt_text and not prompt_text.startswith("/"):
                prefix, _, routed_prompt = prompt_text.partition(":")
                prefix = prefix.strip().lower()
                if prefix in AGENT_DEFS:
                    agent_name = prefix
                    system_persona = persona_for(prefix)
                    self._state["agent_name"] = agent_name
                    if self.query_one(StatusHUD).agent_name != agent_name:
                        self.query_one(StatusHUD).agent_name = agent_name

            # Auto-detect intent when no explicit agent given
            if not system_persona and self._state:
                try:
                    conversation = self._state.get("conversation_history")
                    if isinstance(conversation, list):
                        history: list[dict] = conversation
                    else:
                        history = []
                    intent_label, _conf = detect_intent(routed_prompt)
                    # map intent label -> agent name via orchestrator's intent→agent table
                    intent_agent: str | None = None
                    if isinstance(intent_label, str) and intent_label in AGENT_DEFS:
                        intent_agent = intent_label
                    elif isinstance(intent_label, str) and intent_label in _INTENT_RULES:
                        # translate intent token to agent name via common mapping
                        intent_map = {
                            "code": "coding", "research": "research", "web": "browser",
                            "writing": "writing", "vision": "vision", "planning": "planning",
                            "math": "math", "science": "science", "data_science": "data_science",
                            "security": "security", "cyber": "cyber", "red_team": "red_team",
                            "blue_team": "blue_team", "forensics": "forensics", "reverse_eng": "reverse_eng",
                            "threat_hunt": "threat_hunt", "siem": "siem", "translation": "translation",
                            "audio": "audio", "qa": "qa", "infra": "infra", "finance": "finance",
                            "legal": "legal", "medical": "medical", "design": "design",
                            "summarizer": "summarizer", "fact_check": "fact_checker",
                            "strategy": "strategist", "tools": "toolsmith", "github_sync": "github_sync",
                            "voice": "assistant", "system": "assistant", "chat": "assistant",
                            "unknown": "assistant",
                        }
                        mapped = intent_map.get(intent_label)
                        if mapped and mapped in AGENT_DEFS:
                            intent_agent = mapped
                    if intent_agent and intent_agent in AGENT_DEFS:
                        agent_name = intent_agent
                        system_persona = persona_for(intent_agent)
                        self._state["agent_name"] = agent_name
                        if self.query_one(StatusHUD).agent_name != agent_name:
                            self.query_one(StatusHUD).agent_name = agent_name
                except Exception:
                    pass  # Fall back to current / default agent

            t0 = time.time()
            messages: list[ChatMessage] = []
            if system_persona:
                messages.append(ChatMessage(role="system", content=system_persona))
            messages.append(ChatMessage(role="user", content=routed_prompt))
            result = await self._llm.complete(messages)
            elapsed = (time.time() - t0) * 1000

            if result.content:
                self._chat_messages.append(("agent", result.content))
            else:
                self._chat_messages.append(("error", "No response from model."))
        except Exception as exc:
            logger.exception("LLM error: %s", exc)
            self._chat_messages.append(("error", f"LLM error: {exc}"))
        finally:
            if self._llm:
                try:
                    await self._llm._client.aclose()
                except Exception:
                    pass

        self.query_one(ChatPanel).messages = self._chat_messages

    def action_quit(self) -> None:
        """Quit the standalone moonscope TUI — no WS client to clean up."""
        self.exit()
def main() -> None:
    Moonscope().run()


if __name__ == "__main__":
    main()
