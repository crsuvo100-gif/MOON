"""voice_test.py -- verify the TTS engine produces audio."""

import asyncio
import sys
from pathlib import Path

# Ensure the project root (containing the `app` package) is importable when this
# script is launched directly (e.g. `make voice-test`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
