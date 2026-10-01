#!/usr/bin/env python3
"""Hermes-style console engine for Moon CLI.

Mirrors the console/panel primitives used in Hermes CLI's prompt_toolkit UI,
adapted for Rich. Provides the visual building blocks that hermes_cli uses:
  * Panels (bordered boxes with titles)
  * Tables
  * Spinners / progress indicators
  * Status lines
  * Layout management
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from typing import Optional


_console: Optional[Console] = None


def get_console() -> Console:
    """Get or create the shared Rich console."""
    global _console
    if _console is None:
        _console = Console()
    return _console


def print_panel(title: str, body: str, border_style: str = "blue") -> None:
    """Print a styled panel — mirrors Hermes CLI panel rendering."""
    console = get_console()
    console.print(Panel(body, title=title, border_style=border_style))


def print_table(headers: list[str], rows: list[list[str]], title: str = "") -> None:
    """Print a styled table — mirrors Hermes CLI table rendering."""
    console = get_console()
    table = Table(title=title)
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*row)
    console.print(table)


def print_divider() -> None:
    """Print a horizontal divider line."""
    console = get_console()
    console.print("─" * 60)


def print_spinner(text: str = "Working...") -> None:
    """Print a spinner with text — mirrors Hermes CLI thinking indicator."""
    console = get_console()
    with Live(
        Spinner("dots", text=Text(text, style="dim")),
        console=console,
        transient=True,
    ) as live:
        pass  # spinner shows briefly, then Live context exits


def print_status(text: str, style: str = "dim") -> None:
    """Print a status line."""
    console = get_console()
    console.print(Text(text, style=style))


def hprint(text: str, style: str = "") -> None:
    """Hermes-style colored print."""
    console = get_console()
    console.print(Text(text, style=style))


def hprint_info(text: str) -> None:
    hprint(f"  {text}", "dim")


def hprint_success(text: str) -> None:
    hprint(f"✓ {text}", "green")


def hprint_warning(text: str) -> None:
    hprint(f"⚠ {text}", "yellow")


def hprint_error(text: str) -> None:
    hprint(f"✗ {text}", "red")


def hprint_header(text: str) -> None:
    hprint(f"\n  {text}", "bold yellow")


# ── ConsoleEngine class (mirrors Hermes console engine class) ──────────────

class ConsoleEngine:
    """Hermes-style console engine object — provides panel/table/spinner/status.

    Mirrors the console engine pattern used in hermes_cli.  Provides an
    object-oriented interface so MoonCLI can own a ``self.engine`` instance.
    """

    def __init__(self) -> None:
        self._console = Console()

    def panel(self, title: str, body: str, border_style: str = "blue") -> None:
        """Print a styled panel."""
        self._console.print(Panel(body, title=title, border_style=border_style))

    def table(self, headers: list[str], rows: list[list[str]], title: str = "") -> None:
        """Print a styled table."""
        table = Table(title=title)
        for h in headers:
            table.add_column(h)
        for row in rows:
            table.add_row(*row)
        self._console.print(table)

    def divider(self) -> None:
        """Print a horizontal divider."""
        self._console.print("\u2500" * 60)

    def spinner(self, text: str = "Working...") -> None:
        """Print a brief spinner."""
        with Live(
            Spinner("dots", text=Text(text, style="dim")),
            console=self._console,
            transient=True,
        ) as live:
            pass

    def status(self, text: str, style: str = "dim") -> None:
        """Print a status line."""
        self._console.print(Text(text, style=style))

    def print(self, text: str, style: str = "") -> None:
        """Print with style."""
        self._console.print(Text(text, style=style))

    def info(self, text: str) -> None:
        self.print(f"  {text}", "dim")

    def success(self, text: str) -> None:
        self.print(f"\u2713 {text}", "green")

    def warning(self, text: str) -> None:
        self.print(f"\u26a0 {text}", "yellow")

    def error(self, text: str) -> None:
        self.print(f"\u2717 {text}", "red")

    def header(self, text: str) -> None:
        self._console.print()
        self._console.print(Text(f"  {text}", style="bold yellow"))
        self._console.print()
