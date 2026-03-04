# DEEP CARE — LANGCHAIN UPGRADE PROMPT
# Replace n8n entirely with LangChain + Gemini 2.0 Flash
# Target latency: < 2 seconds end to end

---

## WHAT CHANGED FROM n8n VERSION

```
REMOVED:  n8n, Ollama, Gemma 2B, all webhook calls
ADDED:    LangChain, Google Gemini 2.0 Flash, Tool calling
KEPT:     Whisper STT, ElevenLabs TTS, FastAPI, mock_data.json,
          session_manager.py, summary_generator.py, dob_auth.py,
          db_handler.py, index.html
```

## NEW PIPELINE

```
Audio → Whisper (~0.8s)
           ↓
     LangChain Chain:
       Step 1: Classify intent (Gemini, ~0.3s)
       Step 2: Execute DB tool (Python, ~0.01s)
       Step 3: Generate response (Gemini, ~0.3s)
           ↓
     ElevenLabs TTS (~0.8s)
           ↓
     Return JSON to browser
     TOTAL: ~2.2s
```

---

## NEW FILES TO BUILD

### 1. src/llm/chain.py  ← THE MAIN NEW FILE
### 2. server.py         ← UPDATED (remove n8n, add chain)
### 3. config.env        ← UPDATED (add Google API key)
### 4. requirements.txt  ← UPDATED (add langchain deps)

---

## FILE 1: config.env (full)

```
# Google Gemini
GOOGLE_API_KEY=your_google_api_key_here

# ElevenLabs
ELEVENLABS_API_KEY=your_elevenlabs_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Whisper
WHISPER_MODEL=small

# DB
DB_PATH=./mock_data.json
```

---

## FILE 2: requirements.txt (full)

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

# LangChain
langchain==0.2.6
langchain-google-genai==1.0.6
langchain-core==0.2.10
google-generativeai==0.7.2
```

---

## FILE 3: src/llm/chain.py  ← BUILD THIS COMPLETELY

```python
"""
chain.py — LangChain fixed pipeline
Gemini 2.0 Flash handles intent classification + response generation
Python tools handle all DB operations
No n8n. No webhooks. One straight chain.
"""

import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv("config.env")

# ── MODEL ─────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_tokens=300,
)

# ── OUTPUT SCHEMA ──────────────────────────────────────────
class IntentOutput(BaseModel):
    intent: str = Field(description="One of the 10 intents below")
    params: dict = Field(description="Extracted params like order_id, complaint text")
    sentiment: str = Field(description="positive, neutral, or negative")

class ResponseOutput(BaseModel):
    response: str = Field(description="Natural language reply under 2 sentences")
    key_points: list = Field(description="1-3 key points from this interaction")
    suggested_action: str = Field(description="What the human agent should do next")
    summary_text: str = Field(description="One sentence summary of this turn")

# ── STEP 1: INTENT CLASSIFIER CHAIN ───────────────────────
INTENT_SYSTEM = """You are an intent classifier for a voice customer service system.
Given a customer transcript, return JSON with intent, params, and sentiment.

INTENTS (pick exactly one):
- order_status        → customer asking about order / delivery
- order_tracking      → customer asking for tracking number
- current_bill        → customer asking about bill amount or due date
- payment_history     → customer asking about past payments
- complaint_status    → customer asking about existing complaint
- lodge_complaint     → customer reporting a new problem or issue
- escalate            → customer wants human agent or supervisor
- goodbye             → customer ending the call
- confirm_yes         → customer saying yes to confirm an action
- general             → anything else

PARAMS to extract:
- order_id: if mentioned (e.g. "ORD-4521")
- complaint_id: if mentioned (e.g. "CMP-001")
- issue: for lodge_complaint — the complaint text

SENTIMENT:
- negative: frustrated, angry, problem, wrong, terrible
- positive: thanks, great, happy, resolved
- neutral: everything else

Return ONLY valid JSON. No markdown. No explanation."""

INTENT_HUMAN = """Customer said: "{transcript}"
Conversation so far: {history}

Return JSON only."""

intent_prompt = ChatPromptTemplate.from_messages([
    ("system", INTENT_SYSTEM),
    ("human", INTENT_HUMAN)
])

intent_chain = intent_prompt | llm | JsonOutputParser()

# ── STEP 2: DB TOOL EXECUTOR ───────────────────────────────
# Import all DB handlers
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.db.db_handler import (
    get_order_status,
    get_order_tracking,
    get_current_bill,
    get_payment_history,
    get_complaint_status,
    create_complaint,
    escalate_complaint,
)

def execute_db_tool(intent: str, params: dict, customer_dob: str) -> dict:
    """
    Executes the right DB operation based on intent.
    Returns dict with db_result and action_taken.
    """
    try:
        if intent == "order_status":
            result = get_order_status(customer_dob, params.get("order_id"))
            return {"db_result": result, "action": "READ orders"}

        elif intent == "order_tracking":
            result = get_order_tracking(customer_dob, params.get("order_id"))
            return {"db_result": result, "action": "READ orders.tracking"}

        elif intent == "current_bill":
            result = get_current_bill(customer_dob)
            return {"db_result": result, "action": "READ bills"}

        elif intent == "payment_history":
            result = get_payment_history(customer_dob)
            return {"db_result": result, "action": "READ payment_history"}

        elif intent == "complaint_status":
            result = get_complaint_status(customer_dob, params.get("complaint_id"))
            return {"db_result": result, "action": "READ complaints"}

        elif intent == "lodge_complaint":
            issue = params.get("issue", "Customer reported an issue")
            result = create_complaint(customer_dob, issue)
            return {"db_result": result, "action": "WRITE complaints.create"}

        elif intent == "escalate":
            result = escalate_complaint(customer_dob, params.get("complaint_id"))
            return {"db_result": result, "action": "WRITE complaints.escalate"}

        else:
            return {"db_result": {}, "action": None}

    except Exception as e:
        print(f"[DB Tool Error] {e}")
        return {"db_result": {}, "action": None}

# ── STEP 3: RESPONSE GENERATOR CHAIN ──────────────────────
RESPONSE_SYSTEM = """You are Deep Care, a professional voice customer service AI.
You are speaking with {customer_name}.

Customer context:
{customer_context}

DB result for this query:
{db_result}

Rules:
- Reply in 1-2 sentences ONLY. This is a voice call — be concise.
- Be warm and professional. Never robotic.
- Use actual data from DB result above — never make up numbers or IDs.
- If DB result is empty, say you'll look into it.
- For complaints: be empathetic first, then practical.
- For escalation: confirm transfer warmly.

Return ONLY valid JSON. No markdown. No explanation."""

RESPONSE_HUMAN = """Customer said: "{transcript}"
Intent detected: {intent}

Return JSON with: response, key_points (list), suggested_action, summary_text"""

response_prompt = ChatPromptTemplate.from_messages([
    ("system", RESPONSE_SYSTEM),
    ("human", RESPONSE_HUMAN)
])

response_chain = response_prompt | llm | JsonOutputParser()

# ── MASTER CHAIN ───────────────────────────────────────────
def run_chain(
    transcript: str,
    customer_dob: str,
    customer_name: str,
    customer_context: str,
    history: str = ""
) -> dict:
    """
    Full pipeline:
    1. Classify intent
    2. Execute DB tool
    3. Generate response

    Returns complete result dict.
    """

    # Step 1 — Intent classification
    try:
        intent_result = intent_chain.invoke({
            "transcript": transcript,
            "history": history or "No previous turns."
        })
    except Exception as e:
        print(f"[Intent Chain Error] {e}")
        intent_result = {"intent": "general", "params": {}, "sentiment": "neutral"}

    intent    = intent_result.get("intent", "general")
    params    = intent_result.get("params", {})
    sentiment = intent_result.get("sentiment", "neutral")

    # Step 2 — DB tool execution
    db_data = execute_db_tool(intent, params, customer_dob)
    db_result = db_data.get("db_result", {})
    action    = db_data.get("action")

    # Step 3 — Response generation
    try:
        response_result = response_chain.invoke({
            "transcript":        transcript,
            "intent":            intent,
            "customer_name":     customer_name,
            "customer_context":  customer_context,
            "db_result":         json.dumps(db_result, indent=2) if db_result else "No data found."
        })
    except Exception as e:
        print(f"[Response Chain Error] {e}")
        response_result = {
            "response":        "I'm here to help. Could you repeat that?",
            "key_points":      [],
            "suggested_action": "Review interaction logs.",
            "summary_text":    "Error in processing."
        }

    return {
        "intent":           intent,
        "params":           params,
        "sentiment":        sentiment,
        "action":           action,
        "db_result":        db_result,
        "response":         response_result.get("response", ""),
        "key_points":       response_result.get("key_points", []),
        "suggested_action": response_result.get("suggested_action", ""),
        "summary_text":     response_result.get("summary_text", ""),
    }
```

---

## FILE 4: server.py (FULL REBUILD — replaces n8n version)

```python
"""
server.py — Deep Care Voice Gateway (LangChain version)
No n8n. FastAPI + LangChain + Gemini 2.0 Flash.
"""

import os, uuid, base64
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv("config.env")

from src.stt.whisper_engine       import transcribe_audio
from src.tts.elevenlabs_client    import speak
from src.auth.dob_auth            import extract_dob, lookup_customer, get_customer_context_string
from src.db.db_handler            import load_customer, save_session
from src.session.session_manager  import (create_session, get_session,
                                           set_authenticated, append_turn, get_last_n_turns)
from src.session.summary_generator import generate_summary
from src.llm.chain                import run_chain

app = FastAPI(title="Deep Care Voice Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "model": "gemini-2.0-flash", "chain": "langchain"}


@app.post("/session/start")
async def session_start():
    session_id = str(uuid.uuid4())
    create_session(session_id)
    audio = speak("Welcome to Deep Care! Please say your date of birth to get started.")
    return JSONResponse({
        "session_id": session_id,
        "audio_b64":  base64.b64encode(audio).decode()
    })


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
        return _response(session_id, "", "I didn't catch that. Could you repeat?", audio)

    # ── 3. Auth gate ───────────────────────────────────────────
    if not session["authenticated"]:
        dob = extract_dob(transcript)
        if dob:
            customer = lookup_customer(dob)
            if customer:
                set_authenticated(session_id, customer, dob)
                reply = f"Welcome back, {customer['name']}! How can I help you today?"
                append_turn(session_id, transcript, reply, "auth_success", "positive")
                audio = speak(reply)
                return _response(
                    session_id, transcript, reply, audio,
                    summary=generate_summary(get_session(session_id))
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
    customer_data   = load_customer(session["customer_dob"])
    context_str     = get_customer_context_string(customer_data)
    history_str     = get_last_n_turns(session_id, n=6)

    # ── 5. Run LangChain ───────────────────────────────────────
    chain_result = run_chain(
        transcript       = transcript,
        customer_dob     = session["customer_dob"],
        customer_name    = session["customer_name"],
        customer_context = context_str,
        history          = history_str
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
        chain_result["sentiment"]
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
        intent    = chain_result["intent"],
        db_result = chain_result["db_result"],
        summary   = summary
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

    audio = speak("Thank you for calling Deep Care. Have a wonderful day!")

    return JSONResponse({
        "summary":   summary,
        "audio_b64": base64.b64encode(audio).decode()
    })


# ── HELPER ─────────────────────────────────────────────────
def _response(session_id, transcript, response_text, audio_bytes,
              intent=None, db_result=None, summary=None):
    return JSONResponse({
        "session_id": session_id,
        "transcript": transcript,
        "response":   response_text,
        "intent":     intent,
        "audio_b64":  base64.b64encode(audio_bytes).decode(),
        "db_result":  db_result or {},
        "summary":    summary
    })
```

---

## LATENCY BREAKDOWN (target)

```
Whisper small (CPU)     →  ~0.8s
Gemini intent call      →  ~0.2s  ← 2.0-flash is very fast
DB tool (Python/JSON)   →  ~0.01s
Gemini response call    →  ~0.3s
ElevenLabs TTS          →  ~0.6s
FastAPI overhead        →  ~0.1s
─────────────────────────────────
TOTAL                   →  ~2.0s  ✅
```

## TIPS TO SQUEEZE MORE SPEED

1. Run intent + response as ONE Gemini call (combine prompts)
2. Stream ElevenLabs audio back instead of waiting for full file
3. Pre-warm Whisper model on startup (already done in whisper_engine.py)
4. Use async for TTS call while DB executes

## SINGLE GEMINI CALL OPTION (even faster ~1.6s)

If you want to combine intent + response into ONE API call:

```python
SINGLE_PROMPT = """
You are Deep Care customer service AI speaking with {customer_name}.

Customer context: {customer_context}
History: {history}
Customer said: "{transcript}"

Return JSON with ALL of these fields:
{{
  "intent": "one of: order_status|order_tracking|current_bill|payment_history|complaint_status|lodge_complaint|escalate|goodbye|general",
  "params": {{}},
  "sentiment": "positive|neutral|negative",
  "response": "1-2 sentence reply",
  "key_points": ["point1"],
  "suggested_action": "what agent should do",
  "summary_text": "one sentence summary"
}}

Return ONLY valid JSON. No markdown.
"""
```

This saves one full API round trip. Use this if 2.0s is still too slow.
