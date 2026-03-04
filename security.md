# Security — Voice AI Gateway

## Threat Model

This is a hackathon MVP. Security is designed to be:
- **Demo-safe**: won't crash or expose data during presentation
- **Architecturally sound**: decisions you'd defend in production
- **Honest about limitations**: no security theatre

---

## Authentication

### Current Implementation (MVP)
Date of birth spoken → matched against JSON DB.

**Known weaknesses:**
- DOB is semi-public information (social media, public records)
- No voice biometrics — anyone who knows your DOB can access account
- No rate limiting on failed attempts (beyond 3-retry soft lock)

**Production upgrade path:**
- Add voice biometric layer (speaker verification model e.g. SpeechBrain)
- OTP via SMS as second factor before sensitive write operations
- Account lockout after N failed attempts with cooldown

### Retry Lockout (Implemented in MVP)
```python
MAX_AUTH_ATTEMPTS = 3
if auth_failures >= MAX_AUTH_ATTEMPTS:
    speak(FILLER_PHRASES["transfer"])
    trigger_human_escalation()
```

---

## LLM Write Access Control

### The Core Risk
An LLM suggesting DB writes is dangerous if:
- It hallucinates wrong parameters (wrong order ID, wrong amount)
- It misinterprets ambiguous language ("I was thinking of cancelling" ≠ cancel)
- Prompt injection via user speech manipulates it into unintended actions

### Mitigation: Confirmation Gate (Implemented)
ALL write operations require explicit verbal YES before execution:
```
Bot: "Just to confirm — cancel order #4521 for Laptop Stand. Say YES to proceed."
User: "yes"
→ Python executes write (not Gemma)
```
Gemma **suggests** the action. Python **executes** it. They are separate.

### Mitigation: Bounded Action Set
Gemma can only output actions from a hardcoded enum:
```python
ALLOWED_ACTIONS = {
    "READ orders", "WRITE orders.refund", "WRITE orders.return",
    "READ bills", "WRITE bills.dispute", "WRITE bills.autopay",
    "READ appointments", "WRITE appointments.book",
    "WRITE appointments.cancel", "WRITE appointments.reschedule",
    "READ complaints", "WRITE complaints.lodge",
    "WRITE complaints.feedback", "ESCALATE"
}

if parsed["action"] not in ALLOWED_ACTIONS:
    log_security_event("unknown_action", parsed["action"])
    fallback_response()
```

### Mitigation: Prompt Injection Defense
User input is never concatenated raw into the system prompt:
```python
# WRONG — injectable
system_prompt = f"Customer said: {user_input}"

# CORRECT — sandboxed
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": f'Customer just said: "{user_input}"\nRespond with JSON only.'}
]
```
The user turn is always wrapped and role-separated from system instructions.

---

## Data Security

### Mock DB (MVP)
- Plain JSON file, no encryption
- Acceptable for demo (no real PII)
- `db.json` is in `.gitignore` — never committed

### Production Upgrade Path
- Encrypt at rest (AES-256)
- Never log raw transcripts containing PII
- Anonymize session logs before storage
- GDPR: right to deletion — implement `DELETE /customer/{dob}` endpoint

### What We Log (MVP)
```
/logs/sessions/session_{id}.json     ← actions taken, sentiment
/logs/handoffs/handoff_{id}.json     ← summary cards
/logs/errors/error_{timestamp}.log   ← parse failures, DB errors
```

**Never logged:**
- Raw audio files
- Full transcripts with PII
- Authentication attempts (DOB values)

---

## API Security

### ElevenLabs API Key
```python
# WRONG — hardcoded
ELEVENLABS_KEY = "sk_abc123..."

# CORRECT — environment variable
import os
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_API_KEY")
if not ELEVENLABS_KEY:
    raise EnvironmentError("ELEVENLABS_API_KEY not set")
```
Key stored in `.env`, never in source code, `.env` in `.gitignore`.

### n8n Webhook Security
- Webhook URL includes a secret token: `/webhook/{SECRET_TOKEN}`
- FastAPI verifies token before forwarding to n8n
- n8n runs on localhost only — not exposed externally

### FastAPI
- CORS restricted to `localhost:7860` (Gradio only) in demo mode
- No auth on FastAPI endpoints in MVP (local only — acceptable)
- Production: add JWT bearer tokens per session

---

## Input Validation

### Audio Input
```python
MAX_AUDIO_DURATION_SECONDS = 30
MAX_AUDIO_SIZE_BYTES = 5 * 1024 * 1024  # 5MB

if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
    return {"error": "Audio too large"}
```

### Transcript Sanitization
```python
import re

def sanitize_transcript(text: str) -> str:
    # Remove any injected special characters
    text = text.strip()[:500]  # Max 500 chars
    text = re.sub(r'[<>{}\[\]]', '', text)  # Remove brackets
    return text
```

---

## What to Tell Judges

Be upfront about these limitations — it shows engineering maturity:

> "DOB authentication is intentionally simplified for the MVP. In production
> we'd layer in voice biometrics and OTP. More importantly, note the
> confirmation gate on all write operations — the LLM proposes, the human
> confirms, Python executes. The AI never has unchecked write access.
> That's the right architecture regardless of demo constraints."

---

## Security Checklist Before Demo

- [ ] `.env` file created with API keys (not hardcoded)
- [ ] `db.json` in `.gitignore`
- [ ] n8n webhook token set and verified
- [ ] Max auth retry (3) tested and working
- [ ] Confirmation gate tested for all write intents
- [ ] No real PII in mock db.json
- [ ] Error logs not displaying PII in Gradio UI
-
