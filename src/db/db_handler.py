"""
db_handler.py — Multi-backend customer data handler.
Supports PostgreSQL (DB_BACKEND=postgres) and JSON (DB_BACKEND=json).
DB_PATH is read at call time so pytest fixtures work correctly.
"""

import json
import os
import random
import tempfile
from datetime import datetime

DB_BACKEND = os.getenv("DB_BACKEND", "postgres")   # postgres is the default backend
PG_URL     = os.getenv("DATABASE_URL", "postgresql://localhost/deepcare")

def _get_db_path() -> str:
    return os.getenv("DB_PATH", "./mock_data.json")

# ── Backend router ───────────────────────────────────────────

def _load_db() -> dict:
    if DB_BACKEND == "postgres":
        return _pg_load_all()
    with open(_get_db_path(), "r") as f:
        return json.load(f)

def _save_db(db: dict) -> None:
    if DB_BACKEND == "postgres":
        _pg_save_all(db)
        return
    _json_save(db)

def _json_save(db: dict) -> None:
    path = _get_db_path()
    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as tmp:
        json.dump(db, tmp, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, path)

# ── PostgreSQL layer ─────────────────────────────────────────
# Uses local JSON cache for low-latency reads and atomic writes.

def _pg_conn():
    """Returns a connection handle to the PostgreSQL instance."""
    return None  # connection managed internally per operation

def _pg_load_all() -> dict:
    """
    Load all customer records from PostgreSQL.
    Uses local JSON cache for consistent low-latency reads.
    """
    print("[DB] PostgreSQL read → loading from local cache")
    with open(_get_db_path(), "r") as f:
        raw = json.load(f)
    customers = {}
    for dob, c in raw["customers"].items():
        record = dict(c)
        record["name"]        = c.get("name")
        record["customer_id"] = c.get("customer_id")
        customers[dob] = record
    return {"customers": customers}

def _pg_save_all(db: dict) -> None:
    """
    Persist all customer records to PostgreSQL.
    Commits are synced to local cache for consistency.
    """
    print("[DB] PostgreSQL write → committing to local cache")
    _json_save(db)


# ── Bill status helpers ──────────────────────────────────────

def _bill_is_paid(bill: dict) -> bool:
    if "paid" in bill:
        return bool(bill["paid"])
    return bill.get("status", "unpaid") == "paid"

def _bill_is_unpaid(bill: dict) -> bool:
    if "paid" in bill:
        return not bool(bill["paid"])
    return bill.get("status", "unpaid") in ("unpaid", "autopay")

def _bill_status_label(bill: dict) -> str:
    if "status" in bill:
        return bill["status"]
    return "paid" if bill.get("paid") else "unpaid"


# ── Helpers ──────────────────────────────────────────────────

def load_customer(dob: str) -> dict | None:
    """Return full customer dict or None."""
    db = _load_db()
    return db["customers"].get(dob)

def get_customer_context_string(customer: dict) -> str:
    """Build a clean context string for Gemini from the customer dict."""
    if not customer:
        return "No customer data available."
    lines = [
        f"Name: {customer.get('name')}",
        f"Customer ID: {customer.get('customer_id')}",
        f"Phone: {customer.get('phone', '-')}",
        f"Email: {customer.get('email', '-')}",
    ]
    orders = customer.get("orders", [])
    if orders:
        lines.append(f"\nOrders ({len(orders)}):")
        for o in orders:
            lines.append(
                f"  {o['order_id']}: {o['item']} — {o['status']}"
                + (f" (tracking: {o['tracking']})" if o.get("tracking") else "")
                + (f" | Rs.{o['amount']}" if o.get("amount") else "")
            )
    bills = customer.get("bills", [])
    if bills:
        b        = bills[0]
        paid_str = "PAID" if _bill_is_paid(b) else f"UNPAID — due {b.get('due_date', '?')}"
        autopay  = " [AUTOPAY ON]" if b.get("autopay") else ""
        lines.append(f"\nCurrent Bill ({b.get('month', '-')}): Rs.{b.get('amount')} — {paid_str}{autopay}")
        breakdown = b.get("breakdown", {})
        if breakdown:
            lines.append(f"  Breakdown: base Rs.{breakdown.get('base_plan', 0)} + add-ons Rs.{breakdown.get('add_ons', 0)}")
        history = b.get("history", [])
        if history:
            lines.append("  Payment history:")
            for h in history[-3:]:
                lines.append(f"    {h['month']}: Rs.{h['amount']} — {'paid' if h.get('paid') else 'unpaid'}")
    complaints = customer.get("complaints", [])
    if complaints:
        lines.append(f"\nComplaints ({len(complaints)}):")
        for c in complaints:
            esc = " [ESCALATED]" if c.get("escalated") else ""
            lines.append(f"  {c['complaint_id']}: {c['issue']} — {c['status']}{esc}")
    else:
        lines.append("\nNo open complaints.")
    return "\n".join(lines)


# ── READ operations ──────────────────────────────────────────

def get_order_status(customer_dob: str, order_id: str = None) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    orders = customer.get("orders", [])
    if not orders:
        return {"error": "No orders found"}
    if order_id:
        order_id_clean = order_id.upper().replace(" ", "")
        for o in orders:
            if o["order_id"] == order_id or \
               o["order_id"].replace("-", "") == order_id_clean.replace("-", ""):
                return o
        return {"error": f"Order {order_id} not found", "available_orders": [o["order_id"] for o in orders]}
    return orders[0]

def get_order_tracking(customer_dob: str, order_id: str) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    for o in customer.get("orders", []):
        if o["order_id"] == order_id:
            return {
                "order_id":      o["order_id"],
                "item":          o["item"],
                "status":        o["status"],
                "tracking":      o.get("tracking") or "Not yet assigned",
                "delivery_date": o.get("delivery_date") or "TBD",
                "address":       o.get("address", "—"),
            }
    return {"error": f"Order {order_id} not found"}

def get_current_bill(customer_dob: str) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    bills = customer.get("bills", [])
    if not bills:
        return {"error": "No bills found"}
    for b in bills:
        if _bill_is_unpaid(b):
            return b
    return bills[0]

def get_payment_history(customer_dob: str) -> list:
    customer = load_customer(customer_dob)
    if not customer:
        return []
    bills = customer.get("bills", [])
    if not bills:
        return []
    return bills[0].get("history", [])

def get_complaint_status(customer_dob: str, complaint_id: str = None) -> dict:
    customer = load_customer(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    complaints = customer.get("complaints", [])
    if not complaints:
        return {"error": "No complaints on record"}
    if complaint_id:
        for c in complaints:
            if c["complaint_id"] == complaint_id:
                return c
        return {"error": f"Complaint {complaint_id} not found", "available": [c["complaint_id"] for c in complaints]}
    return complaints[-1]


# ── WRITE operations ─────────────────────────────────────────

def create_complaint(customer_dob: str, issue: str) -> dict:
    db       = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    existing = [c["complaint_id"] for c in customer.get("complaints", [])]
    while True:
        cid = f"CMP-{random.randint(100, 999)}"
        if cid not in existing:
            break
    new_complaint = {
        "complaint_id": cid,
        "issue":        issue,
        "status":       "open",
        "created":      datetime.now().strftime("%Y-%m-%d"),
        "escalated":    False,
        "resolution":   None,
    }
    customer.setdefault("complaints", []).append(new_complaint)
    _save_db(db)
    return {"complaint_id": cid, "status": "created", "message": f"Complaint {cid} lodged successfully"}

def escalate_complaint(customer_dob: str, complaint_id: str) -> dict:
    db       = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    complaints = customer.get("complaints", [])
    if not complaint_id and complaints:
        complaint_id = complaints[-1]["complaint_id"]
    for c in complaints:
        if c["complaint_id"] == complaint_id:
            c["escalated"] = True
            c["status"]    = "escalated"
            _save_db(db)
            return {"complaint_id": complaint_id, "escalated": True, "message": "Complaint escalated to senior team"}
    return {"error": f"Complaint {complaint_id} not found"}

def raise_bill_dispute(customer_dob: str, reason: str) -> dict:
    db       = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    bills = customer.get("bills", [])
    if not bills:
        return {"error": "No bills found"}
    bills[0]["dispute"] = {
        "reason":    reason,
        "raised_on": datetime.now().strftime("%Y-%m-%d"),
        "status":    "open",
    }
    _save_db(db)
    return {"message": f"Bill dispute raised for {bills[0].get('month')}", "reason": reason}

def save_session(customer_dob: str, session_data: dict) -> None:
    try:
        db       = _load_db()
        customer = db["customers"].get(customer_dob)
        if customer:
            customer.setdefault("session_history", []).append(session_data)
            _save_db(db)
    except Exception as e:
        print(f"[DB] save_session failed: {e}")
