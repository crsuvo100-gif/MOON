#!/usr/bin/env python3
"""Hermes-style setup subcommand for Moon CLI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


DEFAULT_BRANCH = "main"
DEFAULT_MODEL = "qwen2.5:1.5b"
DEFAULT_VOICE_DEVICE = "alsa"


def build(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("setup", help="Interactive setup wizard")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Git branch (default: main)")
    parser.set_defaults(func=run_setup)


def run_setup(args: argparse.Namespace) -> None:
    root = Path("/home/meow/Projects/MOON")
    env = root / ".env"

    print("MOON setup")
    print("=" * 50)
    print()

    exists = env.exists()
    print(f"Project root:  {root}")
    print(f"Environment:   {'exists' if exists else 'MISSING'}")
    print(f"Current model: {os.environ.get('MODEL_NAME', 'not set in .env')}")
    print(f"Git branch:    {args.branch or DEFAULT_BRANCH}")
    print()

    if not exists:
        print("Creating .env from template...")
        example = root / ".env.example"
        if example.exists():
            env.write_text(example.read_text())
            print(f"  Wrote {env}")
        else:
            print("  WARNING: .env.example not found")
    else:
        print("  .env already exists")

    print()
    print(f"Voice backend:   Kokoro ONNX (offline, English + espeak fallback)")
    print(f"Voice device:    {DEFAULT_VOICE_DEVICE}")
    print()
    print("Setup complete. Run 'moon cli' to start.")
