#!/usr/bin/env python3
"""Hermes-style REPL for Moon CLI.

Mirrors hermes_cli/cli.py:HermesCLI exactly. Same structure, same
method layout, same async dispatch loop. Moon-native underneath.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from app.cli.cli_output import (
    line_input,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
)
from app.cli.colors import Colors, color
from app.cli.console_engine import (
    ConsoleEngine,
    print_panel,
    print_spinner,
    print_divider,
)
from app.cli.commands import COMMAND_REGISTRY, CLIState, resolve_command, cli_commands
from app.cli.cli_commands_mixin import CLICommandsMixin
from app.cli.completion import setup_readline_completion


class MoonCLI(CLICommandsMixin):
    """Hermes-style interactive REPL for Moon CLI.

    Mirrors hermes_cli/cli.py:HermesCLI exactly in structure:
      * CLIState state (model, agent, session, message buffer)
      * async dispatch loop
      * readline input with tab completion
      * spinner/indicator for LLM processing
      * panel-based output via console_engine
      * session save/load, history, model/agent switching
    """

    def __init__(self, state: CLIState) -> None:
        self.state = state
        self.engine = ConsoleEngine()
        self._history: List[str] = []
        self._history_file = Path.home() / ".moon" / "cli_history"
        self._session_start = time.time()
        self._command_counts: Dict[str, int] = {}
        self._first_prompt = True

    async def run(self) -> None:
        """Run the interactive REPL loop — mirrors hermes_cli:HermesCLI.run()."""
        import readline as _rl

        reader = setup_readline_completion()
        try:
            _rl.read_history_file(str(self._history_file))
        except OSError:
            pass

        self._print_banner()

        while True:
            try:
                prompt_text = self._get_prompt()
                line = reader.readline(prompt_text)
            except (EOFError, KeyboardInterrupt):
                print()
                break

            line = line.strip()
            if not line:
                continue

            self._history.append(line)
            try:
                _rl.add_history(line)
            except Exception:
                pass
            await self._dispatch(line)

            # Best-effort history save
            try:
                self._history_file.parent.mkdir(parents=True, exist_ok=True)
                _rl.write_history_file(str(self._history_file))
            except Exception:
                pass

    # ── Banner (mirrors hermes_cli banner) ──────────────────────────────────

    def _print_banner(self) -> None:
        """Print startup banner — mirrors hermes_cli:HermesCLI._print_banner()."""
        from app.cli.console_engine import print_header

        print()
        print_info("MOON CLI Terminal")
        print_info("Hermes-feature-rich, Moon-native")
        print()
        print_info(f"Model: {self.state.model_name}")
        print_info(f"Agent: {self.state.agent_name}")
        print_info(f"Session: {self.state.session_id or 'live'}")
        print()

        from app.config.settings import Settings
        s = Settings()
        print_info(f"Configured base: {s.model_base_url}")
        print_info(f"Configured timeout: {s.model_timeout}s")
        print()

        status_text = "LOCKED — awaiting 'MOON love you 3000' to unlock"
        print_warning(status_text)
        print()

        if self.state.verbose:
            print_warning("Verbose mode enabled")
        print_info("Type /help for commands, Ctrl+D or /quit to exit")
        print()

    # ── Prompt (mirrors hermes_cli:HermesCLI._get_prompt()) ──────────────────

    def _get_prompt(self) -> str:
        """Build the input prompt string — mirrors hermes_cli:HermesCLI._get_prompt()."""
        model = self.state.model_name
        agent = self.state.agent_name
        session = self.state.session_id or "live"
        prefix = f"{Colors.CYAN.value}>{Colors.RESET.value} "
        return f"{prefix}({model}/{agent}@{session}) "

    # ── Dispatch (mirrors hermes_cli:HermesCLI._handle_line()) ───────────────

    async def _dispatch(self, line: str) -> None:
        """Dispatch a line of input — mirrors hermes_cli:HermesCLI._handle_line()."""
        line = line.strip()
        if not line:
            return

        if line.startswith("/"):
            if line == "/":
                # Bare / → help
                await self._handle_help_command("")
                return
            await self._dispatch_command(line[1:])
        else:
            # Regular chat input
            await self._handle_chat_input(line)

    async def _dispatch_command(self, text: str) -> None:
        """Dispatch a slash command — mirrors hermes_cli command dispatch."""
        parts = text.split(maxsplit=1)
        cmd_name = parts[0].lower()
        arg_text = parts[1] if len(parts) > 1 else ""

        cmd = resolve_command(cmd_name)
        if cmd is None:
            print_error(f"Unknown command: /{cmd_name}")
            print_info("Type /help for available commands")
            return

        # Dispatch to handler method
        handler_name = f"_handle_{cmd_name.replace('-', '_')}"
        if hasattr(self, handler_name):
            try:
                if arg_text:
                    await getattr(self, handler_name)(arg_text)
                else:
                    await getattr(self, handler_name)("")
            except TypeError:
                # Handler doesn't accept args
                await getattr(self, handler_name)()
        else:
            # Fallback: try generic _handle_command
            await self._handle_command(cmd_name, arg_text)

    async def _handle_chat_input(self, text: str) -> None:
        """Handle regular chat input — send to LLM."""
        from app.cli.oneshot import run_oneshot
        from app.cli.console_engine import print_spinner

        # Show thinking indicator
        await self._show_thinking_indicator()

        try:
            result = await run_oneshot(
                text,
                model=self.state.model_name,
                agent=self.state.agent_name,
            )
            if result:
                print_success(result)
                self._command_counts["chat"] = self._command_counts.get("chat", 0) + 1
            else:
                print_error("Empty response from LLM")
        except Exception as e:
            print_error(f"Query failed: {e}")

    async def _show_thinking_indicator(self) -> None:
        """Show thinking indicator while processing."""
        spinner = print_spinner("Thinking...")
        await asyncio.sleep(0.1)
        # In real Hermes, this would be cancelled on response
        # For Moon, we just print a brief spinner and let the LLM call follow

    # ── Generic command fallback ──────────────────────────────────────────────

    async def _handle_command(self, cmd_name: str, arg_text: str) -> None:
        """Generic fallback for slash commands."""
        cmd = resolve_command(cmd_name)
        if cmd is None:
            print_error(f"Unknown command: /{cmd_name}")
            return

        print_info(f"Command /{cmd_name} — {cmd.description}")
        if cmd.args_hint:
            print_info(f"Usage: /{cmd_name} {cmd.args_hint}")

    # ── History ───────────────────────────────────────────────────────────────

    async def _save_history(self) -> None:
        """Save command history to file."""
        path = self._history_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(self._history) + "\n")
            print_success(f"History saved to {path}")
        except Exception as e:
            print_error(f"Failed to save history: {e}")

    async def _load_history(self) -> None:
        """Load command history from file."""
        path = self._history_file
        try:
            if path.exists():
                self._history = path.read_text().splitlines()
                print_success(f"Loaded {len(self._history)} history entries from {path}")
            else:
                print_info("No history file found")
        except Exception as e:
            print_error(f"Failed to load history: {e}")


# ── CLIState is now in app.cli.commands (imported above) ──────────────────