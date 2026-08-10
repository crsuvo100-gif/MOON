#!/usr/bin/env python3
"""voice_loop.py -- MOON's voice companion.

Listens (microphone dictation via vosk, or typed text), sends to MOON over
WebSocket, and speaks MOON's reply in her FEMALE voice.

Usage:
    python scripts/voice_loop.py                 # typed mode + female TTS
    python scripts/voice_loop.py --mic           # microphone dictation mode
    python scripts/voice_loop.py --preset seductive --url ws://127.0.0.1:8777/ws

Requires MOON running (make serve). Female voice needs espeak + sox (both
already present on this host). Dictation needs vosk + VOSK_MODEL_DIR.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice import Voice


async def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8777/ws")
    ap.add_argument("--preset", default="default", choices=["default", "seductive", "warm", "crystal"])
    ap.add_argument("--mic", action="store_true", help="use microphone dictation (needs vosk)")
    ap.add_argument("--unlock", default="MOON love you 3000")
    args = ap.parse_args()

    voice = Voice(preset=args.preset)
    if not voice.available():
        print("[voice] WARNING: espeak not found -- replies will not be spoken.")

    import websockets  # local import; only needed when actually looping

    print(f"[voice] MOON female voice ready (preset={args.preset}). Connecting to {args.url} ...")
    async with websockets.connect(args.url) as ws:
        # unlock once
        await ws.send(json.dumps({"text": args.unlock}))
        async for m in ws:
            d = json.loads(m)
            if d.get("type") == "text":
                print("[moon]", d["text"][:80])
                break

        def get_input() -> str | None:
            if args.mic:
                print("[you] (listening...)")
                return voice.transcribe_mic(seconds=5)
            try:
                return input("[you] ").strip()
            except (EOFError, KeyboardInterrupt):
                return None

        print("[voice] Ready. Type to talk to MOON (Ctrl-C to exit).")
        while True:
            try:
                user = get_input()
            except KeyboardInterrupt:
                break
            if not user:
                if args.mic:
                    continue
                break
            await ws.send(json.dumps({"text": user}))
            reply = ""
            async for m in ws:
                d = json.loads(m)
                t = d.get("type")
                if t == "text" and d.get("text"):
                    reply = d["text"]
                    break
                if t == "audio":
                    # backend may stream audio; we generate our own female voice
                    continue
            print("[moon]", reply)
            wav = await voice.speak(reply)
            if wav:
                os.system(f"play -q {wav} 2>/dev/null || aplay {wav} 2>/dev/null || true")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        print("\n[voice] bye.")
