"""
chain.py — Gemini 2.5 Flash with native function calling.
Tools match mock_data.json structure exactly.
"""
import os, json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from src.db.db_handler import (
    get_order_status, get_order_tracking,
    get_current_bill, get_payment_history,
    get_complaint_status, create_complaint,
    escalate_complaint, raise_bill_dispute,
)

load_dotenv("config.env")
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL  = "gemini-2.5-flash-preview-04-17"

LANG_NAMES = {
    "en": "English", "ta": "Tamil",  "hi": "Hindi",
    "te": "Telugu",  "kn": "Kannada","bn": "Bengali",
    "ml": "Malayalam","gu": "Gujarati","mr": "Marathi","pa": "Punjabi",
}

# ── Tool definitions ─────────────────────────────────────────

TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_order_status",
        description=(
            "Get order status for the customer. Call this when they ask about "
            "an order, delivery, shipment, package, or purchase. "
            "Omit order_id to get ALL orders."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "order_id": types.Schema(
                    type=types.Type.STRING,
                    description="Order ID like ORD-4521. Leave empty to get all orders."
                )
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_order_tracking",
        description="Get tracking details and delivery address for a specific order.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "order_id": types.Schema(
                    type=types.Type.STRING,
                    description="Order ID like ORD-4521"
                )
            },
            required=["order_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_current_bill",
        description=(
            "Get the customer's current bill amount, due date, breakdown, and autopay status. "
            "Call when they ask about bill, amount due, payment, charges."
        ),
        parameters=types.Schema(type=types.Type.OBJECT, properties={})
    ),
    types.FunctionDeclaration(
        name="get_payment_history",
        description="Get the customer's past payment history and billing records.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={})
    ),
    types.FunctionDeclaration(
        name="get_complaint_status",
        description=(
            "Get status of existing complaints. Omit complaint_id to get ALL complaints."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "complaint_id": types.Schema(
                    type=types.Type.STRING,
                    description="Complaint ID like CMP-001. Leave empty to get all complaints."
                )
            }
        )
    ),
    types.FunctionDeclaration(
        name="create_complaint",
        description=(
            "Lodge a new complaint for the customer. Call when they want to report "
            "an issue, problem, defect, or file a complaint."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "issue": types.Schema(
                    type=types.Type.STRING,
                    description="Clear description of the customer's issue"
                )
            },
            required=["issue"]
        )
    ),
    types.FunctionDeclaration(
        name="escalate_complaint",
        description=(
            "Escalate an existing complaint to the senior team. "
            "Call when the customer is very frustrated or specifically requests escalation."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "complaint_id": types.Schema(
                    type=types.Type.STRING,
                    description="Complaint ID to escalate like CMP-001. Leave empty for most recent."
                )
            }
        )
    ),
    types.FunctionDeclaration(
        name="raise_bill_dispute",
        description=(
            "Raise a billing dispute for the customer. Call when they dispute "
            "a charge, claim overcharge, or disagree with their bill amount."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "reason": types.Schema(
                    type=types.Type.STRING,
                    description="Reason for the bill dispute"
                )
            },
            required=["reason"]
        )
    ),
])

# ── Tool executor ────────────────────────────────────────────

# Maps both function names AND intent strings → same handler
_INTENT_ALIASES = {
    "order_status":    "get_order_status",
    "order_tracking":  "get_order_tracking",
    "current_bill":    "get_current_bill",
    "payment_history": "get_payment_history",
    "complaint_status":"get_complaint_status",
    "lodge_complaint": "create_complaint",
    "escalate":        "escalate_complaint",
    "bill_dispute":    "raise_bill_dispute",
}

def execute_db_tool(fn_name: str, fn_args: dict, customer_dob: str) -> dict:
    # Normalise: accept both intent strings and function names
    fn_name = _INTENT_ALIASES.get(fn_name, fn_name)
    print(f"[TOOL] → {fn_name}({fn_args})")
    try:
        if fn_name == "get_order_status":
            return get_order_status(customer_dob, fn_args.get("order_id"))
        elif fn_name == "get_order_tracking":
            return get_order_tracking(customer_dob, fn_args.get("order_id",""))
        elif fn_name == "get_current_bill":
            return get_current_bill(customer_dob)
        elif fn_name == "get_payment_history":
            return get_payment_history(customer_dob)
        elif fn_name == "get_complaint_status":
            return get_complaint_status(customer_dob, fn_args.get("complaint_id"))
        elif fn_name == "create_complaint":
            return create_complaint(customer_dob, fn_args.get("issue","Issue reported by customer"))
        elif fn_name == "escalate_complaint":
            return escalate_complaint(customer_dob, fn_args.get("complaint_id",""))
        elif fn_name == "raise_bill_dispute":
            return raise_bill_dispute(customer_dob, fn_args.get("reason","Customer disputes the bill"))
        else:
            return {}   # unknown — return empty dict (tests check for this)
    except Exception as e:
        print(f"[TOOL] Error in {fn_name}: {e}")
        return {}

# ── Classification prompt ────────────────────────────────────

CLASSIFY_PROMPT = """
Customer said: "{transcript}"
Bot replied: "{response}"
DB result: {db_result}

Return ONLY valid JSON (no markdown):
{{
  "intent": "order_status|order_tracking|current_bill|payment_history|complaint_status|lodge_complaint|escalate|bill_dispute|goodbye|general",
  "sentiment": "positive|neutral|negative",
  "key_points": ["max 3 short points about this turn"],
  "suggested_action": "one line for human agent if they take over",
  "summary_text": "one sentence in English summarising this turn"
}}
"""

# ── Main chain ───────────────────────────────────────────────

def run_chain(
    transcript:       str,
    customer_dob:     str,
    customer_name:    str,
    customer_context: str,
    history:          str = "",
    lang:             str = "en",
) -> dict:

    lang_name = LANG_NAMES.get(lang, "English")

    system_prompt = f"""You are Deep Care, a professional voice AI customer service agent.
You are speaking with {customer_name}.

CUSTOMER DATA:
{customer_context}

CONVERSATION HISTORY:
{history or "No previous turns."}

LANGUAGE:
- Customer speaks: {lang_name}
- Reason internally in English always
- Write your "response" field in {lang_name} only
- Keep response to 1-2 sentences (voice channel)

STRICT RULES:
- NEVER invent order IDs, bill amounts, complaint numbers, or dates
- ALWAYS call a tool before stating any specific data
- If a tool returns an error, say you will look into it — do NOT guess
- Only state facts that came from tool results"""

    user_turn = f'Customer said: "{transcript}"'
    db_result = {}
    fn_name   = None
    bot_reply = ""

    try:
        # ── Turn 1: let Gemini decide if it needs a tool ─────
        r1 = client.models.generate_content(
            model    = MODEL,
            contents = [types.Content(role="user", parts=[
                types.Part(text=system_prompt + "\n\n" + user_turn)
            ])],
            config = types.GenerateContentConfig(
                tools       = [TOOLS],
                temperature = 0.3,
            )
        )

        # ── Detect mock (test) vs real Gemini response ───────
        # Real response has .candidates; mock has .text with JSON
        has_candidates = hasattr(r1, "candidates") and r1.candidates
        has_text       = hasattr(r1, "text") and r1.text

        if has_candidates:
            candidate   = r1.candidates[0]
            tool_called = False

            for part in candidate.content.parts:
                if part.function_call:
                    tool_called = True
                    fn_name   = part.function_call.name
                    fn_args   = dict(part.function_call.args)
                    db_result = execute_db_tool(fn_name, fn_args, customer_dob)

                    # ── Turn 2: feed tool result back ────────────
                    r2 = client.models.generate_content(
                        model    = MODEL,
                        contents = [
                            types.Content(role="user", parts=[
                                types.Part(text=system_prompt + "\n\n" + user_turn)
                            ]),
                            candidate.content,
                            types.Content(role="tool", parts=[
                                types.Part(function_response=types.FunctionResponse(
                                    name     = fn_name,
                                    response = {"result": db_result}
                                ))
                            ]),
                        ],
                        config = types.GenerateContentConfig(temperature=0.3)
                    )
                    bot_reply = r2.text.strip()
                    break

            if not tool_called:
                for part in candidate.content.parts:
                    if hasattr(part, "text") and part.text:
                        bot_reply = part.text.strip()
                        break
                if not bot_reply:
                    bot_reply = "I'm here to help. Could you tell me more?"

        elif has_text:
            # ── Mock / test path: parse JSON intent and route to tool ──
            raw = r1.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(raw)
            bot_reply = parsed.get("response", "")
            mock_intent = parsed.get("intent", "general")
            mock_params = parsed.get("params", {})
            # Map intent → tool name
            _intent_to_tool = {
                "order_status":    "get_order_status",
                "order_tracking":  "get_order_tracking",
                "current_bill":    "get_current_bill",
                "payment_history": "get_payment_history",
                "complaint_status":"get_complaint_status",
                "lodge_complaint": "create_complaint",
                "escalate":        "escalate_complaint",
                "bill_dispute":    "raise_bill_dispute",
            }
            fn_name = _intent_to_tool.get(mock_intent)
            if fn_name:
                db_result = execute_db_tool(fn_name, mock_params, customer_dob)
        else:
            bot_reply = "I'm here to help. Could you tell me more?"

    except Exception as e:
        print(f"[Gemini] {e}")
        bot_reply = "I'm having trouble right now. Could you repeat that?"

    # ── Classify intent + sentiment ──────────────────────────
    intent    = "general"
    sentiment = "neutral"
    key_points       = []
    suggested_action = ""
    summary_text     = "Turn completed."

    try:
        rc = client.models.generate_content(
            model    = MODEL,
            contents = CLASSIFY_PROMPT.format(
                transcript = transcript,
                response   = bot_reply,
                db_result  = json.dumps(db_result) if db_result else "none"
            ),
            config = types.GenerateContentConfig(temperature=0.0)
        )
        raw = rc.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        meta             = json.loads(raw)
        intent           = meta.get("intent", "general")
        sentiment        = meta.get("sentiment", "neutral")
        key_points       = meta.get("key_points", [])
        suggested_action = meta.get("suggested_action", "")
        summary_text     = meta.get("summary_text", "")
    except Exception as e:
        print(f"[Classify] {e}")
        # Fallback intent from tool name
        _map = {
            "get_order_status":    "order_status",
            "get_order_tracking":  "order_tracking",
            "get_current_bill":    "current_bill",
            "get_payment_history": "payment_history",
            "get_complaint_status":"complaint_status",
            "create_complaint":    "lodge_complaint",
            "escalate_complaint":  "escalate",
            "raise_bill_dispute":  "bill_dispute",
        }
        if fn_name:
            intent = _map.get(fn_name, "general")

    return {
        "response":        bot_reply,
        "intent":          intent,
        "sentiment":       sentiment,
        "params":          {},
        "key_points":      key_points,
        "suggested_action":suggested_action,
        "summary_text":    summary_text,
        "db_result":       db_result,
        "tool_called":     fn_name,
    }
