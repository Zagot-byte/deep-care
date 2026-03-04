# DEEP CARE — FULL IMPLEMENTATION PROMPT
# Paste this into any model to generate the complete codebase

---

You are an expert Python/FastAPI engineer building "Deep Care" — a Voice-based
AI Gateway for enterprise customer service. Build this completely and correctly.
Quality doesn't matter as much as working end-to-end flow.

---

## PROJECT STRUCTURE

```
deep-care/
├── config.env
├── server.py                   ← main FastAPI app
├── mock_data.json              ← customer database (provided below)
├── requirements.txt
├── run.sh
└── static/
    └── index.html              ← frontend (already built, do not touch)
└── src/
    ├── auth/
    │   └── dob_auth.py         ← DOB extraction + customer lookup
    ├── stt/
    │   └── whisper_engine.py   ← already built, transcribe_audio(bytes) → (text, confidence)
    ├── tts/
    │   └── elevenlabs_client.py ← ElevenLabs TTS → returns audio bytes
    ├── db/
    │   └── db_handler.py       ← all DB read/write operations
    └── session/
        ├── session_manager.py  ← in-memory session store
        └── summary_generator.py ← builds handoff summary card
```

---

## PIPELINE FLOW

```
Browser sends audio blob → POST /send (FastAPI)
    ↓
FastAPI → Whisper STT → transcript text
    ↓
FastAPI → POST transcript + session_id + customer_context → n8n webhook
    ↓
n8n → Intent Parser → Google Gemini LLM → returns JSON:
    {
      "response": "Natural language reply",
      "intent": "order_status",
      "action": "READ orders",
      "params": { "order_id": "ORD-4521" },
      "sentiment": "neutral",
      "customer_name": "Arjun",
      "customer_id": "DCID-4521",
      "key_points": ["checked order ORD-4521", "status: delivered"],
      "suggested_action": "No follow-up needed"
    }
    ↓
FastAPI → db_handler executes the action against mock_data.json
    ↓
FastAPI → ElevenLabs TTS → converts response text → audio bytes
    ↓
FastAPI → returns JSON to browser:
    {
      "audio_b64": "base64 encoded mp3",
      "transcript": "what user said",
      "response": "what bot said",
      "summary": { ...full summary card object... }
    }
```

---

## FILE 1: config.env

```
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

N8N_WEBHOOK_URL=http://localhost:5678/webhook/voice_message

WHISPER_MODEL=small
DB_PATH=./mock_data.json
```

---

## FILE 2: requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
python-dotenv==1.0.1
httpx==0.27.0
faster-whisper==1.0.1
numpy==1.26.4
aiofiles==23.2.1
python-dateutil==2.9.0
elevenlabs==1.2.2
```

---

## FILE 3: src/auth/dob_auth.py

Build these functions:

### extract_dob(transcript: str) -> str | None
- Input: "my birthday is March 15 1999"
- Output: "15-03-1999" (DD-MM-YYYY format always)
- Handle ALL these formats:
  - "March 15 1999" / "15th March 1999" / "March 15th, 1999"
  - "15/03/1999" / "15-03-1999"
  - "1999 march 15"
- Use dateutil.parser for robust parsing
- Return None if no date found

### lookup_customer(dob: str) -> dict | None
- Load mock_data.json
- Return customers[dob] if exists, else None

### get_customer_context_string(customer: dict) -> str
- Returns a string summary of customer data for injection into n8n/LLM:
  ```
  Customer: Arjun Kumar (DCID-4521)
  Orders: ORD-4521 (Laptop Stand - Delivered), ORD-4522 (Wireless Mouse - Out for Delivery)
  Bills: March 2024 - Rs.2400 due on 2024-03-20 (unpaid)
  Complaints: CMP-001 (Billing overcharge - open)
  ```

---

## FILE 4: src/tts/elevenlabs_client.py

### speak(text: str) -> bytes
- Call ElevenLabs API
- Voice ID from config.env
- Model: eleven_monolingual_v1
- Returns raw mp3 bytes
- On API error → fall back to gTTS

### speak_gtts(text: str) -> bytes
- Fallback using gTTS
- Returns mp3 bytes via BytesIO

### FILLER_PHRASES dict (pre-cache these at module load):
```python
FILLER_PHRASES = {
    "welcome":    "Welcome to Deep Care! Please say your date of birth to get started.",
    "processing": "Sure, let me check that for you.",
    "auth_fail":  "I couldn't find that date of birth. Please try again.",
    "error":      "I didn't catch that clearly. Could you repeat?",
    "transfer":   "Transferring you to a senior agent now. They have your full context.",
    "goodbye":    "Thank you for calling Deep Care. Have a wonderful day!"
}
```

---

## FILE 5: src/db/db_handler.py

Load mock_data.json once at module level.

Build ALL these functions (use customer_dob as key):

### READ operations (return data directly):
```python
get_order_status(customer_dob: str, order_id: str = None) -> dict
    # Returns latest order or specific order by id
    # {"order_id": "ORD-4521", "item": "Laptop Stand", "status": "Delivered", ...}

get_order_tracking(customer_dob: str, order_id: str) -> dict
    # Returns tracking number + status

get_current_bill(customer_dob: str) -> dict
    # Returns latest unpaid bill

get_payment_history(customer_dob: str) -> list
    # Returns bills[0].history

get_complaint_status(customer_dob: str, complaint_id: str = None) -> dict
    # Returns latest complaint or specific one
```

### WRITE operations (return ticket id):
```python
create_complaint(customer_dob: str, issue: str) -> dict
    # Appends new complaint to complaints[]
    # complaint_id = "CMP-" + random 3 digit number
    # Returns {"complaint_id": "CMP-xxx", "status": "created"}

escalate_complaint(customer_dob: str, complaint_id: str) -> dict
    # Sets complaints[x].escalated = True
    # Returns {"escalated": True, "complaint_id": "CMP-xxx"}

save_session(customer_dob: str, session_data: dict) -> None
    # Appends to customers[dob].session_history[]
```

### IMPORTANT: After every write, save mock_data.json back to disk atomically.

---

## FILE 6: src/session/session_manager.py

In-memory dict store keyed by session_id.

```python
SESSION_STORE = {}  # global

def create_session(session_id: str) -> dict:
    # Creates and stores:
    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "authenticated": False,
        "customer_dob": None,
        "customer_name": None,
        "customer_id": None,
        "start_time": datetime.now().isoformat(),
        "turns": [],          # list of {user, bot, intent, sentiment}
        "intents_seen": [],   # deduplicated list
        "sentiment_trajectory": [],
        "escalated": False
    }
    return SESSION_STORE[session_id]

def get_session(session_id: str) -> dict | None:
    return SESSION_STORE.get(session_id)

def set_authenticated(session_id: str, customer: dict, dob: str) -> None:
    s = SESSION_STORE[session_id]
    s["authenticated"] = True
    s["customer_dob"]  = dob
    s["customer_name"] = customer["name"]
    s["customer_id"]   = customer["customer_id"]

def append_turn(session_id: str, user: str, bot: str, intent: str, sentiment: str) -> None:
    s = SESSION_STORE[session_id]
    s["turns"].append({
        "turn": len(s["turns"]) + 1,
        "user": user,
        "bot": bot,
        "intent": intent,
        "sentiment": sentiment,
        "timestamp": datetime.now().isoformat()
    })
    if intent and intent not in s["intents_seen"]:
        s["intents_seen"].append(intent)
    s["sentiment_trajectory"].append(sentiment)

def get_last_n_turns(session_id: str, n: int = 6) -> str:
    # Returns last n turns as formatted string for LLM context
    s = SESSION_STORE.get(session_id, {})
    turns = s.get("turns", [])[-n:]
    return "\n".join([f"User: {t['user']}\nBot: {t['bot']}" for t in turns])
```

---

## FILE 7: src/session/summary_generator.py

```python
def generate_summary(session: dict, n8n_data: dict = None) -> dict:
    """
    Builds the agent handoff summary card.
    Merges session data with any summary fields n8n returned.
    """

    # Duration
    start = datetime.fromisoformat(session["start_time"])
    duration_secs = int((datetime.now() - start).total_seconds())
    duration_str = f"{duration_secs // 60}m {duration_secs % 60}s"

    # Sentiment — take worst seen
    trajectory = session.get("sentiment_trajectory", ["neutral"])
    if "negative" in trajectory:
        final_sentiment = "negative"
    elif "positive" in trajectory:
        final_sentiment = "positive"
    else:
        final_sentiment = "neutral"

    # Key points — from n8n or auto-generated from turns
    key_points = n8n_data.get("key_points") if n8n_data else None
    if not key_points:
        key_points = [t["bot"][:80] for t in session["turns"][-4:] if t.get("bot")]

    # Suggested action — from n8n or auto-generated
    suggested = n8n_data.get("suggested_action") if n8n_data else None
    if not suggested:
        if "negative" in trajectory or session.get("escalated"):
            suggested = "Customer showed frustration — proactive follow-up recommended within 24 hours."
        elif "complaint" in session.get("intents_seen", []):
            suggested = "Review complaint ticket and ensure resolution within SLA."
        else:
            suggested = "No immediate follow-up needed. Review logs if customer contacts again."

    return {
        "name":             session.get("customer_name", "Unknown"),
        "customer_id":      session.get("customer_id", "—"),
        "dob":              session.get("customer_dob", "—"),
        "duration":         duration_str,
        "time":             datetime.now().strftime("%H:%M:%S"),
        "sentiment":        final_sentiment,
        "intents":          session.get("intents_seen", []),
        "summary":          n8n_data.get("summary_text") if n8n_data else f"Customer contacted support with {len(session.get('intents_seen', []))} query type(s) across {len(session.get('turns', []))} turns.",
        "key_points":       key_points,
        "suggested_action": suggested,
        "escalated":        session.get("escalated", False)
    }
```

---

## FILE 8: server.py — FULL REBUILD

```python
"""
server.py — Deep Care Voice Gateway
FastAPI handles: STT (Whisper) + DB operations + TTS (ElevenLabs)
n8n handles: Intent parsing + LLM (Google Gemini)
"""

import os, uuid, base64, json
import httpx
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv("config.env")

from src.stt.whisper_engine      import transcribe_audio
from src.tts.elevenlabs_client   import speak
from src.auth.dob_auth           import extract_dob, lookup_customer, get_customer_context_string
from src.db.db_handler           import (get_order_status, get_current_bill,
                                          get_payment_history, get_complaint_status,
                                          create_complaint, escalate_complaint, save_session)
from src.session.session_manager  import (create_session, get_session,
                                           set_authenticated, append_turn, get_last_n_turns)
from src.session.summary_generator import generate_summary

N8N_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/voice_message")

app = FastAPI(title="Deep Care Voice Gateway")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "n8n": N8N_URL}


@app.post("/session/start")
async def session_start():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    # Return welcome audio
    welcome_audio = speak("Welcome to Deep Care! Please say your date of birth to get started.")
    return JSONResponse({
        "session_id": session_id,
        "audio_b64": base64.b64encode(welcome_audio).decode()
    })


@app.post("/send")
async def send(request: Request):
    # ── 1. Get session_id from header (or create new) ──────────
    session_id = request.headers.get("x-session-id")
    if not session_id:
        session_id = str(uuid.uuid4())
        create_session(session_id)

    session = get_session(session_id)

    # ── 2. Whisper STT ─────────────────────────────────────────
    audio_bytes = await request.body()
    transcript, confidence = transcribe_audio(audio_bytes)

    if confidence < 0.4 or not transcript:
        audio = speak("I didn't catch that clearly. Could you repeat?")
        return JSONResponse({
            "session_id": session_id,
            "transcript": "",
            "response": "I didn't catch that clearly. Could you repeat?",
            "audio_b64": base64.b64encode(audio).decode(),
            "summary": None
        })

    # ── 3. AUTH: if not authenticated, try DOB extraction ──────
    if not session["authenticated"]:
        dob = extract_dob(transcript)
        if dob:
            customer = lookup_customer(dob)
            if customer:
                set_authenticated(session_id, customer, dob)
                reply = f"Welcome back, {customer['name']}! How can I help you today?"
                append_turn(session_id, transcript, reply, "auth_success", "positive")
                audio = speak(reply)
                return JSONResponse({
                    "session_id": session_id,
                    "transcript": transcript,
                    "response": reply,
                    "audio_b64": base64.b64encode(audio).decode(),
                    "summary": generate_summary(get_session(session_id))
                })
            else:
                reply = "I couldn't find that date of birth. Please try again."
                audio = speak(reply)
                return JSONResponse({
                    "session_id": session_id,
                    "transcript": transcript,
                    "response": reply,
                    "audio_b64": base64.b64encode(audio).decode(),
                    "summary": None
                })
        else:
            reply = "Please say your date of birth to verify your account."
            audio = speak(reply)
            return JSONResponse({
                "session_id": session_id,
                "transcript": transcript,
                "response": reply,
                "audio_b64": base64.b64encode(audio).decode(),
                "summary": None
            })

    # ── 4. Build context for n8n ────────────────────────────────
    from src.db.db_handler import load_customer
    customer_data = load_customer(session["customer_dob"])
    context_str   = get_customer_context_string(customer_data)
    history_str   = get_last_n_turns(session_id)

    # ── 5. Send to n8n ──────────────────────────────────────────
    n8n_payload = {
        "transcript":        transcript,
        "session_id":        session_id,
        "customer_context":  context_str,
        "conversation_history": history_str,
        "customer_name":     session["customer_name"]
    }

    n8n_data = {}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(N8N_URL, json=n8n_payload)
            n8n_data = resp.json()
    except Exception as e:
        print(f"[n8n error] {e}")
        n8n_data = {
            "response": "I'm having trouble processing that right now. Could you try again?",
            "intent": "error",
            "sentiment": "neutral"
        }

    # ── 6. Execute DB action if n8n specified one ───────────────
    intent    = n8n_data.get("intent", "unknown")
    action    = n8n_data.get("action", None)
    params    = n8n_data.get("params", {})
    dob       = session["customer_dob"]
    db_result = {}

    if action == "READ orders":
        db_result = get_order_status(dob, params.get("order_id"))
    elif action == "READ bills":
        db_result = get_current_bill(dob)
    elif action == "READ payment_history":
        db_result = get_payment_history(dob)
    elif action == "READ complaints":
        db_result = get_complaint_status(dob)
    elif action == "WRITE complaints.create":
        db_result = create_complaint(dob, params.get("issue", transcript))
    elif action == "WRITE complaints.escalate":
        db_result = escalate_complaint(dob, params.get("complaint_id"))
        session["escalated"] = True

    # ── 7. Get response text ────────────────────────────────────
    bot_response = n8n_data.get("response", "I'm here to help. What else can I do for you?")

    # ── 8. Append turn to session ───────────────────────────────
    sentiment = n8n_data.get("sentiment", "neutral")
    append_turn(session_id, transcript, bot_response, intent, sentiment)

    # ── 9. ElevenLabs TTS ───────────────────────────────────────
    audio_bytes_out = speak(bot_response)

    # ── 10. Generate summary card ───────────────────────────────
    summary = generate_summary(get_session(session_id), n8n_data)

    # ── 11. Return to browser ───────────────────────────────────
    return JSONResponse({
        "session_id": session_id,
        "transcript": transcript,
        "response":   bot_response,
        "intent":     intent,
        "audio_b64":  base64.b64encode(audio_bytes_out).decode(),
        "db_result":  db_result,
        "summary":    summary
    })


@app.post("/session/end")
async def session_end(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    session = get_session(session_id)
    if not session:
        return JSONResponse({"error": "session not found"}, status_code=404)

    summary = generate_summary(session)

    # Save session to DB if authenticated
    if session.get("customer_dob"):
        save_session(session["customer_dob"], summary)

    farewell_audio = speak("Thank you for calling Deep Care. Have a wonderful day!")

    return JSONResponse({
        "summary":   summary,
        "audio_b64": base64.b64encode(farewell_audio).decode()
    })
```

---

## FILE 9: run.sh

```bash
#!/bin/bash
echo "Starting Deep Care Voice Gateway..."
source .env/bin/activate 2>/dev/null || true
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

---

## n8n WEBHOOK — WHAT IT RECEIVES AND MUST RETURN

### Input (from FastAPI POST):
```json
{
  "transcript": "where is my order",
  "session_id": "uuid",
  "customer_context": "Customer: Arjun Kumar (DCID-4521)\nOrders: ORD-4521...",
  "conversation_history": "User: hi\nBot: welcome back arjun",
  "customer_name": "Arjun Kumar"
}
```

### Output (n8n MUST return this JSON):
```json
{
  "response": "Your order ORD-4521 for the Laptop Stand was delivered on March 1st.",
  "intent": "order_status",
  "action": "READ orders",
  "params": { "order_id": "ORD-4521" },
  "sentiment": "neutral",
  "key_points": ["Customer checked order ORD-4521", "Status: Delivered"],
  "suggested_action": "No follow-up needed.",
  "summary_text": "Customer enquired about order status."
}
```

### Intent → Action mapping n8n should output:
```
order_status       → action: "READ orders"
order_tracking     → action: "READ orders"
current_bill       → action: "READ bills"
payment_history    → action: "READ payment_history"
complaint_status   → action: "READ complaints"
lodge_complaint    → action: "WRITE complaints.create"
escalate           → action: "WRITE complaints.escalate"
general            → action: null
goodbye            → action: null
```

---

## ALSO ADD TO db_handler.py:

```python
def load_customer(dob: str) -> dict | None:
    db = _load_db()
    return db["customers"].get(dob)
```

---

## mock_data.json IS PROVIDED SEPARATELY. Path: ./mock_data.json

---

## IMPORTANT NOTES:
1. whisper_engine.py is already built — do NOT rewrite it
2. index.html is already built — do NOT rewrite it
3. Focus on server.py, db_handler.py, auth, session, tts, summary
4. server.py returns audio as base64 in JSON — browser decodes and plays
5. All DB writes must save mock_data.json back to disk
6. Never crash — wrap everything in try/except with fallback responses
