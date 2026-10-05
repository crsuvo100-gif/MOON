# Simple test that launches the Textual UI in headless mode.

import pytest

try:
    from textual.testing import AppTest
    HAVE_TEXTUAL = True
except Exception:
    HAVE_TEXTUAL = False

from app.terminal.ui import MoonTerminalApp

@pytest.mark.skipif(not HAVE_TEXTUAL, reason="textual.testing not installed; optional UI test")
def test_ui_launch():
    # Run the app in headful-less mode – ``run`` returns when the UI finishes
    app = MoonTerminalApp()
    AppTest(app).run()
