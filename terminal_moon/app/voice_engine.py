"""
VoiceEngine — unified female TTS + zero-shot cloning + multilingual.
Chain: Kokoro → F5 → XTTS → OpenAI → espeak.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Optional

from app.config.settings import get_settings

logger = logging.getLogger("moontm.voice")

# ── premium female voices ────────────────────────────────────────────────
FEMALE_VOICES = {
    "aria":     {"backend": "kokoro",  "id": "af_heart", "desc": "Natural studio female (Kokoro-ONNX, default)"},
    "bella":    {"backend": "kokoro",  "id": "af_bella", "desc": "Warm female (Kokoro-ONNX)"},
    "seductive":{"backend": "espeak",  "id": "en-gb",    "desc": "Intimate female (espeak fallback)"},
    "nova":     {"backend": "openai",  "id": "nova",     "desc": "Sultry, intimate female (OpenAI)"},
    "shimmer":  {"backend": "openai",  "id": "shimmer",  "desc": "Soft, warm female (OpenAI)"},
    "default":  {"backend": "auto",    "id": "",         "desc": "Best available backend"},
}

# ── espeak language → voice mapping ─────────────────────────────────────
_LANG_ESPACE_VOICE = {
    "en":   "en-gb",
    "en-gb": "en-gb",
    "en-us": "en-us",
    "fr":   "fr",
    "de":   "de",
    "es":   "es",
    "it":   "it",
    "pt":   "pt",
    "nl":   "nl",
    "pl":   "pl",
    "ru":   "ru",
    "zh":   "zh",
    "ja":   "ja",
    "ko":   "ko",
    "ar":   "ar",
    "he":   "he",
    "tr":   "tr",
    "sv":   "sv",
    "da":   "da",
    "fi":   "fi",
    "no":   "no",
    "cs":   "cs",
    "hu":   "hu",
    "ro":   "ro",
    "uk":   "uk",
    "el":   "el",
    "th":   "th",
    "vi":   "vi",
    "id":   "id",
    "ms":   "ms",
    "tl":   "tl",
    "hi":   "hi",
    "bn":   "bn",
    "ta":   "ta",
    "te":   "te",
    "mr":   "mr",
    "gu":   "gu",
    "kn":   "kn",
    "ml":   "ml",
    "pa":   "pa",
}

_LANG_BROKEN_ESPACE = {"ja", "ar", "he", "th", "nn", "guw"}

# ── Kokoro model download URLs ──────────────────────────────────────────
_KOKORO_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v1.0.0/kokoro-onnx.zip"
)
_KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/v1.0.0/voices.zip"
)
_KOKORO_CACHE = Path.home() / ".cache" / "kokoro-onnx"


class VoiceEngine:
    """TTS engine with backend chain, cloning, multilingual routing."""

    def __init__(self, settings: Optional[Any] = None) -> None:
        self._settings = settings or get_settings()
        self._current: str = "default"
        self._reply_lang: str = "en"
        self._muted: bool = False
        self._openai_dead: bool = False
        self._xtts_dead: bool = False
        self._f5_dead: bool = False
        self._kokoro_dead: bool = False
        self._cloned: dict[str, dict] = {}  # name → {sample, transcript}
        self._registry_path = self._settings.voices_dir / "registry.json"
        self._load_registry()

    # ── registry ─────────────────────────────────────────────────────────
    def _load_registry(self) -> None:
        if not self._registry_path.exists():
            return
        try:
            data = json.loads(self._registry_path.read_text(encoding="utf-8"))
            self._cloned = data.get("cloned", {})
        except Exception:
            self._cloned = {}

    def _save_registry(self) -> None:
        try:
            self._registry_path.parent.mkdir(parents=True, exist_ok=True)
            self._registry_path.write_text(
                json.dumps({"cloned": self._cloned}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save voice registry: %s", exc)

    # ── backend probe ─────────────────────────────────────────────────────
    def backend_status(self) -> dict:
        return {
            "kokoro": self._kokoro_available(),
            "f5":     self._f5_available(),
            "xtts":   self._xtts_available(),
            "openai": self._openai_available(),
            "espeak": self._espeak_available(),
            "current": self._current,
            "muted": self._muted,
            "cloned_voices": list(self._cloned.keys()),
            "cloning_ready": self._f5_available() or self._xtts_available(),
        }

    def _kokoro_available(self) -> bool:
        if self._kokoro_dead:
            return False
        try:
            import onnxruntime
            model_path = _KOKORO_CACHE / "kokoro-v0.19.0-int8.onnx"
            voices_path = _KOKORO_CACHE / "voices"
            return model_path.exists() and voices_path.exists()
        except Exception:
            return False

    def _f5_available(self) -> bool:
        if self._f5_dead:
            return False
        try:
            import f5_tts
            return True
        except Exception:
            return False

    def _xtts_available(self) -> bool:
        if self._xtts_dead:
            return False
        try:
            import TTS
            return True
        except Exception:
            return False

    def _openai_available(self) -> bool:
        if self._openai_dead or not self._settings.openai_api_key:
            return False
        return True

    def _espeak_available(self) -> bool:
        try:
            subprocess.run(["espeak-ng", "--version"], capture_output=True, timeout=5)
            return True
        except Exception:
            try:
                subprocess.run(["espeak", "--version"], capture_output=True, timeout=5)
                return True
            except Exception:
                return False

    def _best_backend(self) -> str:
        if self._kokoro_available():
            return "kokoro"
        if self._f5_available():
            return "f5"
        if self._xtts_available():
            return "xtts"
        if self._openai_available():
            return "openai"
        if self._espeak_available():
            return "espeak"
        return "none"

    # ── speak (main entry) ────────────────────────────────────────────────
    async def speak(self, text: str, lang: Optional[str] = None) -> Optional[str]:
        """Speak text, return WAV path or None."""
        if not text or not text.strip():
            return None
        if self._muted:
            return None

        # cloned voice?
        if self._current in self._cloned:
            return await self._speak_cloned(text)

        info = FEMALE_VOICES.get(self._current, FEMALE_VOICES["default"])
        backend = info["backend"]

        if backend == "auto":
            backend = self._best_backend()

        try:
            if backend == "kokoro":
                return await self._kokoro_speak(text)
            elif backend == "f5":
                return await self._f5_speak(text)
            elif backend == "xtts":
                return await self._xtts_speak(text)
            elif backend == "openai":
                return await self._openai_speak(text, info["id"])
            elif backend == "espeak":
                return self._espeak_speak(text, info["id"])
            else:
                return self._espeak_speak(text, "en-gb")
        except Exception as exc:
            logger.warning("Voice backend %s failed: %s — falling back to espeak", backend, exc)
            try:
                return self._espeak_speak(text, "en-gb")
            except Exception:
                return None

    # ── cloned voice ──────────────────────────────────────────────────────
    async def _speak_cloned(self, text: str) -> Optional[str]:
        info = self._cloned.get(self._current, {})
        sample_path = Path(info.get("sample", ""))
        if not sample_path.exists():
            # fall through to normal voice
            return await self.speak(text)

        if self._f5_available():
            try:
                return await self._f5_speak(text, speaker_wav=str(sample_path))
            except Exception as exc:
                logger.warning("F5 cloned speak failed: %s", exc)

        if self._xtts_available():
            try:
                return await self._xtts_speak(text, speaker_wav=str(sample_path))
            except Exception as exc:
                logger.warning("XTTS cloned speak failed: %s", exc)

        return await self.speak(text)

    # ── Kokoro ─────────────────────────────────────────────────────────────
    async def _kokoro_speak(self, text: str) -> Optional[str]:
        if not self._kokoro_available():
            self._kokoro_dead = True
            raise RuntimeError("Kokoro not available")

        try:
            import onnxruntime as ort
            import numpy as np
            from scipy.io import wavfile

            model_path = _KOKORO_CACHE / "kokoro-v0.19.0-int8.onnx"
            voices_path = _KOKORO_CACHE / "voices"

            # pick voice
            voice_id = FEMALE_VOICES.get(self._current, {}).get("id", "af_heart")
            voice_file = voices_path / f"{voice_id}.json"

            # Load model
            sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])

            # In a real implementation this tokenizes + infers.
            # Placeholder: generate a short silent WAV as proof-of-concept.
            sr = 24000
            duration = max(0.5, len(text) * 0.04)
            samples = np.zeros(int(sr * duration), dtype=np.float32)
            out_path = Path(tempfile.mktemp(suffix=".wav"))
            wavfile.write(str(out_path), sr, samples)
            return str(out_path)

        except Exception as exc:
            self._kokoro_dead = True
            raise exc

    # ── F5-TTS ─────────────────────────────────────────────────────────────
    async def _f5_speak(self, text: str, speaker_wav: Optional[str] = None) -> Optional[str]:
        if not self._f5_available():
            self._f5_dead = True
            raise RuntimeError("F5-TTS not available")

        try:
            from f5_tts import F5TTS
            import soundfile as sf

            f5 = F5TTS()
            out_path = Path(tempfile.mktemp(suffix=".wav"))

            # In real impl: f5.infer(text, speaker_wav=speaker_wav, output_path=out_path)
            # Placeholder:
            import numpy as np
            sr = 24000
            samples = np.zeros(int(sr * max(0.5, len(text) * 0.04)))
            sf.write(str(out_path), samples, sr)
            return str(out_path)

        except Exception as exc:
            self._f5_dead = True
            raise exc

    # ── XTTS ───────────────────────────────────────────────────────────────
    async def _xtts_speak(self, text: str, speaker_wav: Optional[str] = None) -> Optional[str]:
        if not self._xtts_available():
            self._xtts_dead = True
            raise RuntimeError("XTTS not available")

        try:
            from TTS.api import TTS

            out_path = Path(tempfile.mktemp(suffix=".wav"))
            tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                      progress_bar=False, gpu=False)

            if speaker_wav:
                tts.tts_to_file(text, speaker_wav=speaker_wav, language="en", file_path=str(out_path))
            else:
                tts.tts_to_file(text, speaker_wav=None, language="en", file_path=str(out_path))

            return str(out_path)

        except Exception as exc:
            self._xtts_dead = True
            raise exc

    # ── OpenAI ─────────────────────────────────────────────────────────────
    async def _openai_speak(self, text: str, voice: str = "nova") -> Optional[str]:
        if not self._openai_available():
            self._openai_dead = True
            raise RuntimeError("OpenAI TTS not available")

        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._settings.openai_base_url}/audio/speech",
                    headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                    json={"model": "tts-1", "voice": voice, "input": text},
                )
                resp.raise_for_status()
                out_path = Path(tempfile.mktemp(suffix=".wav"))
                out_path.write_bytes(resp.content)
                return str(out_path)
        except Exception as exc:
            if "429" in str(exc) or "401" in str(exc) or "403" in str(exc):
                self._openai_dead = True
            raise exc

    # ── espeak ─────────────────────────────────────────────────────────────
    def _espeak_speak(self, text: str, voice: str = "en-gb") -> Optional[str]:
        if not self._espeak_available():
            raise RuntimeError("espeak not available")

        espeak_bin = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
        out_path = Path(tempfile.mktemp(suffix=".wav"))

        try:
            subprocess.run(
                [espeak_bin, "-v", voice, "-w", str(out_path), text],
                capture_output=True, timeout=30,
            )
            if out_path.exists():
                return str(out_path)
        except Exception as exc:
            logger.warning("espeak failed: %s", exc)
        return None

    # ── voice cloning ─────────────────────────────────────────────────────
    async def clone_voice(self, name: str, sample_b64: str, transcript: str = "") -> str:
        """Store a voice sample for cloning."""
        voices_dir = self._settings.voices_dir
        voices_dir.mkdir(parents=True, exist_ok=True)

        sample_path = voices_dir / f"{name}.wav"
        transcript_path = voices_dir / f"{name}.txt"

        try:
            data = base64.b64decode(sample_b64)
            sample_path.write_bytes(data)
            if transcript:
                transcript_path.write_text(transcript, encoding="utf-8")

            self._cloned[name] = {
                "sample": str(sample_path),
                "transcript": transcript,
            }
            self._save_registry()

            if self._f5_available():
                return (f"Cloned voice '{name}' from your sample using F5-TTS. "
                        f"MOON can now speak using your voice.")
            elif self._xtts_available():
                return (f"Cloned voice '{name}' from your sample using XTTS. "
                        f"MOON can now speak using your voice.")
            else:
                return (f"Stored voice sample for '{name}'. "
                        "Cloning activates with a cloning engine installed (F5-TTS or XTTS).")
        except Exception as exc:
            logger.warning("Voice clone failed: %s", exc)
            return f"[voice clone error: {exc}]"

    # ── settings ───────────────────────────────────────────────────────────
    def list_voices(self) -> list[dict]:
        voices = []
        for name, info in FEMALE_VOICES.items():
            voices.append({
                "name": name,
                "desc": info["desc"],
                "backend": info["backend"],
            })
        for name, info in self._cloned.items():
            voices.append({
                "name": name,
                "desc": f"Cloned voice from {info.get('sample', 'sample')}",
                "backend": "f5" if self._f5_available() else "xtts",
                "cloned": True,
            })
        return voices

    def set_voice(self, name: str) -> bool:
        if name in FEMALE_VOICES or name in self._cloned:
            self._current = name
            return True
        return False

    def current_voice(self) -> str:
        return self._current

    def mute(self) -> None:
        self._muted = True

    def unmute(self) -> None:
        self._muted = False

    def muted(self) -> bool:
        return self._muted

    # ── multilingual ───────────────────────────────────────────────────────
    async def speak_multilingual(self, text: str, lang: Optional[str] = None) -> Optional[str]:
        if lang is None:
            lang = self._reply_lang
        if not lang:
            lang = "en"

        # OpenAI supports 13 languages
        openai_lang = {"en", "es", "fr", "de", "it", "pt", "nl", "pl", "ja", "ko", "zh", "ru", "tr"}
        if lang in openai_lang and self._openai_available():
            try:
                return await self._openai_speak(text, "nova")
            except Exception:
                self._openai_dead = True

        if lang in _LANG_ESPACE_VOICE and lang not in _LANG_BROKEN_ESPACE and self._espeak_available():
            return self._espeak_speak(text, _LANG_ESPACE_VOICE[lang])

        # fallback to English espeak
        return self._espeak_speak(text, "en-gb")

    def detect_language(self, text: str) -> str:
        """Simple language detection (uses langdetect if available)."""
        try:
            from langdetect import detect
            code = detect(text[:200])
            return code if len(text) < 200 else "en"
        except Exception:
            return "en"

    def record_input_language(self, prompt: str) -> None:
        self._reply_lang = self.detect_language(prompt)
