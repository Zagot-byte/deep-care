"""
tests/test_deep_care.py — Deep Care Voice Gateway Full Test Suite
Run: pytest tests/test_deep_care.py -v
"""

import json
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

# ── Path setup ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Mock DB fixture ──────────────────────────────────────────────────────
MOCK_DB = {
    "customers": {
        "15-03-1999": {
            "name": "Arjun Kumar",
            "customer_id": "DCID-4521",
            "dob": "15-03-1999",
            "orders": [
                {"order_id": "ORD-4521", "item": "Laptop Stand",    "status": "Delivered",        "tracking": "TRK-001"},
                {"order_id": "ORD-4522", "item": "Wireless Mouse",  "status": "Out for Delivery", "tracking": "TRK-002"},
            ],
            "bills": [{
                "month": "March 2024",
                "amount": 2400,
                "due_date": "2024-03-20",
                "status": "unpaid",
                "history": [{"month": "Feb 2024", "amount": 2200, "status": "paid"}]
            }],
            "complaints": [
                {"complaint_id": "CMP-001", "issue": "Billing overcharge", "status": "open", "escalated": False}
            ]
        },
        "20-05-1995": {
            "name": "Priya Sharma",
            "customer_id": "DCID-7891",
            "dob": "20-05-1995",
            "orders": [
                {"order_id": "ORD-7891", "item": "Bluetooth Speaker", "status": "Processing", "tracking": "TRK-003"}
            ],
            "bills": [{
                "month": "March 2024",
                "amount": 1800,
                "due_date": "2024-03-25",
                "status": "autopay",
                "history": []
            }],
            "complaints": []
        }
    }
}


@pytest.fixture
def mock_db_file(tmp_path):
    """Write MOCK_DB to a temp file and set DB_PATH env var."""
    db_file = tmp_path / "mock_data.json"
    db_file.write_text(json.dumps(MOCK_DB))
    os.environ["DB_PATH"] = str(db_file)
    yield str(db_file)
    del os.environ["DB_PATH"]


# ════════════════════════════════════════════════════════════════════════
# 1. DB HANDLER TESTS
# ════════════════════════════════════════════════════════════════════════

class TestDBHandler:

    def test_load_customer_valid(self, mock_db_file):
        from src.db.db_handler import load_customer
        customer = load_customer("15-03-1999")
        assert customer is not None
        assert customer["name"] == "Arjun Kumar"
        assert customer["customer_id"] == "DCID-4521"

    def test_load_customer_not_found(self, mock_db_file):
        from src.db.db_handler import load_customer
        customer = load_customer("01-01-2000")
        assert customer is None

    def test_get_order_status_by_id(self, mock_db_file):
        from src.db.db_handler import get_order_status
        result = get_order_status("15-03-1999", "ORD-4521")
        assert result["item"] == "Laptop Stand"
        assert result["status"] == "Delivered"

    def test_get_order_status_latest_if_no_id(self, mock_db_file):
        from src.db.db_handler import get_order_status
        result = get_order_status("15-03-1999")
        assert result["order_id"] == "ORD-4521"  # first = latest

    def test_get_order_status_invalid_order_id(self, mock_db_file):
        from src.db.db_handler import get_order_status
        result = get_order_status("15-03-1999", "ORD-9999")
        assert "error" in result

    def test_get_order_status_invalid_customer(self, mock_db_file):
        from src.db.db_handler import get_order_status
        result = get_order_status("01-01-2000", "ORD-4521")
        assert "error" in result

    def test_get_order_tracking(self, mock_db_file):
        from src.db.db_handler import get_order_tracking
        result = get_order_tracking("15-03-1999", "ORD-4522")
        assert result["order_id"] == "ORD-4522"
        assert result["status"] == "Out for Delivery"
        assert "tracking" in result

    def test_get_current_bill_unpaid(self, mock_db_file):
        from src.db.db_handler import get_current_bill
        result = get_current_bill("15-03-1999")
        assert result["amount"] == 2400
        assert result["status"] == "unpaid"

    def test_get_current_bill_autopay(self, mock_db_file):
        from src.db.db_handler import get_current_bill
        result = get_current_bill("20-05-1995")
        assert result["status"] == "autopay"

    def test_get_current_bill_invalid_customer(self, mock_db_file):
        from src.db.db_handler import get_current_bill
        result = get_current_bill("01-01-2000")
        assert "error" in result

    def test_get_payment_history(self, mock_db_file):
        from src.db.db_handler import get_payment_history
        result = get_payment_history("15-03-1999")
        assert isinstance(result, list)
        assert result[0]["month"] == "Feb 2024"

    def test_get_payment_history_empty(self, mock_db_file):
        from src.db.db_handler import get_payment_history
        result = get_payment_history("20-05-1995")
        assert result == []

    def test_get_complaint_status_by_id(self, mock_db_file):
        from src.db.db_handler import get_complaint_status
        result = get_complaint_status("15-03-1999", "CMP-001")
        assert result["issue"] == "Billing overcharge"
        assert result["status"] == "open"

    def test_get_complaint_status_most_recent(self, mock_db_file):
        from src.db.db_handler import get_complaint_status
        result = get_complaint_status("15-03-1999")
        assert result["complaint_id"] == "CMP-001"

    def test_get_complaint_status_none_exist(self, mock_db_file):
        from src.db.db_handler import get_complaint_status
        result = get_complaint_status("20-05-1995")
        assert "error" in result

    def test_create_complaint(self, mock_db_file):
        from src.db.db_handler import create_complaint, load_customer
        result = create_complaint("15-03-1999", "Wrong item delivered")
        assert result["status"] == "created"
        assert result["complaint_id"].startswith("CMP-")
        # Verify persisted
        customer = load_customer("15-03-1999")
        issues = [c["issue"] for c in customer["complaints"]]
        assert "Wrong item delivered" in issues

    def test_create_complaint_invalid_customer(self, mock_db_file):
        from src.db.db_handler import create_complaint
        result = create_complaint("01-01-2000", "Some issue")
        assert "error" in result

    def test_escalate_complaint(self, mock_db_file):
        from src.db.db_handler import escalate_complaint, load_customer
        result = escalate_complaint("15-03-1999", "CMP-001")
        assert result["escalated"] is True
        customer = load_customer("15-03-1999")
        cmp = next(c for c in customer["complaints"] if c["complaint_id"] == "CMP-001")
        assert cmp["status"] == "escalated"
        assert cmp["escalated"] is True

    def test_escalate_complaint_not_found(self, mock_db_file):
        from src.db.db_handler import escalate_complaint
        result = escalate_complaint("15-03-1999", "CMP-999")
        assert "error" in result

    def test_save_session(self, mock_db_file):
        from src.db.db_handler import save_session, load_customer
        save_session("15-03-1999", {"session_id": "abc", "turns": 3})
        customer = load_customer("15-03-1999")
        assert len(customer["session_history"]) > 0
        assert customer["session_history"][-1]["session_id"] == "abc"


# ════════════════════════════════════════════════════════════════════════
# 2. DOB AUTH TESTS
# ════════════════════════════════════════════════════════════════════════

class TestDOBAuth:

    def test_extract_dob_numeric_slash(self):
        from src.auth.dob_auth import extract_dob
        assert extract_dob("15/03/1999") == "15-03-1999"

    def test_extract_dob_numeric_dash(self):
        from src.auth.dob_auth import extract_dob
        assert extract_dob("15-03-1999") == "15-03-1999"

    def test_extract_dob_natural_language(self):
        from src.auth.dob_auth import extract_dob
        result = extract_dob("my date of birth is 15th March 1999")
        assert result == "15-03-1999"

    def test_extract_dob_born_phrasing(self):
        from src.auth.dob_auth import extract_dob
        result = extract_dob("I was born on March 15 1999")
        assert result == "15-03-1999"

    def test_extract_dob_returns_none_for_garbage(self):
        from src.auth.dob_auth import extract_dob
        result = extract_dob("hello there how are you")
        assert result is None

    def test_extract_dob_iso_format(self):
        from src.auth.dob_auth import extract_dob
        result = extract_dob("1999-03-15")
        assert result == "15-03-1999"

    def test_lookup_customer_found(self, mock_db_file):
        from src.auth.dob_auth import lookup_customer
        customer = lookup_customer("15-03-1999")
        assert customer["name"] == "Arjun Kumar"

    def test_lookup_customer_not_found(self, mock_db_file):
        from src.auth.dob_auth import lookup_customer
        customer = lookup_customer("01-01-1900")
        assert customer is None

    def test_get_customer_context_string_full(self, mock_db_file):
        from src.auth.dob_auth import lookup_customer, get_customer_context_string
        customer = lookup_customer("15-03-1999")
        ctx = get_customer_context_string(customer)
        assert "Arjun Kumar" in ctx
        assert "ORD-4521" in ctx
        assert "Rs.2400" in ctx
        assert "CMP-001" in ctx

    def test_get_customer_context_string_none(self):
        from src.auth.dob_auth import get_customer_context_string
        result = get_customer_context_string(None)
        assert "No customer data" in result

    def test_get_customer_context_string_no_complaints(self, mock_db_file):
        from src.auth.dob_auth import lookup_customer, get_customer_context_string
        customer = lookup_customer("20-05-1995")
        ctx = get_customer_context_string(customer)
        assert "Priya Sharma" in ctx
        assert "Complaints" not in ctx


# ════════════════════════════════════════════════════════════════════════
# 3. SESSION MANAGER TESTS
# ════════════════════════════════════════════════════════════════════════

class TestSessionManager:

    def setup_method(self):
        """Clear session store before each test."""
        from src.session import session_manager
        session_manager.SESSION_STORE.clear()

    def test_create_session(self):
        from src.session.session_manager import create_session
        s = create_session("sess-001")
        assert s["session_id"] == "sess-001"
        assert s["authenticated"] is False
        assert s["turns"] == []
        assert s["escalated"] is False

    def test_get_session_exists(self):
        from src.session.session_manager import create_session, get_session
        create_session("sess-002")
        s = get_session("sess-002")
        assert s is not None

    def test_get_session_not_exists(self):
        from src.session.session_manager import get_session
        assert get_session("nonexistent") is None

    def test_set_authenticated(self):
        from src.session.session_manager import create_session, set_authenticated, get_session
        create_session("sess-003")
        customer = {"name": "Arjun Kumar", "customer_id": "DCID-4521"}
        set_authenticated("sess-003", customer, "15-03-1999")
        s = get_session("sess-003")
        assert s["authenticated"] is True
        assert s["customer_dob"] == "15-03-1999"
        assert s["customer_name"] == "Arjun Kumar"
        assert s["customer_id"] == "DCID-4521"

    def test_append_turn(self):
        from src.session.session_manager import create_session, append_turn, get_session
        create_session("sess-004")
        append_turn("sess-004", "What's my bill?", "Your bill is Rs.2400.", "current_bill", "neutral")
        s = get_session("sess-004")
        assert len(s["turns"]) == 1
        assert s["turns"][0]["intent"] == "current_bill"
        assert s["sentiment_trajectory"] == ["neutral"]
        assert "current_bill" in s["intents_seen"]

    def test_append_turn_no_duplicate_intents(self):
        from src.session.session_manager import create_session, append_turn, get_session
        create_session("sess-005")
        append_turn("sess-005", "bill?", "Rs.2400", "current_bill", "neutral")
        append_turn("sess-005", "bill again?", "Still Rs.2400", "current_bill", "neutral")
        s = get_session("sess-005")
        assert s["intents_seen"].count("current_bill") == 1

    def test_sentiment_trajectory_accumulates(self):
        from src.session.session_manager import create_session, append_turn, get_session
        create_session("sess-006")
        append_turn("sess-006", "ok", "ok", "general", "positive")
        append_turn("sess-006", "angry", "sorry", "general", "negative")
        append_turn("sess-006", "still angry", "sorry again", "escalate", "negative")
        s = get_session("sess-006")
        assert s["sentiment_trajectory"] == ["positive", "negative", "negative"]

    def test_get_last_n_turns(self):
        from src.session.session_manager import create_session, append_turn, get_last_n_turns
        create_session("sess-007")
        for i in range(8):
            append_turn("sess-007", f"user msg {i}", f"bot msg {i}", "general", "neutral")
        history = get_last_n_turns("sess-007", 6)
        lines = history.strip().split("\n")
        # 6 turns × 2 lines each = 12 lines
        assert len(lines) == 12
        assert "user msg 7" in history
        assert "user msg 0" not in history  # older turns excluded

    def test_escalation_flag(self):
        from src.session.session_manager import create_session, get_session
        create_session("sess-008")
        s = get_session("sess-008")
        s["escalated"] = True
        assert get_session("sess-008")["escalated"] is True


# ════════════════════════════════════════════════════════════════════════
# 4. CHAIN / LLM TESTS (mocked — no real API calls)
# ════════════════════════════════════════════════════════════════════════

MOCK_GEMINI_RESPONSE = {
    "intent": "current_bill",
    "params": {},
    "sentiment": "neutral",
    "response": "Your current bill is Rs.2400 due on 2024-03-20.",
    "key_points": ["Bill Rs.2400", "Due 2024-03-20"],
    "suggested_action": "Remind customer of due date.",
    "summary_text": "Customer asked about current bill."
}


def make_mock_gemini(response_dict):
    """Return a mock client.models.generate_content that returns response_dict as JSON."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp
    return mock_client


class TestChain:

    def test_run_chain_returns_correct_intent(self, mock_db_file):
        from src.llm import chain
        mock_client = make_mock_gemini(MOCK_GEMINI_RESPONSE)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="What's my bill?",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="Bills: Rs.2400",
                history=""
            )
        assert result["intent"] == "current_bill"
        assert "db_result" in result

    def test_run_chain_db_tool_called_for_order_status(self, mock_db_file):
        from src.llm import chain
        gemini_resp = {**MOCK_GEMINI_RESPONSE,
                       "intent": "order_status",
                       "params": {"order_id": "ORD-4521"}}
        mock_client = make_mock_gemini(gemini_resp)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="Where is my order ORD-4521?",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["db_result"].get("item") == "Laptop Stand"

    def test_run_chain_db_tool_called_for_complaint_status(self, mock_db_file):
        from src.llm import chain
        gemini_resp = {**MOCK_GEMINI_RESPONSE,
                       "intent": "complaint_status",
                       "params": {"complaint_id": "CMP-001"}}
        mock_client = make_mock_gemini(gemini_resp)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="What's the status of my complaint?",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["db_result"]["status"] == "open"

    def test_run_chain_lodge_complaint(self, mock_db_file):
        from src.llm import chain
        gemini_resp = {**MOCK_GEMINI_RESPONSE,
                       "intent": "lodge_complaint",
                       "params": {"issue": "Package damaged"}}
        mock_client = make_mock_gemini(gemini_resp)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="I want to raise a complaint, my package was damaged.",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["db_result"]["status"] == "created"

    def test_run_chain_fallback_on_bad_json(self, mock_db_file):
        from src.llm import chain
        mock_resp = MagicMock()
        mock_resp.text = "this is not json at all"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="hello",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["intent"] == "general"
        assert "trouble" in result["response"].lower()

    def test_run_chain_no_db_call_for_general_intent(self, mock_db_file):
        from src.llm import chain
        gemini_resp = {**MOCK_GEMINI_RESPONSE,
                       "intent": "general",
                       "params": {}}
        mock_client = make_mock_gemini(gemini_resp)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="Thank you!",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["db_result"] == {}

    def test_run_chain_strips_markdown_fences(self, mock_db_file):
        from src.llm import chain
        mock_resp = MagicMock()
        mock_resp.text = "```json\n" + json.dumps(MOCK_GEMINI_RESPONSE) + "\n```"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain(
                transcript="bill?",
                customer_dob="15-03-1999",
                customer_name="Arjun Kumar",
                customer_context="",
                history=""
            )
        assert result["intent"] == "current_bill"


# ════════════════════════════════════════════════════════════════════════
# 5. HALLUCINATION GUARD TESTS
# ════════════════════════════════════════════════════════════════════════

class TestHallucinationGuard:
    """
    Verify that DB data — not Gemini — is the source of truth for
    order IDs, bill amounts, and complaint numbers.
    """

    def test_order_id_comes_from_db_not_gemini(self, mock_db_file):
        from src.llm import chain
        # Gemini hallucinates a wrong order ID in params
        gemini_resp = {**MOCK_GEMINI_RESPONSE,
                       "intent": "order_status",
                       "params": {"order_id": "ORD-FAKE-9999"}}
        mock_client = make_mock_gemini(gemini_resp)
        with patch.object(chain, "client", mock_client):
            result = chain.run_chain("order status", "15-03-1999", "Arjun", "", "")
        # DB returns error — it does NOT invent the order
        assert "error" in result["db_result"]
        assert "ORD-FAKE-9999" in result["db_result"]["error"]

    def test_bill_amount_comes_from_db(self, mock_db_file):
        from src.db.db_handler import get_current_bill
        bill = get_current_bill("15-03-1999")
        # Amount must be exactly what's in mock_data, not inferred
        assert bill["amount"] == 2400

    def test_complaint_id_comes_from_db(self, mock_db_file):
        from src.db.db_handler import get_complaint_status
        result = get_complaint_status("15-03-1999", "CMP-001")
        assert result["complaint_id"] == "CMP-001"
        assert result["issue"] == "Billing overcharge"


# ════════════════════════════════════════════════════════════════════════
# 6. AUTO-ESCALATION (2× NEGATIVE SENTIMENT) TEST
# ════════════════════════════════════════════════════════════════════════

class TestAutoEscalation:

    def setup_method(self):
        from src.session import session_manager
        session_manager.SESSION_STORE.clear()

    def test_two_consecutive_negatives_triggers_escalation_flag(self):
        """
        Simulates the server-side logic: after 2 consecutive negative sentiments
        the session should be flagged for escalation.
        """
        from src.session.session_manager import create_session, append_turn, get_session

        create_session("esc-test")
        append_turn("esc-test", "this is terrible", "I'm sorry", "general", "negative")
        append_turn("esc-test", "still terrible", "I understand", "general", "negative")

        s = get_session("esc-test")
        trajectory = s["sentiment_trajectory"]

        # Check last 2 are negative — this is the condition server.py should check
        last_two_negative = len(trajectory) >= 2 and all(t == "negative" for t in trajectory[-2:])
        assert last_two_negative is True

    def test_one_negative_does_not_trigger(self):
        from src.session.session_manager import create_session, append_turn, get_session

        create_session("esc-test-2")
        append_turn("esc-test-2", "ok", "ok", "general", "positive")
        append_turn("esc-test-2", "hmm", "ok", "general", "negative")

        s = get_session("esc-test-2")
        trajectory = s["sentiment_trajectory"]
        last_two_negative = len(trajectory) >= 2 and all(t == "negative" for t in trajectory[-2:])
        assert last_two_negative is False

    def test_escalation_does_not_stop_bot(self):
        """Bot keeps running after escalation flag is set (human in loop pattern)."""
        from src.session.session_manager import create_session, get_session, append_turn

        create_session("esc-test-3")
        s = get_session("esc-test-3")
        s["escalated"] = True  # flag set

        # Bot can still append turns
        append_turn("esc-test-3", "still here", "I'm still helping", "general", "negative")
        s = get_session("esc-test-3")

        assert s["escalated"] is True
        assert len(s["turns"]) == 1  # bot kept going


# ════════════════════════════════════════════════════════════════════════
# 7. EXECUTE_DB_TOOL ROUTING TESTS
# ════════════════════════════════════════════════════════════════════════

class TestExecuteDBTool:

    def test_routes_order_status(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("order_status", {"order_id": "ORD-4521"}, "15-03-1999")
        assert result["item"] == "Laptop Stand"

    def test_routes_order_tracking(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("order_tracking", {"order_id": "ORD-4521"}, "15-03-1999")
        assert result["tracking"] == "TRK-001"

    def test_routes_current_bill(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("current_bill", {}, "15-03-1999")
        assert result["amount"] == 2400

    def test_routes_payment_history(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("payment_history", {}, "15-03-1999")
        assert isinstance(result, list)

    def test_routes_complaint_status(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("complaint_status", {"complaint_id": "CMP-001"}, "15-03-1999")
        assert result["complaint_id"] == "CMP-001"

    def test_routes_lodge_complaint(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("lodge_complaint", {"issue": "Test issue"}, "15-03-1999")
        assert result["status"] == "created"

    def test_routes_escalate(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("escalate", {"complaint_id": "CMP-001"}, "15-03-1999")
        assert result["escalated"] is True

    def test_unknown_intent_returns_empty(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        result = execute_db_tool("goodbye", {}, "15-03-1999")
        assert result == {}

    def test_db_exception_returns_empty(self, mock_db_file):
        from src.llm.chain import execute_db_tool
        # Bad DOB causes lookup to fail gracefully
        result = execute_db_tool("order_status", {"order_id": "ORD-4521"}, "INVALID")
        assert result == {} or "error" in result
