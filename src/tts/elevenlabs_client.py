"""
elevenlabs_client.py — ElevenLabs TTS with gTTS fallback
"""

import os
import io
from dotenv import load_dotenv

load_dotenv("config.env")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

FILLER_PHRASES = {
    "welcome":    "Welcome to Deep Care! Please say your date of birth to get started.",
    "processing": "Sure, let me check that for you.",
    "auth_fail":  "I couldn't find that date of birth. Please try again.",
    "error":      "I didn't catch that clearly. Could you repeat?",
    "transfer":   "Transferring you to a senior agent now. They have your full context.",
    "goodbye":    "Thank you for calling Deep Care. Have a wonderful day!"
}


def speak(text: str) -> bytes:
    """Convert text to speech. Returns mp3 bytes."""
    if ELEVENLABS_API_KEY:
        try:
            return _speak_elevenlabs(text)
        except Exception as e:
            print(f"[TTS] ElevenLabs failed ({e}), falling back to gTTS")
    return speak_gtts(text)


def _speak_elevenlabs(text: str) -> bytes:
    """Call ElevenLabs API, return mp3 bytes."""
    import httpx
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.content


def speak_gtts(text: str) -> bytes:
    """Fallback TTS using gTTS. Returns mp3 bytes."""
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        tts = gTTS(text=text, lang="en", slow=False)
        tts.write_to_fp(buf)
        return buf.getvalue()
    except Exception as e:
        print(f"[TTS] gTTS also failed: {e}")
        return b""
