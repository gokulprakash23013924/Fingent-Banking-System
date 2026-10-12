"""Concrete tools. Each is a thin wrapper over services / rules / ml, registered with its agent allowlist."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import knowledge, rules, services
from ..config import get_policy
from ..gateway.guardrail import sanitize_text
from ..ml import fraud
from ..util import fmt_inr, now
from .registry import ToolSpec, register

fs = frozenset


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerArg(Args):
    customer_id: str


class AccountArg(Args):
    account_id: str


class TxnListArg(Args):
    account_id: str
    limit: int = Field(5, ge=1, le=50)


class TxnArg(Args):
    txn_id: str


class FindTxnArg(Args):
    customer_id: str
    txn_id: str | None = None
    amount: float | None = Field(None, gt=0)


class BlockCardArg(Args):
    card_id: str
    reason: str = Field("customer request", max_length=120)


class DisputeArg(Args):
    txn_id: str
    reason: str = Field("transaction not recognised", max_length=120)


class TransferArg(Args):
    from_account: str
    to_account: str
    amount: float = Field(gt=0, le=10_000_000)


class EligibilityArg(Args):
    customer_id: str
    amount: float | None = Field(None, gt=0)
    tenure_months: int | None = Field(None, ge=1, le=360)


class EmiArg(Args):
    amount: float = Field(gt=0, le=1_000_000_000)
    annual_rate: float = Field(ge=0, le=60)
    tenure_months: int = Field(ge=1, le=360)


class OffersArg(Args):
    customer_id: str
    amount: float | None = Field(None, gt=0)


class LoanAppArg(Args):
    customer_id: str
    amount: float = Field(gt=0)
    tenure_months: int = Field(ge=1, le=360)
    rate: float | None = None
    emi: float | None = None
    status: Literal["approved", "under_review"] = "under_review"
    reason: str = Field("", max_length=200)


class PolicyArg(Args):
    query: str = Field(max_length=200)
    k: int = Field(2, ge=1, le=5)


class AlertArg(Args):
    customer_id: str
    message: str = Field(max_length=300)
    severity: Literal["info", "medium", "high"] = "info"
    txn_id: str | None = None


class ListAlertsArg(Args):
    customer_id: str
    after_id: int = Field(0, ge=0)
    limit: int = Field(10, ge=1, le=50)


class LookupCustomerArg(Args):
    query: str = Field(description="Customer name or identifier to search for", max_length=100)


def _clean_txn(t: dict) -> tuple[dict, int]:
    """Transaction fields safe to show or pass on: free text is screened for injected instructions."""
    flagged = 0
    out = {k: t.get(k) for k in ("txn_id", "account_id", "type", "amount", "category", "country", "device_id", "ts", "status")}
    for k in ("merchant", "description"):
        v, f = sanitize_text(t.get(k) or "")
        out[k] = v
        flagged += int(f)
    for k in ("risk_score", "risk_decision"):
        if t.get(k) is not None:
            out[k] = t[k]
    return out, flagged


# ------------------------------------------------------------------ banking
def _profile(ctx, a: CustomerArg) -> dict:
    c = services.get_customer(a.customer_id)
    return {"customer_id": c["customer_id"], "name": c["name"], "segment": c["segment"], "city": c["city"],
            "monthly_income": c["income"], "accounts": [{"account_id": x["account_id"], "type": x["type"], "status": x["status"]}
                                                       for x in services.get_accounts(a.customer_id)]}


def _accounts(ctx, a: CustomerArg) -> dict:
    return {"accounts": [{"account_id": x["account_id"], "type": x["type"], "status": x["status"]} for x in services.get_accounts(a.customer_id)]}


def _balance(ctx, a: AccountArg) -> dict:
    return services.get_balance(a.account_id)


def _transactions(ctx, a: TxnListArg) -> dict:
    rows, flagged = [], 0
    for t in services.get_transactions(a.account_id, a.limit):
        c, f = _clean_txn(t)
        rows.append(c)
        flagged += f
    return {"account_id": a.account_id, "transactions": rows, "injection_flagged": flagged}


def _card_status(ctx, a: CustomerArg) -> dict:
    return {"cards": [{"card_id": c["card_id"], "account_id": c["account_id"], "last4": c["last4"],
                       "status": c["status"], "limit": c["limit_amount"]} for c in services.get_cards(a.customer_id)]}


def _transfer(ctx, a: TransferArg) -> dict:
    services.get_account(a.to_account)  # beneficiary must exist
    if a.to_account == a.from_account:
        raise ValueError("cannot transfer to the same account")
    return services.transfer(a.from_account, a.to_account, a.amount)


def _transfer_needs_approval(a: TransferArg) -> bool:
    return a.amount >= get_policy()["compliance"]["large_transfer_threshold"]


# ------------------------------------------------------------------ fraud
def _find_txn(ctx, a: FindTxnArg) -> dict:
    flagged = 0
    if a.txn_id:
        t = services.get_transaction(a.txn_id)
        if not ctx.session.can_access(t["customer_id"]):
            from .registry import ToolError
            raise ToolError("forbidden", "that transaction does not belong to this session")
        c, flagged = _clean_txn(t)
        return {"found": True, "strategy": "id", "candidates": 1, "transaction": c, "injection_flagged": flagged}
    rows = services.recent_debits(a.customer_id, days=90, limit=300)
    if a.amount:
        tol = max(1.0, a.amount * 0.005)
        hit = [r for r in rows if abs(r["amount"] - a.amount) <= tol]
        if not hit:
            return {"found": False, "strategy": "amount", "candidates": 0}
        c, flagged = _clean_txn(hit[0])
        return {"found": True, "strategy": "amount", "candidates": len(hit), "transaction": c, "injection_flagged": flagged}
    best, best_score = None, -1.0
    for r in rows[:10]:
        s = fraud.score_transaction(r["txn_id"], persist=False)["score"]
        if s > best_score:
            best, best_score = r, s
    if best is None:
        return {"found": False, "strategy": "recent", "candidates": 0}
    c, flagged = _clean_txn(best)
    return {"found": True, "strategy": "recent", "candidates": min(10, len(rows)), "transaction": c, "injection_flagged": flagged}


def _score(ctx, a: TxnArg) -> dict:
    return fraud.score_transaction(a.txn_id, persist=True)


def _devices(ctx, a: CustomerArg) -> dict:
    known = services.get_devices(a.customer_id)
    ids = {d["device_id"] for d in known}
    used = services.db.query(
        "SELECT t.device_id, COUNT(*) AS n, MIN(t.ts) AS first_used FROM transactions t JOIN accounts a ON a.account_id=t.account_id "
        "WHERE a.customer_id=? AND t.device_id IS NOT NULL GROUP BY t.device_id", (a.customer_id,))
    return {"known_devices": [d["device_id"] for d in known],
            "devices_used": [{"device_id": u["device_id"], "transactions": u["n"], "first_used": u["first_used"],
                              "registered": u["device_id"] in ids} for u in used],
            "unregistered_devices": [u["device_id"] for u in used if u["device_id"] not in ids]}


def _assess_recent_risk(ctx, a: CustomerArg) -> dict:
    pol = get_policy()
    sig = pol["risk_signals"]
    rows = services.recent_debits(a.customer_id, days=sig["lookback_days"], limit=sig["max_transactions"])
    flagged, top = [], 0
    for r in rows:
        s = fraud.score_transaction(r["txn_id"], persist=False)
        top = max(top, s["score"])
        if s["decision"] != "allow":
            flagged.append({"txn_id": r["txn_id"], "score": s["score"], "decision": s["decision"],
                            "amount": r["amount"], "merchant": sanitize_text(r["merchant"] or "")[0]})
    elevated = len(flagged) >= sig["refer_if_flagged_count"] or top >= sig["refer_if_max_score"]
    return {"transactions_checked": len(rows), "max_score": top, "flagged_count": len(flagged), "flagged": flagged,
            "elevated": elevated, "lookback_days": sig["lookback_days"]}


def _block_card(ctx, a: BlockCardArg) -> dict:
    return services.block_card(a.card_id, a.reason)


def _dispute(ctx, a: DisputeArg) -> dict:
    return services.create_dispute(a.txn_id, a.reason)


def _describe_block(a: BlockCardArg) -> str:
    try:
        return f"Block card ending {services.get_card(a.card_id)['last4']}"
    except Exception:
        return f"Block card {a.card_id}"


def _describe_dispute(a: DisputeArg) -> str:
    try:
        t = services.get_transaction(a.txn_id)
        return f"Open a dispute for {fmt_inr(t['amount'])} at {sanitize_text(t['merchant'] or '')[0]}"
    except Exception:
        return f"Open a dispute for {a.txn_id}"


# ------------------------------------------------------------------ credit
def _bureau(ctx, a: CustomerArg) -> dict:
    return services.get_bureau(a.customer_id)


def _credit_profile(ctx, a: CustomerArg) -> dict:
    bureau = services.get_bureau(a.customer_id)
    score = bureau["score"]
    rating = "Prime / Excellent" if score >= 750 else ("Good" if score >= 700 else ("Fair" if score >= 650 else "Below Policy Minimum / Poor"))
    return {
        "customer_id": a.customer_id,
        "credit_score": score,
        "bureau_score": score,
        "rating": rating,
        "existing_monthly_emi": bureau["existing_emi"],
        "min_policy_score": 650,
        "loan_eligible": score >= 650,
        "source": "Credit Bureau (CIBIL Stub)"
    }


def _lookup_customer(ctx, a: LookupCustomerArg) -> dict:
    matches = services.find_customer_by_name_or_query(a.query)
    if not matches:
        return {"found": False, "count": 0, "message": f"No customer record found matching '{a.query}'.", "customers": []}
    return {
        "found": True,
        "count": len(matches),
        "customers": [
            {
                "customer_id": c["customer_id"],
                "name": c["name"],
                "income": c.get("income"),
                "segment": c.get("segment"),
                "city": c.get("city")
            } for c in matches
        ]
    }


def _eligibility(ctx, a: EligibilityArg) -> dict:
    p = get_policy()["loan"]
    cust = services.get_customer(a.customer_id)
    bureau = services.get_bureau(a.customer_id)
    tenure = a.tenure_months or p["default_tenure_months"]
    probe = a.amount if a.amount is not None else float(p["min_amount"])
    res = rules.check_eligibility(income=cust["income"], score=bureau["score"], existing_emi=bureau["existing_emi"],
                                  amount=probe, tenure_months=tenure)
    res["amount_requested"] = a.amount
    if a.amount is None:  # no amount asked: report capacity only
        res["decision"] = "approve" if res["max_eligible_amount"] > 0 else "decline"
        res["amount"] = None
        res["emi"] = None
        res["reasons"] = [r for r in res["reasons"] if r["code"] in ("LOW_CREDIT_SCORE", "TENURE_OUT_OF_RANGE")]
        if res["max_eligible_amount"] <= 0 and not res["reasons"]:
            res["reasons"] = [{"code": "FOIR_EXCEEDED", "detail": "existing obligations leave no room for a new EMI"}]
        if res["reasons"]:
            res["decision"] = "decline"
    return res


def _emi(ctx, a: EmiArg) -> dict:
    e = rules.emi(a.amount, a.annual_rate, a.tenure_months)
    return {"amount": a.amount, "annual_rate": a.annual_rate, "tenure_months": a.tenure_months, "emi": round(e, 2),
            "total_payable": round(e * a.tenure_months, 2), "total_interest": round(e * a.tenure_months - a.amount, 2)}


def _offers(ctx, a: OffersArg) -> dict:
    p = get_policy()["loan"]
    cust = services.get_customer(a.customer_id)
    bureau = services.get_bureau(a.customer_id)
    rate = rules.rate_for_score(bureau["score"])
    out = []
    if rate is None:
        return {"offers": [], "rate": None}
    for months in (12, 24, 36, 48, 60):
        e = rules.check_eligibility(income=cust["income"], score=bureau["score"], existing_emi=bureau["existing_emi"],
                                    amount=a.amount or float(p["min_amount"]), tenure_months=months)
        amt = a.amount or e["max_eligible_amount"]
        if amt and e["max_eligible_amount"] >= (a.amount or p["min_amount"]) and amt >= p["min_amount"]:
            m = rules.emi(amt, rate, months)
            out.append({"tenure_months": months, "amount": amt, "rate": rate, "emi": round(m, 2),
                        "total_payable": round(m * months, 2)})
    return {"offers": out, "rate": rate}


def _create_loan(ctx, a: LoanAppArg) -> dict:
    return services.create_loan_application(a.customer_id, a.amount, a.tenure_months, a.rate, a.emi, a.status, a.reason)


def _describe_loan(a: LoanAppArg) -> str:
    return f"Submit a loan application for {fmt_inr(a.amount)} over {a.tenure_months} months"


def _loan_apps(ctx, a: CustomerArg) -> dict:
    return {"applications": [{"app_id": r["app_id"], "amount": r["amount"], "tenure_months": r["tenure_months"],
                              "status": r["status"], "created_at": r["created_at"]} for r in services.loan_applications(a.customer_id)]}


def _policy(ctx, a: PolicyArg) -> dict:
    return {"snippets": knowledge.search(a.query, a.k)}


# ------------------------------------------------------------------ compliance
def _kyc(ctx, a: CustomerArg) -> dict:
    rec = services.get_kyc(a.customer_id)
    v = rules.kyc_verdict(rec, now())
    return {"status": rec["status"] if rec else "missing", "last_verified": rec["last_verified"] if rec else None,
            "aml_flag": bool(rec and rec["aml_flag"]), **v}


def _aml(ctx, a: CustomerArg) -> dict:
    rec = services.get_kyc(a.customer_id)
    flagged = bool(rec and rec["aml_flag"])
    return {"aml_clear": not flagged, "screening": "flagged" if flagged else "clear"}


# ------------------------------------------------------------------ notification
def _alert(ctx, a: AlertArg) -> dict:
    return services.add_alert(a.customer_id, a.message, a.severity, a.txn_id)


def _list_alerts(ctx, a: ListAlertsArg) -> dict:
    return {"alerts": services.list_alerts(a.customer_id, a.after_id, a.limit)}


def _r(name, desc, schema, fn, agents, scope=None, approval=False, describe=None):
    register(ToolSpec(name, desc, schema, fn, fs(agents), scope, approval, describe))


_r("get_customer_profile", "Profile and account list", CustomerArg, _profile, {"banking"}, ("customer_id", "customer_id"))
_r("get_accounts", "List accounts", CustomerArg, _accounts, {"banking"}, ("customer_id", "customer_id"))
_r("get_balance", "Balance of one account", AccountArg, _balance, {"banking"}, ("account_id", "account_id"))
_r("get_transactions", "Recent transactions of one account", TxnListArg, _transactions, {"banking"}, ("account_id", "account_id"))
_r("get_card_status", "Cards of a customer", CustomerArg, _card_status, {"banking", "fraud"}, ("customer_id", "customer_id"))
_r("transfer_funds", "Transfer between accounts (approval at or above the policy threshold)", TransferArg, _transfer,
   {"banking"}, ("account_id", "from_account"), _transfer_needs_approval,
   lambda a: f"Transfer {fmt_inr(a.amount)} from {a.from_account} to {a.to_account}")

_r("find_transaction", "Locate a transaction by id, amount or highest recent risk", FindTxnArg, _find_txn, {"fraud"}, ("customer_id", "customer_id"))
_r("score_transaction", "Deterministic fraud score with reason codes", TxnArg, _score, {"fraud", "notification"}, ("txn_id", "txn_id"))
_r("get_device_history", "Devices used on the customer's accounts", CustomerArg, _devices, {"fraud"}, ("customer_id", "customer_id"))
_r("assess_recent_risk", "Fraud risk signals over recent transactions", CustomerArg, _assess_recent_risk, {"fraud"}, ("customer_id", "customer_id"))
_r("block_card", "Block a card", BlockCardArg, _block_card, {"fraud"}, ("card_id", "card_id"), True, _describe_block)
_r("create_dispute", "Open a dispute on a transaction", DisputeArg, _dispute, {"fraud"}, ("txn_id", "txn_id"), True, _describe_dispute)

_r("get_bureau_score", "Credit bureau score (external stub)", CustomerArg, _bureau, {"credit"}, ("customer_id", "customer_id"))
_r("get_credit_profile", "Credit bureau profile and CIBIL rating", CustomerArg, _credit_profile, {"credit", "supervisor"}, ("customer_id", "customer_id"))
_r("lookup_customer", "Search customer records by name or customer ID", LookupCustomerArg, _lookup_customer, {"supervisor", "banking"})
_r("check_eligibility", "Rule-engine loan eligibility", EligibilityArg, _eligibility, {"credit"}, ("customer_id", "customer_id"))
_r("calculate_emi", "EMI formula", EmiArg, _emi, {"credit"})
_r("get_loan_offers", "Loan offers by tenure", OffersArg, _offers, {"credit"}, ("customer_id", "customer_id"))
_r("list_loan_applications", "Loan applications of a customer", CustomerArg, _loan_apps, {"credit"}, ("customer_id", "customer_id"))
_r("create_loan_application", "Create a loan application", LoanAppArg, _create_loan, {"credit"}, ("customer_id", "customer_id"), True, _describe_loan)
_r("retrieve_policy", "Search the policy documents", PolicyArg, _policy, {"credit", "compliance"})

_r("get_kyc_status", "KYC status and verdict", CustomerArg, _kyc, {"compliance"}, ("customer_id", "customer_id"))
_r("run_aml_check", "AML screening result (stub)", CustomerArg, _aml, {"compliance"}, ("customer_id", "customer_id"))

_r("send_alert", "Send a customer alert", AlertArg, _alert, {"notification"}, ("customer_id", "customer_id"))
_r("list_alerts", "List customer alerts", ListAlertsArg, _list_alerts, {"notification"}, ("customer_id", "customer_id"))
