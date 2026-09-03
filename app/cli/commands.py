#!/usr/bin/env python3
"""
Hermes-style CLI commands registry for Moon CLI.

Mirrors hermes_cli/commands.py: CommandDef dataclass + COMMAND_REGISTRY
+ SlashCommandCompleter + SlashCommandAutoSuggest + resolve_command.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from app.cli.colors import Colors

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    from prompt_toolkit.completion import Completer, Completion
else:
    try:
        from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion  # noqa: F811
        from prompt_toolkit.completion import Completer, Completion       # noqa: F811
    except ImportError:
        AutoSuggest = object  # type: ignore[assignment,misc]
        Completer = object    # type: ignore[assignment,misc]
        Suggestion = None     # type: ignore[assignment]
        Completion = None     # type: ignore[assignment]


# ── CommandDef (mirrors hermes_cli/commands.py:CommandDef) ─────────────────

@dataclass(frozen=True)
class CommandDef:
    """Definition of a single slash command — mirrors Hermes CommandDef exactly."""

    name: str                          # canonical name without slash: "background"
    description: str                   # human-readable description
    category: str                      # "Session", "Configuration", etc.
    aliases: tuple[str, ...] = ()      # alternative names: ("bg",)
    args_hint: str = ""                # argument placeholder: "<prompt>", "[name]"
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
    cli_only: bool = False             # only available in CLI
    gateway_only: bool = False         # only available in gateway/messaging
    busy_policy: str = "reject"        # "dispatch" | "reject" | "interrupt_then_dispatch"
    busy_handler: Optional[str] = None
    execute: Optional[str] = None
    argument_mode: Optional[str] = None
    desktop: Optional[str] = None


# ── COMMAND_REGISTRY (mirrors hermes_cli/commands.py:COMMANDS) ────────────

COMMAND_REGISTRY: list[CommandDef] = [
    # ── Session ──────────────────────────────────────────────────────────────
    CommandDef("help", "Show all commands or detailed help for one", "Session",
               args_hint="[command]"),
    CommandDef("new", "Start a new session (fresh session ID + history)", "Session",
               aliases=("reset",), args_hint="[name]",
               busy_policy="interrupt_then_dispatch", busy_handler="new"),
    CommandDef("clear", "Clear screen and start a new session", "Session",
               cli_only=True, desktop="terminal"),
    CommandDef("history", "Show conversation history", "Session",
               cli_only=True, desktop="terminal"),
    CommandDef("save", "Export the current conversation", "Session",
               args_hint="<json|md|html> [filename]"),
    CommandDef("retry", "Retry the last message (resend to agent)", "Session"),
    CommandDef("undo", "Back up N user turns and re-prompt (default 1)", "Session",
               args_hint="[N]"),
    CommandDef("title", "Set a title for the current session", "Session",
               args_hint="[name]"),
    CommandDef("branch", "Branch the current session (explore a different path)", "Session",
               aliases=("fork",), args_hint="[name]"),
    CommandDef("compress", "Compress conversation context", "Session",
               aliases=("compact",), args_hint="[here [N] | focus topic | --preview]"),

    # ── Configuration ────────────────────────────────────────────────────────
    CommandDef("model", "Show or switch model; /model <name> --query runs one-shot", "Configuration",
               args_hint="[name] [--query <prompt>]",
               busy_policy="reject", busy_handler="model"),
    CommandDef("agent", "Show or switch agent", "Configuration",
               args_hint="[name]"),
    CommandDef("personality", "Set or show personality style", "Configuration",
               args_hint="[default|concise|technical|creative|teacher]",
               argument_mode="options", desktop="terminal"),
    CommandDef("verbose", "Toggle verbose mode", "Configuration",
               desktop="terminal"),
    CommandDef("goal", "Set or show session goal", "Configuration",
               args_hint="[text]"),

    # ── Voice ────────────────────────────────────────────────────────────────
    CommandDef("voice", "Toggle voice mode: on | off | tts | speak | status", "Configuration",
               args_hint="[on|off|tts|speak|status]", desktop="terminal"),

    # ── System / Shell ───────────────────────────────────────────────────────
    CommandDef("shell", "Run a shell command via Moon's own shell dispatch", "System",
               args_hint="<command>", cli_only=True, desktop="terminal"),
    CommandDef("status", "Show Moon backend health", "System",
               cli_only=True, desktop="terminal"),
    CommandDef("doctor", "Check configuration and dependencies", "System",
               cli_only=True, desktop="terminal"),

    # ── Quit ────────────────────────────────────────────────────────────────
    CommandDef("quit", "Exit the CLI", "Session",
               aliases=("exit", "q"), busy_policy="dispatch", desktop="terminal"),
]


# ── Command lookup (mirrors hermes_cli/commands.py:_build_command_lookup) ──

_COMMAND_LOOKUP: Optional[dict[str, CommandDef]] = None


def _build_command_lookup() -> dict[str, CommandDef]:
    global _COMMAND_LOOKUP
    if _COMMAND_LOOKUP is not None:
        return _COMMAND_LOOKUP
    _COMMAND_LOOKUP = {}
    for cmd in COMMAND_REGISTRY:
        _COMMAND_LOOKUP[cmd.name] = cmd
        for alias in cmd.aliases:
            _COMMAND_LOOKUP[alias] = cmd
    return _COMMAND_LOOKUP


def resolve_command(name: str) -> Optional[CommandDef]:
    return _build_command_lookup().get(name)


def get_all_command_names() -> list[str]:
    return sorted(_build_command_lookup().keys())


# ── Completers (mirrors hermes_cli/commands.py) ─────────────────────────────

if Completion is not None:

    class SlashCommandCompleter(Completer):
        """Tab completer for slash commands — mirrors Hermes' SlashCommandCompleter."""

        def __init__(self, registry: Optional[list[CommandDef]] = None) -> None:
            self._registry = registry or COMMAND_REGISTRY

        def get_completions(self, document: Any, complete_event: Any) -> Sequence[Completion]:
            text = document.text
            position = document.cursor_position
            before_cursor = text[:position]
            if " " in before_cursor:
                word = before_cursor.rsplit(" ", 1)[-1]
            else:
                word = before_cursor
            if word.startswith("/"):
                prefix = word[1:]
                completions: list[Completion] = []
                for cmd in self._registry:
                    if cmd.name.startswith(prefix) and not cmd.gateway_only:
                        completions.append(
                            Completion(f"/{cmd.name}", start_position=-len(prefix))
                        )
                    for alias in cmd.aliases:
                        if alias.startswith(prefix):
                            completions.append(
                                Completion(f"/{alias}", start_position=-len(prefix))
                            )
                return completions
            return []


if Suggestion is not None:

    class SlashCommandAutoSuggest(AutoSuggest):
        """Fish-style ghost text for slash commands — mirrors Hermes auto-suggest."""

        def __init__(self, history: Optional[list[str]] = None) -> None:
            self._history = history or []

        def get_suggestion(self, document: Any, buffer: Any) -> Optional[Suggestion]:
            text = document.text
            if not text or not text.startswith("/"):
                return None
            for line in reversed(self._history):
                if line.startswith(text):
                    return Suggestion(line[len(text):])
            return None


# ── Help lines (mirrors hermes_cli/commands.py:gateway_help_lines) ──────────

def gateway_help_lines() -> list[str]:
    """Return gateway help text lines from the registry."""
    lines: list[str] = []
    for cmd in COMMAND_REGISTRY:
        if cmd.gateway_only:
            continue
        line = f"/{cmd.name}"
        if cmd.args_hint:
            line += f" {cmd.args_hint}"
        if cmd.description:
            line += f" — {cmd.description}"
        lines.append(line)
    return lines


# ── Category grouping (mirrors hermes_cli/commands.py) ─────────────────────

def commands_by_category() -> dict[str, list[CommandDef]]:
    by_cat: dict[str, list[CommandDef]] = {}
    for cmd in COMMAND_REGISTRY:
        by_cat.setdefault(cmd.category, []).append(cmd)
    return by_cat


def cli_commands() -> list[CommandDef]:
    return [c for c in COMMAND_REGISTRY if not c.gateway_only]


# ── CLIState (mirrors hermes_cli state) ────────────────────────────────────

class CLIState:
    """CLI session state — mirrors Hermes CLI state structure exactly."""

    def __init__(
        self,
        *,
        model_name: str = "qwen2.5:1.5b",
        agent_name: str = "auto",
        session_id: str | None = None,
        voice_enabled: bool = False,
        tts_enabled: bool = False,
        verbose: bool = False,
        messages: list = None,
    ) -> None:
        self.model_name = model_name
        self.agent_name = agent_name
        self.session_id = session_id or f"cli-{int(time.time())}"
        self.voice_enabled = voice_enabled
        self.tts_enabled = tts_enabled
        self.verbose = verbose
        self.messages: list = messages if messages is not None else []
        self.last_response = None
        self.last_prompt = None
