"""
summary_generator.py — Agent handoff summary card builder
"""

from datetime import datetime


def generate_summary(session: dict, n8n_data: dict = None) -> dict:
    """Builds the handoff summary card from session + optional n8n fields."""

    start = datetime.fromisoformat(session["start_time"])
    duration_secs = int((datetime.now() - start).total_seconds())
    duration_str = f"{duration_secs // 60}m {duration_secs % 60}s"

    trajectory = session.get("sentiment_trajectory", ["neutral"])
    if "negative" in trajectory:
        final_sentiment = "negative"
    elif "positive" in trajectory:
        final_sentiment = "positive"
    else:
        final_sentiment = "neutral"

    key_points = n8n_data.get("key_points") if n8n_data else None
    if not key_points:
        key_points = [t["bot"][:80] for t in session["turns"][-4:] if t.get("bot")]

    suggested = n8n_data.get("suggested_action") if n8n_data else None
    if not suggested:
        if "negative" in trajectory or session.get("escalated"):
            suggested = "Customer showed frustration — proactive follow-up recommended within 24 hours."
        elif "complaint" in session.get("intents_seen", []):
            suggested = "Review complaint ticket and ensure resolution within SLA."
        else:
            suggested = "No immediate follow-up needed."

    turns = session.get("turns", [])
    intents = session.get("intents_seen", [])

    return {
        "name":             session.get("customer_name", "Unknown"),
        "customer_id":      session.get("customer_id", "—"),
        "dob":              session.get("customer_dob", "—"),
        "duration":         duration_str,
        "time":             datetime.now().strftime("%H:%M:%S"),
        "sentiment":        final_sentiment,
        "intents":          intents,
        "summary":          (n8n_data.get("summary_text") if n8n_data
                             else f"Customer contacted support with {len(intents)} query type(s) across {len(turns)} turns."),
        "key_points":       key_points,
        "suggested_action": suggested,
        "escalated":        session.get("escalated", False)
    }
