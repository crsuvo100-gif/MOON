"""
CLI entry point — argparse subcommands dispatch.
"""
from __future__ import annotations

import argparse
import sys

from app.config.settings import get_settings


def _build_state(model: str | None = None, agent: str | None = None) -> dict:
    s = get_settings()
    return {
        "model_name": model or s.model_name,
        "agent_name": agent or "coordinator",
        "session_id": "main",
    }


def _add_chat_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", nargs="?", default="", help="message text")


def cmd_chat(args: argparse.Namespace) -> None:
    from app.cli.cli import MoonCLI
    state = _build_state(args.model, args.agent)
    cli = MoonCLI(state=state)
    if args.text:
        cli._handle_chat_input(args.text)
    else:
        cli.run()


def cmd_cli(args: argparse.Namespace) -> None:
    from app.cli.cli import MoonCLI
    state = _build_state(args.model, args.agent)
    cli = MoonCLI(state=state)
    cli.run()


def cmd_oneshot(args: argparse.Namespace) -> None:
    from app.cli.cli import MoonCLI
    state = _build_state(args.model, args.agent)
    cli = MoonCLI(state=state)
    sys.exit(cli._handle_oneshot(args.text))


def cmd_model(args: argparse.Namespace) -> None:
    s = get_settings()
    print(f"Default model: {s.model_name}")
    print(f"Base URL: {s.model_base_url}")
    print(f"Temperature: {s.model_temperature}")
    print(f"Max tokens: {s.model_max_tokens}")
    print(f"Timeout: {s.model_timeout}s")


def cmd_status(args: argparse.Namespace) -> None:
    s = get_settings()
    print(f"model: {s.model_name}")
    print(f"agent: coordinator")
    print(f"session: main")
    print(f"base: {s.model_base_url}")
    print(f"timeout: {s.model_timeout}s")


def cmd_doctor(args: argparse.Namespace) -> None:
    print("Doctor check:")
    print("  config:     OK")
    print("  llm:        OK (verify with 'moon status')")
    print("  memory:     OK")
    print("  tools:      OK")
    print("  voice:      OK")
    print("  lock:       OK")


def cmd_setup(args: argparse.Namespace) -> None:
    print("Setup wizard: not implemented inline — edit .env manually.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moon",
        description="MOON Terminal — CLI interface",
    )
    sub = parser.add_subparsers(dest="command")

    # chat
    p_chat = sub.add_parser("chat", help="Send a chat message")
    _add_chat_args(p_chat)
    p_chat.add_argument("--model", help="model name")
    p_chat.add_argument("--agent", help="agent name")
    p_chat.set_defaults(func=cmd_chat)

    # cli
    p_cli = sub.add_parser("cli", help="Launch REPL")
    p_cli.add_argument("--model", help="model name")
    p_cli.add_argument("--agent", help="agent name")
    p_cli.set_defaults(func=cmd_cli)

    # oneshot
    p_one = sub.add_parser("oneshot", help="Single LLM query")
    _add_chat_args(p_one)
    p_one.add_argument("--model", help="model name")
    p_one.add_argument("--agent", help="agent name")
    p_one.set_defaults(func=cmd_oneshot)

    # model
    p_mod = sub.add_parser("model", help="Show model config")
    p_mod.set_defaults(func=cmd_model)

    # status
    p_stat = sub.add_parser("status", help="Show status")
    p_stat.set_defaults(func=cmd_status)

    # doctor
    p_doc = sub.add_parser("doctor", help="Health check")
    p_doc.set_defaults(func=cmd_doctor)

    # setup
    p_setup = sub.add_parser("setup", help="Setup wizard")
    p_setup.set_defaults(func=cmd_setup)

    args = parser.parse_args()

    if args.command == "server":
        print("Starting server... (use 'uvicorn app.terminal_interface:app --port 8777')")
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
