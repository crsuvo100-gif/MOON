"""voice_engine.py -- MOON's premium voice engine (female + voice cloning).

ADDITIVE: sits beside app.voice.Voice (espeak fallback) and upgrades MOON to a
high-quality, cloneable female voice. Pluggable backends, tried in order:

  1. kokoro -- Kokoro-ONNX (local, CPU). Natural, clearly FEMALE voices
             (af_heart / af_bella / af_sarah) with no cloud dependency and no
             heavy torch install. The default premium offline voice.
  2. f5     -- F5-TTS (local, zero-shot voice CLONING from a reference WAV).
             Works on Python 3.13 (torch 2.x wheels). This is the cloning
             engine used on modern Python; replaces XTTS-v2 which needs <3.12.
  3. xtts   -- Coqui XTTS-v2 (local). The canonical open voice-CLONING model:
             speaks in any reference voice from a ~6s sample. Requires Python
             <3.12 (Coqui constraint); optional, kept for older hosts.
  4. openai -- OpenAI TTS (cloud). 'nova' / 'shimmer' are the alluring, clearly
             FEMALE voices -- used when an OPENAI_API_KEY with quota is set.
  5. espeak -- app.voice.Voice female (always available, CPU-only fallback).

Voice cloning: Moon can capture/hear a user's voice (a WAV sample) and thereafter
speak USING that voice. Cloned voices are stored under voices/ and referenced by
name; F5-TTS / XTTS use the sample as the speaker embedding. On hosts without a
cloning engine the sample is still stored and the engine reports cloning as
pending (so the UI is honest about capability, never fake).

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

# Kokoro model/voices cache (downloaded on first use).
_KOKORO_DIR = Path(os.path.expanduser("~/.cache/kokoro-onnx"))
_KOKORO_MODEL = _KOKORO_DIR / "kokoro-v1.0.onnx"
_KOKORO_VOICES = _KOKORO_DIR / "voices-v1.0.bin"
# Built-in natural female Kokoro voices (most attractive first).
KOKORO_FEMALE_VOICES = ["af_heart", "af_bella", "af_sarah", "af_nicole", "af_emma"]

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
VOICE_REGISTRY = VOICES_DIR / "registry.json"

# Premium female voices offered to the operator.
FEMALE_VOICES: dict[str, dict] = {
    "nova":      {"backend": "openai", "voice": "nova",    "desc": "Sultry, intimate female (OpenAI)"},
    "shimmer":   {"backend": "openai", "voice": "shimmer", "desc": "Soft, warm female (OpenAI)"},
    "aria":      {"backend": "kokoro", "voice": "af_heart", "desc": "Natural studio female (Kokoro, local)"},
    "bella":     {"backend": "kokoro", "voice": "af_bella",  "desc": "Warm female (Kokoro, local)"},
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
        self._kokoro = None
        self._f5 = None
        self._openai_key = (getattr(settings, "openai_api_key", "") or "") if settings else ""
        # Session breaker for cloud backends that are configured but dead
        # (e.g. quota-exhausted OpenAI key). Avoids a network round-trip on
        # every single speak() call; set True once a hard failure is seen.
        self._openai_dead: bool = False
        self._xtts_dead: bool = False
        self._f5_dead: bool = False
        self._kokoro_dead: bool = False

    def _mark_openai_dead(self) -> None:
        self._openai_dead = True

    def _mark_xtts_dead(self) -> None:
        self._xtts_dead = True

    def _mark_f5_dead(self) -> None:
        self._f5_dead = True

    def _mark_kokoro_dead(self) -> None:
        self._kokoro_dead = True

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
        return {
            "kokoro": self._kokoro_available(),
            "f5": self._f5_available(),
            "xtts": self._xtts_available(),
            "openai": bool(self._openai_key) and not self._openai_dead,
            "espeak": bool(shutil.which("espeak-ng") or shutil.which("espeak")),
            "current": self.current,
            "cloned_voices": list(self._cloned.keys()),
            # True when a real zero-shot cloning engine is present.
            "cloning_ready": self._f5_available() or self._xtts_available(),
        }

    def _f5_available(self) -> bool:
        if self._f5 is not None:
            return self._f5 is not False
        try:
            import f5_tts  # type: ignore  # noqa: F401
            self._f5 = True
        except Exception:  # noqa: BLE001
            self._f5 = False
        return bool(self._f5)

    def _kokoro_available(self) -> bool:
        if self._kokoro is not None:
            return self._kokoro is not False
        try:
            import kokoro_onnx  # type: ignore  # noqa: F401
            # Model weights must be present (downloaded on first speak()).
            self._kokoro = _KOKORO_MODEL.exists() and _KOKORO_VOICES.exists()
        except Exception:  # noqa: BLE001
            self._kokoro = False
        return bool(self._kokoro)

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
    def clone_voice(self, name: str, sample_b64: str, transcript: str = "") -> str:
        """Store a user's voice sample and register it as a clone.

        F5-TTS / XTTS use the sample as the speaker embedding for zero-shot
        cloning. `transcript` is the text spoken in the reference sample
        (improves F5-TTS clone fidelity; optional -- F5 tolerates an empty
        transcript, XTTS does not require it).
        """
        if not name:
            return "clone requires a name."
        try:
            raw = base64.b64decode(sample_b64)
        except Exception:
            return "Invalid audio sample (expected base64 WAV)."
        path = self.voices_dir / f"{name}.wav"
        path.write_bytes(raw)
        self._cloned[name] = str(path)
        # Persist the optional transcript so F5-TTS cloning is high-fidelity.
        if transcript:
            (self.voices_dir / f"{name}.txt").write_text(transcript, encoding="utf-8")
        self._save_registry()
        if self._f5_available() or self._xtts_available():
            engine = "F5-TTS" if self._f5_available() else "XTTS-v2"
            return (f"Cloned voice '{name}' from your sample using {engine}. "
                    f"Moon can now speak using your voice (set 'voice set {name}').")
        return (f"Stored voice sample for '{name}'. Cloning activates with a "
                f"cloning engine installed (pip install f5-tts on Python 3.13+, "
                f"or TTS on <3.12); sample saved at {path}.")

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
            # A selected CLONED voice always routes through a cloning engine.
            if self.current in self._cloned:
                clone_sample = self._cloned[self.current]
                if self._f5_available() and not self._f5_dead:
                    return self._f5_speak(text, clone_sample)
                if self._xtts_available() and not self._xtts_dead:
                    return self._xtts_speak(text, spec, clone_sample)
                # No cloning engine: fall back to the premium female voice.
                logger.warning("clone requested but no cloning engine available")
                if self._kokoro_available():
                    return self._kokoro_speak(text, KOKORO_FEMALE_VOICES[0])
                return await self._espeak_speak(text, "seductive")
            if backend == "kokoro" and self._kokoro_available() and not self._kokoro_dead:
                return self._kokoro_speak(text, spec["voice"])
            if backend == "f5" and self._f5_available() and not self._f5_dead:
                # f5 as a base voice needs a reference sample; without a clone we
                # cannot synthesize, so fall through to kokoro/espeak.
                if self._kokoro_available():
                    return self._kokoro_speak(text, spec["voice"])
                return await self._espeak_speak(text, self.current)
            if backend == "xtts" and self._xtts_available() and not self._xtts_dead:
                return self._xtts_speak(text, spec, self._cloned.get(self.current))
            if backend == "openai" and self._openai_key and not self._openai_dead:
                return self._openai_speak(text, spec["voice"])
            return await self._espeak_speak(text, self.current)
        except Exception as exc:  # noqa: BLE001
            logger.warning("voice engine speak failed: %s", exc)
            # Hard-fail signatures (quota/auth) -> circuit-break so we don't
            # keep hitting a dead cloud backend on every reply.
            msg = str(exc).lower()
            if "429" in msg or "quota" in msg or "401" in msg or "403" in msg:
                if "openai" in msg or backend == "openai":
                    self._mark_openai_dead()
                if "xtts" in msg or backend == "xtts":
                    self._mark_xtts_dead()
                if "kokoro" in msg or backend == "kokoro":
                    self._mark_kokoro_dead()
                if "f5" in msg or backend == "f5":
                    self._mark_f5_dead()
            try:
                return await self._espeak_speak(text, "seductive")
            except Exception:  # noqa: BLE001
                return None

    def _best_backend(self) -> str:
        if self._kokoro_available():
            return "kokoro"
        if self._f5_available():
            return "f5"
        if self._xtts_available():
            return "xtts"
        if self._openai_key and not self._openai_dead:
            return "openai"
        return "espeak"

    # -- backends ------------------------------------------------------------
    def _kokoro_speak(self, text: str, voice: str) -> str | None:
        """Premium offline female voice via Kokoro-ONNX (CPU, no torch)."""
        from kokoro_onnx import Kokoro  # type: ignore

        if not _KOKORO_MODEL.exists() or not _KOKORO_VOICES.exists():
            _KOKORO_DIR.mkdir(parents=True, exist_ok=True)
            import urllib.request

            base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
            for url, path in ((base + "/kokoro-v1.0.onnx", _KOKORO_MODEL),
                              (base + "/voices-v1.0.bin", _KOKORO_VOICES)):
                if not path.exists():
                    urllib.request.urlretrieve(url, str(path))

        k = Kokoro(model_path=str(_KOKORO_MODEL),
                   voices_path=str(_KOKORO_VOICES))
        if voice not in KOKORO_FEMALE_VOICES:
            voice = KOKORO_FEMALE_VOICES[0]
        audio, sr = k.create(text, voice=voice, speed=1.0)
        import numpy as np

        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        from scipy.io import wavfile  # type: ignore

        wavfile.write(out, sr, np.array(audio))
        return out

    def _xtts_speak(self, text: str, spec: dict, clone_sample: str | None) -> str | None:
        from TTS.api import TTS  # type: ignore

        model = "tts_models/multilingual/multi-dataset/xtts_v2"
        # Load on CPU (CPU-only host). `.to("cpu")` is a method on the TTS
        # instance, not the class, so call it unconditionally after construct.
        tts = TTS(model).to("cpu")
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        speaker_wav = clone_sample  # XTTS accepts a reference wav for cloning
        tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            speaker="female" if not clone_sample else None,  # type: ignore[arg-type]
            language="en",
            file_path=out,
        )
        return out

    def _f5_speak(self, text: str, clone_sample: str) -> str | None:
        """Zero-shot voice cloning via F5-TTS (local, CPU, Python 3.13-safe).

        `clone_sample` is a reference WAV; F5-TTS reproduces that speaker's
        voice for `text`. An optional transcript of the reference sample
        (voices/<name>.txt) improves fidelity; F5 tolerates a missing one.
        """
        from f5_tts.api import F5TTS  # type: ignore

        # Optional reference transcript (same stem as the .wav sample).
        ref_text = ""
        txt_path = Path(clone_sample).with_suffix(".txt")
        if txt_path.exists():
            try:
                ref_text = txt_path.read_text(encoding="utf-8").strip()
            except Exception:  # noqa: BLE001
                ref_text = ""

        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tts = F5TTS(model="F5TTS_v1_Base", device="cpu")
        tts.infer(
            ref_audio=str(clone_sample),
            ref_text=ref_text,
            gen_text=text,
            file_path=out,
            seed=42,
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
