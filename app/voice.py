"""voice.py -- TTS engine for MOON (moved from the old terminal package).

Uses Piper neural TTS if available, else falls back to espeak-ng (offline).
Requires the `sox` system binary for any pitch/voice transforms.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class Voice:
    """Lightweight TTS wrapper."""

    def __init__(self, *, voice: str = "en-us-amy-low", rate: int = 100, pitch: float = -300.0) -> None:
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self._piper = shutil.which("piper")
        self._espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        self._sox = shutil.which("sox")

    async def speak(self, text: str) -> str | None:
        """Return a path to a WAV file with the spoken text, or None."""
        if not text:
            return None
        try:
            if self._piper:
                return await self._piper_speak(text)
            if self._espeak:
                return await self._espeak_speak(text)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice speak failed: %s", exc)
            return None

    async def _espeak_speak(self, text: str) -> str:
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = [self._espeak, "-w", wav, "-s", str(self.rate), text]
        if self._sox:
            # apply a subtle tone through sox for a warmer voice
            cmd = [self._espeak, "-w", wav, "-s", str(self.rate), text]
            subprocess.run(cmd, check=False)
            td, out = tempfile.mkstemp(suffix=".wav")
            os.close(td)
            pitch_hz = int(self.pitch)
            subprocess.run(
                [self._sox, wav, out, "pitch", str(pitch_hz)], check=False, stderr=subprocess.DEVNULL
            )
            return out
        subprocess.run(cmd, check=False)
        return wav

    async def _piper_speak(self, text: str) -> str:
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        model = f"{self.voice}.onnx"
        if not Path(model).exists():
            # no model file; fall back to espeak
            if self._espeak:
                return await self._espeak_speak(text)
            return None
        subprocess.run([self._piper, "--model", model, "--output_file", wav], input=text.encode(), check=False)
        return wav
