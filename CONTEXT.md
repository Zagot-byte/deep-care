# CONTEXT.md — Deep Care Voice Gateway
# Updated: Hallucination Control + Human in Loop + Multilingual

---

## WHAT IS THIS

Deep Care is a Voice-Based AI Gateway for enterprise customer service.
Caller speaks → authenticates via DOB → understands query →
fetches real data → speaks back → hands off to human agent with full context card.

Hackathon MVP. Python 3.11, Arch Linux, RTX 4050 6GB.

---

## CURRENT STATUS

```
✅ server.py              — FastAPI, all endpoints
✅ src/stt/whisper_engine — openai-whisper, CPU
✅ src/tts/elevenlabs     — ElevenLabs + gTTS fallback
✅ src/auth/dob_auth      — DOB extraction + lookup
✅ src/db/db_handler      — 9 DB operations
✅ src/llm/chain.py       — Gemini 2.0 Flash direct API
✅ src/session/           — session_manager + summary_generator
✅ static/index.html      — split screen UI fixed
✅ mock_data.json         — 2 demo customers
```

---

## TECH STACK

```
Server:    FastAPI + Uvicorn (Python 3.11)
STT:       openai-whisper small (CPU)
LLM:       Google Gemini 2.0 Flash (direct API, no LangChain)
TTS:       ElevenLabs API (gTTS fallback)
DB:        mock_data.json (swappable to PostgreSQL)
UI:        Vanilla HTML/CSS/JS split screen
Auth:      DOB extraction via dateutil + regex
```

---

## PIPELINE FLOW

```
1.  Page loads → POST /session/start → welcome audio plays
2.  User clicks mic → records webm audio
3.  POST /send (audio bytes + x-session-id header)
4.  Whisper transcribes → transcript + confidence
5.  If not authenticated:
        extract DOB → lookup mock_data.json
        found     → greet by name, set session
        not found → ask again
6.  If authenticated:
        load customer data from DB
        load last 6 turns from session
        Gemini 2.0 Flash: classify intent + generate response (ONE call)
        Python executes DB tool based on intent
        ElevenLabs converts response → mp3
7.  Return JSON: { session_id, transcript, response,
                   intent, audio_b64, db_result, summary }
8.  Browser decodes audio_b64 → plays
9.  Summary panel updates live
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
Order IDs, bill amounts, complaint numbers — all come from Python, not Gemini.

### Prompt Enforcement

```
DB result for this query: {db_result}   ← real data injected

Rules:
- Use ONLY data from DB result above
- If DB result is empty, say you will look into it
- NEVER invent order IDs, amounts, or ticket numbers
```

---

## HUMAN IN LOOP

### Escalation Does NOT Stop the Bot

```python
if chain_result["intent"] == "escalate":
    session["escalated"] = True   # flag only — bot keeps running
```

- Bot keeps answering until agent physically takes over
- Agent sees escalation flag + full summary card on screen
- Agent joins at their discretion (queue time can be 2-5 mins)
- Bot continues building summary during wait

### Auto-Escalation (Sentiment)

Two consecutive negative sentiment turns → bot proactively offers transfer.
Customer does not need to ask.

### Handoff Card

```
POST /session/end → summary card with:
- Customer name + ID + DOB
- Full transcript
- All intents detected
- Sentiment trajectory
- Actions taken (tickets raised, orders checked)
- Suggested action for agent
- Duration + timestamp
```

---

## MULTILINGUAL ARCHITECTURE

### Why Naive Approach Fails

```
❌ WRONG:
Tamil speech → Gemini responds in Tamil → ElevenLabs speaks Tamil

Problems:
- Gemini Tamil output is weak, hallucination spikes to ~40%
- ElevenLabs has no good Tamil voices
- Mispronunciation is severe
```

### Correct Architecture

```
✅ CORRECT:

Whisper detects language → "ta"
        ↓
Gemini reasons in ENGLISH (accurate, no hallucination)
        ↓
IndicTrans2 translates English → Tamil
        ↓
Coqui TTS (Tamil voice model) speaks output

Gemini never thinks in Tamil. Only output is translated.
Accuracy stays at 90%+.
```

### STT — Whisper Native Detection

```python
segments, info = model.transcribe(tmp_path, beam_size=5)
detected_lang = info.language   # "ta", "en", "hi" etc
```

No extra model needed.

### LLM — Always English Internally

```python
PROMPT = """
Always reason and respond in English.
Response will be translated separately.
Customer language: {detected_lang}
"""
```

### Translation Layer (To Build)

```python
# src/translate/indic_translator.py
from indicTrans2 import Translator
translator = Translator()

def translate_response(text: str, target_lang: str) -> str:
    if target_lang == "en":
        return text
    return translator.translate(text, source="en", target=target_lang)
```

### TTS — Language Switch

```python
def speak(text: str, lang: str = "en") -> bytes:
    if lang == "en" and ELEVENLABS_API_KEY:
        return _speak_elevenlabs(text)
    else:
        return _speak_coqui(text, lang)   # Coqui for Indian languages
```

### Roadmap

```
Phase 1 (MVP):     English only           ← current
Phase 2 (Month 2): Tamil
Phase 3 (Month 3): Hindi, Telugu, Kannada
Phase 4 (Month 4): All 22 Indian languages
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
GET  /health        → { status, model }
POST /session/start → { session_id, audio_b64 }
POST /send          → { session_id, transcript, response, intent, audio_b64, db_result, summary }
POST /session/end   → { summary, audio_b64 }
```

---

## HOW TO RUN

```bash
source .env/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile key.pem --ssl-certfile cert.pem --reload
```

---

## KNOWN ISSUES

```
- Confirmation gate designed but not fully wired
- IndicTrans2 not implemented yet
- Session store in-memory (lost on restart)
- ElevenLabs free tier 10k chars/month
- Whisper CPU ~1-2s latency
```

---

## CURRENT TASK

[REPLACE THIS LINE WITH WHAT YOU NEED]
