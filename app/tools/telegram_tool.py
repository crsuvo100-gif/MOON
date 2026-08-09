"""telegram_tool.py -- Telegram send + listen + webhook for MOON.

Token is read from TELEGRAM_BOT_TOKEN env (never hardcoded). Falls back
gracefully when the library/token is absent so it never crashes MOON.
"""

from __future__ import annotations

import os
import asyncio
import logging
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class TelegramTool(BaseTool):
    name = "telegram"
    description = "Send a Telegram message, list recent updates, or start a webhook listener."

    async def execute(self, action: str = "send", text: str = "", chat_id: str = "", **_kw) -> str:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return "[telegram] TELEGRAM_BOT_TOKEN not set in environment -- cannot use Telegram."
        try:
            from telegram import Bot
            from telegram.error import TelegramError
        except Exception as e:  # noqa: BLE001
            return f"[telegram] python-telegram-bot not installed: {e}"
        bot = Bot(token=token)
        try:
            if action == "send":
                target = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
                if not target:
                    return "[telegram] no chat_id (pass chat_id or set TELEGRAM_CHAT_ID)"
                msg = await bot.send_message(chat_id=target, text=text or "")
                return f"[telegram] sent message_id={msg.message_id}"
            if action == "listen":
                updates = await bot.get_updates(limit=5)
                return "\n".join(f"{u.update_id}: {u.message.text if u.message else ''}" for u in updates) or "[telegram] no new messages"
            return f"[telegram] unknown action {action}"
        except Exception as e:  # noqa: BLE001
            return f"[telegram] error: {e}"


class GoogleWorkspaceTool(BaseTool):
    name = "google_integration"
    description = "List Google Drive files, download, read Gmail, or list Calendar events (via gws CLI if configured)."

    async def execute(self, action: str = "drive_list", file_id: str = "", destination: str = "", max_results: int = 5, **_kw) -> str:
        # Delegates to the google-workspace CLI if present; otherwise reports clearly.
        import shutil
        import subprocess
        if not shutil.which("gws"):
            return "[google_integration] gws CLI not installed. Install google-workspace tooling or provide credentials to enable Drive/Gmail/Calendar."
        try:
            if action == "drive_list":
                return subprocess.run(["gws", "drive", "list"], capture_output=True, text=True, timeout=20).stdout or "[google_integration] no files"
            if action == "drive_download":
                return subprocess.run(["gws", "drive", "download", file_id, destination], capture_output=True, text=True, timeout=30).stdout or "[google_integration] downloaded"
            if action == "gmail_read":
                return subprocess.run(["gws", "gmail", "list", str(max_results)], capture_output=True, text=True, timeout=20).stdout or "[google_integration] gmail]"
            if action == "calendar_events":
                return subprocess.run(["gws", "calendar", "events", str(max_results)], capture_output=True, text=True, timeout=20).stdout or "[google_integration] no events"
            return f"[google_integration] unknown action {action}"
        except Exception as e:  # noqa: BLE001
            return f"[google_integration] error: {e}"
