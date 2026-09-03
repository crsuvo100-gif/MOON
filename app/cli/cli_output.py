#!/usr/bin/env python3
"""Hermes-style CLI output helpers for Moon CLI.

Mirrors hermes_cli/cli_output.py exactly:
  print_info(text)      dim informational message
  print_success(text)   green success
  print_warning(text)   yellow warning
  print_error(text)     red error
  print_header(text)    bold yellow header
  line_input(prompt)    readline-aware input (prompt_toolkit if available)
  prompt(question, default)  formatted prompt with default + masking
  prompt_yes_no(question, default)  yes/no prompt
"""

from __future__ import annotations

import sys

from app.cli.colors import Colors, color


# ── Print Helpers (mirrors hermes_cli/cli_output.py) ──────────────────────

def print_info(text: str) -> None:
    """Print a dim informational message."""
    print(color("  " + text, Colors.DIM.name))


def print_success(text: str) -> None:
    """Print a green success message with checkmark prefix."""
    print(color("  OK  " + text, Colors.GREEN.name))


def print_warning(text: str) -> None:
    """Print a yellow warning message with warning prefix."""
    print(color("  WARN  " + text, Colors.YELLOW.name))


def print_error(text: str) -> None:
    """Print a red error message with error prefix."""
    print(color("  ERR  " + text, Colors.RED.name))


def print_header(text: str) -> None:
    """Print a bold yellow header."""
    print()
    print(color("  " + text, Colors.YELLOW.name))
    print()


# ── Input Helpers (mirrors hermes_cli/cli_output.py) ──────────────────────

def line_input(prompt_text: str) -> str:
    """Read text with normal cursor-editing keys on a real TTY.

    Uses prompt_toolkit if available (for arrow keys, history, editing),
    falls back to input() for redirected/pipe mode or if prompt_toolkit
    is not installed.
    Mirrors hermes_cli/cli_output.py:line_input() exactly.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return input(prompt_text)

    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.formatted_text import ANSI
    except ImportError:
        return input(prompt_text)

    try:
        return pt_prompt(ANSI(prompt_text))
    except (KeyboardInterrupt, EOFError):
        raise
    except Exception:
        return input(prompt_text)


def prompt(
    question: str,
    default: str | None = None,
    password: bool = False,
) -> str:
    """Prompt user for input with optional default and password masking.

    Mirrors hermes_cli/cli_output.py:prompt() exactly.
    """
    suffix = f" [{default}]" if default else ""
    display = "  " + color(question, Colors.YELLOW.name) + suffix + ": "

    try:
        if password:
            import getpass
            try:
                return getpass.getpass(display)
            except Exception:
                return input(display)
        else:
            value = line_input(display)
            value = value.strip()
            return value if value else (default or "")
    except (KeyboardInterrupt, EOFError):
        print()
        return ""


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt for yes/no answer. Returns bool.

    Mirrors hermes_cli/cli_output.py:prompt_yes_no() exactly.
    """
    hint = "Y/n" if default else "y/N"
    answer = prompt(f"{question} ({hint})")
    if not answer:
        return default
    return answer.lower().startswith("y")
