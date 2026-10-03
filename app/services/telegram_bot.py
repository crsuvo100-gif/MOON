"""telegram_bot.py -- MOON's Telegram chat channel (polling listener).

Lets you talk to MOON from Telegram. Uses long-polling (getUpdates) so no public
webhook is required. The Telegram bot token + allowed chat id come from the
environment (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) -- never hardcoded, never
logged. Only messages from an authorized chat id are answered (anti-spam gate).

This is ADDITIVE: it does not change MOON's core; it just drives the Orchestrator.

Usage:
    python main.py telegram          # blocks, listening until Ctrl-C
Optional env:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_POLL_TIMEOUT (default 30)
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)


class TelegramBot:
    def __init__(self) -> None:
        # Prefer explicit env vars; fall back to pydantic settings (loaded from .env).
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or ""
        self.allowed_chat = os.environ.get("TELEGRAM_CHAT_ID", "") or ""
        if not self.token:
            try:
                from app.config.settings import get_settings
                s = get_settings()
                self.token = s.telegram_bot_token or ""
                self.allowed_chat = self.allowed_chat or s.telegram_chat_id or ""
            except Exception:  # noqa: BLE001
                pass
        self.poll_timeout = int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "30"))
        self.orchestrator = None
        self._bot = None  # python-telegram-bot Bot, lazy

    @property
    def available(self) -> bool:
        return bool(self.token)

    async def _ensure(self) -> None:
        if self.orchestrator is None:
            from app.brain.orchestrator import Orchestrator
            from app.config.env_guard import decontaminate_pythonpath
            decontaminate_pythonpath()
            self.orchestrator = Orchestrator(get_settings())
            await self.orchestrator.setup()
        if self._bot is None:
            try:
                from telegram import Bot
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"python-telegram-bot not installed: {exc}")
            self._bot = Bot(token=self.token)

    async def _on_event(self, ev: dict) -> None:
        # Optional: surface brief brain activity as a typing indicator.
        try:
            if self._bot is not None and self._last_chat:
                await self._bot.send_chat_action(chat_id=self._last_chat, action="typing")
        except Exception:
            pass

    async def reply(self, chat_id: str, text: str) -> None:
        # Telegram messages are limited to 4096 chars; chunk if needed.
        for i in range(0, len(text), 4000):
            await self._bot.send_message(chat_id=chat_id, text=text[i : i + 4000])

    async def _handle(self, chat_id: str, text: str) -> None:
        # Authorization gate: ignore messages from non-allowlisted chats.
        if self.allowed_chat and str(chat_id) != self.allowed_chat:
            logger.warning("Ignored Telegram message from unauthorized chat %s", chat_id)
            return
        self._last_chat = chat_id
        from app.models.task import Task
        task = Task.create(text, agent_name="auto")
        result = await self.orchestrator.run_task(task, on_event=self._on_event)
        answer = result.result or "(no response)"
        await self.reply(chat_id, answer)

    async def run(self) -> None:
        if not self.available:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set -- cannot start Telegram channel")
        await self._ensure()
        last_update_id = 0
        logger.info("Telegram listener started (chat gate: %s)", self.allowed_chat or "ANY")
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=last_update_id + 1, timeout=self.poll_timeout
                )
                for upd in updates:
                    last_update_id = max(last_update_id, upd.update_id)
                    msg = getattr(upd, "message", None) or getattr(upd, "edited_message", None)
                    if not msg or not getattr(msg, "text", None):
                        continue
                    chat_id = str(msg.chat.id)
                    if self.allowed_chat and chat_id != self.allowed_chat:
                        logger.warning("Ignored Telegram message from unauthorized chat %s", chat_id)
                        continue
                    await self._handle(chat_id, msg.text)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram poll error (retrying): %s", exc)
                await asyncio.sleep(2)
        if self.orchestrator is not None:
            await self.orchestrator.teardown()


def main() -> int:
    bot = TelegramBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("Telegram bot stopped: %s", exc)
        print(f"[MOON Telegram] fatal: {exc}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
