"""
db_handler.py — Reads mock_data.json exactly as structured.
Bills use "paid": true/false (not "status":"paid").
Supports PostgreSQL via DB_BACKEND=postgres in config.env.
"""

import json
import os
import random
import tempfile
from datetime import datetime

DB_BACKEND = os.getenv("DB_BACKEND", "json")
DB_PATH    = os.getenv("DB_PATH", "./mock_data.json")
PG_URL     = os.getenv("DATABASE_URL", "postgresql://localhost/deepcare")

# ── Backend ─────────────────────────────────────────────────

def _load_db() -> dict:
    if DB_BACKEND == "postgres":
        return _pg_load_all()
    with open(DB_PATH, "r") as f:
        return json.load(f)

def _save_db(db: dict) -> None:
    if DB_BACKEND == "postgres":
        _pg_save_all(db)
        return
    dir_ = os.path.dirname(os.path.abspath(DB_PATH))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as tmp:
        json.dump(db, tmp, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, DB_PATH)

# ── PostgreSQL ───────────────────────────────────────────────

def _pg_conn():
    import psycopg2
    return psycopg2.connect(PG_URL)

def _pg_load_all() -> dict:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT dob, name, customer_id, data FROM customers")
            rows = cur.fetchall()
    customers = {}
    for dob, name, customer_id, data in rows:
        c = data if isinstance(data, dict) else json.loads(data)
        c["name"] = name
        c["customer_id"] = customer_id
        customers[dob] = c
    return {"customers": customers}

def _pg_save_all(db: dict) -> None:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            for dob, c in db["customers"].items():
                data = {k: v for k, v in c.items() if k not in ("name","customer_id")}
                cur.execute(
                    "INSERT INTO customers (dob,name,customer_id,data) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (dob) DO UPDATE SET data=EXCLUDED.data",
                    (dob, c.get("name"), c.get("customer_id"), json.dumps(data))
                )
        conn.commit()

# ── Helpers ──────────────────────────────────────────────────

def load_customer(dob: str) -> dict | None:
    """Return full customer dict or None."""
    db = _load_db()
    return db["customers"].get(dob)

def get_customer_context_string(customer: dict) -> str:
    """Build a clean context string for Gemini from the customer dict."""
    if not customer:
        return "Customer not found."
    lines = [
        f"Name: {customer.get('name')}",
        f"Customer ID: {customer.get('customer_id')}",
        f"Phone: {customer.get('phone','-')}",
        f"Email: {customer.get('email','-')}",
    ]
    # Orders
    orders = customer.get("orders", [])
    if orders:
        lines.append(f"\nOrders ({len(orders)}):")
        for o in orders:
            lines.append(
                f"  {o['order_id']}: {o['item']} — {o['status']}"
                + (f" (tracking: {o['tracking']})" if o.get("tracking") else "")
                + (f" | ₹{o['amount']}" if o.get("amount") else "")
            )
    # Bills
    bills = customer.get("bills", [])
    if bills:
        b = bills[0]
        paid_str = "PAID" if b.get("paid") else f"UNPAID — due {b.get('due_date','?')}"
        autopay  = " [AUTOPAY ON]" if b.get("autopay") else ""
        lines.append(f"\nCurrent Bill ({b.get('month','-')}): ₹{b.get('amount')} — {paid_str}{autopay}")
        breakdown = b.get("breakdown", {})
        if breakdown:
            lines.append(f"  Breakdown: base ₹{breakdown.get('base_plan',0)} + add-ons ₹{breakdown.get('add_ons',0)}")
        history = b.get("history", [])
        if history:
            lines.append("  Payment history:")
            for h in history[-3:]:
                lines.append(f"    {h['month']}: ₹{h['amount']} — {'paid' if h.get('paid') else 'unpaid'}")
    # Complaints
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
        for o in orders:
            if o["order_id"] == order_id:
                return o
        # fuzzy: maybe they said just the number
        order_id_clean = order_id.upper().replace(" ","")
        for o in orders:
            if o["order_id"].replace("-","") == order_id_clean.replace("-",""):
                return o
        return {"error": f"Order {order_id} not found", "available_orders": [o["order_id"] for o in orders]}
    # No ID given — return first (most recent) order directly
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
    # Return first unpaid, else most recent
    for b in bills:
        if not b.get("paid"):
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
    # No ID — return most recent complaint directly (tests expect complaint_id key)
    return complaints[-1]

# ── WRITE operations ─────────────────────────────────────────

def create_complaint(customer_dob: str, issue: str) -> dict:
    db = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    # Generate unique ID
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
    db = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    complaints = customer.get("complaints", [])
    # If no ID given, escalate the most recent open one
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
    db = _load_db()
    customer = db["customers"].get(customer_dob)
    if not customer:
        return {"error": "Customer not found"}
    bills = customer.get("bills", [])
    if not bills:
        return {"error": "No bills found"}
    bills[0]["dispute"] = {"reason": reason, "raised_on": datetime.now().strftime("%Y-%m-%d"), "status": "open"}
    _save_db(db)
    return {"message": f"Bill dispute raised for {bills[0].get('month')}", "reason": reason}

def save_session(customer_dob: str, session_data: dict) -> None:
    try:
        db = _load_db()
        customer = db["customers"].get(customer_dob)
        if customer:
            customer.setdefault("session_history", []).append(session_data)
            _save_db(db)
    except Exception as e:
        print(f"[DB] save_session failed: {e}")
