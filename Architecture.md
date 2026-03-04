# Architecture — Voice-Based AI Gateway

## System Overview

The Voice AI Gateway is a locally-hosted, modular pipeline that replaces
fragmented IVR/chatbot/agent stacks with a single intelligent voice layer.
All components run on-device (RTX 4050, 6GB VRAM). No paid APIs except
ElevenLabs TTS (free tier, used only for demo).

---

## High-Level Component Map

```
┌─────────────────────────────────────────────────────────┐
│                     GRADIO UI                           │
│          (mic input  ←→  audio playback)                │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP multipart audio
                    ▼
┌─────────────────────────────────────────────────────────┐
│                  FASTAPI SERVER                         │
│   /transcribe   /speak   /session   /handoff            │
└────┬──────────────────────────────────────┬─────────────┘
     │                                      │
     ▼                                      ▼
┌──────────────┐                  ┌──────────────────────┐
│  WHISPER STT │                  │   ELEVENLABS TTS     │
│  (small/int8)│                  │   (free tier API)    │
│  ~0.8s       │                  │   cached phrases     │
└──────┬───────┘                  └──────────────────────┘
       │ transcript text
       ▼
┌─────────────────────────────────────────────────────────┐
│                   n8n ORCHESTRATOR                      │
│   (self-hosted, localhost:5678)                         │
│                                                         │
│   Webhook → Auth → Intent Router → Branch → Response   │
│                          │                             │
│              ┌───────────┴────────────┐                │
│              │                        │                │
│         Rule Branches            Ollama Node           │
│         (18 intents)             (Gemma 2B)            │
│              │                        │                │
│         JSON DB R/W              LLM Response          │
└─────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### Gradio UI (`ui.py`)
- Captures microphone audio
- Displays live transcript
- Plays bot audio response
- Shows session summary card on end

### FastAPI Server (`server.py`)
- Thin HTTP layer — no business logic
- `POST /transcribe` → runs Whisper → returns text
- `POST /speak` → calls ElevenLabs → returns audio bytes
- `POST /session/start` → loads customer context
- `POST /session/end` → triggers handoff summary
- `POST /webhook/n8n` → forwards transcript to n8n

### Whisper STT (`src/stt/whisper_engine.py`)
- Model: `whisper small` (int8 quantized)
- Loads on startup, stays in RAM (not VRAM)
- Returns transcript + confidence score
- Falls back to retry on low confidence (<0.6)

### n8n Workflow (`src/n8n/workflow.json`)
- Receives: `{ transcript, session_id, customer_context }`
- Auth branch: DOB extraction + JSON DB lookup
- Intent router: keyword pre-filter → Ollama classification
- 18 intent branches: each reads/writes `db.json`
- Returns: `{ response_text, action_taken, updated_context }`

### Ollama / Gemma 2B (`src/llm/`)
- Runs via Ollama daemon (manages VRAM automatically)
- Called only for: bill_dispute, complaint handling, feedback, complex queries
- Always returns structured JSON (see `prompt.md`)
- n8n has native Ollama node — no wrapper code needed

### ElevenLabs TTS (`src/tts/elevenlabs_client.py`)
- Voice: Rachel (professional, clear)
- Common phrases pre-cached at startup (no API call)
- `USE_ELEVENLABS` flag — toggle to gTTS for dev

### JSON Database (`src/db/db.json`)
- Single file, loaded into memory on session start
- Written back atomically on every mutation
- Schema: customers keyed by DOB string `"DD-MM-YYYY"`

---

## Data Flow — Single Turn

```
1. User speaks         → Gradio captures audio blob
2. Audio → /transcribe → Whisper returns text
3. Filler phrase plays → ElevenLabs (cached, instant)
4. Text → n8n webhook  → Auth check / intent routing
5. n8n → DB operation  → Read or write db.json
6. n8n → Ollama        → Only if LLM intent
7. Response text → /speak → ElevenLabs audio
8. Audio plays         → Gradio renders waveform
9. Context updated     → Session object appended
```

---

## VRAM Budget (RTX 4050, 6GB)

| Component    | Location | VRAM  |
|--------------|----------|-------|
| Whisper small| RAM/CPU  | 0 GB  |
| Ollama Gemma | VRAM     | ~2.5 GB|
| Coqui TTS    | CPU      | 0 GB  |
| OS + drivers | VRAM     | ~0.5 GB|
| **Available**|          | **3 GB free** |

Whisper intentionally runs on CPU to preserve VRAM for Gemma.
Ollama manages Gemma loading/unloading automatically.

---

## Session Object Schema

```json
{
  "session_id": "uuid",
  "customer_dob": "15-03-1999",
  "customer_name": "Arjun",
  "authenticated": true,
  "start_time": "ISO8601",
  "turns": [
    {
      "turn": 1,
      "user": "Where is my order?",
      "intent": "order_status",
      "action": "READ orders[0]",
      "bot": "Your order #4521 is out for delivery.",
      "sentiment": "neutral"
    }
  ],
  "actions_taken": [],
  "sentiment_trajectory": ["neutral"],
  "escalation_flag": false
}
```

---

## Handoff Summary Card

Generated at session end, displayed in Gradio and logged to file:

```
┌─────────────────────────────────────────────┐
│  Customer: Arjun        DOB: 15-03-1999     │
│  Session Duration: 6m 42s                   │
├─────────────────────────────────────────────┤
│  ✓ Checked order #4521 → Delivered          │
│  ✓ Refund raised → Ticket #R-8823           │
│  ✓ Appointment rescheduled → Mar 12         │
│  ✓ Complaint lodged → Ticket #C-2201        │
├─────────────────────────────────────────────┤
│  Sentiment: Neutral → Mild frustration      │
│  Suggested Action: Follow up on C-2201      │
└─────────────────────────────────────────────┘
```
