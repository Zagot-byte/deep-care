"""
db_handler.py — All mock_data.json read/write operations
"""

import json
import os
import random
import tempfile

DB_PATH = os.getenv("DB_PATH", "./mock_data.json")


def _load_db() -> dict:
    with open(DB_PATH, "r") as f:
        return json.load(f)


def _save_db(db: dict) -> None:
    """Atomic write — write to temp then rename."""
    dir_ = os.path.dirname(os.path.abspath(DB_PATH))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as tmp:
        json.dump(db, tmp, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, DB_PATH)


# ── READ ────────────────────────────────────────────────────────────────

def load_customer(dob: str) -> dict | None:
    db = _load_db()
    return db["customers"].get(dob)


def get_order_status(customer_dob: str, order_id: str = None) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    orders = customer.get("orders", [])
    if not orders:
        return {"error": "No orders found"}
    if order_id:
        for o in orders:
            if o["order_id"] == order_id:
                return o
        return {"error": f"Order {order_id} not found"}
    return orders[0]  # latest order


def get_order_tracking(customer_dob: str, order_id: str) -> dict:
    order = get_order_status(customer_dob, order_id)
    return {
        "order_id": order.get("order_id"),
        "tracking": order.get("tracking", "N/A"),
        "status":   order.get("status", "Unknown"),
    }


def get_current_bill(customer_dob: str) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    bills = customer.get("bills", [])
    unpaid = [b for b in bills if b.get("status") != "paid"]
    return unpaid[0] if unpaid else (bills[0] if bills else {"error": "No bills found"})


def get_payment_history(customer_dob: str) -> list:
    customer = load_customer(customer_dob)
    if not customer:
        return []
    bills = customer.get("bills", [])
    return bills[0].get("history", []) if bills else []


def get_complaint_status(customer_dob: str, complaint_id: str = None) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    complaints = customer.get("complaints", [])
    if not complaints:
        return {"error": "No complaints found"}
    if complaint_id:
        for c in complaints:
            if c["complaint_id"] == complaint_id:
                return c
        return {"error": f"Complaint {complaint_id} not found"}
    return complaints[-1]  # most recent


# ── WRITE ───────────────────────────────────────────────────────────────

def create_complaint(customer_dob: str, issue: str) -> dict:
    db = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    complaint_id = f"CMP-{random.randint(100, 999)}"
    new_complaint = {
        "complaint_id": complaint_id,
        "issue":        issue,
        "status":       "open",
        "escalated":    False
    }
    customer.setdefault("complaints", []).append(new_complaint)
    _save_db(db)
    return {"complaint_id": complaint_id, "status": "created"}


def escalate_complaint(customer_dob: str, complaint_id: str) -> dict:
    db = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    for c in customer.get("complaints", []):
        if c["complaint_id"] == complaint_id:
            c["escalated"] = True
            c["status"] = "escalated"
            _save_db(db)
            return {"escalated": True, "complaint_id": complaint_id}
    return {"error": f"Complaint {complaint_id} not found"}


def save_session(customer_dob: str, session_data: dict) -> None:
    try:
        db = _load_db()
        customer = db["customers"].get(customer_dob)
        if customer:
            customer.setdefault("session_history", []).append(session_data)
            _save_db(db)
    except Exception as e:
        print(f"[DB] save_session failed: {e}")
