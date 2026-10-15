"""MOON Terminal UI — dark-themed terminal log display.

A single-user terminal that displays a log of automated tasks, rebuilt to
match the Hermes terminal design:

  - Black / dark background
  - Bright green primary text
  - White / yellow section headers ("Full Verification", "preparing
    terminal", "Hermes")
  - Red / pink error & status lines  ("[exit 1]", "[BLOCKED ...]")
  - Monospaced font, no window chrome

Three sections stacked vertically:  full verification  ->  file
preparation  ->  git commit,  followed by a red exit status in the
bottom-left corner.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll, HorizontalScroll
from textual.widgets import Static, Markdown, Button, Label, Input, RichLog, \
    ContentSwitcher, Switch, RadioButton, Checkbox, TextArea, Log, \
    Tab, TabPane, TabbedContent, Rule, Collapsible, Tree
from textual.reactive import reactive
from textual.binding import Binding
from textual import events


# ── colour palette ──────────────────────────────────────────────────────────
BG_DARK       = "#0a0a12"
BG_BAR        = "#14141f"
TEXT_LIGHT    = "#e0e0e0"
TEXT_DIM      = "#9090a8"
GREEN         = "#00ff88"
YELLOW        = "#ffd84d"
RED           = "#ff4455"
WHITE         = "#ffffff"
GRAY          = "#555570"
MONO          = "consolas, 'Courier New', monospace"

# layout
TERM_W        = 110
TERM_H        = 38
PADDING       = 8
PADDING_X     = 10


# ── small rendering helpers ─────────────────────────────────────────────────
class _Green(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, markup=True, **kwargs)


class _Yellow(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, markup=True, **kwargs)


class _Red(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, markup=True, **kwargs)


class _White(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, markup=True, **kwargs)


class _Dim(Static):
    def __init__(self, text: str = "", **kwargs):
        super().__init__(text, markup=True, **kwargs)


# ── the terminal window ─────────────────────────────────────────────────────
class MoonTerminalApp(App):
    """MOON terminal: a dark terminal log of automated tasks."""

    CSS_PATH = "ui.css"
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._lines: list[tuple[str, str]] = []
        self.build_log()

    def build_log(self) -> None:
        """Populate the log content from the Hermes terminal evidence."""
        L = self._lines

        def add(text: str = "", style: str = "output"):
            L.append((text, style))

        # ── header stripe ──
        add("", "output")

        # ── SECTION 1: Full Verification ──
        add("[Full Verification]", "section-header")
        add("The tests pass now. Let me run the full verification:", "output")
        add("")

        # command
        add("$ python3 -c \"import app.terminal.ui as ui; print('=== FULL APP VERIFICATION ===')\"", "command")

        add("", "output")
        add("[OutputDisplay]", "section-header")
        add("Hello world", "output")
        add("File created", "output")
        add("Permission needed", "output-warn")
        add("Plan complete", "output")
        add("", "output")

        add("[Status]", "section-header")
        add("[status]■ Context compacted[/status]", "status")
        add("Total lines", "status")
        add("", "output")

        add("[TerminalFrame]", "section-header")
        add("Checks title-bar, menu-bar, scrollbar, output-text", "output")
        add("Dumps string constants (TerminalFramestr)", "output")
        add("", "output")

        add("[MoonTerminalApp]", "section-header")
        add("CSS_PATH = app/terminal/ui.css", "output")
        add("BINDINGS = [Quit, ...]", "output")
        add("", "output")

        add("[StatusBar]", "section-header")
        add("sb_ram_usage = 128 MB", "output")
        add("process_count = 3", "output")
        add("session_status = active", "output")
        add("", "output")

        # ── red exit status (bottom-left) ──
        add("", "output")
        add("[exit 1]", "exit-status")

        # ── divider ──
        add("", "output")
        add("", "output")

        # ── SECTION 2: File Preparation ──
        add("[preparing terminal...]", "section-header")
        add("")
        add("$ find . -name \"*.pyc\" -delete", "command")
        add("[BLOCKED (hardline): recursive/any delete of t]", "error")
        add("")

        add("$ read preparing_file...", "command")
        add("read ui.py 0.0s", "output")
        add("")
        add("$ read preparing_file...", "command")
        add("read ui.css 0.0s", "output")
        add("", "output")

        # ── divider ──
        add("", "output")
        add("", "output")

        # ── SECTION 3: Git Commit (Hermes) ──
        add("[Hermes]", "hermes-header")
        add("The UI files are complete. Now let me commit and push to the GitHub repo:", "output")
        add("")
        add("$ git status --short", "command")
        add("M  app/terminal/ui.py", "output-warn")
        add("M  app/terminal/ui.css", "output-warn")
        add("")
        add("$ git add app/terminal/ui.py app/terminal/ui.css", "command")
        add("+ 1 command", "output-warn")
        add("")
        add("$ git push origin memory_checkpoint_2026_10_05", "command")
        add("5.0s", "output-warn")
        add("", "output")

    def compose(self) -> ComposeResult:
        self.build_log()
        with VerticalScroll(classes="terminal-screen"):
            with Vertical():
                yield self._build_window()

    def _build_window(self) -> Vertical:
        """Construct the single terminal window with the log content."""
        # build the content children list
        content_children = []
        for text, style in self._lines:
            if style == "section-header":
                content_children.append(_White(text, classes="output"))
            elif style == "command":
                content_children.append(_Green(text, classes="output"))
            elif style == "output":
                content_children.append(_White(text, classes="output"))
            elif style == "output-warn":
                content_children.append(_Yellow(text, classes="output"))
            elif style == "status":
                content_children.append(_White(text, classes="output"))
            elif style == "error":
                content_children.append(_Red(text, classes="output"))
            elif style == "exit-status":
                content_children.append(_Red(text, classes="exit-status"))
        # content
        content = Vertical(*content_children, classes="log-content")
        # build window with children
        window = Vertical(Static(" ", classes="output"), content, classes="term-window")
        return window

    # ── actions ─────────────────────────────────────────────────────────────
    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    MoonTerminalApp().run()
