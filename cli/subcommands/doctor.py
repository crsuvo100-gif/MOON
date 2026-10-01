#!/usr/bin/env python3
"""Hermes-style doctor subcommand for Moon CLI."""

from __future__ import annotations

import argparse
import sys


def build(subparsers: argparse._SubParsersAction) -> None:
    """Build the doctor subparser — mirrors hermes_cli/subcommands/doctor.py."""
    parser = subparsers.add_parser("doctor", help="Check configuration and dependencies")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.set_defaults(func=run_doctor)


def run_doctor(args: argparse.Namespace | None = None) -> None:
    """Run doctor checks — mirrors hermes_cli/subcommands/doctor.py:run_doctor."""
    from app.cli.cli_output import print_info, print_success, print_warning, print_error

    args = args or argparse.Namespace(verbose=False)

    print("MOON CLI Doctor")
    print("=" * 50)
    print()

    checks_passed = 0
    checks_total = 0

    # Python
    checks_total += 1
    import sys as _sys
    ver = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
    if _sys.version_info >= (3, 10):
        print_success(f"Python {ver} >= 3.10")
        checks_passed += 1
    else:
        print_error(f"Python {ver} < 3.10")

    # Rich
    checks_total += 1
    try:
        import rich
        print_success(f"rich {getattr(rich, '__version__', '?')}")
        checks_passed += 1
    except ImportError:
        print_error("rich not installed")

    # httpx
    checks_total += 1
    try:
        import httpx
        print_success(f"httpx {httpx.__version__}")
        checks_passed += 1
    except ImportError:
        print_error("httpx not installed")

    # readline
    checks_total += 1
    try:
        import readline
        print_success("readline available")
        checks_passed += 1
    except ImportError:
        print_error("readline not available")

    # asyncio
    checks_total += 1
    try:
        import asyncio
        print_success("asyncio available")
        checks_passed += 1
    except ImportError:
        print_error("asyncio not available")

    # Settings
    checks_total += 1
    try:
        from app.config.settings import Settings
        s = Settings()
        print_success(f"Settings: model={s.model_name}, base_url={s.model_base_url}")
        checks_passed += 1
    except Exception as e:
        print_error(f"Settings: {e}")

    # LLMService
    checks_total += 1
    try:
        from app.services.llm_service import LLMService, ChatMessage
        llm = LLMService(base_url=s.model_base_url, model_name=s.model_name)
        print_success(f"LLMService: {s.model_name} @ {s.model_base_url}")
        checks_passed += 1
    except Exception as e:
        print_error(f"LLMService: {e}")

    # VoiceEngine
    checks_total += 1
    try:
        from app.voice_engine import VoiceEngine
        engine = VoiceEngine()
        print_success(f"VoiceEngine: initialized ({engine.backend_status().get('backend', '?')})")
        checks_passed += 1
    except Exception as e:
        print_error(f"VoiceEngine: {e}")

    # Backend
    checks_total += 1
    try:
        import httpx as _httpx
        r = _httpx.get("http://127.0.0.1:8777/api/health", timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'HEALTHY':
                print_success(f"Backend: HEALTHY ({data.get('model')})")
                checks_passed += 1
            else:
                print_error(f"Backend: {data.get('status')}")
        else:
            print_error(f"Backend: HTTP {r.status_code}")
    except Exception as e:
        print_error(f"Backend: unreachable ({e})")

    print()
    print(f"Checks: {checks_passed}/{checks_total} passed")
    if checks_passed == checks_total:
        print_success("All checks passed — MOON CLI ready.")
    else:
        print_error("Some checks failed — see above.")
