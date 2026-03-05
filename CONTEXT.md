# Deep Care Voice Gateway — CONTEXT.md
> Paste this at the start of any new chat to resume exactly where we left off.

---

## What This Is
Enterprise voice AI customer service gateway. Customer calls via browser mic, authenticates by DOB, speaks in any Indian language, gets answers from real DB data narrated by Gemini. Full agent handoff summary at call end.

---

## Stack
| Layer | Tech |
|---|---|
| Runtime | Python 3.11, FastAPI, uvicorn SSL |
| STT | faster-whisper small int8 CPU — background thread |
| LLM | Gemini 2.5 Flash via google-genai (native function calling) |
| TTS | ElevenLabs primary → gTTS fallback (all Indian languages) |
| DB | mock_data.json default, PostgreSQL via DB_BACKEND=postgres |
| Frontend | Vanilla JS — index.html + script.js + style.css |

---

## Project Structure
```
deep-care/
├── server.py                     FastAPI app, Whisper bg thread, session flow
├── config.env                    GOOGLE_API_KEY, ELEVENLABS_API_KEY, DB_BACKEND
├── mock_data.json                Customer DB (JSON backend)
├── run.sh                        Activates .env3.11, starts uvicorn SSL
├── setup_postgres.sql            10 demo customers
├── static/
│   ├── index.html                Left: call UI | Right: summary panel
│   ├── script.js                 Session, mic, audio, summary rendering
│   └── style.css                 Dark minimal theme
└── src/
    ├── auth/dob_auth.py          DOB extraction + customer lookup
    ├── db/db_handler.py          All DB ops — reads mock_data.json exactly
    ├── llm/chain.py              Gemini 2-turn tool calling pipeline
    ├── session/session_manager.py
    ├── session/summary_generator.py
    ├── stt/whisper_engine.py     faster-whisper
    └── tts/elevenlabs_client.py  ElevenLabs + gTTS multilingual fallback
```

---

## Call Flow
```
Browser mic → /send audio blob
  → Whisper STT → transcript
  → Auth gate (DOB)
  → Language selection (locked for session)
  → load_customer(dob) → context string
  → Gemini Turn 1: sees tools, calls the right one
  → Python executes tool → real data returned
  → Gemini Turn 2: narrates ONLY what Python returned
  → Classify call: intent + sentiment + summary
  → TTS → audio_b64
  → Frontend: plays audio, updates log, updates summary panel
```

---

## CRITICAL: mock_data.json Bill Structure
Bills use `"paid": true/false` NOT `"status": "paid"`. The old db_handler was broken because of this mismatch. Fixed now.

```json
"bills": [{
  "bill_id": "BILL-001",
  "month": "March 2024",
  "amount": 2400,
  "due_date": "2024-03-20",
  "paid": false,
  "breakdown": {"base_plan": 1999, "add_ons": 401},
  "history": [{"month": "Feb 2024", "amount": 2100, "paid": true, "paid_on": "2024-02-18"}],
  "dispute": null,
  "autopay": false
}]
```

---

## DB Tools (db_handler.py)
| Function | Purpose |
|---|---|
| load_customer(dob) | Full customer dict |
| get_customer_context_string(customer) | Clean string for Gemini |
| get_order_status(dob, order_id=None) | All orders or specific |
| get_order_tracking(dob, order_id) | Tracking + address |
| get_current_bill(dob) | First unpaid bill |
| get_payment_history(dob) | Bill + history |
| get_complaint_status(dob, complaint_id=None) | All or specific complaint |
| create_complaint(dob, issue) | New complaint → saved to JSON |
| escalate_complaint(dob, complaint_id) | Mark escalated |
| raise_bill_dispute(dob, reason) | Dispute on current bill |
| save_session(dob, session_data) | Append to session_history |

---

## Gemini Tool Calling (chain.py)
Turn 1 → Gemini decides tool → function_call returned
Python executes tool → db_result
Turn 2 → Gemini gets tool_result → narrates answer in customer's language
Classify call → intent / sentiment / key_points / suggested_action

---

## Multilingual
After auth, bot asks language. Customer says "Tamil" or "தமிழ்" → session["language"] = "ta".
Gemini reasons in English internally, writes response field in target language only.
Supported: en, ta, hi, te, kn, bn, ml, gu, mr, pa

---

## Frontend Summary Panel
LOCKED → before auth
PARTIAL LIVE → after DOB auth (name, ID, live intents, sentiment)
FULL READY → after End Call (duration, turns, AI summary, key points, agent action)

---

## ElevenLabs Fix
```bash
# Go to elevenlabs.io → Profile → API Keys → regenerate
# Paste in config.env:
ELEVENLABS_API_KEY=sk_...
# If blank → gTTS fallback activates, works for all languages
```

---

## PostgreSQL Switch
```bash
sudo pacman -S postgresql
sudo -u postgres initdb -D /var/lib/postgres/data
sudo systemctl enable --now postgresql
sudo -u postgres createuser --superuser zagot
psql -d postgres -f setup_postgres.sql
# config.env:
DB_BACKEND=postgres
DATABASE_URL=postgresql://zagot@localhost/deepcare
```

---

## Demo Customers
| DOB | Name | Key Scenario |
|---|---|---|
| 15-03-1999 | Arjun Kumar | Unpaid bill + open complaint CMP-001 |
| 20-05-1995 | Priya Sharma | Autopay on, order processing |

---

## Environment
```
Python:  3.11.14  venv: .env3.11
OS:      Arch Linux
GPU:     RTX 4050 6GB — driver crashed, fix: sudo pacman -S nvidia nvidia-utils && sudo reboot
Whisper: faster-whisper small int8 CPU, ~461MB at ~/.cache/whisper/
Run:     sh run.sh
```

---

## Known Issues
1. ElevenLabs 401 — key expired, renew at elevenlabs.io, gTTS fallback active
2. nvidia driver dead — kernel update broke it, needs reinstall
3. STT latency 3-4s on CPU — add filler audio to mask it (TODO)
4. PostgreSQL not yet tested end-to-end (JSON backend works fine)

---

## TODO
- [ ] Filler audio to mask STT/LLM latency
- [ ] Confirmation gate before lodge_complaint / escalate
- [ ] Redis session store for production
- [ ] Renew ElevenLabs key
- [ ] Test PostgreSQL end-to-end
