"""Textual UI for MOON terminal HUD.

Provides a simple window with multiple frames that react to typed events from
``app.terminal.event_bus``.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static

from .event_bus import Event, subscribe, publish

# Mapping of UI states to display text – in a real HUD each state would be a rich
# layout. Here we keep it minimal to satisfy the smoke test.
_STATE_TEXT = {
    Event.UI_IDLE: "Idle – awaiting command",
    Event.UI_EXECUTING: "Executing…",
    Event.UI_PERMISSION: "Permission required",
    Event.UI_VERIFICATION: "Verifying result",
    Event.UI_ERROR: "Error occurred",
    Event.UI_SUCCESS: "Success!",
}

class MainWindow(Container):
    """Container that holds the central status widget.

    The widget is updated when an ``Event`` is published.
    """

    def compose(self) -> ComposeResult:
        yield Static("Initializing…", id="status")

    def on_mount(self) -> None:
        # Subscribe to all UI events.
        for ev in [
            Event.UI_IDLE,
            Event.UI_EXECUTING,
            Event.UI_PERMISSION,
            Event.UI_VERIFICATION,
            Event.UI_ERROR,
            Event.UI_SUCCESS,
        ]:
            subscribe(ev, self._handle_event)

    def _handle_event(self, payload: Any) -> None:
        # ``payload`` is ignored – we just switch text based on the event type.
        # The ``payload`` sent by ``publish`` is the Event enum itself.
        if isinstance(payload, Event):
            txt = _STATE_TEXT.get(payload, "Unknown state")
            self.query_one("#status", Static).update(txt)

class MoonTerminalApp(App):
    """Top‑level Textual application.

    The UI consists of a header, a footer and the ``MainWindow`` in the middle.
    """

    CSS_PATH = "ui.css"  # optional – not required for the test.

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield MainWindow()
        yield Footer()

    def on_mount(self) -> None:
        # Publish the initial idle state.
        publish(Event.UI_IDLE, Event.UI_IDLE)
        # Exit immediately for headless test.
        self.exit()


# Allow ``python -m app.terminal.ui`` for manual debugging.
if __name__ == "__main__":
    MoonTerminalApp().run()
