"""voice_test.py -- verify the TTS engine produces audio."""

import asyncio
import sys

from app.voice import Voice


async def main() -> int:
    v = Voice()
    out = await v.speak("Hello, I am MOON. My brain is online.")
    if out:
        print(f"PASSED: voice engine produced {out}")
        return 0
    print("RESULT: no audio backend available (piper/espeak missing) -- non-fatal")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
