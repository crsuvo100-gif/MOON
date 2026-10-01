#!/usr/bin/env python3
"""
Hermes-style online status subcommand for Moon CLI — mirrors hermes_cli/subcommands/status.py.

Register: moon cli status
"""

from __future__ import annotations

import argparse
import sys
import httpx

from app.cli.colors import Colors


def build(subparsers: argparse._SubParsersAction) -> None:
    """Build the `moon cli status` subparser."""
    parser = subparsers.add_parser("status", help="Show Moon backend health and status")
    parser.set_defaults(func=run_status)
    parser.add_argument("-H", "--host", default="http://127.0.0.1:8777", help="Backend host")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="HTTP timeout")


def run_status(args: argparse.Namespace | None = None) -> None:
    """Run `moon cli status` — mirrors hermes_cli/subcommands/status.py:run_status."""
    from app.cli.cli_output import print_info, print_success, print_error

    args = args or argparse.Namespace(host="http://127.0.0.1:8777", timeout=5.0)

    host = args.host.rstrip("/")
    url = f"{host}/api/health"

    try:
        r = httpx.get(url, timeout=args.timeout)
    except Exception as exc:
        print_error(f"Cannot reach backend at {host}")
        print_error(str(exc))
        sys.exit(1)

    if r.status_code != 200:
        print_error(f"Backend returned HTTP {r.status_code}")
        sys.exit(1)

    data = r.json()

    # Build panels
    panels: list[dict[str, str]] = [
        {"title": "BACKEND", "content": f"{data.get('status', 'UNKNOWN')}"},
        {"title": "MODEL", "content": f"{data.get('model', 'N/A')}"},
        {"title": "LOCKED", "content": str(data.get('locked', 'N/A'))},
        {"title": "SUBSYSTEMS", "content": f"{data.get('summary', 'N/A')}"},
        {"title": "AGENTS", "content": str(data.get('agents', 0))},
        {"title": "TOOLS", "content": str(data.get('tools', 0))},
        {"title": "LTM", "content": str(data.get('ltm', 0))},
        {"title": "STM", "content": str(data.get('stm', 0))},
        {"title": "EPISODIC", "content": str(data.get('episodic', 0))},
        {"title": "KNOWLEDGE", "content": str(data.get('knowledge', 0))},
    ]

    print()  # blank line like Hermes
    print(f"  {'BACKEND':<14} {data.get('status', 'UNKNOWN')}")
    print(f"  {'MODEL':<14} {data.get('model', 'N/A')}")
    print(f"  {'LOCKED':<14} {str(data.get('locked', 'N/A'))}")
    print(f"  {'SUBSYSTEMS':<14} {data.get('summary', 'N/A')}")
    print(f"  {'AGENTS':<14} {data.get('agents', 0)}")
    print(f"  {'TOOLS':<14} {data.get('tools', 0)}")
    print(f"  {'LTM':<14} {data.get('ltm', 0)}")
    print(f"  {'STM':<14} {data.get('stm', 0)}")
    print(f"  {'EPISODIC':<14} {data.get('episodic', 0)}")
    print(f"  {'KNOWLEDGE':<14} {data.get('knowledge', 0)}")
    print()

    # Detailed checks
    for check in data.get("checks", []):
        state = check.get("state", "?")
        name = check.get("subsystem", "?")
        detail = check.get("detail", "")
        if state == "OK":
            print_success(f"  {name}: {detail}")
        else:
            print_error(f"  {name}: {detail}")

    print()

    # Summary
    s = data.get("summary", "")
    if "all checks passed" in s.lower():
        print_success("All subsystems nominal.")
    elif "unhealthy" in s.lower() or "failing" in s.lower():
        print_error("Some subsystems are unhealthy — see above.")

    # Configured model
    print()
    from app.config.settings import Settings
    cfg = Settings()
    print_info(f"Configured model: {cfg.model_name}")
    print_info(f"Configured base_url: {cfg.model_base_url}")

    # Check LLMService connectivity
    print()
    print_info("Checking LLMService connectivity...")
    try:
        from app.services.llm_service import LLMService, ChatMessage
        llm = LLMService(base_url=cfg.model_base_url, model_name=cfg.model_name)
        print_success(f"LLMService ready: {cfg.model_name} @ {cfg.model_base_url}")
    except Exception as e:
        print_error(f"LLMService: {e}")
