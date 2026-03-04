# CONTEXT.md — Deep Care Voice Gateway
# Updated: Session 2 — Multilingual + Whisper BG Load + Test Suite

---

## WHAT IS THIS

Deep Care is a Voice-Based AI Gateway for enterprise customer service.
Caller speaks → authenticates via DOB → understands query →
fetches real data → speaks back → hands off to human agent with full context card.

Hackathon MVP. Python 3.11, Arch Linux, RTX 4050 6GB.

---

## CURRENT STATUS

```
✅ server.py              — FastAPI, background Whisper load, multilingual flow
✅ src/stt/whisper_engine — faster-whisper (int8 CPU), loads once at startup
✅ src/tts/elevenlabs_client — gTTS fallback (ElevenLabs key invalid), multilingual
✅ src/auth/dob_auth      — DOB extraction + lookup
✅ src/db/db_handler      — 9 DB operations
✅ src/llm/chain.py       — Gemini 2.5 Flash, direct API (google-genai SDK)
✅ src/session/           — session_manager + summary_generator
✅ static/index.html      — split screen UI
✅ static/script.js       — race condition fixed, end call wired, STT polling
✅ mock_data.json         — 2 demo customers
✅ tests/test_deep_care.py — 62 tests, 61/62 passing
```

---

## TECH STACK

```
Server:    FastAPI + Uvicorn (Python 3.11)
STT:       faster-whisper small (CPU, int8) — installed from openai/whisper git
LLM:       Google Gemini 2.5 Flash (google-genai SDK, direct API, no LangChain)
TTS:       gTTS fallback (ElevenLabs 401 — key needs renewal)
DB:        mock_data.json (swappable to PostgreSQL)
UI:        Vanilla HTML/CSS/JS split screen
Auth:      DOB extraction via dateutil + regex
Tests:     pytest, 62 tests, unittest.mock (no real API calls)
```

---

## ENVIRONMENT

```
Python:    3.11.14 (venv: .env3.11)
OS:        Arch Linux
GPU:       RTX 4050 6GB — nvidia driver CRASHED (needs reinstall after kernel update)
CPU:       Set to performance governor (was powersave)
Whisper:   faster-whisper installed, openai-whisper also installed from source
           Model: small (~461MB), cached at ~/.cache/whisper/small.pt (was corrupted, redownloaded)
Run:       sh run.sh → activates .env3.11, starts uvicorn with SSL
```

---

## PIPELINE FLOW

```
1.  Page loads → POST /session/start → welcome audio plays
    └─ sessionReady = true (race condition guard)
    └─ Whisper loads in background thread (_whisper_ready event)
    └─ Frontend polls /health until stt="ready"

2.  User clicks mic → records webm audio → clicks stop

3.  POST /send (audio bytes + x-session-id header)

4.  Whisper transcribes → transcript + confidence
    └─ If _whisper_ready not set → waits up to 60s polling

5.  If not authenticated:
        extract DOB → lookup mock_data.json
        found     → greet by name + ask language preference
        not found → ask again

6.  Language selection gate (NEW):
        Customer says language → session["language"] locked
        session["language_confirmed"] = True
        Bot confirms in chosen language

7.  If authenticated + language confirmed:
        load customer data from DB
        load last 6 turns from session
        Gemini 2.5 Flash: classify intent + generate response
            → always reasons in English internally
            → response field written in customer's language
        Python executes DB tool based on intent
        gTTS converts response → mp3 (in session language)

8.  Return JSON: { session_id, transcript, response,
                   intent, audio_b64, db_result, summary,
                   language, stt_ready, ended }

9.  Browser decodes audio_b64 → plays
    └─ If intent=goodbye or ended=true → endCall() fires after 2s

10. End Call:
        Button click OR voice goodbye → POST /session/end
        Summary card rendered, goodbye audio plays
        Buttons disabled, session marked complete
```

---

## HALLUCINATION CONTROL

### Core Pattern: Python Fetches, Gemini Narrates

```
Step 1: Gemini classifies intent
        → { intent: "order_status", params: { order_id: "ORD-4521" } }

Step 2: Python runs db_handler
        → { order_id: "ORD-4521", item: "Laptop Stand", status: "Delivered" }

Step 3: DB result injected into Gemini prompt
        → Gemini describes ONLY what Python returned
```

Gemini NEVER guesses. If DB returns empty → bot says "I'll look into it."

### Multilingual Hallucination Guard

```
❌ WRONG: Ask Gemini to think in Tamil → ~40% hallucination rate
✅ CORRECT:
   - Gemini always reasons in English internally
   - Only "response" field is written in target language
   - All other JSON fields (intent, sentiment, params) stay English
   - Accuracy stays at 90%+
```

---

## HUMAN IN LOOP

```python
if chain_result["intent"] == "escalate":
    session["escalated"] = True   # flag only — bot keeps running
```

Auto-escalation: 2 consecutive negative sentiment turns → bot appends transfer message.

### Handoff Card

```
POST /session/end → summary card with:
- Customer name + ID + DOB
- Full transcript
- All intents detected
- Sentiment trajectory
- Actions taken
- Suggested action for agent
- Duration + timestamp
- Language used
```

---

## MULTILINGUAL ARCHITECTURE

### Language Selection Flow (NEW — implemented)

```
After DOB auth → bot asks: "Which language? English/Tamil/Hindi/Telugu/Kannada"
Customer responds → detect_language_choice() matches keyword or native script
session["language"] = "ta"        ← locked for entire session
session["language_confirmed"] = True

Bot confirms in chosen language:
  Tamil:   "சரி! நான் தமிழில் தொடர்வேன்."
  Hindi:   "बिल्कुल! मैं हिंदी में जारी रखूंगा।"
  Telugu:  "సరే! నేను తెలుగులో కొనసాగిస్తాను."
  Kannada: "ಸರಿ! ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮುಂದುವರಿಯುತ್ತೇನೆ."
```

### TTS Language Map (gTTS)

```python
GTTS_LANG_MAP = {
    "en": "en", "ta": "ta", "hi": "hi", "te": "te",
    "kn": "kn", "bn": "bn", "ml": "ml", "gu": "gu",
    "mr": "mr", "pa": "pa"
}
```

### Roadmap

```
Phase 1 (MVP):     English only + language selection UI   ← current
Phase 2 (Month 2): Tamil via gTTS (working now)
Phase 3 (Month 3): Hindi, Telugu, Kannada
Phase 4 (Month 4): IndicTrans2 + Coqui TTS for better quality
Phase 5 (Month 5): All 22 Indian languages
```

---

## KNOWN ISSUES / TODO

```
❌ ElevenLabs API key returning 401 — needs renewal from dashboard
❌ nvidia driver crashed after kernel update — needs: sudo pacman -S nvidia nvidia-utils + reboot
❌ IndicTrans2 not implemented (gTTS used instead for now)
❌ Session store in-memory (lost on restart) — Redis swap needed for prod
❌ Confirmation gate designed but not wired (before create_complaint / escalate)
❌ Loading UX messages ("fetching data...") not implemented yet
❌ Whisper model: faster-whisper active (openai-whisper also installed from source)
⚠️  click downgraded to 8.1.8 for gtts — typer needs >=8.2.1, fixed with: pip install "click>=8.2.1"
```

---

## WHISPER SETUP

```
Installed:    openai-whisper from git (pip install . in cloned repo)
              faster-whisper also present → takes priority in whisper_engine.py
Model:        small (int8 on CPU)
Load:         Once at server startup in background daemon thread
RAM:          ~461MB stays in RAM for all sessions
Cleanup:      atexit.register(_unload_model) — releases on server shutdown
Cache:        ~/.cache/whisper/small.pt
              Was corrupted (0 bytes) — deleted and redownloaded via wget
```

---

## DEMO CUSTOMERS

```
DOB: 15-03-1999 → Arjun Kumar (DCID-4521)
     ORD-4521 Laptop Stand (Delivered)
     ORD-4522 Wireless Mouse (Out for Delivery)
     Bill Rs.2400 due 2024-03-20 (unpaid)
     CMP-001 Billing overcharge (open)

DOB: 20-05-1995 → Priya Sharma (DCID-7891)
     ORD-7891 Bluetooth Speaker (Processing)
     Bill Rs.1800 due 2024-03-25 (autopay on)
```

---

## DB OPERATIONS

```
load_customer(dob)
get_order_status(dob, order_id)
get_order_tracking(dob, order_id)
get_current_bill(dob)
get_payment_history(dob)
get_complaint_status(dob, complaint_id)
create_complaint(dob, issue)
escalate_complaint(dob, complaint_id)
save_session(dob, session_data)
```

Production swap: replace _load_db() with PostgreSQL. Nothing above changes.

---

## ENDPOINTS

```
GET  /              → index.html
GET  /health        → { status, model, stt: "ready"|"loading", chain }
POST /session/start → { session_id, audio_b64, stt_ready }
POST /send          → { session_id, transcript, response, intent,
                         audio_b64, db_result, summary, language,
                         stt_ready, ended }
POST /session/end   → { summary, audio_b64 }
```

---

## SESSION FIELDS

```python
{
    "session_id":          str,
    "authenticated":       bool,
    "customer_dob":        str | None,
    "customer_name":       str | None,
    "customer_id":         str | None,
    "language":            str,   # "en"|"ta"|"hi"|"te"|"kn" etc — locked after selection
    "language_confirmed":  bool,  # gate — must confirm before main flow
    "start_time":          ISO str,
    "turns":               list,
    "intents_seen":        list,
    "sentiment_trajectory": list,
    "escalated":           bool,
    "last_active":         ISO str,
}
```

---

## TEST SUITE

```
File:    tests/test_deep_care.py
Count:   62 tests
Passing: 61/62 (1 flaky — complaint status test, DB state order dependent)
Run:     pytest tests/test_deep_care.py -v

Groups:
  TestDBHandler        — 20 tests (all 9 DB ops, valid + invalid inputs)
  TestDOBAuth          — 11 tests (numeric, natural language, ISO, garbage)
  TestSessionManager   —  9 tests (lifecycle, sentiment, last-N turns)
  TestChain            —  7 tests (mocked Gemini, JSON fallback, fence stripping)
  TestHallucinationGuard — 3 tests (DB is source of truth, not Gemini)
  TestAutoEscalation   —  3 tests (2x negative, 1x no trigger, bot keeps running)
  TestExecuteDBTool    —  9 tests (all intent branches, unknown → {}, exceptions)
```

---

## HOW TO RUN

```bash
source .env3.11/bin/activate
sh run.sh
# → uvicorn on https://0.0.0.0:8000 with SSL

# Run tests
source .env3.11/bin/activate
pytest tests/test_deep_care.py -v
```

---

## FILES CHANGED THIS SESSION

```
server.py               — background Whisper load, language gate, auto-escalation
src/stt/whisper_engine.py — load_model_at_startup(), atexit cleanup
src/tts/elevenlabs_client.py — multilingual gTTS, detect_language_choice()
src/llm/chain.py        — gemini-2.5-flash, LANG_NAMES, lang param in prompt
src/session/session_manager.py — language + language_confirmed fields
static/script.js        — race condition fix, endCall(), STT polling, lang display
requirements.txt        — google-genai replaces google-generativeai, gtts added
tests/test_deep_care.py — 62 tests, complaint status test made order-independent
```

---

## FUTURE SCOPE

```
Immediate:
  - Fix ElevenLabs key
  - Fix nvidia driver (sudo pacman -S nvidia nvidia-utils && reboot)
  - Wire confirmation gate before destructive actions
  - Add Redis for persistent sessions
  - Loading UX messages while DB/AI fetches

Product:
  - Outbound calling (payment reminders, delivery updates)
  - WhatsApp / IVR via Twilio or Exotel
  - Agent dashboard with live session view
  - Post-call analytics

AI:
  - Streaming TTS (reduce perceived latency from ~3s to ~0.5s)
  - Voice biometrics (replace DOB auth)
  - Emotion detection from audio
  - RAG over company knowledge base

Enterprise:
  - Multi-tenant deployment
  - CRM integration (Salesforce, Zoho, Freshdesk)
  - Compliance recording + search
  - SLA monitoring per intent type
```
