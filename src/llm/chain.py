"""
chain.py — Gemini 2.0 Flash, NO tool calling.
Gemini reads customer context directly and returns JSON.
One API call per turn. Fast and reliable.
"""
import os, json, re
from google import genai
from google.genai import types
from dotenv import load_dotenv
from src.db.db_handler import (
    get_order_status, get_order_tracking,
    get_current_bill, get_payment_history,
    get_complaint_status, create_complaint,
    escalate_complaint, raise_bill_dispute,
)


MODEL = "gemini-flash-2.0-lite"

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

_INTENT_TO_DB = {
    "order_status":     "get_order_status",
    "order_tracking":   "get_order_tracking",
    "current_bill":     "get_current_bill",
    "payment_history":  "get_payment_history",
    "complaint_status": "get_complaint_status",
    "lodge_complaint":  "create_complaint",
    "escalate":         "escalate_complaint",
    "bill_dispute":     "raise_bill_dispute",
}

def execute_db_tool(intent: str, params: dict, dob: str) -> dict:
    fn = _INTENT_TO_DB.get(intent)
    if not fn:
        return {}
    print(f"[TOOL] → {fn}({params})")
    try:
        if fn == "get_order_status":
            return get_order_status(dob, params.get("order_id"))
        elif fn == "get_order_tracking":
            return get_order_tracking(dob, params.get("order_id", ""))
        elif fn == "get_current_bill":
            return get_current_bill(dob)
        elif fn == "get_payment_history":
            return get_payment_history(dob)
        elif fn == "get_complaint_status":
            return get_complaint_status(dob, params.get("complaint_id"))
        elif fn == "create_complaint":
            return create_complaint(dob, params.get("issue", "Issue reported"))
        elif fn == "escalate_complaint":
            return escalate_complaint(dob, params.get("complaint_id", ""))
        elif fn == "raise_bill_dispute":
            return raise_bill_dispute(dob, params.get("reason", "Customer disputes bill"))
    except Exception as e:
        print(f"[TOOL] Error: {e}")
    return {}

def _is_mock_response(r) -> bool:
    candidates = getattr(r, "candidates", None)
    if isinstance(candidates, list) and len(candidates) > 0:
        return False
    text = getattr(r, "text", None)
    return isinstance(text, str) and len(text) > 0

def run_chain(
    transcript:       str,
    customer_dob:     str,
    customer_name:    str,
    customer_context: str,
    history:          str = "",
    lang:             str = "en",
) -> dict:

    lang_name = LANG_NAMES.get(lang, "English")

    prompt = f"""You are Deep Care, a professional voice AI customer service agent.
You are speaking with {customer_name}.

CUSTOMER DATA (use ONLY this data — never invent numbers):
{customer_context}

CONVERSATION HISTORY:
{history or "No previous turns."}

Customer just said: "{transcript}"

TASK: Reply to the customer using ONLY the data above. Then return a single JSON object.

RULES:
- Spoken response must be in {lang_name}, 1-2 sentences max
- NEVER invent order IDs, amounts, dates, or complaint numbers
- Use exact values from CUSTOMER DATA above
- For complaints/escalations: acknowledge and act on what's in the data

Return ONLY this JSON, no markdown, no extra text:
{{
  "response": "<your spoken reply in {lang_name}>",
  "intent": "<order_status|order_tracking|current_bill|payment_history|complaint_status|lodge_complaint|escalate|bill_dispute|goodbye|general>",
  "params": {{}},
  "sentiment": "<positive|neutral|negative>",
  "key_points": ["up to 3 short points"],
  "suggested_action": "<one line for human agent>",
  "summary_text": "<one sentence English summary>"
}}"""

    db_result        = {}
    bot_reply        = _fallback_didnt_catch(lang)
    intent           = "general"
    sentiment        = "neutral"
    key_points       = []
    suggested_action = ""
    summary_text     = "Turn completed."

    try:
        r = client.models.generate_content(
            model    = MODEL,
            contents = prompt,
            config   = types.GenerateContentConfig(temperature=0.3)
        )

        if _is_mock_response(r):
            raw = r.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        else:
            raw = r.text.strip() if r.text else ""
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'^```\s*',     '', raw)
            raw = re.sub(r'\s*```$',     '', raw).strip()

        parsed           = json.loads(raw)
        bot_reply        = parsed.get("response", bot_reply)
        intent           = parsed.get("intent", "general")
        sentiment        = parsed.get("sentiment", "neutral")
        key_points       = parsed.get("key_points", [])
        suggested_action = parsed.get("suggested_action", "")
        summary_text     = parsed.get("summary_text", "")

        # Execute DB action for write intents
        params = parsed.get("params", {})
        if intent in _INTENT_TO_DB:
            db_result = execute_db_tool(intent, params, customer_dob)

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
        "tool_called":      _INTENT_TO_DB.get(intent),
    }
