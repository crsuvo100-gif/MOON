#!/usr/bin/env python3
"""Launch the MOON NEXUS bridge + futuristic UI (additive).

Serves the attached NEXUS frontend (web/nexus/futuristic/*) at
http://127.0.0.1:8787/ and runs the MOON_AGENT_BRIDGE/1 WebSocket server at
ws://127.0.0.1:8765/moon, wired to MOON's real Orchestrator brain.

This does NOT touch MOON's existing terminal interface on :8777.

Usage:
    python web/nexus/run_nexus_bridge.py
    python web/nexus/run_nexus_bridge.py --no-moon   # serve UI + terminal only
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import http.server
import logging
import socketserver
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("moon.nexus")

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "futuristic"

# Make MOON importable regardless of CWD (repo root = web/nexus -> ../..).
_REPO = HERE.parent.parent
import os
import sys

if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
os.chdir(_REPO)

# Bridge module (now importable after the path fix above).
from app.brain.nexus.bridge import (
    DEFAULT_HOST,
    DEFAULT_UI_PORT,
    DEFAULT_WS_PORT,
    NexusBridge,
)


def serve_ui(host: str, port: int) -> None:
    if not UI_DIR.exists():
        logger.error("NEXUS UI dir missing: %s (run from repo root)", UI_DIR)
        return
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(UI_DIR))
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        logger.info("MOON NEXUS UI: http://%s:%s/", host, port)
        httpd.serve_forever()


async def main(connect_moon: bool, ws_port: int = DEFAULT_WS_PORT, ui_port: int = DEFAULT_UI_PORT) -> None:
    orch = None
    if connect_moon:
        try:
            from app.brain.orchestrator import Orchestrator
            from app.config.env_guard import decontaminate_pythonpath
            from app.config.settings import get_settings

            decontaminate_pythonpath()
            settings = get_settings()
            # CPU-only host: keep thinking ON (better answers) but skip the
            # 3-way self-consistency vote so Ollama is never overloaded. The
            # streamed cognition stages stay real; only the redundant voting is
            # dropped. On a capable GPU host you can re-enable it.
            settings.enable_self_consistency = False
            orch = Orchestrator(settings)
            await orch.setup()
            logger.info("NEXUS connected to MOON's real brain (Orchestrator).")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not wire MOON brain (running UI+terminal only): %s", exc)
            orch = None

    bridge = NexusBridge(DEFAULT_HOST, ws_port, ui_port, orchestrator=orch)
    loop = asyncio.get_event_loop()
    # Run UI and the WebSocket bridge concurrently (neither returns).
    await asyncio.gather(
        loop.run_in_executor(None, serve_ui, DEFAULT_HOST, ui_port),
        bridge.run_forever(),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="MOON NEXUS bridge launcher (additive)")
    ap.add_argument("--no-moon", action="store_true", help="Serve UI + terminal without MOON brain")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT, help="WebSocket bridge port (default 8765)")
    ap.add_argument("--ui-port", type=int, default=DEFAULT_UI_PORT, help="UI HTTP port (default 8787)")
    args = ap.parse_args()
    try:
        asyncio.run(main(not args.no_moon, ws_port=args.ws_port, ui_port=args.ui_port))
    except KeyboardInterrupt:
        logger.info("MOON NEXUS bridge stopped.")
