"""
Moon_Twin Terminal — Hermes desktop terminal replica for Moon_Twin.

Interactive TUI REPL with:
- Agent selection (agent: prefix + /agent listing)
- Persona injection into chat
- Tool execution
- Session memory
- Status dashboard
- Integration with Moon_Twin agent engine
"""

from __future__ import annotations

import asyncio
import os
import sys
import signal
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Try importing rich for TUI; fall back to plain terminal if unavailable
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich.align import Align
    from rich.spinner import Spinner
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ---------------------------------------------------------------------------
# Add project root to path
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.engine import (
    AgentEngine,
    default_engine,
    cmd_agent_list,
    cmd_agent_route,
    api_agent_process,
    api_agent_list,
    api_agent_router,
)


# ---------------------------------------------------------------------------
# Console setup
# ---------------------------------------------------------------------------

if HAS_RICH:
    console = Console()
else:
    console = None  # type: ignore


def cprint(*args, **kwargs):
    """Print with rich if available, else plain."""
    if HAS_RICH and console:
        console.print(*args, **kwargs)
    else:
        print(*args, **kwargs)


# ---------------------------------------------------------------------------
# Terminal application
# ---------------------------------------------------------------------------

class MoonTerminal:
    """
    Hermes-desktop-terminal replica for Moon_Twin.

    Provides an interactive terminal session with:
    - Welcome banner + status dashboard
    - Interactive REPL for chatting with Moon_Twin agents
    - /agent command to list available agents
    - agent:<name> prefix for per-prompt agent selection
    - Tool execution
    - Session memory
    - Exit handling
    """

    def __init__(self, engine: AgentEngine | None = None):
        self.engine = engine or default_engine
        self.session_id = f"session-{os.getpid()}-{id(self)}"
        self.running = True
        self.message_count = 0
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Handle Ctrl+C and termination signals gracefully."""
        def handler(sig, frame):
            if self.running:
                cprint("\n[bold red]Interrupted. Type /quit to exit.[/bold red]")
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    # ------------------------------------------------------------------
    # Banner / dashboard
    # ------------------------------------------------------------------

    def show_banner(self):
        """Display the Moon_Twin terminal welcome banner."""
        if HAS_RICH:
            banner = Panel(
                Text.assemble(
                    ("╔", "bold magenta"),
                    ("══════════════════════════════════════════╗", "bold magenta"),
                    ("╔", "bold magenta"),
                    ("═══ MOON_TWIN TERMINAL ════════════════════════╗", "bold cyan"),
                    ("║", "bold magenta"),
                    ("  Moon_Twin Agent System", "bold white"),
                    ("║", "bold magenta"),
                    ("  v1.0.0 | /home/meow/Moon_Twin", "dim"),
                    ("║", "bold magenta"),
                    ("╚══════════════════════════════════════════╝", "bold magenta"),
                ),
                title="[bold red]MOON_TWIN[/bold red]",
                border_style="magenta",
                padding=(1, 2),
            )
            cprint(banner)
        else:
            cprint("╔══════════════════════════════════════════╗")
            cprint("║  MOON_TWIN TERMINAL — Moon_Twin Agent System  ║")
            cprint("║  v1.0.0 | /home/meow/Moon_Twin          ║")
            cprint("╚══════════════════════════════════════════╝")
        cprint()

    def show_status(self):
        """Show current session status dashboard."""
        agents = self.engine.list_agents()
        enabled = sum(1 for a in agents if a["enabled"])
        total = len(agents)

        if HAS_RICH:
            status_table = Table(
                title="[bold green]STATUS[/bold green]",
                border_style="green",
                title_style="bold green",
            )
            status_table.add_column("Metric", style="cyan", justify="right")
            status_table.add_column("Value", style="green")
            status_table.add_row("Session", self.session_id)
            status_table.add_row("Agents", f"{enabled}/{total} enabled")
            status_table.add_row("Messages", str(self.message_count))
            status_table.add_row("Memory entries", str(len(self.engine.get_memory())))
            status_table.add_row("Lock state", "unlocked")
            cprint(status_table)
        else:
            cprint(f"Session: {self.session_id}")
            cprint(f"Agents: {enabled}/{total} enabled")
            cprint(f"Messages: {self.message_count}")
            cprint(f"Memory: {len(self.engine.get_memory())} entries")
            cprint("Lock state: unlocked")
        cprint()

    def show_help(self):
        """Show available commands."""
        if HAS_RICH:
            help_text = (
                "[bold cyan]/agent[/bold cyan]          — List all available agents\n"
                "[bold cyan]/route <query>[/bold cyan]   — Show which agent handles a query\n"
                "[bold cyan]/status[/bold cyan]         — Show session status\n"
                "[bold cyan]/clear[/bold cyan]          — Clear session memory\n"
                "[bold cyan]/help[/bold cyan]           — Show this help\n"
                "[bold cyan]/quit[/bold cyan]           — Exit terminal\n"
                "\n"
                "[bold yellow]agent:<name> <message>[/bold yellow] — Use a specific agent\n"
                "Example: [bold yellow]agent:code write a function[/bold yellow]\n"
                "\n"
                "[bold green]Plain messages[/bold green] are routed by intent automatically."
            )
            cprint(Panel(help_text, title="[bold cyan]COMMANDS[/bold cyan]", border_style="cyan"))
        else:
            cprint("/agent          — List all available agents")
            cprint("/route <query> — Show which agent handles a query")
            cprint("/status         — Show session status")
            cprint("/clear          — Clear session memory")
            cprint("/help           — Show this help")
            cprint("/quit           — Exit terminal")
            cprint()
            cprint("agent:<name> <message> — Use a specific agent")
            cprint("Example: agent:code write a function")
            cprint()
            cprint("Plain messages are routed by intent automatically.")

    # ------------------------------------------------------------------
    # Command processing
    # ------------------------------------------------------------------

    def process_command(self, raw: str) -> bool:
        """
        Process a slash command. Returns True if the session should continue.
        Returns False to signal exit.
        """
        raw = raw.strip()
        if not raw:
            return True

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            cprint("[bold red]Goodbye. Moon_Twin signing off.[/bold red]")
            self.running = False
            return False

        elif cmd in ("/help", "?"):
            self.show_help()

        elif cmd == "/agent":
            cmd_agent_list()

        elif cmd == "/route":
            if arg:
                cmd_agent_route(arg)
            else:
                cprint("[yellow]Usage: /route <query>[/yellow]")

        elif cmd == "/status":
            self.show_status()

        elif cmd == "/clear":
            self.engine.clear_memory(session_id=self.session_id)
            cprint("[bold green]Session memory cleared.[/bold green]")

        else:
            cprint(f"[red]Unknown command: {cmd}. Type /help for available commands.[/red]")

        return True

    # ------------------------------------------------------------------
    # Message processing (agent chat)
    # ------------------------------------------------------------------

    async def process_message(self, message: str) -> Optional[str]:
        """
        Process a chat message through the agent engine.
        Returns a response string, or None on error.
        """
        self.message_count += 1

        # Parse agent: prefix
        agent_name, clean_msg = self.engine.parse_agent_prefix(message)

        # Select agent (explicit or via prefix or intent)
        if agent_name:
            selected = self.engine.get_agent(agent_name)
            if selected:
                cprint(f"[bold yellow]→ Agent: {selected.name}[/bold yellow]")
            else:
                cprint(f"[bold red]→ Unknown agent: {agent_name}. Using general.[/bold red]")
                selected = self.engine.get_agent("general")
                clean_msg = message  # don't strip prefix if agent unknown
        else:
            selected = self.engine.select_agent(message)
            cprint(f"[bold cyan]→ Routed to: {selected.name}[/bold cyan]")

        # Process through engine
        result = await self.engine.process_message(
            message,
            session_id=self.session_id,
        )

        # Show agent persona
        cprint(Panel(
            f"[bold]Agent:[/bold] {result['agent']}\n"
            f"[bold]Persona:[/bold] {result['persona']['description'][:100]}\n"
            f"[bold]System Prompt:[/bold] {result['persona']['system_prompt'][:100]}...",
            title=f"[bold green]AGENT: {result['agent'].upper()}[/bold green]",
            border_style="green",
        ))

        # Generate response (placeholder — real LLM integration goes here)
        response = await self.engine.generate_response(
            selected,
            clean_msg,
        )

        cprint(Panel(
            response,
            title=f"[bold magenta]RESPONSE[/bold magenta]",
            border_style="magenta",
        ))

        return response

    # ------------------------------------------------------------------
    # Main REPL loop
    # ------------------------------------------------------------------

    async def run(self):
        """Run the interactive terminal REPL."""
        self.show_banner()
        self.show_status()
        self.show_help()
        await self.ws_connect()  # Attempt WebSocket connection
        cprint("[bold green]Type /help for commands, /quit to exit.[/bold green]")
        cprint("[bold yellow]Try: agent:code write a hello world function[/bold yellow]")
        cprint()

        while self.running:
            try:
                # Get input
                if HAS_RICH:
                    user_input = console.input("[bold green]moontwin>[/bold green] ").strip()
                else:
                    user_input = input("moontwin> ").strip()

                if not user_input:
                    continue

                # Check for slash commands
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break
                    continue

                # Process as agent message
                await self.process_message(user_input)

            except KeyboardInterrupt:
                cprint("\n[yellow]Interrupted. Continue...[/yellow]")
                continue
            except EOFError:
                cprint("\n[bold red]EOF — exiting.[/bold red]")
                self.running = False
                break
            except Exception as e:
                cprint(f"[bold red]Error: {e}[/bold red]")

        await self.ws_disconnect()
        cprint()
        cprint(f"[dim]Session {self.session_id} ended. {self.message_count} messages processed.[/dim]")

    async def ws_connect(self, url: str = "ws://127.0.0.1:8778/api/ws"):
        """Connect to the API WebSocket for real-time streaming."""
        try:
            import websockets
            self.ws = await websockets.connect(url)
            cprint("[bold green]Connected to API WebSocket[/bold green]")
            return True
        except ImportError:
            cprint("[yellow]websockets not installed — WebSocket disabled[/yellow]")
            return False
        except Exception as e:
            cprint(f"[red]WebSocket connection failed: {e}[/red]")
            return False

    async def ws_send(self, message: str, agent: str | None = None):
        """Send a message via WebSocket."""
        if not hasattr(self, "ws"):
            return None
        try:
            import websockets
            msg = {"text": message, "session_id": self.session_id, "agent": agent}
            await self.ws.send_json(msg)
            response = await self.ws.recv_json()
            return response
        except Exception as e:
            cprint(f"[red]WebSocket send failed: {e}[/red]")
            return None

    async def ws_disconnect(self):
        """Close WebSocket connection."""
        if hasattr(self, "ws"):
            try:
                await self.ws.close()
                cprint("[dim]WebSocket disconnected.[/dim]")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Non-interactive mode (for API / scripting)
    # ------------------------------------------------------------------

    async def process(self, message: str) -> dict:
        """Process a message non-interactively (for API use)."""
        result = await self.engine.process_message(
            message,
            session_id=self.session_id,
        )
        agent_name = result["agent"]
        selected = self.engine.get_agent(agent_name)

        response = await self.engine.generate_response(
            selected,
            result["message"],
        )

        result["response"] = response
        return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry for moon_twin_terminal."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="moon_twin_terminal",
        description="Moon_Twin Terminal — Hermes desktop terminal replica for Moon_Twin",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Process a single message (non-interactive mode)",
    )
    parser.add_argument(
        "--agent", "-a",
        help="Explicit agent to use (overrides routing)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all agents and exit",
    )
    parser.add_argument(
        "--route", "-r",
        help="Route a query to an agent and show result",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON (non-interactive mode)",
    )

    args = parser.parse_args()

    if args.list:
        cmd_agent_list()
        return

    if args.route:
        cmd_agent_route(args.route)
        return

    terminal = MoonTerminal()

    if args.message:
        # Non-interactive mode
        async def _run():
            result = await terminal.process(args.message)
            if args.json:
                import json
                print(json.dumps(result, indent=2))
            else:
                cprint(Panel(
                    result.get("response", ""),
                    title=f"[bold magenta]AGENT: {result['agent'].upper()}[/bold magenta]",
                    border_style="magenta",
                ))

        asyncio.run(_run())
    else:
        # Interactive REPL
        asyncio.run(terminal.run())


if __name__ == "__main__":
    main()
