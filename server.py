"""
server.py — Deep Care Voice Gateway (LangChain version)
No n8n. FastAPI + LangChain + Gemini 2.0 Flash.
"""
import os, uuid, base64
from dotenv import load_dotenv
load_dotenv("config.env")
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.stt.whisper_engine import transcribe_audio, load_model_at_startup
from src.tts.elevenlabs_client import speak
from src.auth.dob_auth import (
    extract_dob,
    lookup_customer,
    get_customer_context_string,
)
from src.db.db_handler import load_customer, save_session
from src.session.session_manager import (
    create_session,
    get_session,
    set_authenticated,
    append_turn,
    get_last_n_turns,
)
from src.session.summary_generator import generate_summary
from src.llm.chain import run_chain

app = FastAPI(title="Deep Care Voice Gateway")

@app.on_event("startup")
async def startup_event():
    print("[Server] Starting up — loading Whisper into RAM...")
    load_model_at_startup()
    print("[Server] All models ready. Accepting requests.")

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
    return {"status": "ok", "model": "gemini-2.5-flash-preview-04-17", "chain": "langchain"}


@app.post("/session/start")
async def session_start():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    audio = speak(
        "Welcome to Deep Care! Please say your date of birth to get started."
    )
    return JSONResponse(
        {
            "session_id": session_id,
            "audio_b64": base64.b64encode(audio).decode(),
        }
    )


@app.post("/send")
async def send(request: Request):

    # ── 1. Session ─────────────────────────────────────────────
    session_id = request.headers.get("x-session-id")
    if not session_id:
        session_id = str(uuid.uuid4())
        create_session(session_id)
    session = get_session(session_id)

    # ── 2. Whisper STT ─────────────────────────────────────────
    audio_bytes = await request.body()
    transcript, confidence = transcribe_audio(audio_bytes)

    if not transcript or confidence < 0.4:
        audio = speak("I didn't catch that. Could you repeat?")
        return _response(
            session_id, "", "I didn't catch that. Could you repeat?", audio
        )

    # ── 3. Auth gate ───────────────────────────────────────────
    if not session["authenticated"]:
        dob = extract_dob(transcript)
        if dob:
            customer = lookup_customer(dob)
            if customer:
                set_authenticated(session_id, customer, dob)
                reply = (
                    f"Welcome back, {customer['name']}! How can I help you today?"
                )
                append_turn(session_id, transcript, reply, "auth_success", "positive")
                audio = speak(reply)
                return _response(
                    session_id,
                    transcript,
                    reply,
                    audio,
                    summary=generate_summary(get_session(session_id)),
                )
            else:
                reply = "I couldn't find that date of birth. Please try again."
                audio = speak(reply)
                return _response(session_id, transcript, reply, audio)
        else:
            reply = "Please say your date of birth to verify your account."
            audio = speak(reply)
            return _response(session_id, transcript, reply, audio)

    # ── 4. Load customer context ───────────────────────────────
    customer_data = load_customer(session["customer_dob"])
    context_str = get_customer_context_string(customer_data)
    history_str = get_last_n_turns(session_id, n=6)

    # ── 5. Run LangChain ───────────────────────────────────────
    chain_result = run_chain(
        transcript=transcript,
        customer_dob=session["customer_dob"],
        customer_name=session["customer_name"],
        customer_context=context_str,
        history=history_str,
    )

    # ── 6. Handle escalation flag ──────────────────────────────
    if chain_result["intent"] == "escalate":
        session["escalated"] = True

    # ── 7. Append turn ─────────────────────────────────────────
    append_turn(
        session_id,
        transcript,
        chain_result["response"],
        chain_result["intent"],
        chain_result["sentiment"],
    )

    # ── 8. TTS ─────────────────────────────────────────────────
    audio_out = speak(chain_result["response"])

    # ── 9. Summary ─────────────────────────────────────────────
    summary = generate_summary(get_session(session_id), chain_result)

    return _response(
        session_id,
        transcript,
        chain_result["response"],
        audio_out,
        intent=chain_result["intent"],
        db_result=chain_result["db_result"],
        summary=summary,
    )


@app.post("/session/end")
async def session_end(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    session = get_session(session_id)

    if not session:
        return JSONResponse({"error": "session not found"}, status_code=404)

    summary = generate_summary(session)

    if session.get("customer_dob"):
        save_session(session["customer_dob"], summary)

    audio = speak("Thank you for calling Deep Care. Have a wonderful day!")

    return JSONResponse(
        {
            "summary": summary,
            "audio_b64": base64.b64encode(audio).decode(),
        }
    )


# ── HELPER ─────────────────────────────────────────────────
def _response(
    session_id,
    transcript,
    response_text,
    audio_bytes,
    intent=None,
    db_result=None,
    summary=None,
):
    return JSONResponse(
        {
            "session_id": session_id,
            "transcript": transcript,
            "response": response_text,
            "intent": intent,
            "audio_b64": base64.b64encode(audio_bytes).decode(),
            "db_result": db_result or {},
            "summary": summary,
        }
    )

