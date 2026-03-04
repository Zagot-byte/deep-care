"""
chain.py — LangChain fixed pipeline
Gemini 2.0 Flash handles intent classification + response generation
Python tools handle all DB operations
No n8n. No webhooks. One straight chain.
"""

import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv("config.env")

# ── MODEL ─────────────────────────────────────────────────
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3,
    max_tokens=300,
)


# ── OUTPUT SCHEMA ──────────────────────────────────────────
class IntentOutput(BaseModel):
    intent: str = Field(description="One of the 10 intents below")
    params: dict = Field(description="Extracted params like order_id, complaint text")
    sentiment: str = Field(description="positive, neutral, or negative")


class ResponseOutput(BaseModel):
    response: str = Field(description="Natural language reply under 2 sentences")
    key_points: list = Field(description="1-3 key points from this interaction")
    suggested_action: str = Field(description="What the human agent should do next")
    summary_text: str = Field(description="One sentence summary of this turn")


# ── STEP 1: INTENT CLASSIFIER CHAIN ───────────────────────
INTENT_SYSTEM = """You are an intent classifier for a voice customer service system.
Given a customer transcript, return JSON with intent, params, and sentiment.

INTENTS (pick exactly one):
- order_status        → customer asking about order / delivery
- order_tracking      → customer asking for tracking number
- current_bill        → customer asking about bill amount or due date
- payment_history     → customer asking about past payments
- complaint_status    → customer asking about existing complaint
- lodge_complaint     → customer reporting a new problem or issue
- escalate            → customer wants human agent or supervisor
- goodbye             → customer ending the call
- confirm_yes         → customer saying yes to confirm an action
- general             → anything else

PARAMS to extract:
- order_id: if mentioned (e.g. "ORD-4521")
- complaint_id: if mentioned (e.g. "CMP-001")
- issue: for lodge_complaint — the complaint text

SENTIMENT:
- negative: frustrated, angry, problem, wrong, terrible
- positive: thanks, great, happy, resolved
- neutral: everything else

Return ONLY valid JSON. No markdown. No explanation."""

INTENT_HUMAN = """Customer said: "{transcript}"
Conversation so far: {history}

Return JSON only."""

intent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", INTENT_SYSTEM),
        ("human", INTENT_HUMAN),
    ]
)

intent_chain = intent_prompt | llm | JsonOutputParser()


# ── STEP 2: DB TOOL EXECUTOR ───────────────────────────────
# Import all DB handlers
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.db.db_handler import (
    get_order_status,
    get_order_tracking,
    get_current_bill,
    get_payment_history,
    get_complaint_status,
    create_complaint,
    escalate_complaint,
)


def execute_db_tool(intent: str, params: dict, customer_dob: str) -> dict:
    """
    Executes the right DB operation based on intent.
    Returns dict with db_result and action_taken.
    """
    try:
        if intent == "order_status":
            result = get_order_status(customer_dob, params.get("order_id"))
            return {"db_result": result, "action": "READ orders"}

        elif intent == "order_tracking":
            result = get_order_tracking(customer_dob, params.get("order_id"))
            return {"db_result": result, "action": "READ orders.tracking"}

        elif intent == "current_bill":
            result = get_current_bill(customer_dob)
            return {"db_result": result, "action": "READ bills"}

        elif intent == "payment_history":
            result = get_payment_history(customer_dob)
            return {"db_result": result, "action": "READ payment_history"}

        elif intent == "complaint_status":
            result = get_complaint_status(customer_dob, params.get("complaint_id"))
            return {"db_result": result, "action": "READ complaints"}

        elif intent == "lodge_complaint":
            issue = params.get("issue", "Customer reported an issue")
            result = create_complaint(customer_dob, issue)
            return {"db_result": result, "action": "WRITE complaints.create"}

        elif intent == "escalate":
            result = escalate_complaint(customer_dob, params.get("complaint_id"))
            return {"db_result": result, "action": "WRITE complaints.escalate"}

        else:
            return {"db_result": {}, "action": None}

    except Exception as e:
        print(f"[DB Tool Error] {e}")
        return {"db_result": {}, "action": None}


# ── STEP 3: RESPONSE GENERATOR CHAIN ──────────────────────
RESPONSE_SYSTEM = """You are Deep Care, a professional voice customer service AI.
You are speaking with {customer_name}.

Customer context:
{customer_context}

DB result for this query:
{db_result}

Rules:
- Reply in 1-2 sentences ONLY. This is a voice call — be concise.
- Be warm and professional. Never robotic.
- Use actual data from DB result above — never make up numbers or IDs.
- If DB result is empty, say you'll look into it.
- For complaints: be empathetic first, then practical.
- For escalation: confirm transfer warmly.

Return ONLY valid JSON. No markdown. No explanation."""

RESPONSE_HUMAN = """Customer said: "{transcript}"
Intent detected: {intent}

Return JSON with: response, key_points (list), suggested_action, summary_text"""

response_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", RESPONSE_SYSTEM),
        ("human", RESPONSE_HUMAN),
    ]
)

response_chain = response_prompt | llm | JsonOutputParser()


# ── MASTER CHAIN ───────────────────────────────────────────
def run_chain(
    transcript: str,
    customer_dob: str,
    customer_name: str,
    customer_context: str,
    history: str = "",
) -> dict:
    """
    Full pipeline:
    1. Classify intent
    2. Execute DB tool
    3. Generate response

    Returns complete result dict.
    """

    # Step 1 — Intent classification
    try:
        intent_result = intent_chain.invoke(
            {
                "transcript": transcript,
                "history": history or "No previous turns.",
            }
        )
    except Exception as e:
        print(f"[Intent Chain Error] {e}")
        intent_result = {"intent": "general", "params": {}, "sentiment": "neutral"}

    intent = intent_result.get("intent", "general")
    params = intent_result.get("params", {})
    sentiment = intent_result.get("sentiment", "neutral")

    # Step 2 — DB tool execution
    db_data = execute_db_tool(intent, params, customer_dob)
    db_result = db_data.get("db_result", {})
    action = db_data.get("action")

    # Step 3 — Response generation
    try:
        response_result = response_chain.invoke(
            {
                "transcript": transcript,
                "intent": intent,
                "customer_name": customer_name,
                "customer_context": customer_context,
                "db_result": json.dumps(db_result, indent=2)
                if db_result
                else "No data found.",
            }
        )
    except Exception as e:
        print(f"[Response Chain Error] {e}")
        response_result = {
            "response": "I'm here to help. Could you repeat that?",
            "key_points": [],
            "suggested_action": "Review interaction logs.",
            "summary_text": "Error in processing.",
        }

    return {
        "intent": intent,
        "params": params,
        "sentiment": sentiment,
        "action": action,
        "db_result": db_result,
        "response": response_result.get("response", ""),
        "key_points": response_result.get("key_points", []),
        "suggested_action": response_result.get("suggested_action", ""),
        "summary_text": response_result.get("summary_text", ""),
    }

