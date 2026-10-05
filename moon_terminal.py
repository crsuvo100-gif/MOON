"""Entry point to launch the Textual terminal UI for MOON.

Running ``python moon_terminal.py`` (or ``python -m moon_terminal``) will start
the ``MoonTerminalApp`` defined in ``app.terminal.ui``.
"""

from app.terminal.ui import MoonTerminalApp

if __name__ == "__main__":
    MoonTerminalApp().run()
