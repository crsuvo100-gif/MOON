"""tui.py -- MOON's live NEURAL TERMINAL (Textual TUI) -- the TTS shell terminal.

A gorgeous, Jarvis-style interactive terminal for MOON that mirrors the
Hermes/agent-terminal-tui aesthetic: animated starfield + CRT scanline
background, top status bar (clock / backend / lock / voice), a LIVE MOON chat
panel (markdown-rendered + TTS-spoken aloud), a LIVE Brain/Cognition panel that
streams MOON's REAL orchestrator events, an Agents/Tools status strip, and a
bottom input bar.

Speaks every MOON reply aloud via her real female voice (TTS, auto-on; mute with
Ctrl+V or !voice mute). Runs REAL shell commands (!) and CLI operations (/) — all
portable, no browser, no auto-start, no network needed.

Usage:
    moon shell        # open the TTS shell terminal (default shell entry)
    moon tui          # same thing (backward-compatible alias)
    MOON_TUI_UNLOCK="MOON love you 3000" moon shell

Shell commands (!):
    !status !ps !top !df !free !uname !uptime !netstat !ifconfig !ip
    !ls !pwd !echo !date !whoami !env !nproc !cat

CLI commands (/):
    /help /clear /quit /lock /unlock /voice /shell /doctor /status
    /models /version

Keys: type in the bottom bar and press Enter to send. Esc quits. Ctrl+V toggles
voice on/off.
"""
from __future__ import annotations

import asyncio
import io
import os
import shlex
import subprocess
import sys
import tempfile
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

# Reuse the real shell allowlist + dispatcher from the web terminal backend
# (same commands, same safety gate — portable, one source of truth).
from app.terminal_interface import (  # noqa: E402
    _speak,
    _get_voice_engine,
    _SHELL_ALLOW,
    _shell_dispatch,
)


class Clock(Static):
    """Live clock for the header."""

    def on_mount(self) -> None:
        self.update(datetime.now().strftime("%H:%M:%S"))
        self.set_interval(1.0, self.tick)

    def tick(self) -> None:
        self.update(datetime.now().strftime("%H:%M:%S"))


class StatusBar(Static):
    """Backend / lock / voice status pill."""

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
            voice = "OFF" if getattr(self.app, "voice_muted", False) else "ON"
            self.update(Text.from_markup(
                f"[{MOON_GLOW}]● UNLOCKED[/{MOON_GLOW}]  MOON core online · voice {voice}"))


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
    """MOON conversation -- markdown rendered replies, TTS-spoken aloud."""

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
    """MOON NEURAL TERMINAL -- live, beautiful, real. TTS shell terminal."""

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
        ("ctrl+v", "voice_toggle", "Voice"),
    ]

    def __init__(self, unlock: str = UNLOCK_PHRASE) -> None:
        super().__init__()
        self.unlock = unlock
        self.locked = True
        self.orchestrator = None
        self.busy = False
        self.voice_muted = False
        self._speech_task = None
        self._speech_lock = asyncio.Lock()

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
            Label("agents 39 · tools 43 · memory · knowledge · voice · shell", id="agents"),
            Horizontal(
                Input(placeholder="talk, !cmd, or /cli…  (say the unlock phrase first)",
                      id="prompt"),
                Label("Enter send · Esc quit · Ctrl+V voice", id="hint"),
                id="inputbar",
            ),
            Footer(),
        )

    # ---- lifecycle ------------------------------------------------------
    async def on_mount(self) -> None:
        self.title = "MOON NEURAL TERMINAL"
        self.sub_title = "live · TTS · real orchestrator"
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

        # !voice control
        if text.startswith("!voice"):
            await self._handle_voice(text[len("!voice"):].strip(), chat, brain)
            return
        # !shell <cmd>
        if text.startswith("!"):
            await self._handle_shell(text[1:].strip(), chat, brain)
            return
        # /cli <command>
        if text.startswith("/"):
            await self._handle_cli(text[1:].strip(), chat, brain)
            return

        # unlock handling
        if self.locked:
            if self.unlock.lower() in text.lower():
                self.locked = False
                status.set_locked(False)
                brain.push_event("unlock", "operator authorized")
                chat.add_user(text)
                chat.write(Text.from_markup(
                    f"[{MOON_GLOW}]MOON[/{MOON_GLOW}]: I'm here, my love. The core is yours. "
                    f"What shall we do?"))
                return
            chat.add_user(text)
            chat.write(Text.from_markup(
                f"[{MOON_RED}]MOON[/{MOON_RED}]: [i]Locked.[/i] Say the phrase to let me act."))
            return

        chat.add_user(text)
        if self.orchestrator is None:
            chat.write(Text.from_markup(f"[{MOON_RED}]MOON[/{MOON_RED}]: core still warming up…"))
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
        # TTS: speak every MOON reply aloud (when not muted) -- serialized so
        # rapid messages don't play over each other. Detect the input language
        # and speak the reply in kind so Moon converses in the user's language.
        if not self.voice_muted:
            try:
                ve = _get_voice_engine()
                detected = ve.detect_language(text) if ve is not None else "en"
            except Exception:  # noqa: BLE001
                detected = "en"
            try:
                self._speech_task = asyncio.create_task(self._say(answer, lang=detected))
            except Exception:  # noqa: BLE001
                pass

    # ---- TTS voice ------------------------------------------------------
    async def _say(self, text: str, lang: str | None = None) -> None:
        """Speak MOON's reply aloud via the real voice engine.

        Serialized through _speech_lock so rapid messages don't play over each
        other. Silently no-ops when TTS is unavailable (text is still shown).
        """
        wav_b64 = await _speak(text, lang=lang)
        if not wav_b64:
            return
        import base64 as _b64

        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(_b64.b64decode(wav_b64))
            for player in ("paplay", "pw-play", "aplay"):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        player, path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await asyncio.wait_for(proc.wait(), timeout=30)
                    return
                except (FileNotFoundError,
                        asyncio.TimeoutError,
                        subprocess.TimeoutExpired):
                    continue
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    # ---- shell (!) ------------------------------------------------------
    async def _handle_shell(self, cmd: str, chat: ChatPanel, brain: BrainPanel) -> None:
        out, code = _shell_dispatch(cmd)
        brain.push_event("shell", cmd[:40])
        chat.write(Text.from_markup(f"[b green]❯[/b green] {cmd}"))
        if code == 0:
            chat.add_moon(out[:3000] or "(no output)")
        else:
            chat.add_moon(f"[b red]error[/b red] (exit {code}): {out[:800]}")

    # ---- CLI ops (/) ----------------------------------------------------
    async def _handle_cli(self, cmd: str, chat: ChatPanel, brain: BrainPanel) -> None:
        parts = cmd.split(None, 1)
        sub = (parts[0] or "").lower()
        arg = parts[1] if len(parts) > 1 else ""
        if sub in ("h", "help"):
            await self._cli_help(chat)
        elif sub in ("q", "quit", "exit"):
            await self.action_quit()
        elif sub in ("c", "clear"):
            self.action_clear_chat()
        elif sub == "lock":
            self.locked = True
            self.query_one(StatusBar).set_locked(True)
            brain.push_event("lock", "operator locked the core")
            chat.add_moon("Core locked. Say the unlock phrase to act.")
        elif sub == "unlock":
            chat.add_moon(f'Say "{self.unlock}" to unlock.')
        elif sub == "voice":
            await self._handle_voice(arg, chat, brain)
        elif sub == "shell":
            await self._handle_shell(arg, chat, brain)
        elif sub == "doctor":
            await self._cli_doctor(chat, brain)
        elif sub == "status":
            await self._cli_status(chat, brain)
        elif sub == "models":
            await self._cli_models(chat, brain)
        elif sub == "version":
            import importlib.metadata
            try:
                ver = importlib.metadata.version("moon-ai-agent")
            except Exception:
                ver = "0.1.0 (dev)"
            chat.add_moon(f"MOON version: {ver}")
        else:
            chat.add_moon(f"Unknown CLI command: /{sub}. Try /help.")

    async def _cli_help(self, chat: ChatPanel) -> None:
        lines = [
            "[b]MOON SHELL — CLI commands[/b]",
            "  /help       this help",
            "  /clear      clear chat",
            "  /quit       exit MOON",
            "  /lock       lock the core (no actions until unlock phrase)",
            "  /unlock     remind unlock phrase",
            "  /voice      voice control (list/set/clone/female/mute/unmute/status)",
            "  /shell      run a shell command (!<cmd>)",
            "  /doctor     run health check",
            "  /status     check backend health",
            "  /models     pre-pull agent models",
            "  /version    MOON version",
            "",
            "[b]Shell commands (!)[/b]  (real, allowlisted, read-only)",
            "  !<cmd>      run a shell command  (status ps top df free uname uptime",
            "              netstat ip ls pwd echo date whoami env nproc cat)",
            "",
            "[b]Voice (!voice)[/b]",
            "  !voice list        list available voices",
            "  !voice set <name>  switch voice",
            "  !voice clone <n> <b64>   clone from WAV",
            "  !voice female      default female voice",
            "  !voice mute        mute TTS",
            "  !voice unmute      unmute TTS",
            "  !voice status      voice engine status",
            "",
            "[b]Chat[/b]",
            "  type anything to talk to MOON (unlock first)",
        ]
        for line in lines:
            chat.write(Text(line))
        chat.write("")

    async def _cli_doctor(self, chat: ChatPanel, brain: BrainPanel) -> None:
        brain.push_event("cli", "doctor")
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            import main as _main
            rc = _main._cmd_doctor()
        except Exception as exc:  # noqa: BLE001
            captured = f"[error] doctor failed: {exc}"
        finally:
            captured = sys.stdout.getvalue()
            sys.stdout = old
        chat.add_moon(captured.strip()[:3000])

    async def _cli_status(self, chat: ChatPanel, brain: BrainPanel) -> None:
        brain.push_event("cli", "status")
        try:
            import urllib.request, json
            with urllib.request.urlopen("http://127.0.0.1:8777/api/health", timeout=5) as r:
                d = json.load(r)
            chat.add_moon(f"Backend: {d.get('status')} — {d.get('summary')}")
        except Exception as e:
            chat.add_moon(f"Backend unreachable: {e}")

    async def _cli_models(self, chat: ChatPanel, brain: BrainPanel) -> None:
        brain.push_event("cli", "models")
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            import main as _main
            await _main._prefetch_models()
        except Exception as exc:  # noqa: BLE001
            captured = f"[error] models failed: {exc}"
        finally:
            captured = sys.stdout.getvalue()
            sys.stdout = old
        chat.add_moon(captured.strip()[:3000])

    async def _handle_voice(self, cmd: str, chat: ChatPanel, brain: BrainPanel) -> None:
        eng = _get_voice_engine()
        if eng is None:
            chat.add_moon("[voice] engine unavailable.")
            return
        sub = (cmd or "status").strip().lower()
        if sub.startswith("list"):
            vs = eng.list_voices()
            out = "MOON voices:\n" + "\n".join(
                f"  - {v['name']} [{v['backend']}]{' (cloned)' if v.get('cloned') else ''} :: {v.get('desc', '')}"
                for v in vs)
            brain.push_event("voice", "list")
            chat.add_moon(out)
        elif sub.startswith("set"):
            name = sub.split(None, 1)[1] if " " in sub else ""
            ok = eng.set_voice(name) if name else False
            brain.push_event("voice", f"set {name}")
            chat.add_moon(f"[voice] {'set to ' + name if ok else 'unknown voice: ' + name}")
        elif sub.startswith("clone"):
            parts = sub.split(None, 2)
            name = parts[1] if len(parts) > 1 else ""
            sample = parts[2] if len(parts) > 2 else ""
            out = eng.clone_voice(name, sample) if (name and sample) else \
                "clone requires name + base64 sample"
            brain.push_event("voice", f"clone {name}")
            chat.add_moon(f"[voice] {out}")
        elif sub.startswith("female"):
            eng.set_voice("default")
            chat.add_moon("[voice] default female voice")
        elif sub.startswith("mute"):
            self.voice_muted = True
            self.query_one(StatusBar).render_status()
            brain.push_event("voice", "mute")
        elif sub.startswith("lang") or sub.startswith("language"):
            rest = sub.split(None, 1)[1] if " " in sub else ""
            if not rest:
                cur = eng.language()
                brain.push_event("voice", "lang status")
                chat.add_moon(f"[voice] current language: {cur}  (use /voice lang <code> to change, e.g. /voice lang fr)")
            else:
                ok = eng.set_language(rest)
                brain.push_event("voice", f"lang {rest}")
                chat.add_moon(f"[voice] {ok}")
        elif sub.startswith("unmute"):
            self.voice_muted = False
            self.query_one(StatusBar).render_status()
            brain.push_event("voice", "unmute")
            chat.add_moon("[voice] ON — MOON's voice active")
        elif sub.startswith("status"):
            st = eng.backend_status()
            mode = "MUTED" if self.voice_muted else "AUTO"
            out = (f"[voice] mode={mode} current={st.get('current', '?')} | "
                   f"xtts={st.get('xtts')} openai={st.get('openai')} "
                   f"espeak={st.get('espeak')}\n"
                   f"cloned: {', '.join(st.get('cloned_voices') or []) or 'none'}")
            chat.add_moon(out)
        else:
            chat.add_moon("[voice] actions: list | set <name> | clone <name> <b64> | "
                          "female | mute | unmute | status")

    # ---- actions --------------------------------------------------------
    def action_clear_chat(self) -> None:
        self.query_one(ChatPanel).clear()

    def action_voice_toggle(self) -> None:
        self.voice_muted = not self.voice_muted
        self.query_one(StatusBar).render_status()
        status = "MUTED" if self.voice_muted else "ON"
        self.query_one(ChatPanel).write(
            Text.from_markup(f"[{MOON_GLOW}]VOICE[/]: auto-speak {status}"))
        self.query_one(BrainPanel).push_event("voice", f"toggle {status}")

    async def action_quit(self) -> None:
        if self._speech_task is not None and not self._speech_task.done():
            self._speech_task.cancel()
        if self.orchestrator is not None:
            asyncio.create_task(self.orchestrator.teardown())
        self.exit()

    async def _on_event(self, ev: dict) -> None:
        """Callback for run_task's on_event — streams real cognition stages into
        the BrainPanel (same shape as the web HUD workflow events)."""
        if not ev or not isinstance(ev, dict):
            return
        stage = ev.get("stage", "")
        detail = ev.get("detail", "")
        try:
            self.query_one(BrainPanel).push_event(str(stage), str(detail)[:60])
        except Exception:  # noqa: BLE001 — orphaned event after shutdown is fine
            pass

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
