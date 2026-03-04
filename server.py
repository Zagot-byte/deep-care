"""
server.py — Deep Care Voice Gateway
Whisper loads in background thread — server accepts requests immediately.
Multilingual: language selected after auth, locked for entire session.
"""
import os, uuid, base64, asyncio, threading
from dotenv import load_dotenv
load_dotenv("config.env")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.stt.whisper_engine import transcribe_audio, load_model_at_startup
from src.tts.elevenlabs_client import (
    speak, detect_language_choice, language_selection_prompt
)
from src.auth.dob_auth import extract_dob, lookup_customer, get_customer_context_string
from src.db.db_handler import load_customer, save_session
from src.session.session_manager import (
    create_session, get_session, set_authenticated,
    append_turn, get_last_n_turns,
)
from src.session.summary_generator import generate_summary
from src.llm.chain import run_chain

app = FastAPI(title="Deep Care Voice Gateway")

# ── Whisper readiness flag ──────────────────────────────────
_whisper_ready = threading.Event()

def _load_whisper_bg():
    try:
        print("[STT] Loading Whisper in background thread...")
        load_model_at_startup()
        _whisper_ready.set()
        print("[STT] Whisper ready — all requests can now use STT.")
    except Exception as e:
        print(f"[STT] ERROR loading Whisper: {e}")
        _whisper_ready.set()

@app.on_event("startup")
async def startup_event():
    print("[Server] Starting — Whisper loading in background...")
    t = threading.Thread(target=_load_whisper_bg, daemon=True)
    t.start()
    print("[Server] Server ready. Whisper still loading in background.")

@app.on_event("shutdown")
async def shutdown_event():
    print("[Server] Shutting down — Whisper will be released from RAM.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model":  "gemini-2.5-flash-preview-04-17",
        "stt":    "ready" if _whisper_ready.is_set() else "loading",
        "chain":  "direct-api",
    }

@app.post("/session/start")
async def session_start():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    audio = speak(
        "Welcome to Deep Care! Please say your date of birth to get started.",
        lang="en"
    )
    return JSONResponse({
        "session_id": session_id,
        "audio_b64":  base64.b64encode(audio).decode(),
        "stt_ready":  _whisper_ready.is_set(),
    })

@app.post("/send")
async def send(request: Request):

    # ── 1. Session ─────────────────────────────────────────
    session_id = request.headers.get("x-session-id")
    if not session_id:
        session_id = str(uuid.uuid4())
        create_session(session_id)
    session = get_session(session_id)
    if session is None:
        create_session(session_id)
        session = get_session(session_id)
    lang    = session.get("language", "en")

    # ── 2. Whisper readiness check ─────────────────────────
    if not _whisper_ready.is_set():
        print("[STT] Whisper still loading — waiting up to 60s...")
        for _ in range(120):
            if _whisper_ready.is_set():
                break
            await asyncio.sleep(0.5)
        else:
            audio = speak("Our speech system is still warming up. Please try again in a moment.", lang="en")
            return _response(session_id, "", "Still warming up, please wait.", audio)

    # ── 3. Whisper STT ─────────────────────────────────────
    audio_bytes = await request.body()
    transcript, confidence = transcribe_audio(audio_bytes)

    if not transcript or confidence < 0.4:
        audio = speak("I didn't catch that. Could you repeat?", lang=lang)
        return _response(session_id, "", "I didn't catch that. Could you repeat?", audio)

    # ── 4. Auth gate ────────────────────────────────────────
    if not session["authenticated"]:
        dob = extract_dob(transcript)
        if dob:
            customer = lookup_customer(dob)
            if customer:
                set_authenticated(session_id, customer, dob)
                reply = f"Welcome back, {customer['name']}! " + language_selection_prompt()
                append_turn(session_id, transcript, reply, "auth_success", "positive")
                audio = speak(reply, lang="en")
                return _response(session_id, transcript, reply, audio,
                                 summary=generate_summary(get_session(session_id)))
            else:
                reply = "I couldn't find that date of birth. Please try again."
                audio = speak(reply, lang="en")
                return _response(session_id, transcript, reply, audio)
        else:
            reply = "Please say your date of birth to verify your account."
            audio = speak(reply, lang="en")
            return _response(session_id, transcript, reply, audio)

    # ── 5. Language selection gate ──────────────────────────
    if not session.get("language_confirmed"):
        lang_code = detect_language_choice(transcript)
        if lang_code:
            session["language"]           = lang_code
            session["language_confirmed"] = True
            lang = lang_code
            confirmations = {
                "en": "Perfect! I'll continue in English. How can I help you today?",
                "ta": "சரி! நான் தமிழில் தொடர்வேன். உங்களுக்கு எவ்வாறு உதவலாம்?",
                "hi": "बिल्कुल! मैं हिंदी में जारी रखूंगा। आज मैं आपकी कैसे मदद कर सकता हूं?",
                "te": "సరే! నేను తెలుగులో కొనసాగిస్తాను. నేను మీకు ఎలా సహాయం చేయగలను?",
                "kn": "ಸರಿ! ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮುಂದುವರಿಯುತ್ತೇನೆ. ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
                "bn": "ঠিক আছে! আমি বাংলায় চালিয়ে যাব। আজ আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
                "ml": "ശരി! ഞാൻ മലയാളത്തിൽ തുടരും. ഇന്ന് ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കും?",
            }
            reply = confirmations.get(lang_code, confirmations["en"])
            audio = speak(reply, lang=lang_code)
            return _response(session_id, transcript, reply, audio, lang=lang_code)
        else:
            reply = "I didn't catch your language preference. Please say English, Tamil, Hindi, Telugu, or Kannada."
            audio = speak(reply, lang="en")
            return _response(session_id, transcript, reply, audio)

    # ── 6. Load customer context ────────────────────────────
    customer_data = load_customer(session["customer_dob"])
    context_str   = get_customer_context_string(customer_data)
    history_str   = get_last_n_turns(session_id, n=6)

    # ── 7. Run Gemini chain ─────────────────────────────────
    chain_result = run_chain(
        transcript       = transcript,
        customer_dob     = session["customer_dob"],
        customer_name    = session["customer_name"],
        customer_context = context_str,
        history          = history_str,
        lang             = lang,
    )

    # ── 8. Escalation flag ──────────────────────────────────
    if chain_result["intent"] == "escalate":
        session["escalated"] = True

    # ── 9. Auto-escalation on 2x negative sentiment ─────────
    session_data = get_session(session_id)
    trajectory   = session_data.get("sentiment_trajectory", [])
    if (len(trajectory) >= 2
            and all(t == "negative" for t in trajectory[-2:])
            and not session_data.get("escalated")):
        session["escalated"] = True
        chain_result["response"] += " I can see you're frustrated — let me connect you with a human agent right away."

    # ── 10. Append turn ─────────────────────────────────────
    append_turn(
        session_id, transcript,
        chain_result["response"],
        chain_result["intent"],
        chain_result["sentiment"],
    )

    # ── 11. TTS in session language ─────────────────────────
    audio_out = speak(chain_result["response"], lang=lang)

    # ── 12. Summary ─────────────────────────────────────────
    summary = generate_summary(get_session(session_id), chain_result)

    return _response(
        session_id, transcript,
        chain_result["response"], audio_out,
        intent    = chain_result["intent"],
        db_result = chain_result["db_result"],
        summary   = summary,
        lang      = lang,
    )

@app.post("/session/end")
async def session_end(request: Request):
    body       = await request.json()
    session_id = body.get("session_id")
    session    = get_session(session_id)

    if not session:
        return JSONResponse({"error": "session not found"}, status_code=404)

    summary = generate_summary(session)

    if session.get("customer_dob"):
        save_session(session["customer_dob"], summary)

    lang  = session.get("language", "en")
    audio = speak("Thank you for calling Deep Care. Have a wonderful day!", lang=lang)

    return JSONResponse({
        "summary":   summary,
        "audio_b64": base64.b64encode(audio).decode(),
    })

def _response(
    session_id, transcript, response_text, audio_bytes,
    intent=None, db_result=None, summary=None, lang="en",
):
    return JSONResponse({
        "session_id":  session_id,
        "transcript":  transcript,
        "response":    response_text,
        "intent":      intent,
        "audio_b64":   base64.b64encode(audio_bytes).decode(),
        "db_result":   db_result or {},
        "summary":     summary,
        "stt_ready":   _whisper_ready.is_set(),
        "language":    lang,
    })
