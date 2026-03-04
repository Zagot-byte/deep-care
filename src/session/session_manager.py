"""
session_manager.py — In-memory session store
"""

from datetime import datetime

SESSION_STORE: dict = {}


def create_session(session_id: str) -> dict:
    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "authenticated": False,
        "customer_dob": None,
        "customer_name": None,
        "customer_id": None,
        "start_time": datetime.now().isoformat(),
        "turns": [],
        "intents_seen": [],
        "sentiment_trajectory": [],
        "escalated": False
    }
    return SESSION_STORE[session_id]


def get_session(session_id: str) -> dict | None:
    return SESSION_STORE.get(session_id)


def set_authenticated(session_id: str, customer: dict, dob: str) -> None:
    s = SESSION_STORE[session_id]
    s["authenticated"] = True
    s["customer_dob"] = dob
    s["customer_name"] = customer["name"]
    s["customer_id"] = customer["customer_id"]


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
    s = SESSION_STORE.get(session_id, {})
    turns = s.get("turns", [])[-n:]
    return "\n".join([f"User: {t['user']}\nBot: {t['bot']}" for t in turns])
