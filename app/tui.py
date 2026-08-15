"""tui.py -- MOON's text-mode (curses) terminal interface.

A lightweight, dependency-free (Python stdlib curses) chat UI for MOON that runs
IN-PROCESS: it spins up the Orchestrator and streams her real brain events
(routing, cognition, reflection, consistency) into a "brain" panel while you
chat in the main panel. No HTTP server required -- ideal for an SSH/headless box.

Usage:
    python main.py tui
    MOON_TUI_UNLOCK="MOON love you 3000" python main.py tui   # pre-supply unlock

Keys:
    Enter        : send the typed line
    Ctrl-L       : clear the conversation
    Ctrl-X / Esc : quit

MOON's existing lock (unlock phrase "MOON love you 3000") is honored: until you
send the phrase, she replies only with the lock notice.
"""

from __future__ import annotations

import asyncio
import curses
import logging
import sys
import time

from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)


class MoonTUI:
    def __init__(self, stdscr, unlock: str = "MOON love you 3000") -> None:
        self.stdscr = stdscr
        self.unlock = unlock
        self.orchestrator = None
        self.chat_lines: list[str] = []          # (role, text) flattened for render
        self.brain_events: list[str] = []
        self.input_buf = ""
        self.running = True
        self._max_y, self._max_x = stdscr.getmaxyx()

    # ------------------------------------------------------------------ #
    async def _ensure_orchestrator(self):
        from app.brain.orchestrator import Orchestrator
        from app.config.env_guard import decontaminate_pythonpath
        decontaminate_pythonpath()
        self.orchestrator = Orchestrator(get_settings())
        await self.orchestrator.setup()

    async def _on_event(self, ev: dict) -> None:
        stage = ev.get("stage", "")
        detail = ev.get("detail", "")
        if stage and detail:
            self.brain_events.append(f"[{stage}] {detail}")
        elif stage:
            self.brain_events.append(f"[{stage}]")
        self.brain_events = self.brain_events[-200:]
        self._render()

    async def _send(self, text: str) -> None:
        self.chat_lines.append(f"You: {text}")
        self.brain_events.append("[you] -> MOON")
        self._render()
        from app.models.task import Task
        task = Task.create(text, agent_name="auto")
        try:
            result = await self.orchestrator.run_task(task, on_event=self._on_event)
            answer = result.result or "(no response)"
        except Exception as exc:  # noqa: BLE001
            answer = f"[error] {exc}"
        self.chat_lines.append(f"MOON: {answer}")
        self.brain_events.append("[done]")
        self._render()

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #
    def _render(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        # Layout: top 60% chat, then brain panel, then input line.
        brain_h = max(4, h // 4)
        chat_h = h - brain_h - 2
        try:
            # Chat panel
            self.stdscr.addnstr(0, 0, "🌙 MOON -- TUI  (Ctrl-X quit, Ctrl-L clear)", w - 1)
            visible = self.chat_lines[-(chat_h - 1):]
            y = 1
            for line in visible:
                clipped = line if len(line) <= w - 1 else line[: w - 4] + "..."
                self.stdscr.addnstr(y, 0, clipped, w - 1)
                y += 1
            # Brain panel divider
            self.stdscr.hline(chat_h, 0, "-", w - 1)
            self.stdscr.addnstr(chat_h, 0, "🧠 MOON brain:", w - 1)
            by = chat_h + 1
            for ev in self.brain_events[-(brain_h - 1):]:
                self.stdscr.addnstr(by, 0, ("  " + ev)[: w - 1], w - 1)
                by += 1
            # Input line
            prompt = "> " + self.input_buf
            self.stdscr.addnstr(h - 1, 0, prompt[: w - 1], w - 1)
        except curses.error:
            pass
        self.stdscr.refresh()

    def _loop_sync(self) -> None:
        """Run the asyncio event loop while processing keystrokes (curses)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._ensure_orchestrator())
        self._render()
        while self.running:
            ch = self.stdscr.getch()
            if ch == curses.KEY_RESIZE:
                self._max_y, self._max_x = self.stdscr.getmaxyx()
                self._render()
                continue
            if ch in (27,):  # Esc
                self.running = False
                break
            if ch == 24:  # Ctrl-X
                self.running = False
                break
            if ch == 12:  # Ctrl-L
                self.chat_lines.clear()
                self._render()
                continue
            if ch in (curses.KEY_ENTER, 10, 13):
                text = self.input_buf.strip()
                self.input_buf = ""
                self._render()
                if text:
                    loop.run_until_complete(self._send(text))
                continue
            if ch in (8, 127, curses.KEY_BACKSPACE):  # backspace
                self.input_buf = self.input_buf[:-1]
            elif 32 <= ch <= 126:  # printable ASCII
                self.input_buf += chr(ch)
            self._render()
        loop.run_until_complete(self.orchestrator.teardown())


def main(unlock: str = "MOON love you 3000") -> int:
    try:
        curses.wrapper(lambda stdscr: MoonTUI(stdscr, unlock=unlock)._loop_sync())
    except Exception as exc:  # noqa: BLE001
        logger.exception("TUI crashed: %s", exc)
        print(f"[MOON TUI] fatal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
