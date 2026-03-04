"""
whisper_engine.py — Whisper STT wrapper
Loads model once at startup, stays in RAM (CPU only to preserve VRAM for Gemma)
"""

import io
import tempfile
import os
from typing import Tuple

import numpy as np

try:
    from faster_whisper import WhisperModel
    _USE_FASTER = True
except ImportError:
    import whisper
    _USE_FASTER = False

_MODEL = None
_MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")


def _load_model():
    global _MODEL
    if _MODEL is None:
        if _USE_FASTER:
            print(f"[STT] Loading faster-whisper '{_MODEL_SIZE}' on CPU (int8)...")
            _MODEL = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
        else:
            print(f"[STT] Loading openai-whisper '{_MODEL_SIZE}' on CPU...")
            _MODEL = whisper.load_model(_MODEL_SIZE, device="cpu")
        print("[STT] Whisper model ready.")
    return _MODEL


def transcribe_audio(audio_bytes: bytes) -> Tuple[str, float]:
    """
    Transcribe raw audio bytes.
    Returns (transcript_text, confidence_score 0.0-1.0)
    """
    model = _load_model()

    # Write to a temp file — Whisper needs a file path or numpy array
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        if _USE_FASTER:
            segments, info = model.transcribe(tmp_path, language="en", beam_size=5)
            segments = list(segments)
            text = " ".join(s.text.strip() for s in segments).strip()
            # faster-whisper gives per-segment avg_logprob; convert to 0-1
            if segments:
                avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
                # logprob is typically -2..0; map to 0-1
                confidence = float(np.clip(np.exp(avg_logprob), 0.0, 1.0))
            else:
                confidence = 0.0
        else:
            result = model.transcribe(tmp_path, language="en", fp16=False)
            text = result.get("text", "").strip()
            # openai-whisper doesn't give confidence directly; use segment avg_logprob
            segments = result.get("segments", [])
            if segments:
                avg_logprob = sum(s["avg_logprob"] for s in segments) / len(segments)
                confidence = float(np.clip(np.exp(avg_logprob), 0.0, 1.0))
            else:
                confidence = 0.5  # fallback
    finally:
        os.unlink(tmp_path)

    return text, confidence
