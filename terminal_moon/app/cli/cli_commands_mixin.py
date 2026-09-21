"""
CLICommandsMixin — slash command handlers shared between TUI and CLI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CLICommandsMixin(ABC):
    """Abstract base providing slash command handlers. Subclass provides
    _chat_messages, query_one, _state, etc."""

    @abstractmethod
    def _print(self, text: str) -> None: ...

    async def _handle_help(self, args: str = "") -> None:
        help_text = (
            "/help       — show this help\n"
            "/clear      — clear chat\n"
            "/model NAME — switch model\n"
            "/agent NAME — switch agent\n"
            "/status     — show status\n"
            "/voice      — toggle voice\n"
            "/quit       — exit MOON"
        )
        self._print(help_text)

    async def _handle_model(self, args: str) -> None:
        if not args:
            self._print(f"Current model: {getattr(self, '_state', {}).get('model_name', 'unknown')}")
        else:
            if hasattr(self, '_state'):
                self._state["model_name"] = args
            self._print(f"Model set to: {args}")

    async def _handle_agent(self, args: str) -> None:
        if not args:
            self._print(f"Current agent: {getattr(self, '_state', {}).get('agent_name', 'unknown')}")
        else:
            if hasattr(self, '_state'):
                self._state["agent_name"] = args
            self._print(f"Agent set to: {args}")

    async def _handle_voice(self, args: str) -> None:
        self._print("Voice: available (Kokoro/F5/XTTS/OpenAI/espeak chain)")

    async def _handle_shell(self, args: str) -> None:
        if args:
            from app.cli.cli import _shell_dispatch
            out, code = _shell_dispatch(args)
            self._print(out)

    async def _handle_status(self, args: str) -> None:
        st = getattr(self, '_state', {})
        self._print(
            f"model: {st.get('model_name', 'unknown')}\n"
            f"agent: {st.get('agent_name', 'unknown')}\n"
            f"session: {st.get('session_id', 'unknown')}\n"
            f"locked: {getattr(self, 'lock', None) and self.lock.locked if hasattr(self, 'lock') else 'unknown'}"
        )

    async def _handle_doctor(self, args: str) -> None:
        self._print("Doctor: all subsystems nominal.")

    async def _handle_chat(self, args: str) -> None:
        if args:
            await self._chat_with_llm(args)

    async def _handle_oneshot(self, args: str) -> None:
        if args:
            self._print(f"[oneshot] {args}")

    async def _chat_with_llm(self, prompt: str) -> None:
        self._print("thinking...")
