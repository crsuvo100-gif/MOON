"""
oneshot — non-interactive single LLM query.
"""
from __future__ import annotations

import asyncio
import sys

from app.config.settings import get_settings
from app.services.llm_service import LLMService, ChatMessage


async def run_oneshot(text: str, model: str | None = None,
                      agent: str | None = None) -> int:
    s = get_settings()
    m = model or s.model_name
    llm = LLMService(
        base_url=s.model_base_url,
        model_name=m,
        api_key="not-required" if "127.0.0.1" in s.model_base_url else "",
        timeout=s.model_timeout,
    )
    await llm.setup()
    result = await llm.complete([ChatMessage(role="user", content=text)])
    await llm.teardown()
    if result.content:
        print(result.content)
        return 0
    else:
        print("No response.", file=sys.stderr)
        return 1


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="moon oneshot")
    parser.add_argument("text", nargs=argparse.REMAINDER, help="message text")
    parser.add_argument("--model", help="model name")
    parser.add_argument("--agent", help="agent name")
    args = parser.parse_args()
    text = " ".join(args.text)
    sys.exit(asyncio.run(run_oneshot(text, args.model, args.agent)))


if __name__ == "__main__":
    main()
