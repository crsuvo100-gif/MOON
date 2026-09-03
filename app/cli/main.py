#!/usr/bin/env python3
"""
Hermes-style CLI entry point for Moon.

Mirrors hermes_cli/main.py exactly:
  * _set_process_title()            — ps shows 'moon-cli'
  * argparse with subcommand modules — model/status/doctor/setup
  * Slack-style or argument parser depending on invocation
  * Safe mode guard (no-op for Moon)
  * Subcommand dispatch via _add_subcommands() + cmd_* functions
"""

from __future__ import annotations

import argparse
import os
import sys

# ── Process title (mirrors hermes_cli/_set_process_title) ─────────────────

def _set_process_title() -> None:
    """Set process title so `ps` shows `moon-cli` — mirrors hermes."""
    try:
        import setproctitle as _st
        _st.setproctitle("moon-cli")
    except ImportError:
        pass
    try:
        import ctypes as _ct
        _libc = _ct.CDLL("libc.so.6", use_errno=True)
        _libc.prctl(15, b"moon-cli", 0, 0, 0)  # PR_SET_NAME
    except Exception:
        pass


_set_process_title()

# ── Ensure project root on path (mirrors hermes_cli/_ensure_project_root_on_path_fast) ──

def _ensure_project_root() -> None:
    root = os.path.realpath(os.path.join(os.path.dirname(__file__), os.pardir))
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_project_root()

# ── Config (mirrors hermes_cli config loading) ────────────────────────────

from app.config.settings import Settings

_settings = Settings()


# ── Resolve use_tui (mirrors hermes_cli/_resolve_use_tui) ─────────────────

def _resolve_use_tui(args: argparse.Namespace) -> bool:
    """Mirrors hermes_cli/_resolve_use_tui — always False for Moon CLI."""
    # Hermes returns True when using prompt_toolkit UI. Moon CLI uses readline.
    return False


# ── Safe mode (mirrors hermes_cli/_apply_safe_mode) ───────────────────────

def _apply_safe_mode(args: argparse.Namespace) -> None:
    """No-op: Moon doesn't have Hermes safe mode."""
    pass


# ── Subcommand parsers (mirror hermes_cli/subcommands/) ───────────────────

from app.cli.subcommands import model, status, doctor, setup


def _add_subcommands(subparsers: argparse._SubParsersAction) -> None:
    """Register all subcommand parsers — mirrors hermes_cli/_parser.py."""
    model.build(subparsers)
    status.build(subparsers)
    doctor.build(subparsers)
    setup.build(subparsers)


# ── Slash command registry (mirrors hermes_cli/commands) ──────────────────

from app.cli.commands import COMMAND_REGISTRY


# ── cmd_chat — interactive REPL (mirrors hermes_cli/cmd_chat) ─────────────

def cmd_chat(args: argparse.Namespace) -> None:
    """Run Moon CLI REPL — mirrors hermes chat command."""
    from app.cli.cli import MoonCLI

    state = _build_state(model=args.model, agent=args.agent)
    if args.query:
        from app.cli.oneshot import run_oneshot
        import asyncio
        asyncio.run(run_oneshot(args.query, state=state))
    else:
        cli = MoonCLI(state)
        import asyncio
        asyncio.run(cli.run())


def _build_state(model: str | None = None, agent: str | None = None) -> dict:
    from app.cli.commands import CLIState
    return CLIState(
        model_name=model or _settings.model_name,
        agent_name=agent or "auto",
    )


# ── cmd_model — mirrors hermes model command ──────────────────────────────

def cmd_model(args: argparse.Namespace) -> None:
    from app.config.settings import Settings

    s = Settings()
    if args.name:
        old = s.model_name
        s.model_name = args.name
        print(f"Model switched: {old} -> {args.name}")
        if args.query:
            from app.cli.oneshot import run_oneshot
            import asyncio
            asyncio.run(run_oneshot(query=args.query, model=args.name, agent=getattr(args, "agent", None) or "auto"))
    else:
        print(f"Current model: {s.model_name}")


# ── cmd_status — mirrors hermes status command ─────────────────────────────

def cmd_status(args: argparse.Namespace) -> None:
    from app.cli.subcommands.status import run as _run_status
    _run_status(args)


# ── cmd_doctor — mirrors hermes doctor command ────────────────────────────

def cmd_doctor(args: argparse.Namespace) -> None:
    from app.cli.subcommands.doctor import run as _run_doctor
    _run_doctor(args)


# ── cmd_setup — mirrors hermes setup command ──────────────────────────────

def cmd_setup(args: argparse.Namespace) -> None:
    from app.cli.subcommands.setup import run as _run_setup
    _run_setup(args)


# ── cmd_oneshot (non-interactive) — mirrors hermes_cli/oneshot.py:main ───

def cmd_oneshot(args: argparse.Namespace) -> None:
    from app.cli.oneshot import run_oneshot
    import asyncio
    asyncio.run(run_oneshot(
        args.query or "",
        model=args.model or _settings.model_name,
        agent=args.agent or "auto",
    ))


# ── Main entry point (mirrors hermes_cli/main.py:main) ────────────────────

def main() -> None:
    """Main entry point — mirrors hermes_cli/main.py:main()."""

    parser = argparse.ArgumentParser(
        prog="moon-cli",
        description="MOON's own interactive CLI terminal (Hermes-feature-rich, Moon-native)",
    )

    parser.add_argument("-Q", "--quiet", action="store_true", help="Suppress banner")
    parser.add_argument("--version", action="version", version="moon-cli 1.0.0")

    subparsers = parser.add_subparsers(dest="subtitle")

    # ── chat / cli (interactive REPL — mirrors `hermes`) ───────────────
    chat = subparsers.add_parser("chat", help="Interactive REPL (default)")
    chat.set_defaults(func=cmd_chat)
    _add_chat_args(chat)

    cli = subparsers.add_parser("cli", help="Interactive CLI terminal (default)")
    cli.set_defaults(func=cmd_chat)
    _add_chat_args(cli)

    # ── oneshot (non-interactive) ─────────────────────────────────────
    os_parser = subparsers.add_parser("oneshot", help="One-shot query (non-interactive)")
    os_parser.set_defaults(func=cmd_oneshot)
    os_parser.add_argument("query", nargs="?", default=None)
    os_parser.add_argument("-m", "--model", default=None)
    os_parser.add_argument("-a", "--agent", default=None)

    # ── subcommands ────────────────────────────────────────────────────
    _add_subcommands(subparsers)

    # ── Parse + dispatch ───────────────────────────────────────────────
    args = parser.parse_args()

    if not hasattr(args, "func"):
        # No subcommand → interactive REPL by default (mirror `hermes`)
        args.func = cmd_chat
        args.query = None
        args.model = None
        args.agent = None

    args.func(args)


def _add_chat_args(parser: argparse.ArgumentParser) -> None:
    """Add common chat/CLI arguments — mirrors hermes_cli."""
    parser.add_argument("-q", "--query", default=None, help="One-shot query (non-interactive)")
    parser.add_argument("-m", "--model", default=None, help="Model name")
    parser.add_argument("-a", "--agent", default=None, help="Agent name")


if __name__ == "__main__":
    main()
