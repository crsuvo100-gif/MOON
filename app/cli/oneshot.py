#!/usr/bin/env python3
"""Hermes-style one-shot mode for Moon CLI.

Mirrors hermes_cli/oneshot.py: run_oneshot() for non-interactive
prompt → LLM → print response → exit.
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Optional

from app.cli.console_engine import ConsoleEngine, get_console, print_panel
from app.config.settings import Settings


# ── Entry points (mirror hermes_cli/oneshot.py) ────────────────────────────

async def run_oneshot(
    prompt_text: str,
    *,
    model: str | None = None,
    agent: str | None = None,
    query: str | None = None,
) -> int:
    """Run a one-shot query — mirrors hermes_cli/oneshot.py:run_oneshot().

    Non-interactive: prompt → LLM → print response → return exit code.

    Args:
        prompt_text: User's query.
        model: Model name override (uses Settings default if None).
        agent: Agent name (not used in one-shot, kept for API parity).
        query: Alias for prompt_text (for API parity with main.py).

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    prompt_text = query if query is not None else prompt_text
    from app.services.llm_service import LLMService, ChatMessage

    console = get_console()
    print_panel("MOON CLI one-shot", prompt_text, border_style="cyan")
    console.print()

    try:
        settings = Settings()
        if model and model != settings.model_name:
            settings.model_name = model

        llm = LLMService(
            base_url=settings.model_base_url,
            model_name=model or settings.model_name,
            timeout=settings.model_timeout,
        )
        messages = [ChatMessage(role="user", content=prompt_text)]

        result = await llm.complete(messages=messages)
        content = getattr(result, 'content', None) or ""

        console.print()
        console.print()

        if content:
            print(f"Model: {content}")
            print()
            rc = 0
        else:
            print("(no response)")
            return 1

    except KeyboardInterrupt:
        console.print()
        print("Interrupted.", style="yellow")
        return 130

    except Exception:
        traceback.print_exc()
        return 1


async def _run_and_exit_oneshot(prompt_text: str, **kwargs: Any) -> None:
    """Run one-shot and hard-exit — mirrors hermes' _run_and_exit_oneshot()."""
    rc = await run_oneshot(prompt_text, **kwargs)
    _exit_after_oneshot(rc)


def _exit_after_oneshot(rc: int) -> None:
    """Exit one-shot mode — mirrors hermes' _exit_after_oneshot()."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(rc)


def main(prompt_text: str, **kwargs: Any) -> None:
    """Sync entry point for one-shot mode — mirrors hermes_cli/oneshot.py:main()."""
    asyncio.run(_run_and_exit_oneshot(prompt_text, **kwargs))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
