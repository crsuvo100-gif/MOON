#!/usr/bin/env python3
"""Hermes-style CLI subcommands for Moon CLI."""

from __future__ import annotations

import argparse
import sys


def build(subparsers: argparse._SubParsersAction) -> None:
    """Build the `moon cli model` subparser — mirrors hermes_cli/subcommands/model.py."""
    p = subparsers.add_parser("model", help="Show or switch model; /model <name> --query runs one-shot")
    p.add_argument("name", nargs="?", default=None, help="Model name to switch to")
    p.add_argument("--query", "-q", default=None, help="One-shot query after switching model")
    p.set_defaults(func=cmd_model)


def cmd_model(args: argparse.Namespace) -> None:
    """Handle model command — mirrors hermes_cli/subcommands/model.py:cmd_model().

    Syntax:
        moon cli model              — show current model
        moon cli model <name>      — switch to <name>
        moon cli model <name> -q "prompt"  — switch + one-shot query
        moon cli model --query "prompt"    — one-shot on current model
    """
    from app.config.settings import Settings

    s = Settings()
    if args.name:
        old = s.model_name
        s.model_name = args.name
        print(f"Model switched: {old} -> {args.name}")
        if args.query:
            from app.cli.oneshot import run_oneshot
            import asyncio
            asyncio.run(run_oneshot(
                args.query,
                model=args.name,
                agent=getattr(args, "agent", None) or "auto",
            ))
    else:
        print(f"Current model: {s.model_name}")
