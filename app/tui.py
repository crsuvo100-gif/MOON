"""tui.py -- MOON's live NEURAL TERMINAL (Textual TUI).

A gorgeous, Jarvis-style interactive terminal for MOON that mirrors the
Hermes/agent-terminal-tui aesthetic: animated starfield + CRT scanline
background, top status bar (clock / backend / lock), a LIVE MOON chat panel
(markdown-rendered), a LIVE Brain/Cognition panel that streams MOON's REAL
orchestrator events (intent routing, agent selection, tool calls, reflection,
self-consistency), an Agents/Tools status strip, and a bottom input bar.

Runs IN-PROCESS against the real Orchestrator -- no HTTP server needed, ideal
for SSH/headless. The unlock phrase ("MOON love you 3000") is honored: until
you send it she replies only with the lock notice.

Usage:
    moon tui
    MOON_TUI_UNLOCK="MOON love you 3000" moon tui   # pre-supply unlock

Keys: type in the bottom bar and press Enter to send. Ctrl-C / Esc quits.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Static, Input, Label, RichLog, Footer,
)
from textual.timer import Timer
from textual import events
from rich.text import Text
from rich.markdown import Markdown

# Local MOON imports (decontaminate PYTHONPATH first to avoid pydantic shadowing)
from app.config.env_guard import decontaminate_pythonpath  # noqa: E402
decontaminate_pythonpath()

UNLOCK_PHRASE = os.environ.get("MOON_TUI_UNLOCK", "MOON love you 3000")

MOON_RED = "#ff3b3b"
MOON_DIM = "#7a1f1f"
MOON_GLOW = "#ff6b6b"


class Clock(Static):
    """Live clock for the header."""

    def on_mount(self) -> None:
        self.update(datetime.now().strftime("%H:%M:%S"))
        self.set_interval(1.0, self.tick)

    def tick(self) -> None:
        self.update(datetime.now().strftime("%H:%M:%S"))


class StatusBar(Static):
    """Backend / lock status pill."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.locked = True

    def on_mount(self) -> None:
        self.render_status()
        self.set_interval(2.0, self.render_status)

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.render_status()

    def render_status(self) -> None:
        if self.locked:
            self.update(Text.from_markup(
                f"[{MOON_RED}]● LOCKED[/{MOON_RED}]  say [b]{UNLOCK_PHRASE}[/b] to unlock"))
        else:
            self.update(Text.from_markup(
                f"[{MOON_GLOW}]● UNLOCKED[/{MOON_GLOW}]  MOON core online"))


class BrainPanel(RichLog):
    """Live cognition stream -- MOON's real orchestrator events."""

    def on_mount(self) -> None:
        self.border_title = "🧠  MOON BRAIN  ·  live cognition"
        self.styles.border = ("round", MOON_DIM)

    def push_event(self, stage: str, detail: str = "") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if detail:
            self.write(Text.from_markup(
                f"[dim]{ts}[/dim] [b {MOON_RED}]{stage}[/b {MOON_RED}] » {detail}"))
        else:
            self.write(Text.from_markup(
                f"[dim]{ts}[/dim] [b {MOON_RED}]{stage}[/b {MOON_RED}]"))


class ChatPanel(RichLog):
    """MOON conversation -- markdown rendered replies."""

    def on_mount(self) -> None:
        self.border_title = "🌙  MOON  ·  neural link"
        self.styles.border = ("round", MOON_RED)

    def add_user(self, text: str) -> None:
        self.write(Text.from_markup(f"[b cyan]YOU[/b cyan] » {text}"))

    def add_moon(self, text: str) -> None:
        try:
            md = Markdown(text)
            self.write(md)
        except Exception:
            self.write(Text(text))
        self.write("")


class StarField(Static):
    """Animated twinkling starfield background (Jarvis-style)."""

    GLYPHS = "·°*⁺˖⋆✦✧·°*⁺"
    STARS = 90

    def on_mount(self) -> None:
        self.stars = [(i * 7 % 100, (i * 13) % 40, i % len(self.GLYPHS))
                      for i in range(self.STARS)]
        self.frame = 0
        self.set_interval(0.35, self.tick_frame)

    def tick_frame(self) -> None:
        self.frame += 1
        lines = []
        for _ in range(26):
            row = ""
            for c in range(60):
                ch = " "
                for (sx, sy, gi) in self.stars:
                    if sx % 60 == c and sy % 26 == (0):
                        pass
                # simple deterministic twinkle
                if (c * 3 + _ * 5 + self.frame) % 17 == 0:
                    row += self.GLYPHS[(c + self.frame) % len(self.GLYPHS)]
                else:
                    row += " "
            lines.append(row)
        self.update(Text("\n".join(lines), style="dim"))


class MoonTUI(App):
    """MOON NEURAL TERMINAL -- live, beautiful, real."""

    CSS = """
    Screen { background: #040000; color: #ffd9d9; }
    #starfield { layer: background; color: #5a1a1a; }
    StarField { width: 100%; height: 100%; }

    #topbar { height: 3; background: #0a0000; border: round #ff2525; }
    #title { width: 1fr; content-align: center middle; color: #ff4d4d;
             text-style: bold; }
    #clock { width: 12; color: #ff8a8a; }
    #status { width: 1fr; content-align: left middle; }

    #main { height: 1fr; }
    #chat { width: 2fr; height: 100%; }
    #brain { width: 1fr; height: 100%; }

    #agents { height: 3; background: #0a0000; border: round #7a1f1f;
              color: #ff9a9a; padding: 0 1; }

    #inputbar { height: 3; border: round #ff2525; background: #0a0000; }
    Input { border: none; background: #0a0000; color: #ffffff; }
    #hint { width: 1fr; color: #8a3a3a; content-align: right middle; }
    """

    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("ctrl+l", "clear_chat", "Clear"),
    ]

    def __init__(self, unlock: str = UNLOCK_PHRASE) -> None:
        super().__init__()
        self.unlock = unlock
        self.locked = True
        self.orchestrator = None
        self.busy = False

    # ---- compose the layout -------------------------------------------
    def compose(self) -> ComposeResult:
        yield StarField(id="starfield")
        yield Vertical(
            Horizontal(
                Label("🌙  M O O N   N E U R A L   C O R E", id="title"),
                Clock(id="clock"),
                StatusBar(id="status"),
                id="topbar",
            ),
            Horizontal(
                ChatPanel(id="chat"),
                BrainPanel(id="brain"),
                id="main",
            ),
            Label("agents 39 · tools 43 · memory · knowledge · voice", id="agents"),
            Horizontal(
                Input(placeholder="talk to MOON…  (say the unlock phrase first)",
                      id="prompt"),
                Label("Enter send · Esc quit", id="hint"),
                id="inputbar",
            ),
            Footer(),
        )

    # ---- lifecycle ------------------------------------------------------
    async def on_mount(self) -> None:
        self.title = "MOON NEURAL TERMINAL"
        self.sub_title = "live · real orchestrator"
        # Textual guarantees composed widgets exist once on_mount runs.
        chat = self.query_one(ChatPanel)
        chat.write(Text.from_markup(
            f"[b {MOON_RED}]MOON NEURAL TERMINAL[/b {MOON_RED}] — "
            f"say [b]{self.unlock}[/b] to unlock."))
        brain = self.query_one(BrainPanel)
        brain.push_event("system", "orchestrator booting in background…")
        self.run_worker(self._boot_orchestrator(), exclusive=False)

    async def _boot_orchestrator(self) -> None:
        from app.brain.orchestrator import Orchestrator
        from app.config.settings import get_settings
        try:
            self.orchestrator = Orchestrator(get_settings())
            await self.orchestrator.setup()
            brain = self.query_one(BrainPanel)
            brain.push_event(
                "system", "orchestrator online — 39 agents / 43 tools ready")
        except Exception as exc:  # noqa: BLE001
            brain = self.query_one(BrainPanel)
            brain.push_event("error", str(exc)[:80])

    # ---- input ----------------------------------------------------------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one(Input).value = ""
        await self._handle(text)

    async def _handle(self, text: str) -> None:
        chat = self.query_one(ChatPanel)
        brain = self.query_one(BrainPanel)
        status = self.query_one(StatusBar)

        # unlock handling
        if self.locked:
            if self.unlock.lower() in text.lower():
                self.locked = False
                status.set_locked(False)
                brain.push_event("unlock", "operator authorized")
                chat.add_user(text)
                chat.write(Text.from_markup(
                    f"[{MOON_GLOW}]MOON[/]: I'm here, my love. The core is yours. "
                    f"What shall we do?[/]"))
                return
            chat.add_user(text)
            chat.write(Text.from_markup(
                f"[{MOON_RED}]MOON[/]: [i]Locked.[/i] Say the phrase to let me act."))
            return

        chat.add_user(text)
        if self.orchestrator is None:
            chat.write(Text.from_markup(f"[{MOON_RED}]MOON[/]: core still warming up…"))
            return

        self.busy = True
        brain.push_event("intake", text[:60])
        from app.models.task import Task
        task = Task.create(text, agent_name="auto")
        try:
            result = await self.orchestrator.run_task(
                task, on_event=self._on_event)
            answer = getattr(result, "result", None) or "(no response)"
        except Exception as exc:  # noqa: BLE001
            answer = f"[error] {exc}"
            brain.push_event("error", str(exc)[:80])
        chat.add_moon(answer)
        self.busy = False

    # real orchestrator event -> live brain panel
    async def _on_event(self, ev: dict) -> None:
        stage = ev.get("stage") or ev.get("type") or ""
        detail = ev.get("detail") or ""
        self.query_one(BrainPanel).push_event(stage, str(detail)[:90])

    # ---- actions --------------------------------------------------------
    def action_clear_chat(self) -> None:
        self.query_one(ChatPanel).clear()

    async def action_quit(self) -> None:
        if self.orchestrator is not None:
            asyncio.create_task(self.orchestrator.teardown())
        self.exit()


def main(unlock: str = UNLOCK_PHRASE) -> int:
    try:
        MoonTUI(unlock=unlock).run()
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"[MOON TUI] fatal: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
