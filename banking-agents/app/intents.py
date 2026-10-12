"""Intent catalogue, rule-based entity extraction (no LLM) and tier 0 exact-match routing."""
from __future__ import annotations

import re
from dataclasses import dataclass

INTENTS: dict[str, str] = {
    "check_balance": "Customer wants the balance of their account(s).",
    "mini_statement": "Customer wants recent transactions or a statement.",
    "card_status": "Customer asks about the status, limit or details of their card.",
    "account_info": "Customer wants their profile or list of accounts.",
    "report_fraud": "Customer does not recognise a transaction or reports fraud or unauthorised use.",
    "block_card": "Customer wants a card blocked or frozen (lost, stolen).",
    "loan_eligibility": "Customer asks whether they can get a loan or how much they qualify for.",
    "calculate_emi": "Customer wants an EMI or instalment calculation for a loan amount.",
    "apply_loan": "Customer wants to apply for or start a loan application.",
    "loan_status": "Customer asks about the status of an existing loan application.",
    "transfer_money": "Customer wants to send or transfer money to another account.",
    "view_alerts": "Customer wants to see alerts or notifications.",
    "kyc_status": "Customer asks whether their KYC is complete, verified, pending or expired.",
    "explain_decision": "Customer asks why a decision (loan, block, flag) was made.",
    "help": "Greeting or request for what the assistant can do.",
    "out_of_scope": "Investment advice, general chat or anything the bank assistant does not handle.",
}

# ---------------------------------------------------------------- entities
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "fifth": 5}
_MULT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "k": 1e3, "thousand": 1e3}

_RE_TXN = re.compile(r"\bT\d{6}\b", re.I)
_RE_ACCT = re.compile(r"(?<!\d)\d{9,18}(?!\d)")
_RE_AID = re.compile(r"\bA\d{4}\b", re.I)  # demo account ids such as A1002
_RE_RATE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pc\b)")
_RE_LAST4 = re.compile(r"(?:ending(?:\s+in|\s+with)?|card(?:\s+no\.?|\s+number)?|xxxx|\*{2,})\s*[:\-]?\s*(\d{4})\b", re.I)
_RE_TENURE = re.compile(r"(\d+(?:\.\d+)?)\s*(years?|yrs?|yr|months?|mos?|mths?)\b", re.I)
_RE_COUNT1 = re.compile(r"(?:last|past|recent|latest|previous)\s+(\d{1,3})\b", re.I)
_RE_COUNT2 = re.compile(r"(?<![\d,.])(\d{1,3})\s+(?:transactions?|txns?|entries|payments?|debits?)\b", re.I)
_RE_AMT_CUR = re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr|k|thousand)?", re.I)
_RE_AMT_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr|k|thousand)\b", re.I)
_RE_PLAIN = re.compile(r"(?<![\w.,])(\d[\d,]*(?:\.\d+)?)(?![\w.]*\d)")


def _amount(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    return v * _MULT[unit.lower()] if unit else v


def extract_entities(text: str, expecting: list[str] | None = None) -> dict:
    """Rule-based entity extraction. Runs on raw text locally; nothing here touches a model."""
    from .llm.typo_normalizer import normalize_banking_query
    expecting = expecting or []
    ent: dict = {}
    t = normalize_banking_query(text)

    # number words before units ("three years", "five transactions")
    t = re.sub(r"\b(" + "|".join(_WORDS) + r")\b(?=\s+(?:years?|yrs?|months?|transactions?|txns?|payments?))",
               lambda m: str(_WORDS[m.group(1).lower()]), t, flags=re.I)

    m = _RE_TXN.search(t)
    if m:
        ent["txn_id"] = m.group(0).upper()
        t = t.replace(m.group(0), " ")
    m_cur = _RE_AMT_CUR.search(t) or _RE_AMT_UNIT.search(t)
    if m_cur:
        ent["amount"] = _amount(m_cur.group(1), m_cur.group(2))
        t = t.replace(m_cur.group(0), " ")
    else:
        m_amt_lead = re.search(r"\b(?:transfer|send|wire|pay|deposit|borrow|amount|sum of|rupees|rs\.?|inr)\s+([0-9,]+(?:\.[0-9]+)?)\b", t, re.I)
        if m_amt_lead:
            ent["amount"] = float(m_amt_lead.group(1).replace(",", ""))
            t = t.replace(m_amt_lead.group(0), " ")

    m = _RE_AID.search(t) or _RE_ACCT.search(t)
    if m:
        ent["account_ref"] = m.group(0).upper()
        t = t.replace(m.group(0), " ")
    m = _RE_RATE.search(t)
    if m:
        ent["rate"] = float(m.group(1))
        t = t.replace(m.group(0), " ")
    m = _RE_LAST4.search(t)
    if m:
        ent["card_last4"] = m.group(1)
        t = t.replace(m.group(0), " ")
    m = _RE_TENURE.search(t)
    if m:
        v = float(m.group(1))
        ent["tenure_months"] = int(round(v * 12)) if m.group(2).lower().startswith(("y",)) else int(round(v))
        t = t.replace(m.group(0), " ")
    m = _RE_COUNT1.search(t) or _RE_COUNT2.search(t)
    if m and (m.re is _RE_COUNT1 or int(m.group(1)) <= 100):
        ent["count"] = int(m.group(1))
        t = t.replace(m.group(0), " ")
    if "amount" not in ent:
        for pm in _RE_PLAIN.finditer(t):
            v = float(pm.group(1).replace(",", ""))
            if v >= 100 or "amount" in expecting:
                ent["amount"] = v
                break
    if "option" in expecting or "transaction" in expecting:
        low = text.lower()
        for w, n in _ORD.items():
            if re.search(rf"\b{w}\b", low):
                ent["option"] = n
                break
        else:
            m = re.fullmatch(r"\s*(?:option\s*|no\.?\s*|#)?([1-9])\s*[.)]?\s*", low)
            if m:
                ent["option"] = int(m.group(1))
    return ent


# ---------------------------------------------------------------- tier 0
@dataclass
class IntentHit:
    intent: str
    confidence: float


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9/ ]+", " ", text.lower()).split())


_EXACT: dict[str, str] = {
    "balance": "check_balance", "bal": "check_balance", "/balance": "check_balance", "check balance": "check_balance",
    "my balance": "check_balance", "account balance": "check_balance", "what is my balance": "check_balance",
    "whats my balance": "check_balance", "balance enquiry": "check_balance",
    "statement": "mini_statement", "mini statement": "mini_statement", "/statement": "mini_statement",
    "transactions": "mini_statement", "recent transactions": "mini_statement", "last transactions": "mini_statement",
    "card": "card_status", "card status": "card_status", "/card": "card_status",
    "block card": "block_card", "block my card": "block_card", "/block": "block_card",
    "profile": "account_info", "my accounts": "account_info", "accounts": "account_info", "/accounts": "account_info",
    "report fraud": "report_fraud", "/fraud": "report_fraud",
    "loan status": "loan_status", "/loanstatus": "loan_status",
    "apply loan": "apply_loan", "apply for loan": "apply_loan", "/loan": "apply_loan",
    "loan eligibility": "loan_eligibility", "/eligibility": "loan_eligibility",
    "kyc": "kyc_status", "kyc status": "kyc_status", "/kyc": "kyc_status", "check kyc": "kyc_status",
    "alerts": "view_alerts", "my alerts": "view_alerts", "/alerts": "view_alerts", "notifications": "view_alerts",
    "help": "help", "/help": "help", "hi": "help", "hello": "help", "hey": "help", "menu": "help", "start": "help", "/start": "help",
    "why": "explain_decision", "explain": "explain_decision", "/explain": "explain_decision",
}
_REGEX0: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:show |get )?(?:last|recent|past) \d{1,2} (?:transactions|txns)$"), "mini_statement"),
    (re.compile(r"^block (?:my )?card ending (?:in )?\d{4}$"), "block_card"),
    (re.compile(r"^(?:dispute|report) t\d{6}$"), "report_fraud"),
    (re.compile(r"^emi (?:for )?\d+(?: ?(?:k|lakh|lakhs))?(?: for \d+ (?:months|years))?$"), "calculate_emi"),
]


def tier0(text: str) -> IntentHit | None:
    from .llm.typo_normalizer import normalize_banking_query
    n = normalize(normalize_banking_query(text))
    if n in _EXACT:
        return IntentHit(_EXACT[n], 1.0)
    for pat, intent in _REGEX0:
        if pat.match(n):
            return IntentHit(intent, 1.0)
    return None
