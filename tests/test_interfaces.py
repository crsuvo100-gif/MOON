"""Tests for the new MOON interfaces: TUI, Telegram channel, and the Terminal
authz gate. All mock external deps (curses/telegram/network) -- no real I/O.

Coverage:
  * TUI module imports and the MoonTUI class is constructible (curses importable).
  * TelegramBot routes an incoming message through the orchestrator and replies,
    and ignores chats that are not the authorized chat id.
  * _token_ok enforces Bearer auth when TERMINAL_TOKEN is set, and is open when not.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import types

import pytest


# --------------------------------------------------------------------------- #
# TUI  (live Textual NEURAL TERMINAL)
# --------------------------------------------------------------------------- #
def test_tui_module_importable_and_class_present():
    m = importlib.import_module("app.tui")
    assert hasattr(m, "MoonTUI")
    assert callable(getattr(m, "main"))


def test_tui_construct_without_terminal():
    # The Textual TUI must be constructible off a real terminal (headless),
    # mirroring the old curses TUI's "constructible without drawing" contract.
    from app.tui import MoonTUI
    tui = MoonTUI(unlock="MOON love you 3000")
    assert tui.unlock == "MOON love you 3000"
    assert tui.locked is True
    # compose() must yield real widgets without raising (off-TTY safe).
    widgets = list(tui.compose())
    assert len(widgets) >= 1
    # The chat/brain panels exist as queryable attributes after mount would,
    # but at minimum the app object is coherent.
    assert tui.orchestrator is None  # not booted until mount


# --------------------------------------------------------------------------- #
# Telegram channel
# --------------------------------------------------------------------------- #
class _FakeMsg:
    def __init__(self, chat_id, text):
        self.chat = types.SimpleNamespace(id=int(chat_id))
        self.text = text


class _FakeUpdate:
    def __init__(self, uid, chat_id, text):
        self.update_id = uid
        self.message = _FakeMsg(chat_id, text)


class _FakeBot:
    def __init__(self):
        self.sent = []
        self.actions = []

    async def send_message(self, chat_id, text):
        self.sent.append((str(chat_id), text))
        return types.SimpleNamespace(message_id=len(self.sent))

    async def send_chat_action(self, chat_id, action):
        self.actions.append((str(chat_id), action))

    async def get_updates(self, offset=0, timeout=30):
        return []


def _make_bot():
    """Build a TelegramBot with a fake orchestrator + fake python-telegram-bot."""
    import app.services.telegram_bot as tbm
    bot = tbm.TelegramBot()
    bot.token = "fake-token"
    bot.allowed_chat = "12345"

    # Fake orchestrator
    class _FakeResult:
        result = "MOON says hi back"
    class _FakeOrch:
        async def setup(self): pass
        async def teardown(self): pass
        async def run_task(self, task, on_event=None):
            return _FakeResult()
    bot.orchestrator = _FakeOrch()

    # Inject fake telegram lib
    fake_telegram = types.ModuleType("telegram")
    fake_telegram.Bot = lambda token=None: _FakeBot()
    import sys
    monkeypatch_telegram = fake_telegram
    return bot, monkeypatch_telegram


def test_telegram_routes_authorized_chat_and_replies(monkeypatch):
    bot, fake_tg = _make_bot()
    monkeypatch.setitem(__import__("sys").modules, "telegram", fake_tg)
    # _handle needs _bot; inject a fake so replies can be captured.
    fake_bot = _FakeBot()
    bot._bot = fake_bot
    asyncio.run(bot._handle("12345", "hello MOON"))
    assert any("MOON says hi back" in t for _, t in fake_bot.sent)


def test_telegram_ignores_unauthorized_chat(monkeypatch):
    bot, fake_tg = _make_bot()
    monkeypatch.setitem(__import__("sys").modules, "telegram", fake_tg)
    fake_bot = _FakeBot()
    bot._bot = fake_bot
    # Wrong chat id should not produce a reply.
    asyncio.run(bot._handle("99999", "intruder"))
    assert fake_bot.sent == []


def test_telegram_unavailable_without_token():
    import app.services.telegram_bot as tbm
    bot = tbm.TelegramBot()
    bot.token = ""
    assert bot.available is False


# --------------------------------------------------------------------------- #
# Terminal authz gate
# --------------------------------------------------------------------------- #
def test_token_ok_open_when_no_token():
    import app.terminal_interface as ti
    saved = ti.TERMINAL_TOKEN
    ti.TERMINAL_TOKEN = ""
    try:
        assert ti._token_ok({}) is True
        assert ti._token_ok({"authorization": "Bearer whatever"}) is True
    finally:
        ti.TERMINAL_TOKEN = saved


def test_token_ok_enforces_bearer(monkeypatch):
    import app.terminal_interface as ti
    saved = ti.TERMINAL_TOKEN
    ti.TERMINAL_TOKEN = "secret"
    try:
        assert ti._token_ok({"authorization": "Bearer secret"}) is True
        assert ti._token_ok({"authorization": "Bearer wrong"}) is False
        assert ti._token_ok({}) is False
        # WebSocket header path
        ws = types.SimpleNamespace(headers=types.SimpleNamespace(get=lambda k, d="": "Bearer secret" if k == "authorization" else d))
        assert ti._token_ok(ws) is True
    finally:
        ti.TERMINAL_TOKEN = saved
