"""Mock banking back end (core banking, cards, transactions, loans, KYC, bureau, alerts).

These plain functions are what the tool layer wraps and what the FastAPI routes expose.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timedelta

from . import db
from .util import fmt_inr, now, now_iso, short_id, parse_ts


class ServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------ customers / accounts
def list_customers() -> list[dict]:
    return db.query("SELECT customer_id, name, income, segment, city FROM customers ORDER BY customer_id")


def get_customer(customer_id: str) -> dict:
    row = db.query_one("SELECT * FROM customers WHERE customer_id=?", (customer_id,))
    if not row:
        raise ServiceError("NOT_FOUND", f"customer {customer_id} not found")
    return row


def find_customer_by_name_or_query(query: str) -> list[dict]:
    """Find customer records by exact ID, exact name, or fuzzy name matching."""
    q = (query or "").strip()
    if not q:
        return []

    # 1. Direct customer_id match
    row = db.query_one("SELECT * FROM customers WHERE LOWER(customer_id)=?", (q.lower(),))
    if row:
        return [row]

    # 2. Direct full name match
    rows = db.query("SELECT * FROM customers WHERE LOWER(name)=?", (q.lower(),))
    if rows:
        return rows

    # 3. Normalized / Token matching
    all_cust = db.query("SELECT * FROM customers")
    q_norm = re.sub(r"['’]s\b", "", q.lower()).strip()
    # Remove common filler words
    noise = {"the", "account", "balance", "of", "for", "customer", "user", "mr", "ms", "mrs", "dr", "bank"}
    q_tokens = [w for w in re.findall(r"\b\w+\b", q_norm) if w not in noise]

    matches = []
    for c in all_cust:
        c_name = c["name"].lower()
        c_tokens = re.findall(r"\b\w+\b", c_name)

        # Full substring match
        if q_norm and (q_norm in c_name or c_name in q_norm):
            matches.append(c)
            continue

        if not q_tokens or not c_tokens:
            continue

        # Match first name
        if q_tokens[0] == c_tokens[0]:
            if len(q_tokens) > 1 and len(c_tokens) > 1:
                # e.g., "dass" vs "das"
                q_last = q_tokens[1].rstrip("s")
                c_last = c_tokens[1].rstrip("s")
                if q_last == c_last:
                    matches.append(c)
            elif len(q_tokens) == 1:
                matches.append(c)

    # Deduplicate by customer_id
    seen = set()
    deduped = []
    for m in matches:
        if m["customer_id"] not in seen:
            seen.add(m["customer_id"])
            deduped.append(m)
    return deduped


def get_accounts(customer_id: str) -> list[dict]:
    return db.query("SELECT * FROM accounts WHERE customer_id=? ORDER BY account_id", (customer_id,))


def get_account(account_id: str) -> dict:
    row = db.query_one("SELECT * FROM accounts WHERE account_id=?", (account_id,))
    if not row:
        raise ServiceError("NOT_FOUND", f"account {account_id} not found")
    return row


def get_balance(account_id: str) -> dict:
    a = get_account(account_id)
    return {"account_id": a["account_id"], "type": a["type"], "balance": a["balance"], "currency": "INR", "status": a["status"]}


def get_transactions(account_id: str, limit: int = 10) -> list[dict]:
    get_account(account_id)
    return db.query("SELECT * FROM transactions WHERE account_id=? ORDER BY ts DESC, txn_id DESC LIMIT ?", (account_id, int(limit)))


def get_transaction(txn_id: str) -> dict:
    row = db.query_one(
        "SELECT t.*, a.customer_id FROM transactions t JOIN accounts a ON a.account_id=t.account_id WHERE t.txn_id=?",
        (txn_id,))
    if not row:
        raise ServiceError("NOT_FOUND", f"transaction {txn_id} not found")
    return row


def customer_of(kind: str, ident: str) -> str | None:
    """Resolve the owning customer of an account, card, transaction or customer id (None if unknown)."""
    if kind == "customer_id":
        return ident
    if kind == "account_id":
        r = db.query_one("SELECT customer_id FROM accounts WHERE account_id=?", (ident,))
    elif kind == "card_id":
        r = db.query_one("SELECT a.customer_id FROM cards c JOIN accounts a ON a.account_id=c.account_id WHERE c.card_id=?", (ident,))
    elif kind == "txn_id":
        r = db.query_one("SELECT a.customer_id FROM transactions t JOIN accounts a ON a.account_id=t.account_id WHERE t.txn_id=?", (ident,))
    else:
        return None
    return r["customer_id"] if r else None


# ------------------------------------------------------------ cards / disputes
def get_cards(customer_id: str) -> list[dict]:
    return db.query(
        "SELECT c.*, a.customer_id FROM cards c JOIN accounts a ON a.account_id=c.account_id WHERE a.customer_id=? ORDER BY c.card_id",
        (customer_id,))


def get_card(card_id: str) -> dict:
    row = db.query_one("SELECT c.*, a.customer_id FROM cards c JOIN accounts a ON a.account_id=c.account_id WHERE c.card_id=?", (card_id,))
    if not row:
        raise ServiceError("NOT_FOUND", f"card {card_id} not found")
    return row


def block_card(card_id: str, reason: str = "customer request") -> dict:
    card = get_card(card_id)
    if card["status"] == "blocked":
        return {"card_id": card_id, "last4": card["last4"], "status": "blocked", "already_blocked": True, "reason": reason}
    db.execute("UPDATE cards SET status='blocked' WHERE card_id=?", (card_id,))
    return {"card_id": card_id, "last4": card["last4"], "status": "blocked", "already_blocked": False, "reason": reason}


def create_dispute(txn_id: str, reason: str = "transaction not recognised") -> dict:
    txn = get_transaction(txn_id)
    existing = db.query_one("SELECT * FROM disputes WHERE txn_id=? AND status='open'", (txn_id,))
    if existing:
        return {**existing, "already_open": True}
    did = short_id("DSP-").upper()
    db.execute("INSERT INTO disputes (dispute_id, txn_id, customer_id, reason, status, created_at) VALUES (?,?,?,?,?,?)",
               (did, txn_id, txn["customer_id"], reason, "open", now_iso()))
    db.execute("UPDATE transactions SET status='disputed' WHERE txn_id=?", (txn_id,))
    return {"dispute_id": did, "txn_id": txn_id, "customer_id": txn["customer_id"], "reason": reason,
            "status": "open", "amount": txn["amount"], "already_open": False}


# ------------------------------------------------------------ external stubs
def get_bureau(customer_id: str) -> dict:
    row = db.query_one("SELECT * FROM bureau WHERE customer_id=?", (customer_id,))
    if not row:
        raise ServiceError("NOT_FOUND", f"no bureau record for {customer_id}")
    return {"customer_id": customer_id, "score": row["score"], "existing_emi": row["existing_emi"], "source": "bureau-stub"}


def get_kyc(customer_id: str) -> dict | None:
    return db.query_one("SELECT * FROM kyc_records WHERE customer_id=?", (customer_id,))


# ------------------------------------------------------------ loans
def create_loan_application(customer_id: str, amount: float, tenure_months: int, rate: float | None,
                            emi: float | None, status: str = "submitted", reason: str = "") -> dict:
    app_id = short_id("LN-").upper()
    db.execute("INSERT INTO loan_applications (app_id, customer_id, amount, tenure_months, rate, emi, status, decision_reason, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (app_id, customer_id, amount, tenure_months, rate, emi, status, reason, now_iso()))
    return {"app_id": app_id, "customer_id": customer_id, "amount": amount, "tenure_months": tenure_months,
            "rate": rate, "emi": emi, "status": status}


def loan_applications(customer_id: str) -> list[dict]:
    return db.query("SELECT * FROM loan_applications WHERE customer_id=? ORDER BY created_at DESC", (customer_id,))


# ------------------------------------------------------------ transactions
def next_txn_id() -> str:
    row = db.query_one("SELECT MAX(CAST(SUBSTR(txn_id,2) AS INTEGER)) AS m FROM transactions WHERE txn_id GLOB 'T[0-9]*'")
    return f"T{(row['m'] or 0) + 1:06d}"


def insert_transaction(*, account_id: str, type: str, amount: float, merchant: str, category: str = "other",
                       country: str = "IN", device_id: str | None = None, ts: str | None = None,
                       status: str = "posted", description: str = "", txn_id: str | None = None) -> str:
    for _ in range(5):
        tid = txn_id or next_txn_id()
        try:
            db.execute("INSERT INTO transactions (txn_id, account_id, type, amount, merchant, category, country, device_id, ts, status, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (tid, account_id, type, amount, merchant, category, country, device_id, ts or now_iso(), status, description))
            return tid
        except sqlite3.IntegrityError:
            if txn_id:
                raise
    raise ServiceError("ID_CONFLICT", "could not allocate a transaction id")


def set_txn_risk(txn_id: str, score: float, decision: str) -> None:
    db.execute("UPDATE transactions SET risk_score=?, risk_decision=? WHERE txn_id=?", (score, decision, txn_id))


def transfer(from_account: str, to_account: str, amount: float) -> dict:
    if amount <= 0:
        raise ServiceError("INVALID_AMOUNT", "amount must be positive")
    conn = db.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT balance, status, customer_id FROM accounts WHERE account_id=?", (from_account,)).fetchone()
        if not row:
            raise ServiceError("NOT_FOUND", f"account {from_account} not found")
        if row["status"] != "active":
            raise ServiceError("ACCOUNT_INACTIVE", "source account is not active")
        if row["balance"] < amount:
            raise ServiceError("INSUFFICIENT_FUNDS", "insufficient balance for this transfer")

        to_row = conn.execute("SELECT balance, status, customer_id FROM accounts WHERE account_id=?", (to_account,)).fetchone()

        new_balance = row["balance"] - amount
        conn.execute("UPDATE accounts SET balance=? WHERE account_id=?", (new_balance, from_account))

        new_to_balance = None
        if to_row:
            if to_row["status"] != "active":
                raise ServiceError("BENEFICIARY_INACTIVE", "beneficiary account is not active")
            new_to_balance = to_row["balance"] + amount
            conn.execute("UPDATE accounts SET balance=? WHERE account_id=?", (new_to_balance, to_account))

        last = conn.execute("SELECT MAX(CAST(SUBSTR(txn_id,2) AS INTEGER)) AS m FROM transactions WHERE txn_id GLOB 'T[0-9]*'").fetchone()["m"] or 0
        tid_debit = f"T{last + 1:06d}"

        # Razorpay dummy simulation gateway identifiers
        rzp_id = f"pay_rzp_{uuid.uuid4().hex[:12]}"
        rzp_order = f"order_rzp_{uuid.uuid4().hex[:10]}"

        from_cust = conn.execute("SELECT name, customer_id FROM customers WHERE customer_id=?", (row["customer_id"],)).fetchone()
        to_cust = conn.execute("SELECT name, customer_id FROM customers WHERE customer_id=?", (to_row["customer_id"],)).fetchone() if to_row else None

        from_name = from_cust["name"] if from_cust else row["customer_id"]
        to_name = to_cust["name"] if to_cust else to_account

        dev = conn.execute("SELECT d.device_id FROM devices d JOIN accounts a ON a.customer_id=d.customer_id WHERE a.account_id=? ORDER BY d.device_id LIMIT 1", (from_account,)).fetchone()
        ts_now = now_iso()

        # 1. Sender Debit Record
        conn.execute("INSERT INTO transactions (txn_id, account_id, type, amount, merchant, category, country, device_id, ts, status, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (tid_debit, from_account, "debit", amount, f"RAZORPAY TRANSFER TO {to_name}", "transfer", "IN",
                      dev["device_id"] if dev else None, ts_now, "posted", f"Razorpay P2P Transfer to {to_name} ({to_account}) [Ref: {rzp_id}]"))

        # 2. Recipient Credit Record (if beneficiary belongs to our simulated bank)
        if to_row:
            tid_credit = f"T{last + 2:06d}"
            conn.execute("INSERT INTO transactions (txn_id, account_id, type, amount, merchant, category, country, device_id, ts, status, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (tid_credit, to_account, "credit", amount, f"RAZORPAY TRANSFER FROM {from_name}", "transfer", "IN",
                          None, ts_now, "posted", f"Razorpay P2P Received from {from_name} ({from_account}) [Ref: {rzp_id}]"))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Create real-time notification alerts
    if from_cust:
        create_alert(from_cust["customer_id"], "info", f"Payment Sent: {fmt_inr(amount)} sent to {to_name} via Razorpay (Ref: {rzp_id}).")
    if to_cust:
        create_alert(to_cust["customer_id"], "info", f"Payment Received: {fmt_inr(amount)} credited from {from_name} via Razorpay (Ref: {rzp_id}).")

    return {
        "txn_id": tid_debit,
        "razorpay_payment_id": rzp_id,
        "razorpay_order_id": rzp_order,
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
        "new_balance": new_balance,
        "recipient_new_balance": new_to_balance,
        "sender_name": from_name,
        "recipient_name": to_name,
        "gateway": "Razorpay Sandbox (rzp_test_Fingent2026)"
    }


# ------------------------------------------------------------ devices / history
def get_devices(customer_id: str) -> list[dict]:
    return db.query("SELECT * FROM devices WHERE customer_id=? ORDER BY device_id", (customer_id,))


def debit_history(customer_id: str, before_ts: str, days: int = 90, exclude_txn: str | None = None) -> list[dict]:
    start = (parse_ts(before_ts) - timedelta(days=days)).isoformat()
    rows = db.query(
        "SELECT t.txn_id, t.amount, t.merchant, t.ts FROM transactions t JOIN accounts a ON a.account_id=t.account_id "
        "WHERE a.customer_id=? AND t.type='debit' AND t.ts<? AND t.ts>=? AND t.txn_id<>? ORDER BY t.ts",
        (customer_id, before_ts, start, exclude_txn or ""))
    return [{"txn_id": r["txn_id"], "amount": r["amount"], "merchant": r["merchant"], "ts": parse_ts(r["ts"])} for r in rows]


def recent_debits(customer_id: str, days: int, limit: int) -> list[dict]:
    start = (now() - timedelta(days=days)).isoformat()
    return db.query(
        "SELECT t.* FROM transactions t JOIN accounts a ON a.account_id=t.account_id "
        "WHERE a.customer_id=? AND t.type='debit' AND t.ts>=? ORDER BY t.ts DESC, t.txn_id DESC LIMIT ?",
        (customer_id, start, int(limit)))


# ------------------------------------------------------------ alerts
def add_alert(customer_id: str, message: str, severity: str = "info", txn_id: str | None = None) -> dict:
    ts = now_iso()
    aid = db.execute("INSERT INTO alerts (customer_id, txn_id, severity, message, created_at) VALUES (?,?,?,?,?)",
                     (customer_id, txn_id, severity, message, ts))
    return {"alert_id": aid, "customer_id": customer_id, "txn_id": txn_id, "severity": severity, "message": message, "created_at": ts}


create_alert = add_alert


def list_alerts(customer_id: str | None = None, after_id: int = 0, limit: int = 20) -> list[dict]:
    if customer_id:
        return db.query("SELECT * FROM alerts WHERE customer_id=? AND alert_id>? ORDER BY alert_id DESC LIMIT ?", (customer_id, after_id, limit))
    return db.query("SELECT * FROM alerts WHERE alert_id>? ORDER BY alert_id DESC LIMIT ?", (after_id, limit))
