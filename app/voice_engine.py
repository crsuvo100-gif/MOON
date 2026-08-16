"""voice_engine.py -- MOON's premium voice engine (female + voice cloning).

ADDITIVE: sits beside app.voice.Voice (espeak fallback) and upgrades MOON to a
high-quality, cloneable female voice. Pluggable backends, tried in order:

  1. xtts   -- Coqui XTTS-v2 (local). The canonical open voice-CLONING model:
             speaks in any reference voice from a ~6s sample, with female
             speakers. Runs on a capable host (GPU/strong CPU).
  2. openai -- OpenAI TTS (cloud). 'nova' / 'shimmer' are the alluring, clearly
             FEMALE voices -- used as the "sexiest female AI assistant" option
             when an OPENAI_API_KEY is configured.
  3. espeak -- app.voice.Voice female (always available, CPU-only fallback).

Voice cloning: Moon can capture/hear a user's voice (a WAV sample) and thereafter
speak USING that voice. Cloned voices are stored under voices/ and referenced by
name; XTTS uses the sample as the speaker embedding. On hosts without XTTS the
sample is still stored and the engine reports cloning as pending (so the UI is
honest about capability, never fake).

No secrets are logged; API keys come from settings (gitignored .env).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
VOICE_REGISTRY = VOICES_DIR / "registry.json"

# Premium female voices offered to the operator.
FEMALE_VOICES: dict[str, dict] = {
    "nova":      {"backend": "openai", "voice": "nova",    "desc": "Sultry, intimate female (OpenAI)"},
    "shimmer":   {"backend": "openai", "voice": "shimmer", "desc": "Soft, warm female (OpenAI)"},
    "aria":      {"backend": "xtts",   "voice": "female",  "desc": "Studio female (XTTS, local)"},
    "seductive": {"backend": "espeak", "voice": "seductive", "desc": "Intimate female (espeak + SoX)"},
    "default":   {"backend": "auto",   "voice": "auto",    "desc": "Best available female voice"},
}


class VoiceEngine:
    """Unified female TTS + voice cloning for MOON."""

    def __init__(self, settings=None) -> None:
        self._settings = settings
        self.current: str = "default"
        self.voices_dir = VOICES_DIR
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._cloned: dict[str, str] = self._load_registry()
        self._xtts = None
        self._openai_key = (getattr(settings, "openai_api_key", "") or "") if settings else ""

    # -- registry -----------------------------------------------------------
    def _load_registry(self) -> dict[str, str]:
        try:
            if VOICE_REGISTRY.exists():
                return {k: v for k, v in json.loads(VOICE_REGISTRY.read_text()).items()}
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice registry load failed: %s", exc)
        return {}

    def _save_registry(self) -> None:
        try:
            VOICE_REGISTRY.write_text(json.dumps(self._cloned, indent=2))
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice registry save failed: %s", exc)

    # -- capability detection ----------------------------------------------
    def backend_status(self) -> dict[str, Any]:
        xtts = bool(shutil.which("xtts_available") or self._xtts_available())
        return {
            "xtts": xtts,
            "openai": bool(self._openai_key),
            "espeak": bool(shutil.which("espeak-ng") or shutil.which("espeak")),
            "current": self.current,
            "cloned_voices": list(self._cloned.keys()),
        }

    def _xtts_available(self) -> bool:
        if self._xtts is not None:
            return self._xtts is not False
        try:
            import TTS  # type: ignore  # noqa: F401
            self._xtts = True
        except Exception:  # noqa: BLE001
            self._xtts = False
        return bool(self._xtts)

    # -- voice selection ----------------------------------------------------
    def list_voices(self) -> list[dict]:
        out = [{"name": k, "desc": v["desc"], "backend": v["backend"],
                "cloned": False} for k, v in FEMALE_VOICES.items()]
        for name in self._cloned:
            out.append({"name": name, "desc": "Cloned voice (heard from user)",
                        "backend": "xtts", "cloned": True})
        return out

    def set_voice(self, name: str) -> str:
        if name in FEMALE_VOICES or name in self._cloned:
            self.current = name
            return f"Voice set to '{name}'."
        return f"Unknown voice '{name}'. Use 'voice list'."

    # -- cloning -------------------------------------------------------------
    def clone_voice(self, name: str, sample_b64: str) -> str:
        """Store a user's voice sample and register it as a clone (XTTS uses it)."""
        if not name:
            return "clone requires a name."
        try:
            raw = base64.b64decode(sample_b64)
        except Exception:
            return "Invalid audio sample (expected base64 WAV)."
        path = self.voices_dir / f"{name}.wav"
        path.write_bytes(raw)
        self._cloned[name] = str(path)
        self._save_registry()
        if self._xtts_available():
            return (f"Cloned voice '{name}' from your sample. Moon can now speak "
                    f"using your voice (set 'voice set {name}').")
        return (f"Stored voice sample for '{name}'. Cloning activates with XTTS-v2 "
                f"installed (pip install TTS); sample saved at {path}.")

    # -- TTS ----------------------------------------------------------------
    async def speak(self, text: str) -> str | None:
        """Return a path to a WAV file with MOON's female voice, or None."""
        if not text:
            return None
        try:
            spec = FEMALE_VOICES.get(self.current, FEMALE_VOICES["default"])
            backend = spec["backend"]
            if backend == "auto":
                backend = self._best_backend()
            if backend == "xtts" and self._xtts_available():
                return self._xtts_speak(text, spec, self._cloned.get(self.current))
            if backend == "openai" and self._openai_key:
                return self._openai_speak(text, spec["voice"])
            return await self._espeak_speak(text, self.current)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice engine speak failed: %s", exc)
            try:
                return await self._espeak_speak(text, "seductive")
            except Exception:  # noqa: BLE001
                return None

    def _best_backend(self) -> str:
        if self._xtts_available():
            return "xtts"
        if self._openai_key:
            return "openai"
        return "espeak"

    # -- backends ------------------------------------------------------------
    def _xtts_speak(self, text: str, spec: dict, clone_sample: str | None) -> str | None:
        from TTS.api import TTS  # type: ignore

        model = "tts_models/multilingual/multi-dataset/xtts_v2"
        tts = TTS(model).to("cpu") if hasattr(Tts := TTS, "to") else TTS(model)  # cpu-safe
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        speaker = clone_sample or None
        speaker_wav = clone_sample  # XTTS accepts a reference wav for cloning
        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            speaker="female" if not clone_sample else None,  # type: ignore[arg-type]
            language="en",
            file_path=out,
        )
        return out

    def _openai_speak(self, text: str, voice: str) -> str | None:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=self._openai_key)
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with client.audio.speech.with_streaming_response.create(
            model="tts-1", voice=voice, input=text
        ) as resp:
            resp.stream_to_file(out)
        return out

    async def _espeak_speak(self, text: str, preset: str) -> str | None:
        from app.voice import Voice

        v = Voice(preset=preset if preset in ("seductive", "warm", "crystal", "default") else "default")
        return await v.speak(text)
