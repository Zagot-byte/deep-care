"""
dob_auth.py — DOB extraction + customer lookup
"""

import json
import re
import os
from dateutil import parser as dateutil_parser

DB_PATH = os.getenv("DB_PATH", "./mock_data.json")


def _load_db() -> dict:
    with open(DB_PATH, "r") as f:
        return json.load(f)


def extract_dob(transcript: str) -> str | None:
    """
    Extract DOB from natural language transcript.
    Returns DD-MM-YYYY string or None.
    """
    text = transcript.lower().strip()

    # Remove filler words to help dateutil parse
    filler = r"\b(my|birthday|birth|date of birth|dob|is|it's|its|was|the|on|i was born|born)\b"
    cleaned = re.sub(filler, " ", text, flags=re.IGNORECASE).strip()

    # Try dateutil first
    try:
        parsed = dateutil_parser.parse(cleaned, fuzzy=True, dayfirst=True)
        return parsed.strftime("%d-%m-%Y")
    except Exception:
        pass

    # Fallback regex patterns
    patterns = [
        # 15/03/1999 or 15-03-1999
        r"(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})",
        # 1999/03/15
        r"(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            parts = m.groups()
            try:
                if len(parts[0]) == 4:  # YYYY-MM-DD
                    year, month, day = parts
                else:
                    day, month, year = parts
                return f"{int(day):02d}-{int(month):02d}-{year}"
            except Exception:
                continue

    return None


def lookup_customer(dob: str) -> dict | None:
    """Look up customer by DOB string DD-MM-YYYY."""
    try:
        db = _load_db()
        return db["customers"].get(dob)
    except Exception:
        return None


def get_customer_context_string(customer: dict) -> str:
    """Build a plain-text customer context summary for the LLM."""
    if not customer:
        return "No customer data available."

    lines = [f"Customer: {customer.get('name', 'Unknown')} ({customer.get('customer_id', '—')})"]

    orders = customer.get("orders", [])
    if orders:
        order_parts = [f"{o['order_id']} ({o['item']} - {o['status']})" for o in orders]
        lines.append("Orders: " + ", ".join(order_parts))

    bills = customer.get("bills", [])
    if bills:
        b = bills[0]
        lines.append(
            f"Bills: {b.get('month', '—')} - Rs.{b.get('amount', '—')} "
            f"due on {b.get('due_date', '—')} ({b.get('status', '—')})"
        )

    complaints = customer.get("complaints", [])
    if complaints:
        c_parts = [f"{c['complaint_id']} ({c['issue']} - {c['status']})" for c in complaints]
        lines.append("Complaints: " + ", ".join(c_parts))

    return "\n".join(lines)
