# CONTEXT.md — Deep Care Voice Gateway
# Paste this into any model to get full project context

---

## WHAT IS THIS

Deep Care is a Voice-Based AI Gateway for enterprise customer service.
A caller speaks into a browser mic. The system authenticates them by date
of birth, understands their query, fetches real data, speaks back naturally.
At the end, a human agent receives a full summary card.

Built in 24 hours for a hackathon. PS: AI02.

---

## CURRENT STATUS

```
✅ server.py          — FastAPI, all endpoints working
✅ src/stt/           — Whisper STT (openai-whisper)
✅ src/tts/           — ElevenLabs TTS
✅ src/auth/          — DOB extraction + customer lookup
✅ src/db/            — All DB read/write operations
✅ src/session/       — Session tracking + summary generator
✅ src/llm/chain.py   — Direct Gemini 2.0 Flash (no LangChain)
✅ static/index.html  — Split screen UI (call left, summary right)
✅ mock_data.json     — 2 demo customers
❌ src/audio/         — converter.py exists but not used
```

---

## TECH STACK

```
Language:     Python 3.11 (Arch Linux)
Server:       FastAPI + Uvicorn
STT:          openai-whisper (small model, CPU)
LLM:          Google Gemini 2.0 Flash (direct API, no LangChain)
TTS:          ElevenLabs API (free tier, Rachel voice)
DB:           mock_data.json (flat JSON file)
UI:           Vanilla HTML/CSS/JS (split screen)
Orchestration: None — FastAPI handles everything inline
```

---

## DIRECTORY STRUCTURE

```
deep-care/
├── config.env                     # API keys + config
├── server.py                      # FastAPI main app
├── mock_data.json                  # Customer database
├── requirements.txt
├── run.sh
├── test.ogg                       # Test audio file
├── cert.pem / key.pem             # SSL certs (for HTTPS mic access)
│
├── static/
│   └── index.html                 # Split screen voice UI
│
└── src/
    ├── __init__.py
    ├── audio/
    │   └── converter.py           # ffmpeg webm→wav (not used yet)
    ├── auth/
    │   └── dob_auth.py            # DOB extract + DB lookup
    ├── db/
    │   └── db_handler.py          # All 7 DB operations
    ├── llm/
    │   ├── __init__.py
    │   └── chain.py               # Gemini 2.0 Flash pipeline
    ├── session/
    │   ├── session_manager.py     # In-memory session store
    │   └── summary_generator.py   # Handoff card generator
    ├── stt/
    │   ├── __init__.py
    │   └── whisper_engine.py      # Whisper STT wrapper
    └── tts/
        └── elevenlabs_client.py   # ElevenLabs TTS wrapper
```

---

## PIPELINE FLOW

```
1. Browser records mic audio (webm)
2. POST audio → FastAPI /send
       Header: x-session-id: {uuid}
3. Whisper transcribes audio → transcript text
4. If not authenticated:
       Extract DOB from transcript → lookup mock_data.json
       If found → set session authenticated, greet by name
       If not  → ask again (max 3 tries)
5. If authenticated:
       Load customer context from mock_data.json
       Load last 6 turns from session
       POST to Gemini 2.0 Flash with single prompt
       Gemini returns JSON: intent + response + key_points + sentiment
       Execute DB tool based on intent (Python function)
6. ElevenLabs converts response text → mp3 bytes
7. FastAPI returns JSON to browser:
       { session_id, transcript, response, intent,
         audio_b64, db_result, summary }
8. Browser decodes audio_b64 → plays audio
9. Browser updates summary panel live
```

---

## ENDPOINTS

```
GET  /              → serves static/index.html
GET  /health        → { status, model }
POST /session/start → creates session, returns welcome audio
POST /send          → main pipeline (audio in, audio+summary out)
POST /session/end   → generates final summary, saves to DB
```

### /send request:
```
Headers: Content-Type: audio/webm
         x-session-id: {uuid}
Body:    raw audio bytes
```

### /send response:
```json
{
  "session_id": "uuid",
  "transcript": "what user said",
  "response":   "what bot said",
  "intent":     "order_status",
  "audio_b64":  "base64 mp3 string",
  "db_result":  { ...raw DB data... },
  "summary": {
    "name":             "Arjun Kumar",
    "customer_id":      "DCID-4521",
    "dob":              "15-03-1999",
    "duration":         "4m 12s",
    "time":             "14:32:01",
    "sentiment":        "neutral",
    "intents":          ["order_status", "current_bill"],
    "summary":          "Customer enquired about order and billing.",
    "key_points":       ["Order ORD-4521 delivered", "Bill Rs.2400 due Mar 20"],
    "suggested_action": "No follow-up needed.",
    "escalated":        false
  }
}
```

---

## GEMINI PROMPT (in src/llm/chain.py)

Single API call — intent classification + response generation together.

Input fields:
- customer_name
- customer_context (orders, bills, complaints as text)
- history (last 6 turns)
- transcript (what user just said)

Output JSON fields:
- intent (one of 9 intents)
- params (order_id, complaint_id, issue etc)
- sentiment (positive/neutral/negative)
- response (1-2 sentence voice reply)
- key_points (list of 1-3 strings)
- suggested_action (for human agent)
- summary_text (one sentence)

Intents:
```
order_status | order_tracking | current_bill | payment_history |
complaint_status | lodge_complaint | escalate | goodbye | general
```

---

## DB OPERATIONS (src/db/db_handler.py)

```
load_customer(dob)                          → dict
get_order_status(dob, order_id=None)        → dict
get_order_tracking(dob, order_id)           → dict
get_current_bill(dob)                       → dict
get_payment_history(dob)                    → list
get_complaint_status(dob, complaint_id)     → dict
create_complaint(dob, issue)                → { complaint_id, status }
escalate_complaint(dob, complaint_id)       → { escalated, complaint_id }
save_session(dob, session_data)             → None
```

---

## MOCK DATABASE (mock_data.json)

Two demo customers:

```
DOB: 15-03-1999  → Arjun Kumar (DCID-4521)
     Orders:     ORD-4521 Laptop Stand (Delivered)
                 ORD-4522 Wireless Mouse (Out for Delivery)
     Bill:       Rs.2400 due 2024-03-20 (unpaid)
     Complaint:  CMP-001 Billing overcharge (open)

DOB: 20-05-1995  → Priya Sharma (DCID-7891)
     Orders:     ORD-7891 Bluetooth Speaker (Processing)
     Bill:       Rs.1800 due 2024-03-25 (autopay on)
     Complaints: none
```

---

## SESSION OBJECT (in-memory, src/session/session_manager.py)

```json
{
  "session_id":           "uuid",
  "authenticated":        true,
  "customer_dob":         "15-03-1999",
  "customer_name":        "Arjun Kumar",
  "customer_id":          "DCID-4521",
  "start_time":           "ISO8601",
  "turns": [
    {
      "turn": 1,
      "user": "where is my order",
      "bot":  "Your order ORD-4521 was delivered on March 1st.",
      "intent": "order_status",
      "sentiment": "neutral",
      "timestamp": "ISO8601"
    }
  ],
  "intents_seen":          ["auth_success", "order_status"],
  "sentiment_trajectory":  ["positive", "neutral"],
  "escalated":             false
}
```

---

## config.env

```
GOOGLE_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
WHISPER_MODEL=small
DB_PATH=./mock_data.json
HOST=0.0.0.0
PORT=8000
```

---

## KNOWN ISSUES / TODO

```
- converter.py not wired in (audio goes directly to Whisper as webm)
- No rate limiting on /send endpoint
- Session store is in-memory (lost on server restart)
- ElevenLabs free tier: 10k chars/month (enough for demo)
- Whisper small on CPU: ~1-2s transcription latency
- Gemini 2.0 Flash: ~0.3-0.5s response latency
- Total pipeline latency: ~2-3s per turn
```

---

## HOW TO RUN

```bash
# Activate venv
source .env/bin/activate

# Start server
uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# Or with HTTPS (needed for mic on non-localhost)
uvicorn server:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem --reload

# Open browser
https://localhost:8000
```

---

## DEMO SCRIPT

```
Bot:  "Welcome to Deep Care! Please say your date of birth."
User: "My birthday is March 15, 1999"
Bot:  "Welcome back, Arjun Kumar! How can I help you today?"

User: "Where is my order?"
Bot:  "Your order ORD-4521 for the Laptop Stand was delivered on March 1st."

User: "What's my bill this month?"
Bot:  "Your March bill is Rs.2400, due on March 20th. It's currently unpaid."

User: "I want to raise a complaint, I was overcharged"
Bot:  "I'm sorry to hear that. I've logged complaint CMP-xxx for you."

User: "I want to talk to a supervisor"
Bot:  "Transferring you now. Your agent has your full session context."

[Handoff card appears on screen with full summary]
```

---

## CURRENT TASK

[REPLACE THIS LINE WITH WHAT YOU NEED]
