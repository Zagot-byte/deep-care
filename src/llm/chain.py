"""
chain.py — Direct Gemini 2.0 Flash call. No LangChain.
"""

import os, json
import google.generativeai as genai
from dotenv import load_dotenv
from src.db.db_handler import (
    get_order_status, get_order_tracking, get_current_bill,
    get_payment_history, get_complaint_status,
    create_complaint, escalate_complaint
)

load_dotenv("config.env")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

PROMPT = """You are Deep Care, a professional voice customer service AI speaking with {customer_name}.

Customer context:
{customer_context}

History:
{history}

INTENTS: order_status | order_tracking | current_bill | payment_history | complaint_status | lodge_complaint | escalate | goodbye | general

Customer said: "{transcript}"

Return ONLY valid JSON, no markdown:
{{
  "intent": "...",
  "params": {{}},
  "sentiment": "positive|neutral|negative",
  "response": "1-2 sentence voice reply",
  "key_points": ["point1"],
  "suggested_action": "what agent should do",
  "summary_text": "one sentence summary"
}}"""

def execute_db_tool(intent, params, customer_dob):
    try:
        if intent == "order_status":
            return get_order_status(customer_dob, params.get("order_id"))
        elif intent == "order_tracking":
            return get_order_tracking(customer_dob, params.get("order_id"))
        elif intent == "current_bill":
            return get_current_bill(customer_dob)
        elif intent == "payment_history":
            return get_payment_history(customer_dob)
        elif intent == "complaint_status":
            return get_complaint_status(customer_dob, params.get("complaint_id"))
        elif intent == "lodge_complaint":
            return create_complaint(customer_dob, params.get("issue", "Issue reported"))
        elif intent == "escalate":
            return escalate_complaint(customer_dob, params.get("complaint_id", ""))
        else:
            return {}
    except Exception as e:
        print(f"[DB] {e}")
        return {}

def run_chain(transcript, customer_dob, customer_name, customer_context, history=""):
    try:
        prompt = PROMPT.format(
            transcript       = transcript,
            customer_name    = customer_name,
            customer_context = customer_context,
            history          = history or "No previous turns."
        )
        resp = model.generate_content(prompt)
        raw  = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
        result = json.loads(raw)
    except Exception as e:
        print(f"[Gemini] {e}")
        result = {
            "intent": "general", "params": {}, "sentiment": "neutral",
            "response": "I'm having trouble right now. Could you repeat that?",
            "key_points": [], "suggested_action": "Review logs.", "summary_text": "Error."
        }

    intent    = result.get("intent", "general")
    db_result = execute_db_tool(intent, result.get("params", {}), customer_dob)

    return {**result, "db_result": db_result}