#!/usr/bin/env python3
"""Hermes-style completion module for Moon CLI.

Mirrors hermes_cli/completion.py: readline completer + optional
prompt_toolkit completers (guarded — not required).
"""

from __future__ import annotations

import logging
import readline
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path.home() / ".moon" / "cli_history"
_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def setup_readline_completion() -> "_ReadlineInputReader":
    """Configure readline for Moon CLI: history + tab completion."""
    _hist = str(_HISTORY_FILE)

    try:
        readline.read_history_file(_hist)
    except OSError:
        pass

    readline.set_completer_delims(" \t\n`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?")
    readline.parse_and_bind("tab: complete")
    readline.set_completer(_command_completer)

    return _ReadlineInputReader()


class _ReadlineInputReader:
    def readline(self, prompt: str = "") -> str:
        try:
            line = input(prompt)
            readline.add_history(line)
            try:
                readline.write_history_file(_HISTORY_FILE)
            except OSError:
                pass
            return line
        except (EOFError, KeyboardInterrupt):
            raise


# ── Readline completer (mirrors Hermes completion) ──────────────────────────

def _command_completer(text: str, state: int) -> Optional[str]:
    """Tab completer for slash commands — mirrors Hermes' SlashCommandCompleter."""
    try:
        from app.cli.commands import COMMAND_REGISTRY
    except ImportError:
        return None

    commands = [cmd.name for cmd in COMMAND_REGISTRY]
    for cmd in COMMAND_REGISTRY:
        commands.extend(cmd.aliases)
    commands.extend("/")

    if not text.startswith("/"):
        return None

    _matches: List[str] = [c for c in commands if c.startswith(text.lower())]
    _matches.sort()
    if state < len(_matches):
        return _matches[state]
    return None


# ── Prompt_toolkit completer classes (guarded — only when pt available) ───

try:
    from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    from prompt_toolkit.completion import Completion, Completer

    class SlashCommandCompleter(Completer):
        """Tab completer for slash commands — mirrors Hermes' SlashCommandCompleter."""

        def __init__(self, commands: List[str]) -> None:
            self._commands = sorted(commands)
            self._filtered: List[str] = []
            self._index = 0

        def get_completions(self, document: Any, complete_event: Any) -> Any:
            text = document.text.lower()
            if not text.startswith("/"):
                return
            self._filtered = sorted(c for c in self._commands if c.startswith(text))
            self._index = 0
            for match in self._filtered:
                yield Completion(match, start_position=0)

    class SlashCommandAutoSuggest(AutoSuggest):
        """Fish-style ghost text for slash commands — mirrors Hermes auto-suggest."""

        def __init__(self, commands: List[str]) -> None:
            self._commands = sorted(commands)

        def get_suggestion(self, document: Any, buffer: Any) -> Optional[Suggestion]:
            text = document.text.lower()
            if not text.startswith("/"):
                return None
            matches = [c for c in self._commands if c.startswith(text)]
            if matches:
                suffix = matches[0][len(text):]
                return Suggestion(suffix)
            return None

except ImportError:
    logger.debug("prompt_toolkit not available — SlashCommandCompleter skipped")
