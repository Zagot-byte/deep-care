"""
whisper_engine.py — Whisper STT wrapper
Loads ONCE at server startup, stays in RAM for all sessions.
Cleans up automatically when server shuts down.
"""
import os
import tempfile
import atexit
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


def load_model_at_startup():
    """
    Called once when server starts. Loads Whisper into RAM.
    All sessions share this single instance.
    """
    global _MODEL
    if _MODEL is not None:
        return  # already loaded

    if _USE_FASTER:
        print(f"[STT] Loading faster-whisper '{_MODEL_SIZE}' on CPU (int8)...")
        _MODEL = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
    else:
        print(f"[STT] Loading openai-whisper '{_MODEL_SIZE}' on CPU...")
        _MODEL = whisper.load_model(_MODEL_SIZE, device="cpu")

    print("[STT] Whisper model ready. Staying in RAM for all sessions.")

    # Register cleanup when Python process exits
    atexit.register(_unload_model)


def _unload_model():
    """Called automatically when server shuts down."""
    global _MODEL
    if _MODEL is not None:
        print("[STT] Server shutting down — unloading Whisper from RAM.")
        del _MODEL
        _MODEL = None


def transcribe_audio(audio_bytes: bytes) -> Tuple[str, float]:
    """
    Transcribe raw audio bytes.
    Uses the already-loaded model — never reloads between sessions.
    Returns (transcript_text, confidence_score 0.0-1.0)
    """
    global _MODEL

    # Safety net — should never happen if startup ran correctly
    if _MODEL is None:
        print("[STT] WARNING: Model not loaded at startup — loading now.")
        load_model_at_startup()

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        if _USE_FASTER:
            segments, info = _MODEL.transcribe(tmp_path, language="en", beam_size=5)
            segments = list(segments)
            text = " ".join(s.text.strip() for s in segments).strip()
            if segments:
                avg_logprob = sum(s.avg_logprob for s in segments) / len(segments)
                confidence = float(np.clip(np.exp(avg_logprob), 0.0, 1.0))
            else:
                confidence = 0.0
        else:
            result = _MODEL.transcribe(tmp_path, language="en", fp16=False)
            text = result.get("text", "").strip()
            segments = result.get("segments", [])
            if segments:
                avg_logprob = sum(s["avg_logprob"] for s in segments) / len(segments)
                confidence = float(np.clip(np.exp(avg_logprob), 0.0, 1.0))
            else:
                confidence = 0.5
    finally:
        os.unlink(tmp_path)

    return text, confidence
