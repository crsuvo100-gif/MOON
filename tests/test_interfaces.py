"""Tests for the new MOON interfaces: Telegram channel and the Terminal authz gate.

The TUI (Textual NEURAL TERMINAL) was removed — MOON now has a single terminal
type: the Hermes-style CLI REPL (moon / moon run / moon terminal / moon cli).
Telegram + terminal authz tests remain.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import types

import pytest


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
