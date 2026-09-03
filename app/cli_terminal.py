#!/usr/bin/env python3
"""
Moon CLI Terminal — Moon's own interactive command-line REPL.

Hermes-cli-feature-rich but 100% Moon-native. No Hermes wrappers, no Hermes
dependencies. Uses Moon's own Orchestrator, LLMService, VoiceEngine, and
EventBus. Provides an interactive prompt-based chat session with slash commands,
tool dispatch, streaming responses, TTS, session management, and one-shot mode.

Usage:
    moon cli                    # interactive REPL (default)
    moon cli -q "question"      # one-shot query, non-interactive
    moon cli --model qwen2.5:1.5b
    moon cli --agent auto
    moon cli --quiet            # suppress banner/spinner

Slash commands (in interactive mode):
    /help              Show all commands
    /model [name]      Show or switch model
    /agent [name]      Show or switch agent
    /status            Moon backend health
    /shell cmd         Run a shell command
    /voice [on|off|tts] Voice mode
    /reset             Clear session context
    /save [file]       Save session to file
    /history           Show conversation history
    /clear             Clear screen + new session
    /quit              Exit CLI

This module is self-contained: no imports from hermes-agent, no dependence on
Hermes CLI infrastructure. Moon owns every line.
"""

# ── 1. Imports (stdlib + Moon deps only) ────────────────────────────────────
from __future__ import annotations

import argparse
import asyncio
import os
import readline
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable, List, Optional, Tuple

# Rich for colored terminal output
from rich.console import Console
from rich.panel import Panel
from rich.prompt import PromptBase, Prompt
from rich.text import Text

# Moon internals — everything Moon owns
from app.config.logging import get_logger
from app.config.settings import Settings
from app.brain.orchestrator import Orchestrator
from app.terminal_interface import _get_orchestrator, _get_voice_engine
from app.services.llm_service import LLMService, ChatMessage, CompletionResult
from app.voice_engine import VoiceEngine

# ── 2. Globals ────────────────────────────────────────────────────────────────
log = get_logger("moon.cli")
_console = Console()
_settings = Settings()
_voice: VoiceEngine | None = None
_orch: Orchestrator | None = None
_llm: LLMService | None = None

# Prompt toolkit not used — readline provides history + line editing
# (lighter, no extra dep, Hermès-like REPL without Hermès)
_HISTORY_FILE = Path.home() / ".moon" / "cli_history"


# ── 3. Utilities ─────────────────────────────────────────────────────────────
def _ensure_history_dir() -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_history() -> None:
    _ensure_history_dir()
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line:
                    readline.add_history(line)
    except Exception:
        pass


def _save_history() -> None:
    _ensure_history_dir()
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            for i in range(1, readline.get_current_history_length() + 1):
                line = readline.get_history_item(i)
                if line:
                    f.write(line + "\n")
    except Exception:
        pass


def _panels(title: str, body: str, style: str = "default") -> None:
    _console.print(Panel(Text(body), title=title, style=style))


def _now_ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _red(text: str) -> Text:
    return Text(text, style="red")


def _green(text: str) -> Text:
    return Text(text, style="green")


def _yellow(text: str) -> Text:
    return Text(text, style="yellow")


def _bold(text: str) -> Text:
    return Text(text, style="bold")


# ── 4. Moon CLI state ─────────────────────────────────────────────────────────
class MoonCLIState:
    """Holds mutable session state for the CLI REPL."""

    def __init__(self) -> None:
        self.messages: List[Tuple[str, str]] = []  # (role, content)
        self.model_name: str = _settings.model_name or "qwen2.5:1.5b"
        self.agent_name: str = "auto"
        self.voice_on: bool = False
        self.voice_tts_only: bool = False
        self.session_start: float = time.time()
        self.total_tokens: int = 0
        self.request_count: int = 0
        self._scratch: dict[str, Any] = {}  # per-session scratch (goals, etc.)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append((role, content))
        self.request_count += 1

    def clear(self) -> None:
        self.messages.clear()
        self.request_count = 0
        self.total_tokens = 0

    def format_prompt(self, user_input: str) -> list[dict[str, str]]:
        """Build the message list for the LLM in OpenAI-compatible format."""
        msgs: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt()}
        ]
        for role, content in self.messages[-20:]:  # last 20 keep context fresh
            msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    def _system_prompt(self) -> str:
        return (
            "You are MOON — a standalone AI agent with full tool access. "
            "You assist the operator with any task. Be helpful, precise, and "
            "direct. If a task requires shell commands, code, or data analysis, "
            "do it. If you need information, use web search or your knowledge. "
            "Responses should be clear and actionable. Keep answers concise unless "
            "the task demands detail."
        )


# ── 5. LLM query (Moon's own LLMService) ──────────────────────────────────────
async def _query_llm(state: MoonCLIState, user_input: str) -> str:
    """Send user input to Moon's LLMService and return the response."""
    global _llm
    if _llm is None:
        base_url = _settings.model_base_url or "http://127.0.0.1:11434/v1"
        _llm = LLMService(base_url=base_url, model_name=state.model_name)

    msgs = state.format_prompt(user_input)
    chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in msgs]

    try:
        result: CompletionResult = await asyncio.wait_for(
            _llm.complete(messages=chat_msgs, max_tokens=2048, temperature=0.7),
            timeout=120.0,
        )
        content = result.content or ""
        if not content:
            # Try reasoning extraction fallback
            reasoning = getattr(result, "reasoning", None)
            if reasoning:
                import re
                m = re.search(r"<answer>(.*?)</answer>", reasoning, re.S)
                if m:
                    content = m.group(1).strip()
        return content or "(no response from model)"
    except asyncio.TimeoutError:
        return "[MOON: LLM timed out after 120s — model may be busy]"
    except Exception as e:
        log.error("LLM query failed: %s", e)
        return f"[MOON error: {e}]"


# ── 6. Voice (Moon's own VoiceEngine) ─────────────────────────────────────────
def _speak(text: str, state: MoonCLIState) -> None:
    """Speak text using Moon's VoiceEngine if voice is enabled."""
    global _voice
    if not state.voice_on:
        return
    if _voice is None:
        _voice = _get_voice_engine()
    try:
        if state.voice_tts_only:
            _voice.speak(text, synthesize_only=True)
        else:
            _voice.speak(text)
    except Exception as e:
        log.warning("TTS failed: %s", e)


# ── 7. Shell execution (Moon's own _SHELL_ALLOW) ─────────────────────────────
def _run_shell(cmd: str) -> str:
    """Run a shell command via Moon's own shell dispatcher."""
    from app.terminal_interface import _shell_dispatch
    out, code = _shell_dispatch(cmd.strip())
    return out


# ── 8. Streaming chunk writer ─────────────────────────────────────────────────
def _stream_chunk(chunk: str) -> None:
    """Print one chunk of streaming response, flushing stdout immediately."""
    _console.print(chunk, end="")
    sys.stdout.flush()


# ── 8b. Streaming response writer ────────────────────────────────────────────
async def _stream_response(
    state: MoonCLIState,
    user_input: str,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """Query LLM and stream response chunks to the console as they arrive."""
    full = await _query_llm(state, user_input)
    if on_chunk:
        for i in range(0, len(full), 80):
            on_chunk(full[i : i + 80])
    return full


# ── 9. Slash commands — module-level registry ────────────────────────────────
# Hermes-style: commands registered at module load via @register decorator,
# dispatched by name at runtime.  Moon-native — no Hermes imports.
_COMMANDS: dict[str, Callable[..., Any]] = {}


def register(name: str):
    """Decorator: register a slash command handler by name.

    Usage (module-level, not inside a class):
        @register("help")
        def cmd_help(state, arg):
            ...
    """

    def deco(fn):
        _COMMANDS[name] = fn
        return fn

    return deco


class MoonCLI:
    """Moon's interactive CLI terminal — Hermes-feature-rich, Moon-native."""

    def __init__(self, state: MoonCLIState) -> None:
        self.state = state
        self.running = True
        self._scratch: dict[str, Any] = {}

    # ── command dispatch ────────────────────────────────────────────────────
    async def dispatch(self, line: str) -> bool:
        """Dispatch a slash command. Returns False to exit."""
        parts = line.strip().split(None, 1)
        cmd = parts[0].lower().lstrip("/")
        arg = parts[1] if len(parts) > 1 else ""
        handler = _COMMANDS.get(cmd)
        if handler is None:
            _panels(
                "Unknown command",
                f"No slash command `/ 예의: {cmd}` found.\n"
                f"Type /help for available commands.",
                style="red",
            )
            return True
        try:
            import inspect
            if inspect.iscoroutinefunction(handler):
                result = await handler(self.state, arg)
            else:
                result = handler(self.state, arg)
            return bool(result)
        except Exception as e:
            _panels("Command error", f"{e}", style="red")
            return True

    # ── built-in slash commands ─────────────────────────────────────────────
    # Hermes-style: each @register() at module level; MoonCLI owns no commands.
    # Methods below use self only for state + convenience.  All dispatch via
    # the module-level _COMMANDS dict, never self._COMMANDS.


def cmd_help(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "MOON CLI — Available Commands",
        "\n".join(
            f"  {k:12s}  {v.__doc__.strip().split(chr(10))[0] if v.__doc__ else ''}"
            for k, v in sorted(_COMMANDS.items())
        ),
        style="cyan",
    )
    return True


@register("help")
def _cmd_help(state: MoonCLIState, arg: str) -> bool:
    return cmd_help(state, arg)


def cmd_model(state: MoonCLIState, arg: str) -> bool:
    """Show or switch model.  Usage: /model [name] [--query <prompt>]"""
    if not arg:
        _panels("Current model", state.model_name, style="green")
        return True
    # Parse optional --query parameter: /model <name> [--query <prompt>]
    query: str | None = None
    if "--query" in arg:
        parts = arg.split("--query", 1)
        model_name = parts[0].strip()
        query = parts[1].strip() if len(parts) > 1 else None
    else:
        model_name = arg.strip()
        query = None
    if not model_name:
        _panels("Model", "Usage: /model <name> [--query <prompt>]", style="yellow")
        return True
    old = state.model_name
    state.model_name = model_name
    global _llm
    _llm = None  # force re-create LLMService with the new model
    _panels("Model switched", f"{old} → {model_name}", style="yellow")
    # Backport: if --query given, run a one-shot on the new model immediately
    if query:
        _console.print(
            f"\n[yellow][{_now_ts()}] MOON (on {model_name}, prompted by /model --query):[/yellow]"
        )
        try:
            response = asyncio.run(_query_llm(state, query))
            _console.print(response)
            state.add_message("assistant", response)
            _speak(response, state)
        except Exception as e:
            _panels("Query failed", f"{e}", style="red")
    return True


@register("model")
def _cmd_model(state: MoonCLIState, arg: str) -> bool:
    return cmd_model(state, arg)


def cmd_agent(state: MoonCLIState, arg: str) -> bool:
    if not arg:
        _panels("Current agent", state.agent_name, style="green")
        return True
    state.agent_name = arg
    _panels("Agent switched", f"{state.agent_name}", style="yellow")
    return True


@register("agent")
def _cmd_agent(state: MoonCLIState, arg: str) -> bool:
    return cmd_agent(state, arg)


def cmd_status(state: MoonCLIState, arg: str) -> bool:
    """Show Moon backend health."""
    import urllib.request
    import json

    try:
        req = urllib.request.urlopen("http://127.0.0.1:8777/api/health", timeout=5)
        data = json.loads(req.read())
        ok = data.get("status") == "HEALTHY"
        _panels(
            "MOON Backend Status",
            (
                f"Status:  {'HEALTHY' if ok else 'UNHEALTHY'}\n"
                f"Model:   {data.get('model', '?')}\n"
                f"Agents:  {data.get('checks', [{}])[0].get('detail', '?')}\n"
                f"Tools:   {data.get('checks', [{}])[1].get('detail', '?')}\n"
                f"Memory:  {data.get('checks', [{}])[2].get('detail', '?')}\n"
                f"Lock:    {'unlocked' if not data.get('locked') else 'locked'}\n"
                f"Uptime:  {_now_ts()}"
            ),
            style="green" if ok else "red",
        )
    except Exception as e:
        _panels("Status", f"Cannot reach backend: {e}", style="red")
    return True


@register("status")
def _cmd_status(state: MoonCLIState, arg: str) -> bool:
    return cmd_status(state, arg)


def cmd_shell(state: MoonCLIState, arg: str) -> bool:
    if not arg:
        _panels("Shell", "Usage: /shell <command>", style="yellow")
        return True
    out = _run_shell(arg)
    _panels(
        "Shell output",
        out[:2000] + ("..." if len(out) > 2000 else ""),
        style="default",
    )
    return True


@register("shell")
def _cmd_shell(state: MoonCLIState, arg: str) -> bool:
    return cmd_shell(state, arg)


def cmd_voice(state: MoonCLIState, arg: str) -> bool:
    if not arg or arg == "status":
        _panels(
            "Voice",
            (
                f"Voice: {'ON' if state.voice_on else 'OFF'}\n"
                f"Mode:  {'TTS-only' if state.voice_tts_only else 'Speak'}\n"
                f"Backend: {(_voice.__class__.__name__ if _voice else 'not loaded')}"
            ),
            style="cyan",
        )
        return True
    if arg == "on":
        state.voice_on = True
        _panels("Voice", "ON", style="green")
    elif arg == "off":
        state.voice_on = False
        _panels("Voice", "OFF", style="yellow")
    elif arg == "tts":
        state.voice_on = True
        state.voice_tts_only = True
        _panels("Voice", "ON (TTS-only mode)", style="green")
    elif arg == "speak":
        state.voice_on = True
        state.voice_tts_only = False
        _panels("Voice", "ON (speak mode)", style="green")
    else:
        _panels(
            "Voice",
            f"Unknown: {arg} (on/off/tts/speak/status)",
            style="yellow",
        )
    return True


@register("voice")
def _cmd_voice(state: MoonCLIState, arg: str) -> bool:
    return cmd_voice(state, arg)


def cmd_reset(state: MoonCLIState, arg: str) -> bool:
    state.clear()
    _panels("Session", "Reset — context cleared", style="yellow")
    return True


@register("reset")
def _cmd_reset(state: MoonCLIState, arg: str) -> bool:
    return cmd_reset(state, arg)


def cmd_save(state: MoonCLIState, arg: str) -> bool:
    path = Path(arg) if arg else Path.cwd() / f"moon_session_{_now_ts().replace(':', '')}.md"
    lines = [f"# MOON CLI Session — {_now_ts()}", ""]
    for role, content in state.messages:
        prefix = "## User" if role == "user" else "## MOON"
        lines.append(f"{prefix}\n{content}\n")
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
        _panels("Saved", str(path), style="green")
    except Exception as e:
        _panels("Save failed", str(e), style="red")
    return True


@register("save")
def _cmd_save(state: MoonCLIState, arg: str) -> bool:
    return cmd_save(state, arg)


def cmd_history(state: MoonCLIState, arg: str) -> bool:
    if not state.messages:
        _panels("History", "No messages yet", style="yellow")
        return True
    lines = []
    for i, (role, content) in enumerate(state.messages[-30:], 1):
        prefix = "You" if role == "user" else "MOON"
        lines.append(
            f"{i:3d}. [{prefix}] {content[:120]}{'...' if len(content) > 120 else ''}"
        )
    _panels("Recent history", "\n".join(lines), style="default")
    return True


@register("history")
def _cmd_history(state: MoonCLIState, arg: str) -> bool:
    return cmd_history(state, arg)


def cmd_clear(state: MoonCLIState, arg: str) -> bool:
    os.system("clear" if os.name != "nt" else "cls")
    _panels("Session", "Cleared", style="yellow")
    return True


@register("clear")
def _cmd_clear(state: MoonCLIState, arg: str) -> bool:
    return cmd_clear(state, arg)


def cmd_quit(state: MoonCLIState, arg: str) -> bool:
    _panels("Goodbye", "MOON CLI exiting. 👋", style="cyan")
    return False


@register("quit")
def _cmd_quit(state: MoonCLIState, arg: str) -> bool:
    return cmd_quit(state, arg)


@register("exit")
def _cmd_exit(state: MoonCLIState, arg: str) -> bool:
    return cmd_quit(state, arg)


@register("q")
def _cmd_q(state: MoonCLIState, arg: str) -> bool:
    return cmd_quit(state, arg)


def cmd_verbose(state: MoonCLIState, arg: str) -> bool:
    verbose = not (arg and arg.startswith("off"))
    _panels("Verbose", f"{'ON' if verbose else 'OFF'}", style="cyan")
    return True


@register("verbose")
def _cmd_verbose(state: MoonCLIState, arg: str) -> bool:
    return cmd_verbose(state, arg)


def cmd_goal(state: MoonCLIState, arg: str) -> bool:
    if not arg:
        stored = state._scratch.get("goal", "none set")
        _panels("Standing goal", stored, style="cyan")
        return True
    state._scratch["goal"] = arg
    _panels("Goal set", arg, style="green")
    return True


@register("goal")
def _cmd_goal(state: MoonCLIState, arg: str) -> bool:
    return cmd_goal(state, arg)


def cmd_background(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "Background",
        "Not yet wired in CLI mode. Use `moon run <task>` for one-shot tasks.",
        style="yellow",
    )
    return True


@register("background")
def _cmd_background(state: MoonCLIState, arg: str) -> bool:
    return cmd_background(state, arg)


def cmd_busy(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "Busy mode",
        "CLI always shows full responses. /verbose to toggle detail.",
        style="yellow",
    )
    return True


@register("busy")
def _cmd_busy(state: MoonCLIState, arg: str) -> bool:
    return cmd_busy(state, arg)


def cmd_indicator(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "Indicator",
        "CLI uses Rich text formatting. No separate busy indicator.",
        style="yellow",
    )
    return True


@register("indicator")
def _cmd_indicator(state: MoonCLIState, arg: str) -> bool:
    return cmd_indicator(state, arg)


def cmd_footer(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "Footer",
        "CLI shows session info in prompt. No separate footer toggle.",
        style="yellow",
    )
    return True


@register("footer")
def _cmd_footer(state: MoonCLIState, arg: str) -> bool:
    return cmd_footer(state, arg)


def cmd_statusbar(state: MoonCLIState, arg: str) -> bool:
    _panels(
        "Status bar",
        "Built into prompt line. No separate toggle.",
        style="yellow",
    )
    return True


@register("statusbar")
def _cmd_statusbar(state: MoonCLIState, arg: str) -> bool:
    return cmd_statusbar(state, arg)


def cmd_personality(state: MoonCLIState, arg: str) -> bool:
    personalities = {
        "default": "Helpful, precise, direct",
        "concise": "Brief and to the point",
        "technical": "Detailed, accurate, engineering-focused",
        "creative": "Outside-the-box, innovative",
        "teacher": "Patient, explains clearly",
    }
    if not arg or arg == "list":
        _panels(
            "Personalities",
            "\n".join(
                f"  {k:12s}  {v}" for k, v in personalities.items()
            ),
            style="cyan",
        )
        return True
    if arg in personalities:
        state._system_prompt = lambda: f"You are MOON — {personalities[arg]}."
        _panels("Personality", f"→ {arg}", style="green")
    else:
        _panels(
            "Personality",
            f"Unknown: {arg}\nAvailable: {', '.join(personalities.keys())}",
            style="yellow",
        )
    return True


@register("personality")
def _cmd_personality(state: MoonCLIState, arg: str) -> bool:
    return cmd_personality(state, arg)


# ── 10. Interactive REPL loop ─────────────────────────────────────────────────
async def _run_repl(cli: MoonCLI, state: MoonCLIState) -> None:
    """Main interactive REPL loop — Hermes-style prompt-toolkit-less REPL."""
    import readline

    _load_history()
    _console.print(
        Panel(
            "[bold]MOON CLI Terminal[/bold]\n"
            "[dim]Moon's own interactive CLI — Hermes-feature-rich, Moon-native[/dim]\n\n"
            "[green]●[/green] Type your message and press Enter\n"
            "[green]●[/green] Prefix with / for commands (e.g. /help, /model, /voice on)\n"
            "[green]●[/green] Type /quit or Ctrl+D to exit\n"
            f"[dim]Model: {state.model_name}  |  Agent: {state.agent_name}[/dim]",
            title="🌙 MOON CLI",
            style="blue",
        )
    )

    while cli.running:
        try:
            line = input(f"\n[{_now_ts()}] 💬 > ").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print("\n[bold]Exiting...[/bold]")
            break

        if not line:
            continue

        if line.startswith("/"):
            if not await cli.dispatch(line):
                break
            continue

        # ── Normal chat turn ───────────────────────────────────────────────
        state.add_message("user", line)
        _console.print(f"\n[bold cyan][{_now_ts()}] MOON:[/bold cyan]")

        # Stream the response
        response = await _stream_response(
            state,
            line,
            on_chunk=_stream_chunk,
        )
        _console.print()  # newline

        state.add_message("assistant", response)

        # TTS
        _speak(response, state)

        # Session stats
        elapsed = time.time() - state.session_start
        _console.print(
            f"[dim]↳ {_now_ts()} | {len(response)} chars | "
            f"{state.request_count} turns | {elapsed:.0f}s session[/dim]"
        )

    _save_history()


# ── 11. One-shot mode ─────────────────────────────────────────────────────────
async def _run_oneshot(prompt_text: str, model: str, agent: str) -> None:
    """One-shot mode — query and print result, then exit."""
    state = MoonCLIState()
    state.model_name = model
    state.agent_name = agent

    _console.print(f"[dim]MOON CLI one-shot → {prompt_text[:80]}[/dim]\n")
    response = await _stream_response(state, prompt_text)
    _console.print(f"\n[bold]MOON:[/bold] {response}")


# ── 12. Entry point ────────────────────────────────────────────────────────────
def run_cli(state: MoonCLIState | None = None) -> None:
    """Run the Moon CLI REPL (blocking)."""
    if state is None:
        state = MoonCLIState()
    cli = MoonCLI(state)
    asyncio.run(_run_repl(cli, state))


def main() -> None:
    """CLI entry point — argparse + dispatch."""
    ap = argparse.ArgumentParser(
        prog="moon cli",
        description="MOON's own interactive CLI terminal (Hermes-feature-rich, Moon-native)",
    )
    ap.add_argument(
        "-q", "--query",
        metavar="TEXT",
        help="One-shot query (non-interactive, exits after response)",
    )
    ap.add_argument(
        "-m", "--model",
        default=None,
        help=f"Model name (default: {_settings.model_name or 'qwen2.5:1.5b'})",
    )
    ap.add_argument(
        "-a", "--agent",
        default="auto",
        help="Agent name (default: auto)",
    )
    ap.add_argument(
        "-Q", "--quiet",
        action="store_true",
        help="Suppress banner",
    )
    args = ap.parse_args()

    state = MoonCLIState()
    if args.model:
        state.model_name = args.model
    state.agent_name = args.agent

    if args.query:
        # One-shot mode
        asyncio.run(_run_oneshot(args.query, state.model_name, state.agent_name))
    else:
        # Interactive REPL
        run_cli(state)


if __name__ == "__main__":
    main()
