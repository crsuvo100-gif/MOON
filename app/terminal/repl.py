"""MOON Terminal REPL — interactive readline terminal wired to the main brain.

Usage:
    python -m app.terminal.repl
    moon terminal

This is the single user-facing surface: a readline-driven interactive session
with the full MOON brain (Orchestrator) behind it. Natural language is routed
through the Orchestrator's cognition loop; shell commands are executed via
the TerminalInterface's execution engine.

Special commands:
    /help          Show this help
    /status        Show terminal + brain status
    /sessions      List active sessions
    /processes     List background processes
    /history       Show execution history
    /clear         Clear the screen
    /brain         Show brain info (model, agents, tools)
    /exec <cmd>    Execute a shell command directly
    /quit          Exit the terminal

Shell execution:
    !<command>     Execute a shell command (e.g., !ls -la)
    $<command>     Execute and show output inline

Natural language:
    Anything else is sent to MOON's brain for a response.
"""

from __future__ import annotations

import asyncio
import os
import readline
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from app.config.logging import get_logger
from app.config.settings import get_settings
from app.terminal.terminal_interface import terminal_interface
from app.terminal.environment_manager import environment_manager
from app.terminal.history_manager import history_manager

logger = get_logger(__name__)

# ── ANSI color codes (MOON red/black HUD palette) ──

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_WHITE = "\033[37m"
_BG_RED = "\033[41m"
_BG_BLACK = "\033[40m"

# ── Prompt ──

_PROMPT = f"{_BG_BLACK}{_BOLD}{_RED} MOON {_RESET} {_CYAN}❯{_RESET} "
_PROMPT_BUSY = f"{_BG_BLACK}{_BOLD}{_RED} MOON {_RESET} {_YELLOW}◌{_RESET} "


def _print_banner() -> None:
    """Print the MOON terminal banner."""
    banner = f"""
{_BOLD}{_RED}  ███╗   ███╗ ██████╗  ██████╗ ███╗   ██╗{_RESET}
{_BOLD}{_RED}  ████╗ ████║██╔═══██╗██╔═══██╗████╗  ██║{_RESET}
{_BOLD}{_RED}  ██╔████╔██║██║   ██║██║   ██║██╔██╗ ██║{_RESET}
{_BOLD}{_RED}  ██║╚██╔╝██║██║   ██║██║   ██║██║╚██╗██║{_RESET}
{_BOLD}{_RED}  ██║ ╚═╝ ██║╚██████╔╝╚██████╔╝██║ ╚████║{_RESET}
{_BOLD}{_RED}  ╚═╝     ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝{_RESET}

{_BOLD}{_CYAN}  MOON Terminal — AI Agent Execution Platform{_RESET}
{_DIM}  Type /help for commands. Natural language goes to the brain.{_RESET}
{_DIM}  Prefix with ! for shell, $ for inline shell, /exec for direct exec.{_RESET}
"""
    print(banner)


def _print_help() -> None:
    """Print help text."""
    help_text = f"""
{_BOLD}{_CYAN}  MOON Terminal — Help{_RESET}

{_BOLD}  Special Commands:{_RESET}
    /help          Show this help
    /status        Show terminal + brain status
    /sessions      List active sessions
    /processes     List background processes
    /history       Show execution history
    /clear         Clear the screen
    /brain         Show brain info (model, agents, tools)
    /exec <cmd>    Execute a shell command directly
    /quit          Exit the terminal

{_BOLD}  Shell Execution:{_RESET}
    !<command>     Execute a shell command (e.g., !ls -la)
    $<command>     Execute and show output inline

{_BOLD}  Natural Language:{_RESET}
    Anything else is sent to MOON's brain for a response.

{_BOLD}  Examples:{_RESET}
    > What is the capital of France?
    !ls -la
    $pwd
    /exec echo hello
    /status
"""
    print(help_text)


def _print_status(orchestrator) -> None:
    """Print terminal + brain status."""
    status = terminal_interface.get_status()
    print(f"\n{_BOLD}{_CYAN}  ── Terminal Status ──{_RESET}")
    print(f"  Shells:     {', '.join(status['shells'].keys())}")
    print(f"  Default:    {status['default_shell']}")
    print(f"  Sessions:   {status['sessions']}")
    print(f"  Processes:  {status['processes']}")
    print(f"  PTY:        {'available' if status['pty_available'] else 'unavailable'}")
    print(f"  History:    {status['history_entries']} entries")
    print(f"  OS:         {status['os'].get('system', 'unknown')} {status['os'].get('release', '')}")

    if orchestrator is not None:
        print(f"\n{_BOLD}{_CYAN}  ── Brain Status ──{_RESET}")
        settings = get_settings()
        print(f"  Model:      {settings.model_name}")
        print(f"  Endpoint:   {settings.model_base_url}")
        agents = getattr(orchestrator, '_agents', {})
        print(f"  Agents:     {len(agents)} ({', '.join(list(agents.keys())[:5])}{'...' if len(agents) > 5 else ''})")
        tools = getattr(getattr(orchestrator, '_tools', None), '_registry', None)
        if tools:
            tool_names = [t.name for t in tools.all()]
            print(f"  Tools:      {len(tool_names)} available")
        else:
            print(f"  Tools:      not loaded")
    print()


def _print_sessions() -> None:
    """Print active sessions."""
    sessions = terminal_interface.list_sessions()
    if not sessions:
        print(f"\n{_DIM}  No active sessions.{_RESET}\n")
        return
    print(f"\n{_BOLD}{_CYAN}  ── Sessions ({len(sessions)}) ──{_RESET}")
    for s in sessions:
        print(f"  {s.session_id[:8]}  {s.shell:8s}  {s.status:10s}  {s.cwd}")
    print()


def _print_processes() -> None:
    """Print background processes."""
    procs = terminal_interface.list_processes()
    if not procs:
        print(f"\n{_DIM}  No background processes.{_RESET}\n")
        return
    print(f"\n{_BOLD}{_CYAN}  ── Processes ({len(procs)}) ──{_RESET}")
    for p in procs:
        print(f"  {p.execution_id[:8]}  PID {p.pid}  {p.status:10s}  {p.command[:60]}")
    print()


def _print_history(count: int = 10) -> None:
    """Print execution history."""
    entries = terminal_interface.get_history(count=count)
    if not entries:
        print(f"\n{_DIM}  No history entries.{_RESET}\n")
        return
    print(f"\n{_BOLD}{_CYAN}  ── History (last {len(entries)}) ──{_RESET}")
    for e in entries:
        ts = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
        status_color = _GREEN if e.status == "success" else _RED
        print(f"  {ts}  {status_color}{e.status:8s}{_RESET}  {e.command[:60]}")
    print()


def _print_brain_info(orchestrator) -> None:
    """Print brain information."""
    if orchestrator is None:
        print(f"\n{_RED}  Brain not initialized.{_RESET}\n")
        return
    settings = get_settings()
    print(f"\n{_BOLD}{_CYAN}  ── Brain Info ──{_RESET}")
    print(f"  Model:      {settings.model_name}")
    print(f"  Endpoint:   {settings.model_base_url}")
    print(f"  Temp:       {settings.model_temperature}")
    print(f"  Max tokens: {settings.model_max_tokens}")

    agents = getattr(orchestrator, '_agents', {})
    print(f"\n  {_BOLD}Agents ({len(agents)}):{_RESET}")
    for name, card in list(agents.items())[:10]:
        tools = getattr(card, 'allowed_tools', [])
        print(f"    {name:20s}  tools: {len(tools)}")
    if len(agents) > 10:
        print(f"    ... and {len(agents) - 10} more")

    tools = getattr(getattr(orchestrator, '_tools', None), '_registry', None)
    if tools:
        tool_names = [t.name for t in tools.all()]
        print(f"\n  {_BOLD}Tools ({len(tool_names)}):{_RESET}")
        for name in tool_names[:15]:
            print(f"    {name}")
        if len(tool_names) > 15:
            print(f"    ... and {len(tool_names) - 15} more")
    print()


def _execute_shell(command: str, inline: bool = False) -> None:
    """Execute a shell command via TerminalInterface."""
    try:
        result = terminal_interface.execute(command, timeout=30)
        if inline:
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(f"{_RED}{result.stderr.rstrip()}{_RESET}")
        else:
            print(f"\n{_DIM}  $ {command}{_RESET}")
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(f"{_RED}{result.stderr.rstrip()}{_RESET}")
            status_color = _GREEN if result.status == "success" else _RED
            print(f"  {status_color}[{result.status}]{_RESET}  exit={result.exit_code}  {result.duration:.2f}s")
            print()
    except Exception as exc:
        print(f"{_RED}  Error: {exc}{_RESET}")


async def _run_brain(orchestrator, prompt: str) -> str:
    """Run a prompt through the Orchestrator's cognition loop."""
    from app.models.task import Task
    task = Task(prompt=prompt, agent_name="auto")
    try:
        result_task = await orchestrator.run_task(task)
        return result_task.result or "(no response)"
    except Exception as exc:
        return f"[brain error: {exc}]"


class MoonTerminalREPL:
    """Interactive readline REPL wired to MOON's main brain."""

    def __init__(self):
        self.orchestrator = None
        self._running = False
        self._busy = False

    async def start(self) -> None:
        """Initialize the brain and start the REPL."""
        _print_banner()

        # Initialize the Orchestrator (main brain)
        print(f"{_DIM}  Initializing brain...{_RESET}")
        try:
            from app.brain.orchestrator import Orchestrator
            settings = get_settings()
            self.orchestrator = Orchestrator(settings)
            await self.orchestrator.setup()
            n_agents = len(getattr(self.orchestrator, '_agents', {}) or {})
            print(f"{_GREEN}  Brain ready: {n_agents} agents loaded.{_RESET}")
        except Exception as exc:
            print(f"{_YELLOW}  Brain init failed: {exc}{_RESET}")
            print(f"{_DIM}  Continuing in shell-only mode.{_RESET}")
            self.orchestrator = None

        print()
        self._running = True
        self._repl_loop()

    def _repl_loop(self) -> None:
        """Main readline loop."""
        # Set up readline history
        history_file = Path.home() / ".moon_terminal_history"
        try:
            readline.read_history_file(str(history_file))
        except (FileNotFoundError, OSError):
            pass

        while self._running:
            try:
                prompt = _PROMPT_BUSY if self._busy else _PROMPT
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            # Save to readline history
            readline.add_history(user_input)

            # Handle special commands
            if user_input.startswith("/"):
                self._handle_command(user_input)
            elif user_input.startswith("!"):
                # Shell execution
                cmd = user_input[1:].strip()
                if cmd:
                    _execute_shell(cmd, inline=False)
            elif user_input.startswith("$"):
                # Inline shell execution
                cmd = user_input[1:].strip()
                if cmd:
                    _execute_shell(cmd, inline=True)
            else:
                # Natural language → brain
                self._handle_brain_input(user_input)

        # Save readline history
        try:
            readline.write_history_file(str(history_file))
        except (FileNotFoundError, OSError):
            pass

        # Cleanup
        if self.orchestrator is not None:
            print(f"\n{_DIM}  Shutting down brain...{_RESET}")
            try:
                asyncio.run(self.orchestrator.teardown())
            except Exception:
                pass
        print(f"{_DIM}  Goodbye.{_RESET}\n")

    def _handle_command(self, cmd: str) -> None:
        """Handle /commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/quit" or command == "/exit":
            self._running = False
        elif command == "/help":
            _print_help()
        elif command == "/status":
            _print_status(self.orchestrator)
        elif command == "/sessions":
            _print_sessions()
        elif command == "/processes":
            _print_processes()
        elif command == "/history":
            count = int(arg) if arg.isdigit() else 10
            _print_history(count)
        elif command == "/clear":
            os.system("clear" if os.name != "nt" else "cls")
        elif command == "/brain":
            _print_brain_info(self.orchestrator)
        elif command == "/exec":
            if arg:
                _execute_shell(arg, inline=False)
            else:
                print(f"{_YELLOW}  Usage: /exec <command>{_RESET}")
        else:
            print(f"{_YELLOW}  Unknown command: {command}. Type /help for help.{_RESET}")

    def _handle_brain_input(self, prompt: str) -> None:
        """Send natural language to the brain."""
        if self.orchestrator is None:
            print(f"{_RED}  Brain not available. Use !<cmd> for shell or /help for commands.{_RESET}")
            return

        self._busy = True
        print(f"{_DIM}  Thinking...{_RESET}")
        try:
            response = asyncio.run(_run_brain(self.orchestrator, prompt))
            print(f"\n{_BOLD}{_RED}  MOON:{_RESET} {response}\n")
        except Exception as exc:
            print(f"{_RED}  Brain error: {exc}{_RESET}\n")
        finally:
            self._busy = False


def main() -> None:
    """Entry point for the MOON Terminal REPL."""
    repl = MoonTerminalREPL()
    try:
        asyncio.run(repl.start())
    except KeyboardInterrupt:
        print(f"\n{_DIM}  Interrupted.{_RESET}")
    sys.exit(0)


if __name__ == "__main__":
    main()
