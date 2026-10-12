"""Deterministic business logic: EMI, loan eligibility, fraud rule scoring, KYC verdicts.

No LLM and no I/O in here, so every decision is reproducible and unit-testable.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime

from .config import get_policy


# ---------------------------------------------------------------- loans
def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 12 / 100
    if months <= 0:
        raise ValueError("months must be positive")
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def principal_for_emi(max_emi: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 12 / 100
    if max_emi <= 0:
        return 0.0
    if r == 0:
        return max_emi * months
    f = (1 + r) ** months
    return max_emi * (f - 1) / (r * f)


def rate_for_score(score: int, policy: dict | None = None) -> float | None:
    policy = policy or get_policy()
    for tier in sorted(policy["loan"]["rates"], key=lambda t: -t["min_score"]):
        if score >= tier["min_score"]:
            return float(tier["annual_rate"])
    return None


def check_eligibility(*, income: float, score: int, existing_emi: float, amount: float,
                      tenure_months: int, policy: dict | None = None) -> dict:
    p = (policy or get_policy())["loan"]
    reasons: list[dict] = []
    trace: list[dict] = []

    def rule(name: str, passed: bool, detail: str, code: str | None = None) -> None:
        trace.append({"rule": name, "passed": passed, "detail": detail})
        if not passed and code:
            reasons.append({"code": code, "detail": detail})

    rule("amount_min", amount >= p["min_amount"], f"amount {amount:.0f} vs minimum {p['min_amount']}", "AMOUNT_BELOW_MIN")
    rule("amount_max", amount <= p["max_amount"], f"amount {amount:.0f} vs maximum {p['max_amount']}", "AMOUNT_ABOVE_MAX")
    rule("tenure_range", p["min_tenure_months"] <= tenure_months <= p["max_tenure_months"],
         f"tenure {tenure_months} months vs allowed {p['min_tenure_months']}-{p['max_tenure_months']}", "TENURE_OUT_OF_RANGE")

    rate = rate_for_score(score, policy)
    rule("credit_score", score >= p["min_credit_score"],
         f"credit score {score} vs minimum {p['min_credit_score']}", "LOW_CREDIT_SCORE")

    income_cap = income * p["max_amount_multiple_of_monthly_income"]
    rule("income_multiple", amount <= income_cap,
         f"amount {amount:.0f} vs income cap {income_cap:.0f}", "AMOUNT_EXCEEDS_INCOME_MULTIPLE")

    new_emi = None
    foir = None
    max_amount = 0.0
    if rate is not None and tenure_months > 0:
        new_emi = emi(amount, rate, tenure_months)
        foir = (existing_emi + new_emi) / income if income > 0 else 9.9
        rule("foir", foir <= p["max_foir"],
             f"obligations-to-income {foir:.2f} vs maximum {p['max_foir']:.2f}", "FOIR_EXCEEDED")
        room = p["max_foir"] * income - existing_emi
        cap = min(principal_for_emi(room, rate, tenure_months), income_cap, p["max_amount"])
        max_amount = math.floor(cap / 1000) * 1000
        if max_amount < p["min_amount"]:
            max_amount = 0.0

    return {
        "decision": "decline" if reasons else "approve",
        "reasons": reasons,
        "rate": rate,
        "emi": round(new_emi, 2) if new_emi is not None else None,
        "foir": round(foir, 4) if foir is not None else None,
        "max_eligible_amount": float(max_amount),
        "score": score,
        "income": income,
        "existing_emi": existing_emi,
        "amount": amount,
        "tenure_months": tenure_months,
        "rule_trace": trace,
    }


# ---------------------------------------------------------------- fraud
def compute_features(*, amount: float, ts: datetime, country: str, home_country: str,
                     device_id: str | None, merchant: str | None, history: list[dict],
                     known_devices: set[str], window_minutes: int = 10) -> dict:
    amounts = [h["amount"] for h in history]
    if len(amounts) >= 5:
        mean = statistics.fmean(amounts)
        # spend is right-skewed, so compare in log space: one big but ordinary purchase is not an outlier
        logs = [math.log(max(a, 1.0)) for a in amounts]
        std = max(statistics.pstdev(logs), 0.25)
        z = (math.log(max(amount, 1.0)) - statistics.fmean(logs)) / std
    else:
        mean, std, z = (statistics.fmean(amounts) if amounts else 0.0), 0.0, 0.0
    merchants = {h["merchant"] for h in history if h.get("merchant")}
    velocity = sum(1 for h in history if 0 <= (ts - h["ts"]).total_seconds() <= window_minutes * 60)
    return {
        "amount_z": round(z, 3),
        "hour": ts.hour,
        "foreign": int((country or home_country) != home_country),
        "new_device": int(bool(device_id) and device_id not in known_devices),
        "new_merchant": int(bool(merchant) and merchant not in merchants),
        "velocity": velocity,
        "history_count": len(amounts),
        "history_mean": round(mean, 2),
    }


def rule_score(features: dict, policy: dict | None = None) -> tuple[int, list[dict]]:
    f = (policy or get_policy())["fraud"]
    w = f["weights"]
    pts = 0
    reasons: list[dict] = []

    def add(code: str, detail: str, points: int) -> None:
        nonlocal pts
        pts += points
        reasons.append({"code": code, "detail": detail, "points": points})

    z = features["amount_z"]
    if z >= 3:
        add("HIGH_AMOUNT_VS_HISTORY", f"amount is {z:.1f} standard deviations above this customer's usual spend (log scale)", w["amount_z_high"])
    elif z >= 2:
        add("ELEVATED_AMOUNT_VS_HISTORY", f"amount is {z:.1f} standard deviations above this customer's usual spend (log scale)", w["amount_z_mid"])
    if features["new_device"]:
        add("NEW_DEVICE", "payment came from a device not seen on this account before", w["new_device"])
    if features["foreign"]:
        add("FOREIGN_COUNTRY", "payment originated outside the customer's home country", w["foreign_country"])
    if features["hour"] in f["night_hours"]:
        add("UNUSUAL_HOUR", f"payment made at {features['hour']:02d}:00, an unusual hour", w["night_hour"])
    if features["new_merchant"]:
        add("NEW_MERCHANT", "first payment to this merchant", w["new_merchant"])
    if features["velocity"] >= f["velocity_count"]:
        add("HIGH_VELOCITY", f"{features['velocity']} payments within {f['velocity_window_minutes']} minutes", w["velocity"])
    return min(pts, 100), reasons


def fraud_decision(score: float, policy: dict | None = None) -> str:
    f = (policy or get_policy())["fraud"]
    if score >= f["block_threshold"]:
        return "block"
    if score >= f["review_threshold"]:
        return "review"
    return "allow"


# ---------------------------------------------------------------- kyc / aml
def kyc_verdict(record: dict | None, today: datetime, amount: float | None = None,
                policy: dict | None = None) -> dict:
    pol = (policy or get_policy())["compliance"]
    reasons: list[dict] = []
    if record is None:
        return {"verdict": "refer", "reasons": [{"code": "KYC_MISSING", "detail": "no KYC record on file"}]}
    if record.get("aml_flag"):
        return {"verdict": "fail", "reasons": [{"code": "AML_FLAG", "detail": "customer is flagged by AML screening"}]}
    if record["status"] != "verified":
        reasons.append({"code": "KYC_NOT_VERIFIED", "detail": f"KYC status is {record['status']}"})
    elif record.get("last_verified"):
        age = (today - datetime.fromisoformat(record["last_verified"])).days
        if age > pol["kyc_max_age_days"]:
            reasons.append({"code": "KYC_EXPIRED", "detail": f"KYC last verified {age} days ago"})
    if reasons:
        return {"verdict": "refer", "reasons": reasons}
    return {"verdict": "pass", "reasons": []}
