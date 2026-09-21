#!/usr/bin/env python3
"""
MOON TWIN — Standalone Moon Agent System

A self-contained AI agent system with:
- Multi-agent persona engine (general, code, security, research, voice, admin, creative, monitor)
- Per-prompt agent selection via `agent:<name>` prefix
- Intent→agent routing (keyword-based)
- Agent persona injection into chat
- Tool execution framework
- SQLite-backed session memory
- Hermes-desktop-terminal replica TUI
- /api/moon-agent REST + WebSocket integration endpoint
- Health endpoint at /api/health

Entry points:
    moon_twin                        Interactive terminal REPL
    moon_twin --list/-l              List all agents
    moon_twin --route/-r <q>        Route a query to an agent
    moon_twin <message>              Process a single message (non-interactive)
    moon_twin --agent/-a <name> <message>  Use a specific agent
    moon_twin --json/-j <message>   JSON output mode
    moon_twin_agent_api              Start /api/moon-agent server on :8778
    moon_twin_agent_api --test       Run self-test

System CLI: /home/meow/.local/bin/moon_twin
         → cd /home/meow/Moon_Twin && exec .venv/bin/python main.py "$@"

Author: MOON / Moon_Twin
Version: 1.0.0
"""

from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Add project root to path (before any other imports)
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Agent engine & terminal
# ---------------------------------------------------------------------------

from agent.engine import (
    AgentEngine,
    default_engine,
    cmd_agent_list,
    cmd_agent_route,
)
from terminal.app import MoonTerminal

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

__version__ = "1.0.0"
__author__ = "MOON / Moon_Twin"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="moon_twin",
        description=(
            "MOON TWIN — Standalone Moon Agent System\n"
            "Multi-agent persona engine with Hermes-desktop-terminal replica."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  moon_twin                          Interactive terminal REPL
  moon_twin --list                   List all available agents
  moon_twin --route "scan my network"   Route a query to an agent
  moon_twin "agent:code write hello"    Non-interactive: use code agent
  moon_twin "hello moon"               Non-interactive: auto-routed
  moon_twin --json "agent:research AI"  JSON output mode
  moon_twin_agent_api --test           Run API self-test
  moon_twin_agent_api                  Start /api/moon-agent on :8778
        """,
    )

    parser.add_argument(
        "message",
        nargs="?",
        default=None,
        help="Message to process (non-interactive mode)",
    )
    parser.add_argument(
        "--agent", "-a",
        help="Explicit agent name (overrides intent routing)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all agents and exit",
    )
    parser.add_argument(
        "--route", "-r",
        metavar="QUERY",
        help="Route a query to an agent and show result",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON (non-interactive mode)",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"moon_twin {__version__}",
    )

    args = parser.parse_args()

    # -- List agents --
    if args.list:
        return cmd_agent_list()

    # -- Route query --
    if args.route:
        return cmd_agent_route(args.route)

    # -- Non-interactive message processing --
    if args.message:
        terminal = MoonTerminal()
        full_message = args.message

        if args.agent:
            full_message = f"agent:{args.agent} {args.message}"

        async def _run():
            result = await terminal.process(full_message)
            if args.json:
                import json
                print(json.dumps({k: v for k, v in result.items() if k != "session_id"}, indent=2))
            else:
                from rich.console import Console
                from rich.panel import Panel
                c = Console()
                agent_name = result.get("agent", "unknown")
                c.print(Panel(
                    result.get("response", "(no LLM connected — showing persona reply)"),
                    title=f"[bold magenta]AGENT: {agent_name.upper()}[/bold magenta]",
                    border_style="magenta",
                ))

        import asyncio
        asyncio.run(_run())
        return 0

    # -- Interactive REPL --
    terminal = MoonTerminal()
    import asyncio
    asyncio.run(terminal.run())
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[Interrupted. Goodbye.]")
        sys.exit(0)
    except Exception as e:
        print(f"[Error: {e}]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
