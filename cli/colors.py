#!/usr/bin/env python3
"""Hermes-style colors module for Moon CLI.

Mirrors hermes_cli/colors.py: Colors enum + color() ANSI function.
"""

from __future__ import annotations

from enum import Enum


class Colors(str, Enum):
    """ANSI color constants for terminal output.

    Mirrors hermes_cli/colors.py:Colors exactly.
    """

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"


def color(text: str, color_name: str) -> str:
    """Wrap text in ANSI color code.

    Mirrors hermes_cli/colors.py:color() exactly.

    Args:
        text: Text to colorize.
        color_name: color name (case-insensitive).
    """
    codes = {
        "red": Colors.RED,
        "green": Colors.GREEN,
        "yellow": Colors.YELLOW,
        "blue": Colors.BLUE,
        "magenta": Colors.MAGENTA,
        "cyan": Colors.CYAN,
        "white": Colors.WHITE,
        "reset": Colors.RESET,
        "bold": Colors.BOLD,
        "dim": Colors.DIM,
        "underline": Colors.UNDERLINE,
        "bright_black": Colors.BRIGHT_BLACK,
        "bright_red": Colors.BRIGHT_RED,
        "bright_green": Colors.BRIGHT_GREEN,
        "bright_yellow": Colors.BRIGHT_YELLOW,
        "bright_blue": Colors.BRIGHT_BLUE,
        "bright_magenta": Colors.BRIGHT_MAGENTA,
        "bright_cyan": Colors.BRIGHT_CYAN,
        "bright_white": Colors.BRIGHT_WHITE,
    }

    code = codes.get(color_name.lower())
    if code is None:
        return text
    return f"{code}{text}{Colors.RESET.value}"
