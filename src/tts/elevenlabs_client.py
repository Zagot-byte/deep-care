"""
elevenlabs_client.py — Multilingual TTS
English: ElevenLabs (premium) → gTTS fallback
Indian languages: gTTS native (ta, hi, te, kn, bn, ml, gu, mr, pa)
"""

import os
import io
from dotenv import load_dotenv

load_dotenv("config.env")

ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

# gTTS language codes for Indian languages
GTTS_LANG_MAP = {
    "en": "en",
    "ta": "ta",   # Tamil
    "hi": "hi",   # Hindi
    "te": "te",   # Telugu
    "kn": "kn",   # Kannada
    "bn": "bn",   # Bengali
    "ml": "ml",   # Malayalam
    "gu": "gu",   # Gujarati
    "mr": "mr",   # Marathi
    "pa": "pa",   # Punjabi
}

FILLER_PHRASES = {
    "welcome":    "Welcome to Deep Care! Please say your date of birth to get started.",
    "processing": "Sure, let me check that for you.",
    "auth_fail":  "I couldn't find that date of birth. Please try again.",
    "error":      "I didn't catch that clearly. Could you repeat?",
    "transfer":   "Transferring you to a senior agent now. They have your full context.",
    "goodbye":    "Thank you for calling Deep Care. Have a wonderful day!"
}


def speak(text: str, lang: str = "en") -> bytes:
    """
    Convert text to speech. Returns mp3 bytes.
    
    For English: tries ElevenLabs first, falls back to gTTS
    For Indian languages: uses gTTS directly (best support)
    """
    if lang == "en" and ELEVENLABS_API_KEY:
        try:
            return _speak_elevenlabs(text)
        except Exception as e:
            print(f"[TTS] ElevenLabs failed ({e}), falling back to gTTS")

    return _speak_gtts(text, lang)


def _speak_elevenlabs(text: str) -> bytes:
    """ElevenLabs API — English only, premium voice."""
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


def _speak_gtts(text: str, lang: str = "en") -> bytes:
    """
    gTTS — supports all Indian languages natively.
    lang: ISO 639-1 code (en, ta, hi, te, kn, bn, ml, gu, mr, pa)
    """
    try:
        from gtts import gTTS
        gtts_lang = GTTS_LANG_MAP.get(lang, "en")
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=gtts_lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        print(f"[TTS] gTTS spoke in lang='{gtts_lang}' ({len(buf.getvalue())} bytes)")
        return buf.getvalue()
    except Exception as e:
        print(f"[TTS] gTTS failed: {e}")
        return b""


# ── Language detection helper ───────────────────────────────

SUPPORTED_LANGUAGES = {
    "english": "en",
    "tamil":   "ta",  "தமிழ்": "ta",
    "hindi":   "hi",  "हिंदी": "hi",
    "telugu":  "te",  "తెలుగు": "te",
    "kannada": "kn",  "ಕನ್ನಡ": "kn",
    "bengali": "bn",  "বাংলা": "bn",
    "malayalam": "ml","മലയാളം": "ml",
    "gujarati": "gu", "ગુજરાતી": "gu",
    "marathi": "mr",  "मराठी": "mr",
    "punjabi": "pa",  "ਪੰਜਾਬੀ": "pa",
}

def detect_language_choice(transcript: str) -> str | None:
    """
    Called after auth — customer says which language they want.
    Returns ISO code or None if not recognized.
    """
    text = transcript.lower().strip()
    for keyword, code in SUPPORTED_LANGUAGES.items():
        if keyword.lower() in text:
            return code
    return None


def language_selection_prompt() -> str:
    """The prompt bot speaks to ask for language choice."""
    return (
        "Great! Which language would you like to continue in? "
        "You can say English, Tamil, Hindi, Telugu, or Kannada."
    )
