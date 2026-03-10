"""
chain.py — Gemini 2.0 Flash with native function calling.
Single API call per turn — classification folded into main prompt.
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
MODEL  = "models/gemini-2.0-flash"

LANG_NAMES = {
    "en": "English", "ta": "Tamil",  "hi": "Hindi",
    "te": "Telugu",  "kn": "Kannada","bn": "Bengali",
    "ml": "Malayalam","gu": "Gujarati","mr": "Marathi","pa": "Punjabi",
}

LANG_FALLBACKS = {
    "en": ("I'm sorry, I didn't catch that. Could you please repeat?",
           "I'm having trouble right now. Could you repeat that?"),
    "ta": ("மன்னிக்கவும், எனக்கு புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
           "இப்போது சிக்கல் உள்ளது. மீண்டும் சொல்லுங்கள்."),
    "hi": ("माफ़ कीजिए, मुझे समझ नहीं आया। क्या आप दोबारा कह सकते हैं?",
           "अभी कुछ समस्या हो रही है। क्या आप दोबारा बोल सकते हैं?"),
    "te": ("క్షమించండి, నాకు అర్థం కాలేదు. మళ్ళీ చెప్పగలరా?",
           "ప్రస్తుతం సమస్య ఉంది. మళ్ళీ చెప్పండి."),
    "kn": ("ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
           "ಈಗ ತೊಂದರೆ ಆಗುತ್ತಿದೆ. ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ."),
    "bn": ("দুঃখিত, আমি বুঝতে পারিনি। আবার বলতে পারবেন?",
           "এখন সমস্যা হচ্ছে। আবার বলুন।"),
    "ml": ("ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. വീണ്ടും പറയാമോ?",
           "ഇപ്പോൾ ബുദ്ധിമുട്ടുണ്ട്. വീണ്ടും പറയൂ."),
    "gu": ("માફ કરો, મને સમજાયું નહીં. ફરીથી કહી શકો છો?",
           "અત્યારે સમસ્યા છે. ફરી કહો."),
    "mr": ("माफ करा, मला समजले नाही. पुन्हा सांगाल का?",
           "आत्ता अडचण येत आहे. पुन्हा सांगा."),
    "pa": ("ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਕੀ ਤੁਸੀਂ ਦੁਬਾਰਾ ਕਹਿ ਸਕਦੇ ਹੋ?",
           "ਹੁਣ ਸਮੱਸਿਆ ਹੋ ਰਹੀ ਹੈ। ਦੁਬਾਰਾ ਕਹੋ."),
}

def _fallback_didnt_catch(lang): return LANG_FALLBACKS.get(lang, LANG_FALLBACKS["en"])[0]
def _fallback_trouble(lang):     return LANG_FALLBACKS.get(lang, LANG_FALLBACKS["en"])[1]

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
        description="Get status of existing complaints. Omit complaint_id to get ALL complaints.",
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

_INTENT_ALIASES = {
    "order_status":     "get_order_status",
    "order_tracking":   "get_order_tracking",
    "current_bill":     "get_current_bill",
    "payment_history":  "get_payment_history",
    "complaint_status": "get_complaint_status",
    "lodge_complaint":  "create_complaint",
    "escalate":         "escalate_complaint",
    "bill_dispute":     "raise_bill_dispute",
}

def execute_db_tool(fn_name: str, fn_args: dict, customer_dob: str) -> dict:
    fn_name = _INTENT_ALIASES.get(fn_name, fn_name)
    print(f"[TOOL] → {fn_name}({fn_args})")
    try:
        if fn_name == "get_order_status":
            return get_order_status(customer_dob, fn_args.get("order_id"))
        elif fn_name == "get_order_tracking":
            return get_order_tracking(customer_dob, fn_args.get("order_id", ""))
        elif fn_name == "get_current_bill":
            return get_current_bill(customer_dob)
        elif fn_name == "get_payment_history":
            return get_payment_history(customer_dob)
        elif fn_name == "get_complaint_status":
            return get_complaint_status(customer_dob, fn_args.get("complaint_id"))
        elif fn_name == "create_complaint":
            return create_complaint(customer_dob, fn_args.get("issue", "Issue reported by customer"))
        elif fn_name == "escalate_complaint":
            return escalate_complaint(customer_dob, fn_args.get("complaint_id", ""))
        elif fn_name == "raise_bill_dispute":
            return raise_bill_dispute(customer_dob, fn_args.get("reason", "Customer disputes the bill"))
        else:
            return {}
    except Exception as e:
        print(f"[TOOL] Error in {fn_name}: {e}")
        return {}

# ── Mock detection ───────────────────────────────────────────

def _is_mock_response(r) -> bool:
    candidates = getattr(r, "candidates", None)
    if isinstance(candidates, list) and len(candidates) > 0:
        return False
    text = getattr(r, "text", None)
    return isinstance(text, str) and len(text) > 0

# ── Intent inference from tool name ─────────────────────────

_FN_TO_INTENT = {
    "get_order_status":    "order_status",
    "get_order_tracking":  "order_tracking",
    "get_current_bill":    "current_bill",
    "get_payment_history": "payment_history",
    "get_complaint_status":"complaint_status",
    "create_complaint":    "lodge_complaint",
    "escalate_complaint":  "escalate",
    "raise_bill_dispute":  "bill_dispute",
}

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

    # Classification instructions folded into Turn 2 prompt
    # so we only use 2 API calls max (Turn1 + Turn2) instead of 3
    classify_suffix = """

After answering the customer, append exactly this JSON block on a new line:
###META###
{"intent":"<one of: order_status|order_tracking|current_bill|payment_history|complaint_status|lodge_complaint|escalate|bill_dispute|goodbye|general>","sentiment":"<positive|neutral|negative>","key_points":["up to 3 short points"],"suggested_action":"<one line for human agent>","summary_text":"<one sentence English summary>"}"""

    system_prompt = f"""You are Deep Care, a professional voice AI customer service agent.
You are speaking with {customer_name}.

CUSTOMER DATA:
{customer_context}

CONVERSATION HISTORY:
{history or "No previous turns."}

LANGUAGE:
- Customer speaks: {lang_name}
- Reason internally in English always
- Write your spoken response in {lang_name} only
- Keep spoken response to 1-2 sentences (voice channel)

STRICT RULES:
- NEVER invent order IDs, bill amounts, complaint numbers, or dates
- ALWAYS call a tool before stating any specific data
- If a tool returns an error, say you will look into it — do NOT guess
- Only state facts that came from tool results"""

    user_turn = f'Customer said: "{transcript}"'
    db_result = {}
    fn_name   = None
    bot_reply = ""
    intent           = "general"
    sentiment        = "neutral"
    key_points       = []
    suggested_action = ""
    summary_text     = "Turn completed."

    _intent_to_tool = {
        "order_status":     "get_order_status",
        "order_tracking":   "get_order_tracking",
        "current_bill":     "get_current_bill",
        "payment_history":  "get_payment_history",
        "complaint_status": "get_complaint_status",
        "lodge_complaint":  "create_complaint",
        "escalate":         "escalate_complaint",
        "bill_dispute":     "raise_bill_dispute",
    }

    try:
        # ── Turn 1: tool selection ────────────────────────────
        r1 = client.models.generate_content(
            model    = MODEL,
            contents = [types.Content(role="user", parts=[
                types.Part(text=system_prompt + "\n\n" + user_turn)
            ])],
            config = types.GenerateContentConfig(
                tools       = [TOOLS],
                tool_config = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="AUTO")
                ),
                temperature = 0.3,
            )
        )

        if _is_mock_response(r1):
            # ── Test / mock path ──────────────────────────────
            raw         = r1.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed      = json.loads(raw)
            bot_reply   = parsed.get("response", "")
            mock_intent = parsed.get("intent", "general")
            mock_params = parsed.get("params", {})
            fn_name     = _intent_to_tool.get(mock_intent)
            if fn_name:
                db_result = execute_db_tool(fn_name, mock_params, customer_dob)
            intent    = mock_intent
            sentiment = parsed.get("sentiment", "neutral")

        else:
            # ── Real Gemini path ──────────────────────────────
            candidate   = r1.candidates[0]
            tool_called = False

            for part in candidate.content.parts:
                if getattr(part, "thought", None) or getattr(part, "thought_signature", None):
                    continue
                fc = getattr(part, "function_call", None)
                if fc is not None and getattr(fc, "name", None):
                    tool_called = True
                    fn_name   = fc.name
                    fn_args   = dict(fc.args) if fc.args else {}
                    db_result = execute_db_tool(fn_name, fn_args, customer_dob)
                    intent    = _FN_TO_INTENT.get(fn_name, "general")

                    # ── Turn 2: narrate result + classify ─────
                    r2 = client.models.generate_content(
                        model    = MODEL,
                        contents = [
                            types.Content(role="user", parts=[
                                types.Part(text=system_prompt + classify_suffix + "\n\n" + user_turn)
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
                    raw2 = r2.text.strip() if r2.text else ""
                    if "###META###" in raw2:
                        parts2       = raw2.split("###META###", 1)
                        bot_reply    = parts2[0].strip()
                        try:
                            meta         = json.loads(parts2[1].strip())
                            intent       = meta.get("intent", intent)
                            sentiment    = meta.get("sentiment", "neutral")
                            key_points   = meta.get("key_points", [])
                            suggested_action = meta.get("suggested_action", "")
                            summary_text = meta.get("summary_text", "")
                        except Exception:
                            pass
                    else:
                        bot_reply = raw2
                    break

            if not tool_called:
                # No tool needed — general/empathy response
                # Ask Gemini to respond + classify in one shot
                r_gen = client.models.generate_content(
                    model    = MODEL,
                    contents = [types.Content(role="user", parts=[
                        types.Part(text=system_prompt + classify_suffix + "\n\n" + user_turn)
                    ])],
                    config = types.GenerateContentConfig(temperature=0.3)
                )
                raw_gen = r_gen.text.strip() if r_gen.text else ""
                if "###META###" in raw_gen:
                    parts_gen    = raw_gen.split("###META###", 1)
                    bot_reply    = parts_gen[0].strip()
                    try:
                        meta         = json.loads(parts_gen[1].strip())
                        intent       = meta.get("intent", "general")
                        sentiment    = meta.get("sentiment", "neutral")
                        key_points   = meta.get("key_points", [])
                        suggested_action = meta.get("suggested_action", "")
                        summary_text = meta.get("summary_text", "")
                    except Exception:
                        pass
                else:
                    bot_reply = raw_gen

                if not bot_reply:
                    bot_reply = _fallback_didnt_catch(lang)

    except Exception as e:
        print(f"[Gemini] {e}")
        bot_reply = _fallback_trouble(lang)

    return {
        "response":         bot_reply,
        "intent":           intent,
        "sentiment":        sentiment,
        "params":           {},
        "key_points":       key_points,
        "suggested_action": suggested_action,
        "summary_text":     summary_text,
        "db_result":        db_result,
        "tool_called":      fn_name,
    }
