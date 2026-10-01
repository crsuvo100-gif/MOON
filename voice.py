"""voice.py -- MOON's female voice (TTS) + speech-to-text (STT).

Female voice design
-------------------
MOON speaks with a warm, clearly-FEMALE voice. The pipeline:
  1. espeak-ng synthesises with an explicit *female* voice (f5, raised pitch,
     softer intonation) -- espeak's voice 5 is its female preset.
  2. SoX reshapes the timbre into an attractive, intimate tone:
       - `pitch`   : raises overall pitch (female register)
       - `bass -f`  : trims hiss / adds body so it is not thin/robotic
       - `treble`   : gentle air/presence
       - `chorus`   : subtle stereo width for a fuller, "studio" feel
       - `reverb`   : a touch of room so it is not dry
  The exact numbers are tuned in FemaleVoicePresets and can be overridden.

Speech-to-text (dictation)
--------------------------
Optional `vosk` offline model. If unavailable, dictation simply reports it is
disabled -- the rest of MOON keeps working.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


# Aesthetic "world's most attractive female voice" tuning.
# pitch_hz  : SoX pitch shift in cents-ish Hz (positive = higher = more feminine)
# formant   : `bass` gain (dB) for body/roundness
# air       : `treble` gain (dB) for breathy presence
FEMALE_PRESETS: dict[str, dict] = {
    "seductive":  {"pitch_hz": 280, "formant": 2.5, "air": 2.0, "chorus": True,  "reverb": 0.12},
    "warm":       {"pitch_hz": 220, "formant": 3.0, "air": 1.2, "chorus": True,  "reverb": 0.08},
    "crystal":    {"pitch_hz": 340, "formant": 1.5, "air": 3.0, "chorus": False, "reverb": 0.04},
    "default":    {"pitch_hz": 260, "formant": 2.5, "air": 1.8, "chorus": True,  "reverb": 0.10},
}


class Voice:
    """Female TTS + optional STT wrapper for MOON."""

    def __init__(
        self,
        *,
        preset: str = "default",
        espeak_voice: str = "en+f5",
        rate: int = 175,
    ) -> None:
        self.preset_name = preset if preset in FEMALE_PRESETS else "default"
        self.preset = FEMALE_PRESETS[self.preset_name]
        self.espeak_voice = espeak_voice  # f5 == female voice in espeak
        self.rate = rate
        self._espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        self._sox = shutil.which("sox")
        self._vosk_model: str | None = None
        # locate an optional vosk model directory
        for cand in (os.environ.get("VOSK_MODEL_DIR"), ""):
            if cand and Path(cand).exists():
                self._vosk_model = cand
                break

    # -- TTS -----------------------------------------------------------------
    async def speak(self, text: str) -> str | None:
        """Return a path to a WAV file with MOON's female voice, or None."""
        if not text:
            return None
        if not self._espeak:
            logger.warning("no TTS engine (espeak) available; cannot speak")
            return None
        try:
            return await self._female_speak(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice speak failed: %s", exc)
            return None

    async def _female_speak(self, text: str) -> str:
        fd, raw = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        # 1) espeak with explicit FEMALE voice + raised pitch + softer intonation
        subprocess.run(
            [
                self._espeak,
                "-v", self.espeak_voice,
                "-s", str(self.rate),
                "-p", "60",          # higher pitch baseline (espeak 0-99)
                "-a", "110",         # amplitude
                "-w", raw,
                text,
            ],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        if not self._sox:
            return raw
        # 2) SoX timbre chain -> warm, intimate, attractive female tone
        out_fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(out_fd)
        p = self.preset
        sox_cmd = [self._sox, raw, out]
        sox_cmd += ["pitch", str(p["pitch_hz"])]
        sox_cmd += ["bass", str(p["formant"])]
        sox_cmd += ["treble", str(p["air"])]
        sox_cmd += ["highpass", "80"]          # remove rumble
        sox_cmd += ["compand", "0.02,0.2", "-60,-60,-30,-15,-10,-6,0,0", "-6", "0", "0.1"]
        if p["chorus"]:
            sox_cmd += ["chorus", "0.7", "0.9", "55", "0.4", "0.25", "2.0", "-s"]
        if p["reverb"]:
            sox_cmd += ["reverb", "-w", str(p["reverb"])]
        sox_cmd += ["gain", "-1"]              # gentle normalisation
        subprocess.run(sox_cmd, check=False, stderr=subprocess.DEVNULL)
        return out

    def available(self) -> bool:
        return bool(self._espeak)

    # -- STT (dictation) -----------------------------------------------------
    def stt_available(self) -> bool:
        if not self._vosk_model:
            return False
        try:
            import vosk  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    def transcribe_mic(self, *, seconds: int = 5, device: int | None = None) -> str | None:
        """Capture `seconds` of microphone audio and return the transcript.

        Requires vosk + a model dir set via VOSK_MODEL_DIR. Returns None if
        dictation is unavailable.
        """
        if not self.stt_available():
            logger.info("dictation unavailable (install vosk + VOSK_MODEL_DIR)")
            return None
        try:
            import wave

            import pyaudio  # type: ignore
            import vosk
        except Exception as exc:  # noqa: BLE001
            logger.warning("dictation deps missing: %s", exc)
            return None
        # capture
        rec_fd, rec = tempfile.mkstemp(suffix=".wav")
        os.close(rec_fd)
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                             input=True, frames_per_buffer=8000,
                             input_device_index=device)
            frames = []
            for _ in range(int(16000 / 8000 * seconds)):
                frames.append(stream.read(8000, exception_on_overflow=False))
            stream.stop_stream(); stream.close(); pa.terminate()
            with wave.open(rec, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
            recog = vosk.KaldiRecognizer(vosk.Model(self._vosk_model), 16000)
            with wave.open(rec, "rb") as wf:
                data = wf.readframes(wf.getnframes())
            recog.AcceptWaveFile(data)
            res = recog.Result()
            import json
            return json.loads(res).get("text", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("dictation failed: %s", exc)
            return None
