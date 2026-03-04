# Control Flow — Voice AI Gateway

## Master Flow Diagram

```
START
  │
  ▼
[GRADIO UI boots]
  │── FastAPI server starts (localhost:8000)
  │── Whisper small loads into RAM
  │── ElevenLabs cache pre-generates:
  │     "Welcome! Please say your date of birth."
  │     "Sure, let me check that for you..."
  │     "I'm sorry, could you repeat that?"
  │     "Transferring you to an agent now."
  │── Ollama daemon starts (Gemma 2B loads into VRAM)
  │── n8n starts (localhost:5678)
  │
  ▼
[CALL STARTS]
  │
  ├── Bot speaks: "Welcome! Please say your date of birth."
  │              (ElevenLabs cached audio — instant)
  │
  ▼
[AUTH LOOP]
  │
  ├── User speaks DOB
  │     │
  │     ▼
  │   Whisper transcribes → "my birthday is March 15 1999"
  │     │
  │     ▼
  │   n8n Auth Node:
  │     ├── Regex extract DOB → "15-03-1999"
  │     ├── Lookup db.json customers["15-03-1999"]
  │     │
  │     ├── FOUND →
  │     │     Load customer context into session
  │     │     Bot: "Welcome back, Arjun! How can I help?"
  │     │     → GO TO [CONVERSATION LOOP]
  │     │
  │     └── NOT FOUND →
  │           Bot: "I couldn't find that. Please try again."
  │           Retry counter++
  │           If retry > 3 → escalate to human
  │           → LOOP back
  │
  ▼
[CONVERSATION LOOP]
  │
  ├── User speaks query
  │     │
  │     ▼
  │   Whisper transcribes text
  │     │
  │     ▼
  │   Play filler: "Sure, let me check that for you..."
  │   (async — plays immediately while processing continues)
  │     │
  │     ▼
  │   n8n Intent Router:
  │     │
  │     ├── Keyword pre-filter (fast check):
  │     │     "order","track","deliver" → ORDER intents
  │     │     "bill","payment","charge" → BILLING intents
  │     │     "appointment","doctor","book" → APPT intents
  │     │     "complaint","problem","wrong","frustrated" → COMPLAINT
  │     │     "human","agent","supervisor" → ESCALATE
  │     │     No match → send to Ollama for classification
  │     │
  │     ▼
  │   [INTENT BRANCH]
  │     │
  │     ├── ORDER INTENTS
  │     │     ├── order_status        → READ db.orders[].status
  │     │     ├── order_tracking      → READ db.orders[].tracking
  │     │     ├── refund_request      → CONFIRM → WRITE db.orders[].refund
  │     │     ├── return_replace      → CONFIRM → WRITE db.orders[].return
  │     │     ├── address_change      → CONFIRM → WRITE db.orders[].address
  │     │     └── promo_apply         → WRITE db.orders[].promo
  │     │
  │     ├── BILLING INTENTS
  │     │     ├── current_bill        → READ db.bills[].amount
  │     │     ├── payment_history     → READ db.bills[].history
  │     │     ├── due_date            → READ db.bills[].due_date
  │     │     ├── bill_dispute        → OLLAMA → WRITE db.bills[].dispute
  │     │     └── autopay_setup       → CONFIRM → WRITE db.bills[].autopay
  │     │
  │     ├── APPOINTMENT INTENTS
  │     │     ├── book_appointment    → CHECK slots → WRITE db.appointments[]
  │     │     ├── cancel_appointment  → CONFIRM → WRITE db.appointments[].status
  │     │     ├── reschedule          → CHECK slots → WRITE db.appointments[].datetime
  │     │     ├── get_details         → READ db.appointments[]
  │     │     ├── doctor_availability → READ db.appointments[].slots
  │     │     └── waitlist_add        → WRITE db.appointments[].waitlist
  │     │
  │     └── COMPLAINT INTENTS
  │           ├── lodge_complaint     → OLLAMA → WRITE db.complaints[]
  │           ├── complaint_followup  → OLLAMA → READ db.complaints[]
  │           ├── request_supervisor  → → ESCALATE FLOW
  │           └── feedback            → OLLAMA → WRITE db.complaints[].feedback
  │
  │     ▼
  │   [WRITE CONFIRMATION GATE]
  │     ├── Is this a WRITE operation?
  │     │     YES → Bot reads back: "Just to confirm — [action]. Say YES to proceed."
  │     │             User: "yes" → execute write
  │     │             User: "no"  → cancel, return to loop
  │     │     NO  → Execute read immediately
  │     │
  │     ▼
  │   DB operation executes (Python JSON handler)
  │     │
  │     ▼
  │   Generate response text
  │     │── Simple intents: template string + DB values
  │     │── Complex intents: Ollama generates natural response
  │     │
  │     ▼
  │   Sentiment analysis (keyword-based):
  │     ├── Negative words detected? → flag session
  │     ├── Consecutive frustration? → auto-escalate
  │     └── Update sentiment_trajectory[]
  │     │
  │     ▼
  │   ElevenLabs TTS → audio response
  │     │
  │     ▼
  │   Gradio plays audio + updates transcript panel
  │     │
  │     ▼
  │   Session context updated (append turn)
  │     │
  │   ← LOOP (back to "User speaks query")
  │
  ▼
[ESCALATION FLOW]  (triggered by: request, 3x frustration, 3x auth fail)
  │
  ├── Bot: "Transferring you to an agent. They'll have your full context."
  ├── Session summarizer runs:
  │     ├── Extracts all actions_taken[]
  │     ├── Generates sentiment trajectory string
  │     └── Builds handoff summary card
  ├── Summary card displayed in Gradio UI
  ├── Summary card written to /logs/handoff_{session_id}.json
  └── Call ends
  │
  ▼
[SESSION END]  (triggered by: "goodbye", "bye", "that's all", timeout 30s)
  │
  ├── Bot: "Thank you for calling. Have a great day!"
  ├── Summary card generated (same as escalation)
  ├── db.json written (all pending changes flushed)
  └── Session object cleared

END
```

---

## Error Recovery Flow

```
PARSE ERROR (Gemma returns invalid JSON)
  │
  ├── Retry once with: "Please repeat your request."
  ├── Second failure → fallback template response
  └── Third failure → escalate

LOW CONFIDENCE (Whisper < 0.6)
  │
  └── Bot: "I didn't catch that clearly. Could you repeat?"

UNKNOWN INTENT (no keyword match, Ollama unsure)
  │
  ├── Bot: "I can help with orders, billing, appointments, or complaints.
  │         Which of these can I help you with?"
  └── Present menu options

DB WRITE FAILURE
  │
  ├── Log error to /logs/errors.log
  ├── Bot: "I'm having trouble updating that right now.
  │         I'll flag this for our team."
  └── Add to session.failed_actions[]
```

---

## Confirmation Gate Detail

All WRITE intents pass through this gate before execution:

```python
WRITE_INTENTS = [
    "refund_request", "return_replace", "delivery_address_change",
    "autopay_setup", "book_appointment", "cancel_appointment",
    "reschedule_appointment", "waitlist_add", "lodge_complaint"
]

if intent in WRITE_INTENTS:
    confirmation_text = build_confirmation(intent, params)
    speak(confirmation_text)           # "Confirm: cancel order #4521?"
    user_response = listen()           # Wait for yes/no
    if "yes" in user_response.lower():
        execute_db_write(intent, params)
    else:
        speak("No problem, cancelled.")
```

---

## Sentiment Escalation Trigger

```python
NEGATIVE_KEYWORDS = [
    "frustrated", "angry", "terrible", "useless", "stupid",
    "worst", "never again", "ridiculous", "unacceptable"
]

if consecutive_negative_turns >= 2:
    trigger_escalation()
```
